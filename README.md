# ProcureOps AI

**An enterprise AI platform for procurement invoice exception resolution.**

ProcureOps AI demonstrates how to combine deterministic business rules, workflow orchestration, retrieval-grounded policy guidance, and controlled tool execution in an auditable enterprise workflow.

> **Integration status:** The MVP uses simulated ERP/SAP-style APIs and synthetic procurement data. It does not connect to a live SAP system. The project is a learning and portfolio implementation, not a production payment system.

## Problem and business goal

Before an invoice can be approved for payment, its details need to be checked against the purchase order (PO) and goods receipts (GR). Comparing only invoice and PO totals is insufficient: an invoice can have the correct total while the received quantity is lower than the invoiced quantity.

The MVP performs **line-level three-way matching** and returns every detected exception with the evidence used to identify it. A separate policy and authorization step determines what may happen next.

## Target workflow

1. **Receive invoice** — accept an invoice and its line items.
2. **Validate references and basic fields** — resolve the vendor and PO, check PO status and currency, and look for duplicate invoices.
3. **Load procurement evidence** — retrieve PO lines, goods-receipt events, and relevant prior invoices through simulated ERP APIs.
4. **Run deterministic three-way matching** — compare invoice lines with PO authorization and cumulative received/invoiced quantities; evaluate price tolerance using decimal arithmetic.
5. **Return findings** — report all applicable exception codes, affected line IDs, supporting values, and evidence references rather than hiding secondary exceptions behind one status.
6. **Apply policy and authorization** — determine whether the invoice can proceed, should be held for more evidence, or requires human review. Matching and authorization remain separate decisions.
7. **Record an auditable outcome** — preserve the inputs, evidence, findings, policy result, and any approved action.

An LLM may summarize evidence or help investigate an exception. It must not determine financial correctness, override deterministic matching, grant authorization, or independently approve or pay an invoice.

## MVP scope and assumptions

- Simulated ERP/SAP-style REST APIs; no live SAP integration.
- One currency per PO and invoice. Currency conversion is out of scope.
- Invoice quantities and PO quantities use the same unit of measure (UOM); UOM conversion is out of scope. Incompatible UOMs require review.
- Partial goods receipts are supported. Receipt events are aggregated per PO line without double-counting.
- Prior invoices count toward cumulative invoiced quantity unless they are voided or rejected. Blocked duplicate attempts do not count as valid prior invoices.
- Matching is deterministic and testable. Money calculations use Python `Decimal`, not binary floating point.
- Company price tolerance defaults to **2%**; a PO-specific override takes precedence.
- Tax, shipping, and discounts may be stored separately, but their detailed validation is outside the initial matching scope.
- No automatic payment, posting, or other irreversible financial action is permitted in the MVP.

## Exception taxonomy

The matching result can contain multiple exceptions at once. Each finding should include the relevant invoice/PO/receipt references and the values or rule that explain it.

| Code | Meaning | Expected handling |
|---|---|---|
| `MATCHED` | All required matching checks pass and no blocking matching exception remains. | Eligible for a separate policy/authorization decision; not itself approval or payment. |
| `PRICE_VARIANCE` | Invoice unit price exceeds the effective PO/company tolerance. | Review or hold according to policy. |
| `QUANTITY_MISMATCH` | Source quantities are individually valid, but receipt/PO relationships or quantities violate canonical procurement invariants (for example, a receipt line points to a PO line belonging to another PO). | Treat as a data-integrity finding, exclude invalid receipt quantity, and require review. Missing/ambiguous invoice-to-PO-line mapping is an intake validation/manual-resolution failure, not this code. Normal partial receipts and over-invoicing use their dedicated codes. |
| `PENDING_RECEIPT` | Invoiced quantity is within PO authorization, but some quantity is not yet recorded as received. | Hold, wait, or consider partial-payment recommendation according to company policy. Does not prove supplier fault or that goods are in transit. |
| `OVER_INVOICED_QUANTITY` | Cumulative valid invoice quantity exceeds the PO-authorized quantity. | Blocking exception; human/policy resolution required. |
| `MISSING_GOODS_RECEIPT` | No receipt record exists for a PO line that requires receipt evidence. | Hold or review; do not assume the goods were received. |
| `DUPLICATE_INVOICE` | An exact duplicate key already exists. | Block normal approval/payment progression; retain and audit the duplicate attempt. |
| `POTENTIAL_DUPLICATE` | A heuristic suggests a possible duplicate but is not conclusive. | Human review required; never automatically reject solely on this signal. |
| `VENDOR_MISMATCH` | Invoice vendor differs from the PO vendor. | Blocking exception; review. |
| `INVALID_PURCHASE_ORDER` | The referenced PO cannot be found. | Blocking exception; do not fabricate PO-dependent findings. |
| `CURRENCY_MISMATCH` | Invoice currency differs from PO currency. | Review; no automatic currency conversion. |
| `PO_NOT_OPEN` | PO is closed, cancelled, or otherwise not open for the relevant process. | Block approval/payment progression and retain the underlying PO status. |

