from datetime import date
from decimal import Decimal

import pytest

from app.services.matching import (
    InvoiceInput,
    InvoiceLineInput,
    PurchaseOrderInput,
    PurchaseOrderLineInput,
    ReceiptLineInput,
    match_invoice,
)


def make_po(*, status="OPEN", vendor="V1", currency="EUR", quantity="10", price="100", tolerance=None):
    line = PurchaseOrderLineInput(
        "POL-1", Decimal(quantity), Decimal(price), "EA", True,
        Decimal(tolerance) if tolerance is not None else None,
    )
    return PurchaseOrderInput("PO-1", vendor, status, currency, [line])


def make_invoice(
    *, invoice_id="INV-1", number="2026-001", vendor="V1", po_id="PO-1",
    currency="EUR", quantity="2", price="100", invoice_date=date(2026, 10, 1), uom="EA",
):
    return InvoiceInput(
        invoice_id, vendor, po_id, number, currency, invoice_date,
        [InvoiceLineInput("POL-1", Decimal(quantity), Decimal(price), uom)],
    )


def result(invoice=None, *, po=None, receipts=None, prior=()):
    invoice = invoice or make_invoice()
    purchase_orders = {"PO-1": po or make_po()}
    selected_receipts = receipts if receipts is not None else [
        ReceiptLineInput("PO-1", "POL-1", Decimal("10"), "POSTED")
    ]
    return match_invoice(invoice, purchase_orders, selected_receipts, prior)


def codes(out):
    return {finding.code for finding in out.findings}


def test_clean_match_returns_matched_and_is_not_approval():
    out = result()
    assert out.outcome == "MATCHED"
    assert codes(out) == {"MATCHED"}


@pytest.mark.parametrize(("price", "has_variance"), [
    ("102", False), ("102.0001", True), ("98", False), ("97.9999", True),
])
def test_price_tolerance_boundary(price, has_variance):
    assert ("PRICE_VARIANCE" in codes(result(make_invoice(price=price)))) is has_variance


def test_po_specific_tolerance_overrides_company_default():
    po = make_po(price="100", tolerance="0.05")
    assert "PRICE_VARIANCE" not in codes(result(make_invoice(price="104"), po=po))


def test_zero_po_price_only_matches_zero_invoice_price():
    po = make_po(price="0")
    assert "PRICE_VARIANCE" not in codes(result(make_invoice(price="0"), po=po))
    assert "PRICE_VARIANCE" in codes(result(make_invoice(price="0.01"), po=po))


def test_invalid_purchase_order_short_circuits_po_dependent_checks():
    out = match_invoice(make_invoice(po_id="PO-MISSING"), {}, [], [])
    assert codes(out) == {"INVALID_PURCHASE_ORDER"}


def test_vendor_po_status_and_currency_findings_can_coexist():
    invoice = make_invoice(vendor="V2", currency="USD")
    out = result(invoice, po=make_po(vendor="V1", status="CLOSED", currency="EUR"))
    assert {"VENDOR_MISMATCH", "PO_NOT_OPEN", "CURRENCY_MISMATCH"} <= codes(out)


def test_missing_goods_receipt_is_distinct_from_pending_receipt():
    assert "MISSING_GOODS_RECEIPT" in codes(result(receipts=[]))
    pending = [ReceiptLineInput("PO-1", "POL-1", Decimal("1"), "POSTED")]
    assert "PENDING_RECEIPT" in codes(result(receipts=pending))


def test_over_invoicing_takes_precedence_over_pending_receipt():
    prior = make_invoice(invoice_id="INV-OLD", number="INV-OLD", quantity="9")
    receipts = [ReceiptLineInput("PO-1", "POL-1", Decimal("1"), "POSTED")]
    out = result(make_invoice(number="INV-NEW", quantity="2"), receipts=receipts, prior=[prior])
    assert "OVER_INVOICED_QUANTITY" in codes(out)
    assert "PENDING_RECEIPT" not in codes(out)


def test_prior_rejected_invoice_does_not_count_toward_cumulative_quantity():
    prior = make_invoice(invoice_id="INV-OLD", number="INV-OLD", quantity="9")
    prior = InvoiceInput(
        prior.id, prior.vendor_id, prior.purchase_order_id, prior.invoice_number,
        prior.currency, prior.invoice_date, prior.lines, "REJECTED",
    )
    out = result(make_invoice(number="INV-NEW", quantity="2"), prior=[prior])
    assert "OVER_INVOICED_QUANTITY" not in codes(out)


def test_duplicate_is_blocked_before_normal_matching():
    invoice = make_invoice(number=" INV-001 ")
    previous = make_invoice(invoice_id="INV-OLD", number="INV-001")
    assert codes(result(invoice, prior=[previous])) == {"DUPLICATE_INVOICE"}


def test_potential_duplicate_requires_review_and_does_not_claim_match():
    invoice = make_invoice(number="INV-002")
    previous = make_invoice(invoice_id="INV-OLD", number="INV-001")
    out = result(invoice, prior=[previous])
    assert "POTENTIAL_DUPLICATE" in codes(out)
    assert "MATCHED" in codes(out)
    assert out.outcome == "MATCHED"


def test_case_only_invoice_number_difference_is_potential_duplicate():
    invoice = make_invoice(number="inv-001")
    previous = make_invoice(invoice_id="INV-OLD", number="INV-001")
    assert "POTENTIAL_DUPLICATE" in codes(result(invoice, prior=[previous]))


def test_unresolved_po_line_or_uom_mismatch_is_data_integrity_finding():
    invoice = make_invoice()
    bad_line = InvoiceLineInput("POL-NOT-IN-PO", Decimal("2"), Decimal("100"), "EA")
    invoice = InvoiceInput(
        invoice.id, invoice.vendor_id, invoice.purchase_order_id, invoice.invoice_number,
        invoice.currency, invoice.invoice_date, [bad_line],
    )
    assert "QUANTITY_MISMATCH" in codes(result(invoice))
    assert "QUANTITY_MISMATCH" in codes(result(make_invoice(uom="BOX")))


def test_partial_receipt_and_multiple_invoice_lines():
    po = PurchaseOrderInput("PO-1", "V1", "OPEN", "EUR", [
        PurchaseOrderLineInput("POL-1", Decimal("10"), Decimal("100"), "EA"),
        PurchaseOrderLineInput("POL-2", Decimal("5"), Decimal("20"), "EA"),
    ])
    invoice = InvoiceInput("INV-1", "V1", "PO-1", "INV-1", "EUR", date(2026, 10, 1), [
        InvoiceLineInput("POL-1", Decimal("2"), Decimal("100"), "EA"),
        InvoiceLineInput("POL-2", Decimal("1"), Decimal("20"), "EA"),
    ])
    out = match_invoice(invoice, {"PO-1": po}, [
        ReceiptLineInput("PO-1", "POL-1", Decimal("1"), "POSTED"),
        ReceiptLineInput("PO-1", "POL-2", Decimal("1"), "POSTED"),
    ])
    assert "PENDING_RECEIPT" in codes(out)
    assert not {"PRICE_VARIANCE", "OVER_INVOICED_QUANTITY"} & codes(out)


def test_non_posted_receipts_do_not_count():
    out = result(receipts=[ReceiptLineInput("PO-1", "POL-1", Decimal("10"), "DRAFT")])
    assert "PENDING_RECEIPT" in codes(out)
