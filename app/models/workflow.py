from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MatchingRun(Base):
    __tablename__ = "matching_runs"
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_matching_runs_status"),
        Index("ix_matching_runs_invoice_created", "invoice_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    rules_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[object] = mapped_column(nullable=False, server_default="CURRENT_TIMESTAMP")
    completed_at: Mapped[object | None] = mapped_column(nullable=True)

    invoice: Mapped[Invoice] = relationship(back_populates="matching_runs", foreign_keys=[invoice_id])
    exceptions: Mapped[list[InvoiceException]] = relationship(back_populates="matching_run")
    current_for_invoices: Mapped[list[Invoice]] = relationship(
        "Invoice", foreign_keys="Invoice.current_matching_run_id", viewonly=True
    )


class InvoiceException(Base):
    __tablename__ = "invoice_exceptions"
    __table_args__ = (
        CheckConstraint("severity IN ('INFO', 'WARNING', 'BLOCKING')", name="ck_invoice_exceptions_severity"),
        Index("ix_invoice_exceptions_invoice_status", "invoice_id", "status"),
        Index("ix_invoice_exceptions_code", "code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False)
    matching_run_id: Mapped[str] = mapped_column(ForeignKey("matching_runs.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="BLOCKING")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    affected_line_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[object] = mapped_column(nullable=False, server_default="CURRENT_TIMESTAMP")

    invoice: Mapped[Invoice] = relationship(back_populates="exceptions")
    matching_run: Mapped[MatchingRun] = relationship(back_populates="exceptions")


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('APPROVED', 'REJECTED', 'RETURNED')", name="ck_approval_decisions_decision"),
        Index("ix_approval_decisions_invoice_created", "invoice_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[object] = mapped_column(nullable=False, server_default="CURRENT_TIMESTAMP")

    invoice: Mapped[Invoice] = relationship(back_populates="approval_decisions")


class InvoiceAttachment(Base):
    __tablename__ = "invoice_attachments"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_invoice_attachments_storage_key"),
        CheckConstraint("size_bytes >= 0", name="ck_invoice_attachments_size_nonnegative"),
        Index("ix_invoice_attachments_invoice_id", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[object] = mapped_column(nullable=False, server_default="CURRENT_TIMESTAMP")

    invoice: Mapped[Invoice] = relationship(back_populates="attachments")
