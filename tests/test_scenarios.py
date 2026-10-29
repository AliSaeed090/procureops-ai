from scripts.generate_scenarios import generate


def test_generator_is_reproducible_for_same_seed():
    assert generate(seed=123) == generate(seed=123)


def test_different_seeds_change_generated_records():
    assert generate(seed=123) != generate(seed=124)


def test_generated_relationships_are_valid_and_dataset_has_variety():
    data = generate(seed=20261029)
    vendors = {row["id"] for row in data["vendors"]}
    pos = {row["id"]: row for row in data["purchase_orders"]}
    po_lines = {row["id"]: row for row in data["purchase_order_lines"]}
    invoices = {row["id"]: row for row in data["invoices"]}

    assert all(row["vendor_id"] in vendors for row in data["purchase_orders"])
    assert all(row["vendor_id"] in vendors for row in data["invoices"])
    assert all(row["purchase_order_id"] in pos for row in data["purchase_order_lines"])
    assert all(row["purchase_order_line_id"] in po_lines for row in data["invoice_lines"])
    assert all(row["invoice_id"] in invoices for row in data["invoice_lines"])
    assert all(
        po_lines[row["purchase_order_line_id"]]["purchase_order_id"]
        == invoices[row["invoice_id"]]["purchase_order_id"]
        for row in data["invoice_lines"]
    )
    assert len(data["purchase_orders"]) >= 10
    assert len(data["invoice_lines"]) > len(data["invoices"])


def test_matching_case_catalog_covers_all_supported_exception_codes():
    data = generate(seed=20261029)
    codes = {code for case in data["matching_cases"] for code in case["expected_codes"]}
    assert {
        "MATCHED", "PRICE_VARIANCE", "QUANTITY_MISMATCH", "PENDING_RECEIPT",
        "OVER_INVOICED_QUANTITY", "MISSING_GOODS_RECEIPT", "DUPLICATE_INVOICE",
        "POTENTIAL_DUPLICATE", "VENDOR_MISMATCH", "INVALID_PURCHASE_ORDER",
        "CURRENCY_MISMATCH", "PO_NOT_OPEN",
    } <= codes
    assert any(case.get("fixture_only") for case in data["matching_cases"])
    assert any(
        len(case["expected_codes"]) > 1
        for case in data["matching_cases"]
    )
