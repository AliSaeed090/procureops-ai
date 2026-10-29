"""Safely reseed only ProcureOps demo records in a development database."""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select, update

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    ApprovalDecision,
    AuditEvent,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceAttachment,
    InvoiceException,
    InvoiceIntake,
    InvoiceLineItem,
    MatchingRun,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)
from scripts.generate_scenarios import generate


def reseed(seed: int = 20261029, vendors: int = 4, purchase_orders: int = 12) -> dict[str, int]:
    settings = get_settings()
    if settings.app_env.lower() != "development":
        raise RuntimeError("Refusing to seed: APP_ENV must be 'development'.")
    dataset = generate(seed=seed, vendors=vendors, purchase_orders=purchase_orders)

    with SessionLocal() as db:
        demo_invoice_ids = select(Invoice.id).where(Invoice.id.like("demo-%"))
        demo_po_ids = select(PurchaseOrder.id).where(PurchaseOrder.id.like("demo-%"))
        demo_receipt_ids = select(GoodsReceipt.id).where(GoodsReceipt.id.like("demo-%"))

        # Remove dependent demo evidence first. Non-demo business records are never
        # truncated or deleted by this command.
        db.execute(delete(InvoiceException).where(InvoiceException.invoice_id.in_(demo_invoice_ids)))
        db.execute(delete(ApprovalDecision).where(ApprovalDecision.invoice_id.in_(demo_invoice_ids)))
        db.execute(delete(InvoiceAttachment).where(InvoiceAttachment.invoice_id.in_(demo_invoice_ids)))
        db.execute(delete(MatchingRun).where(MatchingRun.invoice_id.in_(demo_invoice_ids)))
        db.execute(
            delete(InvoiceIntake).where(
                InvoiceIntake.id.like("demo-%") | InvoiceIntake.invoice_id.in_(demo_invoice_ids)
            )
        )
        db.execute(update(Invoice).where(Invoice.id.in_(demo_invoice_ids)).values(current_matching_run_id=None))
        db.execute(delete(InvoiceLineItem).where(InvoiceLineItem.invoice_id.in_(demo_invoice_ids)))
        db.execute(
            delete(AuditEvent).where(
                AuditEvent.id.like("demo-%")
                | AuditEvent.entity_id.in_(demo_invoice_ids)
                | AuditEvent.entity_id.in_(demo_po_ids)
            )
        )
        db.execute(
            delete(GoodsReceiptLine).where(
                GoodsReceiptLine.id.like("demo-%")
                | GoodsReceiptLine.goods_receipt_id.in_(demo_receipt_ids)
            )
        )
        db.execute(delete(Invoice).where(Invoice.id.in_(demo_invoice_ids)))
        db.execute(delete(GoodsReceipt).where(GoodsReceipt.id.in_(demo_receipt_ids)))
        db.execute(delete(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id.in_(demo_po_ids)))
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.id.in_(demo_po_ids)))
        db.execute(delete(Vendor).where(Vendor.id.like("demo-%")))

        vendor_rows = [
            Vendor(
                id=row["id"], external_id=row["external_id"], name=row["name"],
                status=row["status"],
            )
            for row in dataset["vendors"]
        ]
        db.add_all(vendor_rows)
        db.flush()

        po_rows = [
            PurchaseOrder(
                id=row["id"], external_id=row["external_id"], vendor_id=row["vendor_id"],
                status=row["status"], currency=row["currency"],
                price_tolerance=Decimal(row["price_tolerance"]),
                order_date=date.fromisoformat(row["order_date"]),
            )
            for row in dataset["purchase_orders"]
        ]
        db.add_all(po_rows)
        db.flush()

        po_line_rows = [
            PurchaseOrderLine(
                id=row["id"], purchase_order_id=row["purchase_order_id"],
                line_number=row["line_number"], description=row["description"],
                quantity=Decimal(row["quantity"]), unit_price=Decimal(row["unit_price"]),
                uom=row["uom"],
            )
            for row in dataset["purchase_order_lines"]
        ]
        db.add_all(po_line_rows)
        db.flush()

        receipt_rows = [
            GoodsReceipt(
                id=row["id"], external_id=row["external_id"],
                purchase_order_id=row["purchase_order_id"], status=row["status"],
                received_at=date(2026, 10, 1),
            )
            for row in dataset["goods_receipts"]
        ]
        db.add_all(receipt_rows)
        db.flush()
        db.add_all([
            GoodsReceiptLine(
                id=f"{row['id']}-line", goods_receipt_id=row["id"],
                purchase_order_line_id=row["purchase_order_line_id"],
                quantity=Decimal(row["quantity"]),
            )
            for row in dataset["goods_receipts"]
        ])

        lines_by_invoice: dict[str, list[dict]] = {}
        for line in dataset["invoice_lines"]:
            lines_by_invoice.setdefault(line["invoice_id"], []).append(line)
        invoice_rows = []
        for row in dataset["invoices"]:
            subtotal = sum(
                (Decimal(line["line_amount"]) for line in lines_by_invoice[row["id"]]),
                start=Decimal("0.00"),
            )
            invoice_rows.append(Invoice(
                id=row["id"], external_id=row["external_id"], vendor_id=row["vendor_id"],
                purchase_order_id=row["purchase_order_id"], invoice_number=row["invoice_number"],
                normalized_invoice_number=row["normalized_invoice_number"],
                currency=row["currency"], invoice_date=date.fromisoformat(row["invoice_date"]),
                status=row["status"], subtotal=subtotal,
                tax_amount=Decimal("0.00"), shipping_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
            ))
        db.add_all(invoice_rows)
        db.flush()
        db.add_all([
            InvoiceLineItem(
                id=row["id"], invoice_id=row["invoice_id"],
                purchase_order_line_id=row["purchase_order_line_id"],
                line_number=row["line_number"], description=row["description"],
                quantity=Decimal(row["quantity"]), unit_price=Decimal(row["unit_price"]),
                line_amount=Decimal(row["line_amount"]), uom=row["uom"],
            )
            for row in dataset["invoice_lines"]
        ])
        db.commit()

    return {
        "vendors": len(dataset["vendors"]),
        "purchase_orders": len(dataset["purchase_orders"]),
        "purchase_order_lines": len(dataset["purchase_order_lines"]),
        "goods_receipts": len(dataset["goods_receipts"]),
        "invoices": len(dataset["invoices"]),
        "invoice_lines": len(dataset["invoice_lines"]),
        "matching_cases": len(dataset["matching_cases"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--vendors", type=int, default=4)
    parser.add_argument("--purchase-orders", type=int, default=12)
    parser.add_argument(
        "--confirm-demo-reset", action="store_true",
        help="required because existing demo-prefixed records will be replaced",
    )
    args = parser.parse_args()
    if not args.confirm_demo_reset:
        parser.error("pass --confirm-demo-reset to replace existing demo-prefixed records")
    if args.vendors < 1 or args.purchase_orders < 1:
        parser.error("--vendors and --purchase-orders must both be positive")
    counts = reseed(args.seed, args.vendors, args.purchase_orders)
    print("Re-seeded only demo-prefixed records: " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
