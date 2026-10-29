"""Generate a deterministic, relationship-valid demo dataset as JSON.

This creates portable seed fixtures without resetting or mutating a database.
It is useful for API development until the simulated ERP persistence adapter is
implemented.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


def generate(seed: int = 20261029, vendors: int = 4, purchase_orders: int = 12) -> dict:
    rng = random.Random(seed)
    records: dict[str, list[dict]] = {
        "vendors": [], "purchase_orders": [], "purchase_order_lines": [],
        "goods_receipts": [], "invoices": [], "invoice_lines": [],
    }
    for index in range(1, vendors + 1):
        records["vendors"].append({
            "id": f"demo-vendor-{index:03d}", "external_id": f"DEMO-V-{index:03d}",
            "name": f"Synthetic Supplier {index:03d}", "status": "ACTIVE",
        })

    for index in range(1, purchase_orders + 1):
        vendor_index = 1 if index == 2 else (index - 1) % vendors + 1
        po_id = f"demo-po-{index:03d}"
        vendor_id = f"demo-vendor-{vendor_index:03d}"
        currency = "EUR" if index % 5 else "USD"
        status = "CLOSED" if index % 11 == 0 else "OPEN"
        records["purchase_orders"].append({
            "id": po_id, "external_id": f"DEMO-PO-{index:03d}",
            "vendor_id": vendor_id, "status": status, "currency": currency,
            "price_tolerance": "0.020000", "order_date": "2026-10-01",
        })
        line_count = 2 if index % 3 == 0 else 1
        for line_no in range(1, line_count + 1):
            line_id = f"demo-pol-{index:03d}-{line_no:02d}"
            quantity = Decimal(rng.randint(5, 30))
            price = Decimal(rng.randint(10, 250))
            records["purchase_order_lines"].append({
                "id": line_id, "purchase_order_id": po_id, "line_number": line_no,
                "description": f"Synthetic item {index:03d}-{line_no:02d}",
                "quantity": format(quantity, "f"), "unit_price": format(price, ".2f"),
                "uom": "EA",
            })
            receipt_qty = quantity / Decimal("2") if index % 4 == 0 else quantity
            if index % 7 != 0:
                records["goods_receipts"].append({
                    "id": f"demo-gr-{index:03d}-{line_no:02d}",
                    "external_id": f"DEMO-GR-{index:03d}-{line_no:02d}",
                    "purchase_order_id": po_id, "purchase_order_line_id": line_id,
                    "status": "POSTED", "quantity": format(receipt_qty, "f"),
                })
        invoice_id = f"demo-invoice-{index:03d}"
        invoice_vendor = f"demo-vendor-{(vendor_index % vendors) + 1}" if index % 8 == 0 else vendor_id
        invoice_currency = ("USD" if currency == "EUR" else "EUR") if index % 9 == 0 else currency
        invoice_number = f"DEMO-INV-{index:03d}"
        invoice_date = date(2026, 10, 1) + timedelta(days=index % 20)
        records["invoices"].append({
            "id": invoice_id, "external_id": f"DEMO-INVOICE-{index:03d}",
            "vendor_id": invoice_vendor, "purchase_order_id": po_id,
            "invoice_number": invoice_number, "normalized_invoice_number": invoice_number,
            "currency": invoice_currency, "invoice_date": invoice_date.isoformat(),
            "status": "RECEIVED",
        })
        po_lines = [line for line in records["purchase_order_lines"] if line["purchase_order_id"] == po_id]
        for line in po_lines:
            qty = Decimal(line["quantity"])
            unit_price = Decimal(line["unit_price"])
            if index % 6 == 0:
                unit_price *= Decimal("1.05")
            if index % 10 == 0:
                qty += Decimal("1")
            records["invoice_lines"].append({
                "id": f"demo-il-{index:03d}-{line['line_number']:02d}",
                "invoice_id": invoice_id, "purchase_order_line_id": line["id"],
                "line_number": line["line_number"], "description": line["description"],
                "quantity": format(qty, "f"), "unit_price": format(unit_price, ".2f"),
                "line_amount": format((qty * unit_price).quantize(Decimal("0.01")), ".2f"),
                "uom": "EA",
            })

    if len(records["invoices"]) >= 2:
        records["invoices"][1]["invoice_number"] = records["invoices"][1]["invoice_number"].lower()
        records["invoices"][1]["normalized_invoice_number"] = records["invoices"][1]["invoice_number"]
    return {"seed": seed, "generated_by": "scripts/generate_scenarios.py", **records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--vendors", type=int, default=4)
    parser.add_argument("--purchase-orders", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("data/demo_scenarios.json"))
    args = parser.parse_args()
    if args.vendors < 1 or args.purchase_orders < 1:
        parser.error("--vendors and --purchase-orders must both be positive")
    dataset = generate(args.seed, args.vendors, args.purchase_orders)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(dataset['vendors'])} vendors, {len(dataset['purchase_orders'])} POs, "
        f"{len(dataset['invoices'])} invoices to {args.output} (seed={args.seed})."
    )


if __name__ == "__main__":
    main()
