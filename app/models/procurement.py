from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_vendors_external_id"),
        CheckConstraint("length(trim(external_id)) > 0", name="ck_vendors_external_id_nonempty"),
        CheckConstraint("length(trim(name)) > 0", name="ck_vendors_name_nonempty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="vendor")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="vendor")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_purchase_orders_external_id"),
        CheckConstraint("length(trim(external_id)) > 0", name="ck_purchase_orders_external_id_nonempty"),
        CheckConstraint("status IN ('DRAFT', 'OPEN', 'CLOSED', 'CANCELLED')", name="ck_purchase_orders_status"),
        CheckConstraint("length(currency) = 3", name="ck_purchase_orders_currency_length"),
        CheckConstraint("price_tolerance IS NULL OR (price_tolerance >= 0 AND price_tolerance <= 1)", name="ck_purchase_orders_tolerance_range"),
        Index("ix_purchase_orders_vendor_status", "vendor_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_tolerance: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    order_date: Mapped[object | None] = mapped_column(Date, nullable=True)

    vendor: Mapped[Vendor] = relationship(back_populates="purchase_orders")
    lines: Mapped[list[PurchaseOrderLine]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan")
    receipts: Mapped[list[GoodsReceipt]] = relationship(back_populates="purchase_order")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_number", name="uq_po_lines_po_line_number"),
        CheckConstraint("line_number > 0", name="ck_po_lines_line_number_positive"),
        CheckConstraint("quantity > 0", name="ck_po_lines_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_po_lines_unit_price_nonnegative"),
        CheckConstraint("length(trim(uom)) > 0", name="ck_po_lines_uom_nonempty"),
        Index("ix_po_lines_po_id", "purchase_order_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    uom: Mapped[str] = mapped_column(String(32), nullable=False)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    receipt_lines: Mapped[list[GoodsReceiptLine]] = relationship(back_populates="purchase_order_line")
    invoice_lines: Mapped[list[InvoiceLineItem]] = relationship(back_populates="purchase_order_line")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_goods_receipts_external_id"),
        CheckConstraint("status IN ('DRAFT', 'POSTED', 'REVERSED')", name="ck_goods_receipts_status"),
        Index("ix_goods_receipts_po_status", "purchase_order_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    received_at: Mapped[object | None] = mapped_column(Date, nullable=True)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="receipts")
    lines: Mapped[list[GoodsReceiptLine]] = relationship(back_populates="goods_receipt", cascade="all, delete-orphan")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_receipt_lines_quantity_positive"),
        Index("ix_receipt_lines_po_line_id", "purchase_order_line_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    goods_receipt_id: Mapped[str] = mapped_column(ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False)
    purchase_order_line_id: Mapped[str] = mapped_column(ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    goods_receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
    purchase_order_line: Mapped[PurchaseOrderLine] = relationship(back_populates="receipt_lines")
