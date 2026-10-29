"""Create the ProcureOps procurement domain schema.

Revision ID: 0002_procurement_models
Revises: 0001_bootstrap
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_procurement_models"
down_revision: Union[str, None] = "0001_bootstrap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_vendors_external_id"),
        sa.CheckConstraint("length(trim(external_id)) > 0", name="ck_vendors_external_id_nonempty"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_vendors_name_nonempty"),
    )
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("vendor_id", sa.String(36), sa.ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("price_tolerance", sa.Numeric(7, 6), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("external_id", name="uq_purchase_orders_external_id"),
        sa.CheckConstraint("length(trim(external_id)) > 0", name="ck_purchase_orders_external_id_nonempty"),
        sa.CheckConstraint("status IN ('DRAFT', 'OPEN', 'CLOSED', 'CANCELLED')", name="ck_purchase_orders_status"),
        sa.CheckConstraint("length(currency) = 3", name="ck_purchase_orders_currency_length"),
        sa.CheckConstraint("price_tolerance IS NULL OR (price_tolerance >= 0 AND price_tolerance <= 1)", name="ck_purchase_orders_tolerance_range"),
    )
    op.create_index("ix_purchase_orders_vendor_status", "purchase_orders", ["vendor_id", "status"])
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("purchase_order_id", sa.String(36), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("uom", sa.String(32), nullable=False),
        sa.UniqueConstraint("purchase_order_id", "line_number", name="uq_po_lines_po_line_number"),
        sa.CheckConstraint("line_number > 0", name="ck_po_lines_line_number_positive"),
        sa.CheckConstraint("quantity > 0", name="ck_po_lines_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_po_lines_unit_price_nonnegative"),
        sa.CheckConstraint("length(trim(uom)) > 0", name="ck_po_lines_uom_nonempty"),
    )
    op.create_index("ix_po_lines_po_id", "purchase_order_lines", ["purchase_order_id"])
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("purchase_order_id", sa.String(36), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=True),
        sa.UniqueConstraint("external_id", name="uq_goods_receipts_external_id"),
        sa.CheckConstraint("status IN ('DRAFT', 'POSTED', 'REVERSED')", name="ck_goods_receipts_status"),
    )
    op.create_index("ix_goods_receipts_po_status", "goods_receipts", ["purchase_order_id", "status"])
    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("goods_receipt_id", sa.String(36), sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_line_id", sa.String(36), sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_receipt_lines_quantity_positive"),
    )
    op.create_index("ix_receipt_lines_po_line_id", "goods_receipt_lines", ["purchase_order_line_id"])
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=True, unique=True),
        sa.Column("vendor_id", sa.String(36), sa.ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_id", sa.String(36), sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_number", sa.String(100), nullable=False),
        sa.Column("normalized_invoice_number", sa.String(100), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("shipping_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("current_matching_run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("vendor_id", "normalized_invoice_number", name="uq_invoices_vendor_normalized_number"),
        sa.CheckConstraint("status IN ('RECEIVED', 'VALIDATING', 'MATCHED', 'EXCEPTION', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'VOIDED')", name="ck_invoices_status"),
        sa.CheckConstraint("length(trim(invoice_number)) > 0", name="ck_invoices_number_nonempty"),
        sa.CheckConstraint("length(currency) = 3", name="ck_invoices_currency_length"),
        sa.CheckConstraint("subtotal >= 0", name="ck_invoices_subtotal_nonnegative"),
    )
    op.create_index("ix_invoices_po_status", "invoices", ["purchase_order_id", "status"])
    op.create_index("ix_invoices_status_created", "invoices", ["status", "created_at"])
    op.create_table(
        "invoice_line_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_line_id", sa.String(36), sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("line_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("uom", sa.String(32), nullable=False),
        sa.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_lines_invoice_line_number"),
        sa.CheckConstraint("line_number > 0", name="ck_invoice_lines_line_number_positive"),
        sa.CheckConstraint("quantity > 0", name="ck_invoice_lines_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_invoice_lines_unit_price_nonnegative"),
        sa.CheckConstraint("length(trim(uom)) > 0", name="ck_invoice_lines_uom_nonempty"),
    )
    op.create_index("ix_invoice_lines_po_line_id", "invoice_line_items", ["purchase_order_line_id"])
    op.create_table(
        "invoice_intakes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("source_system", "idempotency_key", name="uq_invoice_intakes_source_idempotency"),
        sa.CheckConstraint("length(trim(source_system)) > 0", name="ck_invoice_intakes_source_nonempty"),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_invoice_intakes_key_nonempty"),
        sa.CheckConstraint("length(payload_hash) = 64", name="ck_invoice_intakes_hash_length"),
    )
    op.create_index("ix_invoice_intakes_invoice_id", "invoice_intakes", ["invoice_id"])
    op.create_table(
        "matching_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rules_version", sa.String(50), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_matching_runs_status"),
    )
    op.create_index("ix_matching_runs_invoice_created", "matching_runs", ["invoice_id", "created_at"])
    op.create_foreign_key(
        "fk_invoices_current_matching_run_id_matching_runs",
        "invoices",
        "matching_runs",
        ["current_matching_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "invoice_exceptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("matching_run_id", sa.String(36), sa.ForeignKey("matching_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("affected_line_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("severity IN ('INFO', 'WARNING', 'BLOCKING')", name="ck_invoice_exceptions_severity"),
    )
    op.create_index("ix_invoice_exceptions_invoice_status", "invoice_exceptions", ["invoice_id", "status"])
    op.create_index("ix_invoice_exceptions_code", "invoice_exceptions", ["code"])
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("principal_id", sa.String(100), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("decision IN ('APPROVED', 'REJECTED', 'RETURNED')", name="ck_approval_decisions_decision"),
    )
    op.create_index("ix_approval_decisions_invoice_created", "approval_decisions", ["invoice_id", "created_at"])
    op.create_table(
        "invoice_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_invoice_attachments_storage_key"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_invoice_attachments_size_nonnegative"),
    )
    op.create_index("ix_invoice_attachments_invoice_id", "invoice_attachments", ["invoice_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_audit_events_entity_created", "audit_events", ["entity_type", "entity_id", "created_at"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_index("ix_audit_events_entity_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_invoice_attachments_invoice_id", table_name="invoice_attachments")
    op.drop_table("invoice_attachments")
    op.drop_index("ix_approval_decisions_invoice_created", table_name="approval_decisions")
    op.drop_table("approval_decisions")
    op.drop_index("ix_invoice_exceptions_code", table_name="invoice_exceptions")
    op.drop_index("ix_invoice_exceptions_invoice_status", table_name="invoice_exceptions")
    op.drop_table("invoice_exceptions")
    op.drop_constraint("fk_invoices_current_matching_run_id_matching_runs", "invoices", type_="foreignkey")
    op.drop_index("ix_matching_runs_invoice_created", table_name="matching_runs")
    op.drop_table("matching_runs")
    op.drop_index("ix_invoice_intakes_invoice_id", table_name="invoice_intakes")
    op.drop_table("invoice_intakes")
    op.drop_index("ix_invoice_lines_po_line_id", table_name="invoice_line_items")
    op.drop_table("invoice_line_items")
    op.drop_index("ix_invoices_status_created", table_name="invoices")
    op.drop_index("ix_invoices_po_status", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_receipt_lines_po_line_id", table_name="goods_receipt_lines")
    op.drop_table("goods_receipt_lines")
    op.drop_index("ix_goods_receipts_po_status", table_name="goods_receipts")
    op.drop_table("goods_receipts")
    op.drop_index("ix_po_lines_po_id", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")
    op.drop_index("ix_purchase_orders_vendor_status", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_table("vendors")
