from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Vendor
    from app.models.workflow import ApprovalDecision, InvoiceAttachment, InvoiceException, MatchingRun


INVOICE_STATUSES = (
    "RECEIVED",
    "VALIDATING",
    "MATCHED",
    "EXCEPTION",
    "PENDING_REVIEW",
    "APPROVED",
    "REJECTED",
    "VOIDED",
)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("vendor_id", "normalized_invoice_number", name="uq_invoices_vendor_normalized_number"),
        CheckConstraint("status IN ('RECEIVED', 'VALIDATING', 'MATCHED', 'EXCEPTION', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'VOIDED')", name="ck_invoices_status"),
        CheckConstraint("length(trim(invoice_number)) > 0", name="ck_invoices_number_nonempty"),
        CheckConstraint("length(currency) = 3", name="ck_invoices_currency_length"),
        CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_nonnegative"),
        Index("ix_invoices_po_status", "purchase_order_id", "status"),
        Index("ix_invoices_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    invoice_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RECEIVED")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    shipping_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    current_matching_run_id: Mapped[str | None] = mapped_column(ForeignKey("matching_runs.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    vendor: Mapped[Vendor] = relationship(back_populates="invoices")
    purchase_order: Mapped[PurchaseOrder] = relationship()
    lines: Mapped[list[InvoiceLineItem]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    intake: Mapped[InvoiceIntake | None] = relationship(back_populates="invoice", uselist=False)
    attachments: Mapped[list[InvoiceAttachment]] = relationship(back_populates="invoice")
    matching_runs: Mapped[list[MatchingRun]] = relationship(
        back_populates="invoice", foreign_keys="MatchingRun.invoice_id"
    )
    exceptions: Mapped[list[InvoiceException]] = relationship(back_populates="invoice")
    approval_decisions: Mapped[list[ApprovalDecision]] = relationship(back_populates="invoice")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_lines_invoice_line_number"),
        CheckConstraint("line_number > 0", name="ck_invoice_lines_line_number_positive"),
        CheckConstraint("quantity > 0", name="ck_invoice_lines_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_lines_unit_price_nonnegative"),
        CheckConstraint("length(trim(uom)) > 0", name="ck_invoice_lines_uom_nonempty"),
        Index("ix_invoice_lines_po_line_id", "purchase_order_line_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    purchase_order_line_id: Mapped[str] = mapped_column(ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    uom: Mapped[str] = mapped_column(String(32), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    purchase_order_line: Mapped[PurchaseOrderLine] = relationship(back_populates="invoice_lines")


class InvoiceIntake(Base):
    __tablename__ = "invoice_intakes"
    __table_args__ = (
        UniqueConstraint("source_system", "idempotency_key", name="uq_invoice_intakes_source_idempotency"),
        CheckConstraint("length(trim(source_system)) > 0", name="ck_invoice_intakes_source_nonempty"),
        CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_invoice_intakes_key_nonempty"),
        CheckConstraint("length(payload_hash) = 64", name="ck_invoice_intakes_hash_length"),
        Index("ix_invoice_intakes_invoice_id", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    invoice: Mapped[Invoice | None] = relationship(back_populates="intake")
