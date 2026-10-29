from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Numeric, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    AuditEvent,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceIntake,
    InvoiceLineItem,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def uid() -> str:
    return str(uuid4())


def seed_vendor_po(db: Session) -> tuple[Vendor, PurchaseOrder, PurchaseOrderLine]:
    vendor = Vendor(id=uid(), external_id="V-001", name="Example Supplier")
    po = PurchaseOrder(
        id=uid(), external_id="PO-001", vendor=vendor, status="OPEN", currency="EUR",
        price_tolerance=Decimal("0.020000"), order_date=date(2026, 1, 1),
    )
    line = PurchaseOrderLine(
        id=uid(), purchase_order=po, line_number=1, description="Widget",
        quantity=Decimal("10.000000"), unit_price=Decimal("12.340000"), uom="EA",
    )
    db.add_all([vendor, po, line])
    db.commit()
    return vendor, po, line


def test_models_register_and_create_schema(db: Session) -> None:
    tables = set(Base.metadata.tables)
    assert {
        "vendors", "purchase_orders", "purchase_order_lines", "goods_receipts",
        "goods_receipt_lines", "invoices", "invoice_line_items", "invoice_intakes",
        "matching_runs", "invoice_exceptions", "approval_decisions", "invoice_attachments",
        "audit_events",
    } <= tables


def test_purchase_order_and_invoice_relationships(db: Session) -> None:
    vendor, po, po_line = seed_vendor_po(db)
    receipt = GoodsReceipt(id=uid(), external_id="GR-001", purchase_order=po, status="POSTED")
    receipt_line = GoodsReceiptLine(
        id=uid(), goods_receipt=receipt, purchase_order_line=po_line, quantity=Decimal("10")
    )
    invoice = Invoice(
        id=uid(), vendor=vendor, purchase_order=po, invoice_number="INV-001",
        normalized_invoice_number="INV-001", currency="EUR", status="RECEIVED",
        subtotal=Decimal("123.40"),
    )
    invoice_line = InvoiceLineItem(
        id=uid(), invoice=invoice, purchase_order_line=po_line, line_number=1,
        description="Widget", quantity=Decimal("10"), unit_price=Decimal("12.34"),
        line_amount=Decimal("123.40"), uom="EA",
    )
    db.add_all([receipt, receipt_line, invoice, invoice_line])
    db.commit()
    loaded = db.scalar(select(Invoice).where(Invoice.id == invoice.id))
    assert loaded is not None
    assert loaded.vendor.external_id == "V-001"
    assert loaded.purchase_order.lines[0].id == po_line.id
    assert loaded.lines[0].line_amount == Decimal("123.40")
    assert loaded.purchase_order.receipts[0].lines[0].quantity == Decimal("10.000000")


def test_duplicate_invoice_business_key_is_rejected(db: Session) -> None:
    vendor, po, _ = seed_vendor_po(db)
    values = dict(
        vendor=vendor, purchase_order=po, invoice_number="INV-DUP",
        normalized_invoice_number="INV-DUP", currency="EUR", status="RECEIVED",
        subtotal=Decimal("1.00"),
    )
    db.add(Invoice(id=uid(), **values))
    db.commit()
    db.add(Invoice(id=uid(), **values))
    with pytest.raises(IntegrityError):
        db.commit()


def test_duplicate_invoice_intake_idempotency_key_is_rejected(db: Session) -> None:
    first = InvoiceIntake(
        id=uid(), source_system="demo", idempotency_key="request-1",
        payload_hash="a" * 64, payload={"invoice": "one"},
    )
    db.add(first)
    db.commit()
    db.add(InvoiceIntake(
        id=uid(), source_system="demo", idempotency_key="request-1",
        payload_hash="b" * 64, payload={"invoice": "two"},
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_invalid_quantity_is_rejected_by_check_constraint(db: Session) -> None:
    _, po, _ = seed_vendor_po(db)
    db.add(PurchaseOrderLine(
        id=uid(), purchase_order=po, line_number=2, description="Bad quantity",
        quantity=Decimal("0"), unit_price=Decimal("1"), uom="EA",
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_key_rejects_unknown_vendor(db: Session) -> None:
    db.add(PurchaseOrder(
        id=uid(), external_id="PO-ORPHAN", vendor_id=uid(), status="OPEN", currency="EUR"
    ))
    with pytest.raises(IntegrityError):
        db.commit()


def test_decimal_columns_and_audit_model(db: Session) -> None:
    _, po, line = seed_vendor_po(db)
    assert isinstance(line.quantity, Decimal)
    column_type = PurchaseOrderLine.__table__.c.quantity.type
    assert isinstance(column_type, Numeric)
    assert column_type.precision == 18 and column_type.scale == 6
    event_record = AuditEvent(
        id=uid(), event_type="TEST", entity_type="purchase_order", entity_id=po.id,
        actor_type="system", details={"result": "created"},
    )
    db.add(event_record)
    db.commit()
    assert db.get(AuditEvent, event_record.id) is not None
