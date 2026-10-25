"""
Tests for Phase 1 Mock Data Generation.
Validates:
1. CSV file existence and exact schema.
2. Exact counts: 5 districts, 10 godowns, 50 shops, 6 users (one per role).
3. Deliberately seeded edge cases (delayed deliveries, low-stock shops, discrepancies, diff deliveries, stale records).
4. Critical stock balance rule: NO location ever has negative stock at any point in history.
"""

import csv
import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def read_csv(filename):
    filepath = os.path.join(DATA_DIR, filename)
    assert os.path.exists(filepath), f"File {filename} does not exist in {DATA_DIR}"
    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def test_csv_files_exist():
    expected_files = [
        "districts.csv",
        "godowns.csv",
        "shops.csv",
        "commodities.csv",
        "users.csv",
        "stock_movements.csv",
        "deliveries.csv",
        "monthly_distribution.csv",
        "measurements.csv",
    ]
    for filename in expected_files:
        assert os.path.exists(os.path.join(DATA_DIR, filename))


def test_districts_and_godowns_and_shops_counts():
    districts = read_csv("districts.csv")
    godowns = read_csv("godowns.csv")
    shops = read_csv("shops.csv")

    assert len(districts) == 5, f"Expected 5 districts, got {len(districts)}"
    assert len(godowns) == 10, f"Expected 10 godowns, got {len(godowns)}"
    assert len(shops) == 50, f"Expected 50 shops, got {len(shops)}"

    # Check that godowns belong to valid districts (2 per district)
    district_ids = {d["id"] for d in districts}
    godown_districts = [g["district_id"] for g in godowns]
    for d_id in district_ids:
        assert godown_districts.count(d_id) == 2, f"District {d_id} should have exactly 2 godowns"

    # Check that shops link to a godown in their district (5 per godown)
    godown_map = {g["id"]: g["district_id"] for g in godowns}
    godown_ids = set(godown_map.keys())

    shop_godowns = [s["godown_id"] for s in shops]
    for g_id in godown_ids:
        assert shop_godowns.count(g_id) == 5, f"Godown {g_id} should have exactly 5 shops"

    for s in shops:
        assert s["godown_id"] in godown_map, f"Shop {s['id']} linked to invalid godown {s['godown_id']}"
        assert s["district_id"] == godown_map[s["godown_id"]], f"Shop {s['id']} district mismatch with godown"


def test_users_one_per_role():
    users = read_csv("users.csv")
    assert len(users) == 6, f"Expected 6 users, got {len(users)}"
    
    expected_roles = {
        "state_admin",
        "district_officer",
        "godown_manager",
        "shop_manager",
        "stock_inspector",
        "data_entry_officer",
    }
    roles_present = {u["role"] for u in users}
    assert roles_present == expected_roles, f"User roles mismatch: {roles_present}"


def test_deliberate_edge_cases():
    deliveries = read_csv("deliveries.csv")
    measurements = read_csv("measurements.csv")
    shops = read_csv("shops.csv")
    monthly_dist = read_csv("monthly_distribution.csv")
    movements = read_csv("stock_movements.csv")

    # 1. 3-4 Delayed deliveries
    delayed = [d for d in deliveries if d["status"] == "DELAYED"]
    assert 3 <= len(delayed) <= 4, f"Expected 3-4 delayed deliveries, found {len(delayed)}"

    # 2. 1-2 deliveries received with difference
    diff_deliveries = [d for d in deliveries if d["status"] == "RECEIVED_WITH_DIFFERENCE"]
    assert 1 <= len(diff_deliveries) <= 2, f"Expected 1-2 difference deliveries, found {len(diff_deliveries)}"
    for d in diff_deliveries:
        assert float(d["dispatched_qty_kg"]) != float(d["received_qty_kg"])
        assert float(d["received_qty_kg"]) > 0

    # 3. 2-3 measured-stock discrepancies (> 2% tolerance)
    # Calculate closing stock per location to compare with measurements
    godowns = read_csv("godowns.csv")
    godown_stocks = {g["id"]: float(g["opening_stock_kg"]) for g in godowns}
    shop_stocks = {s["id"]: float(s["opening_stock_kg"]) for s in shops}

    # Replay movements in chronological order
    sorted_movements = sorted(movements, key=lambda m: m["timestamp"])
    
    # We will track balances up to measurement dates
    discrepancy_count = 0
    for m in measurements:
        meas_date = m["measured_date"]
        loc_type = m["location_type"]
        loc_id = m["location_id"]
        measured_val = float(m["measured_stock_kg"])

        # Calculate expected stock at meas_date
        if loc_type == "godown":
            curr_stock = float([g["opening_stock_kg"] for g in godowns if g["id"] == loc_id][0])
            for mov in sorted_movements:
                if mov["timestamp"] <= meas_date and mov["location_type"] == "godown" and mov["location_id"] == loc_id:
                    if mov["movement_type"] == "RECEIPT":
                        curr_stock += float(mov["quantity_kg"])
                    elif mov["movement_type"] == "DISPATCH":
                        curr_stock -= float(mov["quantity_kg"])
                    elif mov["movement_type"] == "ADJUSTMENT":
                        curr_stock += float(mov["quantity_kg"])
        else:
            curr_stock = float([s["opening_stock_kg"] for s in shops if s["id"] == loc_id][0])
            for mov in sorted_movements:
                if mov["timestamp"] <= meas_date and mov["location_type"] == "shop" and mov["location_id"] == loc_id:
                    if mov["movement_type"] == "CONFIRMED_DELIVERY":
                        curr_stock += float(mov["quantity_kg"])
                    elif mov["movement_type"] == "DISTRIBUTION":
                        curr_stock -= float(mov["quantity_kg"])
                    elif mov["movement_type"] == "ADJUSTMENT":
                        curr_stock += float(mov["quantity_kg"])

        diff_pct = abs(measured_val - curr_stock) / curr_stock if curr_stock > 0 else 0
        if diff_pct > 0.02:  # 2% discrepancy threshold from spec
            discrepancy_count += 1

    assert 2 <= discrepancy_count <= 3, f"Expected 2-3 discrepancies (>2%), found {discrepancy_count}"

    # 4. 4-5 low stock shops (closing stock < 20% of monthly average distribution)
    # Calculate final shop balances and 6-month average distributions
    final_shop_stocks = {s["id"]: float(s["opening_stock_kg"]) for s in shops}
    for mov in sorted_movements:
        if mov["location_type"] == "shop":
            s_id = mov["location_id"]
            if mov["movement_type"] == "CONFIRMED_DELIVERY":
                final_shop_stocks[s_id] += float(mov["quantity_kg"])
            elif mov["movement_type"] == "DISTRIBUTION":
                final_shop_stocks[s_id] -= float(mov["quantity_kg"])
            elif mov["movement_type"] == "ADJUSTMENT":
                final_shop_stocks[s_id] += float(mov["quantity_kg"])

    # Average monthly distribution per shop (from monthly_distribution.csv)
    avg_distributions = {}
    for row in monthly_dist:
        s_id = row["shop_id"]
        avg_distributions[s_id] = avg_distributions.get(s_id, 0.0) + float(row["distributed_qty_kg"])
    for s_id in avg_distributions:
        avg_distributions[s_id] /= 6.0  # 6 months

    low_stock_shops = [
        s_id for s_id, stock in final_shop_stocks.items()
        if stock < (0.20 * avg_distributions[s_id])
    ]
    assert 4 <= len(low_stock_shops) <= 5, f"Expected 4-5 low-stock shops, found {len(low_stock_shops)}: {low_stock_shops}"

    # 5. 1-2 stale-record cases (no movements in the last 10 days of October)
    stale_shops = []
    latest_cutoff = "2026-10-14 23:59:59"
    for s in shops:
        s_id = s["id"]
        recent_movs = [
            m for m in movements
            if m["location_id"] == s_id and m["timestamp"] > latest_cutoff
        ]
        if not recent_movs:
            stale_shops.append(s_id)
    assert 1 <= len(stale_shops) <= 2, f"Expected 1-2 stale-record shops, found {len(stale_shops)}: {stale_shops}"