A potential-duplicate warning is kept separate from the matching status, but it must prevent silent progression to approval. Preserve all findings that can be established from available evidence; avoid inferring a specific cause when evidence is insufficient.

## Deterministic matching rules

### Quantity and receipts

- Match invoice lines to referenced PO lines; do not rely on invoice grand totals alone.
- Aggregate receipt events per PO line, counting each receipt event once.
- Compare cumulative valid invoiced quantity with PO-authorized quantity, accounting for prior invoices that are not voided or rejected.
- A duplicate attempt blocked by the duplicate check is not included in cumulative invoiced quantity.
- Distinguish unreceived but PO-authorized quantity (`PENDING_RECEIPT`) from invoicing beyond the PO-authorized quantity (`OVER_INVOICED_QUANTITY`).
- If a line requires receipt evidence and no receipt record exists, report `MISSING_GOODS_RECEIPT`; if receipt records exist but posted received quantity is below cumulative eligible invoiced quantity, report `PENDING_RECEIPT` when cumulative invoicing is still within PO authorization.
- If cumulative eligible invoiced quantity exceeds PO-authorized quantity, report `OVER_INVOICED_QUANTITY` for that line and do not also report `PENDING_RECEIPT` for the same quantity condition.
- Partial invoices are allowed; invoice quantity need not equal the full PO-line quantity. For example, an invoice for 40 units against a 100-unit PO line can pass quantity checks if 40 units are posted received and cumulative invoicing remains within authorization.
- The company policy determines the next action for pending receipts; the matching result itself does not authorize payment.

### Price tolerance and money

For a non-zero PO unit price:

```text
relative_variance = abs(invoice_unit_price - po_unit_price) / abs(po_unit_price)
```

The variance is within tolerance when it is **less than or equal to** the effective tolerance. The PO-specific tolerance overrides the company default of 2%.

- If the PO unit price is zero, an invoice unit price of zero is within tolerance; any non-zero invoice unit price is a price variance.
- Use `Decimal` for price and amount calculations.
- Round each line's monetary extension to the currency's minor unit using `ROUND_HALF_UP`; calculate goods subtotal as the sum of rounded line amounts.
- Preserve submitted values/precision as needed for audit and explain calculations in evidence.

### Duplicate detection

- **Exact duplicate key:** vendor identity + invoice number.
- Trim leading/trailing whitespace from invoice number for comparison, but preserve case and internal whitespace. Comparison is case-sensitive; preserve the original submitted value for audit.
- Exact duplicates are blocked from normal approval/payment progression. Keep the original invoice unchanged and record the duplicate attempt.
- Flag a **potential duplicate** for human review if the same vendor and currency have either:
  1. the same PO and goods subtotal, with invoice dates within 7 calendar days; or
  2. invoice numbers that differ only by letter case.
- Potential-duplicate heuristics are review signals, not proof of duplication and not grounds for automatic rejection.

### What `MATCHED` means

An invoice can be marked `MATCHED` only when the PO exists and is open, vendor and currency match, required receipt evidence exists, quantities are fully received and within PO authorization, prices are within effective tolerance, and no blocking matching exception remains.

**`MATCHED` does not mean approved or paid.** Policy evaluation and authorization are separate. A potential-duplicate warning can coexist with a matching result but must block silent progression pending review.

## Illustrative scenarios

These are acceptance-test expectations for the MVP. More than one finding may apply to a single invoice.

