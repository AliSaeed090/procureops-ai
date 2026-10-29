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