def test_no_negative_stock_balances_at_any_time():
    """
    CRITICAL ARCHITECTURE INVARIANT:
    Ensures that at no point in time did any godown or shop ever drop below 0 kg.
    """
    godowns = read_csv("godowns.csv")
    shops = read_csv("shops.csv")
    movements = read_csv("stock_movements.csv")

    godown_stocks = {g["id"]: float(g["opening_stock_kg"]) for g in godowns}
    shop_stocks = {s["id"]: float(s["opening_stock_kg"]) for s in shops}

    # All initial stocks must be strictly positive
    for g_id, stock in godown_stocks.items():
        assert stock > 0, f"Godown {g_id} has non-positive opening stock {stock}"
    for s_id, stock in shop_stocks.items():
        assert stock > 0, f"Shop {s_id} has non-positive opening stock {stock}"

    # Sort all movements chronologically
    sorted_movements = sorted(movements, key=lambda m: (m["timestamp"], m["id"]))

    for mov in sorted_movements:
        loc_type = mov["location_type"]
        loc_id = mov["location_id"]
        qty = float(mov["quantity_kg"])
        m_type = mov["movement_type"]
        t_stamp = mov["timestamp"]

        assert qty > 0, f"Movement {mov['id']} has non-positive quantity {qty}"

        if loc_type == "godown":
            if m_type == "RECEIPT":
                godown_stocks[loc_id] += qty
            elif m_type == "DISPATCH":
                godown_stocks[loc_id] -= qty
            elif m_type == "ADJUSTMENT":
                godown_stocks[loc_id] += qty
            else:
                pytest.fail(f"Invalid movement type {m_type} for godown")

            assert godown_stocks[loc_id] >= 0, (
                f"Negative stock detected at Godown {loc_id} after {m_type} of {qty}kg on {t_stamp}! "
                f"Balance: {godown_stocks[loc_id]}"
            )

        elif loc_type == "shop":
            if m_type == "CONFIRMED_DELIVERY":
                shop_stocks[loc_id] += qty
            elif m_type == "DISTRIBUTION":
                shop_stocks[loc_id] -= qty
            elif m_type == "ADJUSTMENT":
                shop_stocks[loc_id] += qty
            else:
                pytest.fail(f"Invalid movement type {m_type} for shop")

            assert shop_stocks[loc_id] >= 0, (
                f"Negative stock detected at Shop {loc_id} after {m_type} of {qty}kg on {t_stamp}! "
                f"Balance: {shop_stocks[loc_id]}"
            )

    # Verify all final closing balances remain strictly non-negative
    for g_id, stock in godown_stocks.items():
        assert stock >= 0, f"Godown {g_id} closing stock is negative: {stock}"
    for s_id, stock in shop_stocks.items():
        assert stock >= 0, f"Shop {s_id} closing stock is negative: {stock}"