| Scenario | Expected finding / behavior |
|---|---|
| PO, invoice, vendor, currency, price, and fully received quantities all agree | `MATCHED`; still requires separate authorization. |
| Price variance is exactly at the effective tolerance boundary | Within tolerance; no `PRICE_VARIANCE` for that line. |
| Price variance exceeds the effective tolerance | `PRICE_VARIANCE`; include prices, calculated variance, and applied tolerance. |
| No receipt record exists for a line that requires receipt evidence | `MISSING_GOODS_RECEIPT`; hold/review. |
| PO authorizes 100 units, 80 are received, and 100 are invoiced | `PENDING_RECEIPT` for the unreceived quantity; do not claim the supplier is at fault. |
| Cumulative valid invoice quantity exceeds PO-authorized quantity | `OVER_INVOICED_QUANTITY`; block progression. |
| One PO line has multiple receipt events | Aggregate receipt quantities once and compare with invoice/PO quantities. |
| Same vendor and invoice number are submitted again after trimming outer whitespace | `DUPLICATE_INVOICE`; preserve original record and audit the attempt. |
| Potential duplicate heuristic matches | `POTENTIAL_DUPLICATE`; require human review without automatic rejection. |
| Vendor mismatch, missing PO, closed PO, or currency mismatch | Return the applicable distinct exception(s); do not invent missing evidence. |
| Tax, shipping, or discounts are present | Store them separately; detailed validation remains out of scope for the MVP. |

## Architecture direction

The intended design separates responsibilities:

- **FastAPI** — typed API contracts and request validation.
- **PostgreSQL** — durable procurement entities, constraints, and audit records.
- **Deterministic matching service** — business correctness, quantities, prices, duplicate checks, and exception evidence.
- **Simulated ERP adapter / MCP tools** — controlled access to procurement data; start read-only.
- **LangGraph orchestration** — explicit workflow state, routing, and recovery rather than unconstrained autonomous action.
- **Policy/RAG layer** — retrieves relevant policy passages with citations to support explanations and recommendations; it does not replace deterministic checks.
- **Authorization and human review** — enforce permissions and approval boundaries before any simulated write action.
- **Evaluation and observability** — unit/golden-case tests, traces, structured audit events, and measurable exception outcomes.

The architecture will be implemented incrementally. Components listed here are design direction, not a claim that they already exist.

## Local development

### Prerequisites

- Docker Engine with the Docker Compose plugin.
- Python 3.11+ for running tests locally (the container image uses Python 3.12).

### Start the stack

```bash
cp .env.example .env
# Optional: change the local development password in .env before starting.
docker compose up --build -d
docker compose ps
```

Apply database migrations explicitly:

```bash
docker compose exec app alembic upgrade head
```

The initial migration establishes the Alembic baseline; domain tables are added with the SQLAlchemy model implementation. Migrations are not run automatically at application startup.

### Check service health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

- `GET /health` is a liveness check and does not require PostgreSQL.
- `GET /health/ready` executes `SELECT 1` and returns HTTP 503 if PostgreSQL is unavailable.
- Interactive API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### Run tests and lint

Run these commands from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
python -m pip install -e ".[dev]"
ruff check app tests
pytest
```

GitHub Actions runs lint and tests on pull requests and pushes to `main`.

### Stop the stack

```bash
docker compose down
```

This stops containers but preserves the named PostgreSQL volume. To **permanently delete** the local development database as well, run `docker compose down -v`.

Configuration is read from environment variables; `.env` is ignored by Git. `.env.example` contains development-only defaults and must not be used for production credentials. Never commit real secrets.

## Development plan

1. Define workflow, business assumptions, exception taxonomy, and acceptance examples.
2. Model procurement entities and relationships.
3. Specify and test deterministic three-way matching.
4. Bootstrap FastAPI, PostgreSQL, and Docker Compose.
5. Add SQLAlchemy models, constraints, and reproducible synthetic scenarios.
6. Implement matching with unit tests and golden cases.
7. Add simulated ERP read tools, policy retrieval, and LangGraph orchestration.
8. Add policy/authorization gates, auditability, evaluations, and deployment automation.

Track work in [GitHub Issues](https://github.com/AliSaeed090/procureops-ai/issues).

## Current status

The FastAPI/PostgreSQL development scaffold is implemented on the infrastructure branch: Docker Compose, environment-based settings, liveness/readiness endpoints, Alembic configuration, basic tests, and CI lint/test checks. The SQLAlchemy domain schema and matching logic are the next implementation steps. See [Issue #1: Define procure-to-pay workflow and business assumptions](https://github.com/AliSaeed090/procureops-ai/issues/1) for the business decisions and acceptance criteria.

## Out of scope for the initial MVP

- Live SAP connectivity or real ERP credentials.
- Automatic payment or posting to a financial ledger.
- LLM-based financial matching or autonomous approval.
- Currency conversion and UOM conversion.
- Full tax, shipping, and discount validation.
- Production-grade multi-tenant deployment and enterprise identity integration.
- Advanced fuzzy duplicate scoring beyond the explicitly defined review heuristics.

## License

License and reuse terms will be added when selected.
