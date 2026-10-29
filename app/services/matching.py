"""Deterministic line-level invoice/PO/goods-receipt matching.

This service has no LLM dependency. Its output is evidence for a separate
policy/authorization workflow; MATCHED never means approved or paid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Sequence

DEFAULT_PRICE_TOLERANCE = Decimal("0.02")
ELIGIBLE_PRIOR_STATUSES = {
    "RECEIVED", "VALIDATING", "MATCHED", "EXCEPTION", "PENDING_REVIEW", "APPROVED"
}


@dataclass(frozen=True)
class PurchaseOrderLineInput:
    id: str
    quantity: Decimal
    unit_price: Decimal
    uom: str
    requires_receipt: bool = True
    price_tolerance: Decimal | None = None


@dataclass(frozen=True)
class PurchaseOrderInput:
    id: str
    vendor_id: str
    status: str
    currency: str
    lines: Sequence[PurchaseOrderLineInput]


@dataclass(frozen=True)
class ReceiptLineInput:
    purchase_order_id: str
    purchase_order_line_id: str
    quantity: Decimal
    status: str = "POSTED"


@dataclass(frozen=True)
class InvoiceLineInput:
    purchase_order_line_id: str
    quantity: Decimal
    unit_price: Decimal
    uom: str


@dataclass(frozen=True)
class InvoiceInput:
    id: str
    vendor_id: str
    purchase_order_id: str | None
    invoice_number: str
    currency: str
    invoice_date: date
    lines: Sequence[InvoiceLineInput]
    status: str = "RECEIVED"


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    line_id: str | None = None
    evidence: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchingResult:
    outcome: str
    findings: tuple[Finding, ...]


def _money(value: Decimal) -> str:
    return format(value, "f")


def _invoice_subtotal(invoice: InvoiceInput) -> Decimal:
    return sum(
        (line.quantity * line.unit_price for line in invoice.lines),
        start=Decimal("0"),
    )


def match_invoice(
    invoice: InvoiceInput,
    purchase_orders: dict[str, PurchaseOrderInput],
    receipts: Sequence[ReceiptLineInput],
    prior_invoices: Sequence[InvoiceInput] = (),
    company_price_tolerance: Decimal = DEFAULT_PRICE_TOLERANCE,
) -> MatchingResult:
    """Return deterministic findings using only supplied source-of-truth data."""
    normalized_number = invoice.invoice_number.strip()
    duplicate = next(
        (
            candidate for candidate in prior_invoices
            if candidate.id != invoice.id
            and candidate.vendor_id == invoice.vendor_id
            and candidate.invoice_number.strip() == normalized_number
        ),
        None,
    )
    if duplicate is not None:
        return MatchingResult("EXCEPTION", (Finding(
            "DUPLICATE_INVOICE",
            "An invoice with the same vendor and normalized invoice number already exists.",
            evidence={"existing_invoice_id": duplicate.id, "invoice_number": normalized_number},
        ),))

    if invoice.purchase_order_id is None or invoice.purchase_order_id not in purchase_orders:
        return MatchingResult("EXCEPTION", (
            Finding("INVALID_PURCHASE_ORDER", "The referenced purchase order could not be resolved."),
        ))

    po = purchase_orders[invoice.purchase_order_id]
    findings: list[Finding] = []
    if invoice.vendor_id != po.vendor_id:
        findings.append(Finding(
            "VENDOR_MISMATCH", "Invoice vendor differs from the purchase-order vendor.",
            evidence={"invoice_vendor_id": invoice.vendor_id, "po_vendor_id": po.vendor_id},
        ))
    if po.status != "OPEN":
        findings.append(Finding(
            "PO_NOT_OPEN", "Purchase order is not open for invoice matching.",
            evidence={"po_status": po.status},
        ))
    if invoice.currency != po.currency:
        findings.append(Finding(
            "CURRENCY_MISMATCH", "Invoice and purchase order currencies must match.",
            evidence={"invoice_currency": invoice.currency, "po_currency": po.currency},
        ))

    potential = next(
        (
            candidate for candidate in prior_invoices
            if candidate.id != invoice.id
            and candidate.vendor_id == invoice.vendor_id
            and candidate.currency == invoice.currency
            and (
                (
                    candidate.purchase_order_id == invoice.purchase_order_id
                    and _invoice_subtotal(candidate) == _invoice_subtotal(invoice)
                    and abs((candidate.invoice_date - invoice.invoice_date).days) <= 7
                )
                or candidate.invoice_number.casefold() == invoice.invoice_number.casefold()
            )
        ),
        None,
    )
    if potential is not None:
        findings.append(Finding(
            "POTENTIAL_DUPLICATE", "Invoice resembles a prior invoice and requires human review.",
            evidence={"possible_duplicate_invoice_id": potential.id},
        ))

    po_lines = {line.id: line for line in po.lines}
    posted_receipts: dict[str, Decimal] = {}
    receipt_exists: set[str] = set()
    for receipt in receipts:
        if receipt.purchase_order_id != po.id:
            continue
        receipt_exists.add(receipt.purchase_order_line_id)
        if receipt.status != "POSTED":
            continue
        if receipt.purchase_order_line_id not in po_lines or receipt.quantity <= 0:
            findings.append(Finding(
                "QUANTITY_MISMATCH", "Receipt line has an invalid PO-line reference or quantity.",
                line_id=receipt.purchase_order_line_id,
            ))
            continue
        posted_receipts[receipt.purchase_order_line_id] = (
            posted_receipts.get(receipt.purchase_order_line_id, Decimal("0")) + receipt.quantity
        )

    cumulative: dict[str, Decimal] = {}
    for previous in prior_invoices:
        if previous.id == invoice.id or previous.status not in ELIGIBLE_PRIOR_STATUSES:
            continue
        if previous.purchase_order_id != po.id:
            continue
        for line in previous.lines:
            cumulative[line.purchase_order_line_id] = (
                cumulative.get(line.purchase_order_line_id, Decimal("0")) + line.quantity
            )

    seen_lines: set[str] = set()
    for line in invoice.lines:
        line_id = line.purchase_order_line_id
        po_line = po_lines.get(line_id)
        if po_line is None:
            findings.append(Finding(
                "QUANTITY_MISMATCH",
                "Invoice line cannot be resolved to a line on the referenced purchase order.",
                line_id=line_id,
            ))
            continue
        if line_id in seen_lines:
            findings.append(Finding(
                "QUANTITY_MISMATCH", "Invoice contains duplicate canonical lines for one PO line.",
                line_id=line_id,
            ))
        seen_lines.add(line_id)
        if line.quantity <= 0 or line.unit_price < 0 or not line.uom.strip():
            findings.append(Finding(
                "QUANTITY_MISMATCH", "Invoice line quantity, price, or unit of measure is invalid.",
                line_id=line_id,
            ))
            continue
        if line.uom != po_line.uom:
            findings.append(Finding(
                "QUANTITY_MISMATCH", "Invoice and PO line units of measure do not match.",
                line_id=line_id, evidence={"invoice_uom": line.uom, "po_uom": po_line.uom},
            ))
            continue

        tolerance = (
            po_line.price_tolerance
            if po_line.price_tolerance is not None
            else company_price_tolerance
        )
        if po_line.unit_price == 0:
            variance = Decimal("0") if line.unit_price == 0 else Decimal("1")
        else:
            variance = abs(line.unit_price - po_line.unit_price) / abs(po_line.unit_price)
        if variance > tolerance:
            findings.append(Finding(
                "PRICE_VARIANCE", "Invoice unit price exceeds the effective tolerance.",
                line_id=line_id,
                evidence={
                    "invoice_unit_price": _money(line.unit_price),
                    "po_unit_price": _money(po_line.unit_price),
                    "relative_variance": _money(variance),
                    "effective_tolerance": _money(tolerance),
                },
            ))

        cumulative[line_id] = cumulative.get(line_id, Decimal("0")) + line.quantity
        if cumulative[line_id] > po_line.quantity:
            findings.append(Finding(
                "OVER_INVOICED_QUANTITY", "Cumulative eligible invoiced quantity exceeds PO authorization.",
                line_id=line_id,
                evidence={
                    "cumulative_invoiced_quantity": _money(cumulative[line_id]),
                    "po_quantity": _money(po_line.quantity),
                },
            ))
        elif po_line.requires_receipt and line_id not in receipt_exists:
            findings.append(Finding(
                "MISSING_GOODS_RECEIPT", "No goods-receipt record exists for a receipt-required PO line.",
                line_id=line_id,
            ))
        elif po_line.requires_receipt and posted_receipts.get(line_id, Decimal("0")) < cumulative[line_id]:
            findings.append(Finding(
                "PENDING_RECEIPT", "Posted receipt quantity is below cumulative eligible invoiced quantity.",
                line_id=line_id,
                evidence={
                    "cumulative_invoiced_quantity": _money(cumulative[line_id]),
                    "posted_received_quantity": _money(posted_receipts.get(line_id, Decimal("0"))),
                },
            ))

    blocking_findings = [finding for finding in findings if finding.code != "POTENTIAL_DUPLICATE"]
    if not blocking_findings:
        return MatchingResult(
            "MATCHED",
            tuple(findings) + (Finding("MATCHED", "All deterministic matching checks passed."),),
        )
    return MatchingResult("EXCEPTION", tuple(findings))
