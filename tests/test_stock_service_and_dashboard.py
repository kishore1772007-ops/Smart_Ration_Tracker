"""
Tests for Phase 3: Stock Service and State Dashboard.
Validates:
1. Stock derivation formulas for Godowns and Shops.
2. CRITICAL SPEC TEST: State total stock equals the exact sum of all district stocks.
3. Physical audit reconciliation helper with neutral discrepancy labels.
4. Dashboard HTML page rendering with permanent demo banner, 6 cards, 4 charts, and district table.
5. GET /api/summary and GET /api/districts summary APIs.
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.services.stock import (
    compute_godown_stock,
    compute_shop_stock,
    compute_district_summary,
    compute_state_summary,
    reconcile_measurements,
)
from app.main import app

client = TestClient(app)


def test_godown_stock_derivation_formula():
    """Verify Godown stock = opening + receipts - dispatches + adjustments."""
    db = SessionLocal()
    try:
        gdn_stock = compute_godown_stock(db, "GDN-001")
        assert gdn_stock["location_id"] == "GDN-001"
        assert gdn_stock["opening_stock_kg"] == 180000.0
        assert gdn_stock["receipts_kg"] > 0
        assert gdn_stock["dispatches_kg"] > 0
        
        expected_calc = round(
            gdn_stock["opening_stock_kg"]
            + gdn_stock["receipts_kg"]
            - gdn_stock["dispatches_kg"]
            + gdn_stock["adjustments_kg"],
            2,
        )
        assert gdn_stock["expected_stock_kg"] == expected_calc
        assert gdn_stock["expected_stock_kg"] > 0
    finally:
        db.close()


def test_shop_stock_derivation_formula():
    """Verify Shop stock = opening + confirmed_deliveries - distributions + adjustments."""
    db = SessionLocal()
    try:
        shop_stock = compute_shop_stock(db, "FPS-0001")
        assert shop_stock["location_id"] == "FPS-0001"
        assert shop_stock["opening_stock_kg"] > 0
        assert shop_stock["confirmed_deliveries_kg"] > 0
        assert shop_stock["distributions_kg"] > 0

        expected_calc = round(
            shop_stock["opening_stock_kg"]
            + shop_stock["confirmed_deliveries_kg"]
            - shop_stock["distributions_kg"]
            + shop_stock["adjustments_kg"],
            2,
        )
        assert shop_stock["expected_stock_kg"] == expected_calc
        assert shop_stock["expected_stock_kg"] > 0
        assert shop_stock["status"] in ["NORMAL", "LOW", "CRITICAL"]
    finally:
        db.close()


def test_state_total_equals_sum_of_districts():
    """
    CRITICAL SPEC REQUIREMENT:
    Verify that the state total stock (both godown and shop balances)
    and distributions exactly equal the sum of districts.
    """
    db = SessionLocal()
    try:
        # Test for specific month
        summary_oct = compute_state_summary(db, month="2026-10")
        districts = summary_oct["districts_breakdown"]
        cards = summary_oct["cards"]

        sum_godown = round(sum(d["total_godown_stock_kg"] for d in districts), 2)
        sum_shop = round(sum(d["total_shop_stock_kg"] for d in districts), 2)
        sum_total = round(sum(d["total_stock_kg"] for d in districts), 2)
        sum_dist = round(sum(d["monthly_distributed_kg"] for d in districts), 2)

        assert cards["total_godown_stock_kg"] == sum_godown, "State godown stock does not match sum of districts"
        assert cards["total_shop_stock_kg"] == sum_shop, "State shop stock does not match sum of districts"
        assert cards["total_combined_stock_kg"] == sum_total, "State total stock does not match sum of districts"
        assert cards["total_distributed_kg"] == sum_dist, "State distribution does not match sum of districts"

        # Also test for all-time baseline (month=None)
        summary_all = compute_state_summary(db, month=None)
        districts_all = summary_all["districts_breakdown"]
        cards_all = summary_all["cards"]

        sum_dist_all = round(sum(d["monthly_distributed_kg"] for d in districts_all), 2)
        assert cards_all["total_distributed_kg"] == sum_dist_all
    finally:
        db.close()


def test_reconciliation_helper_neutral_phrasing():
    """Verify physical audit reconciliation detects seeded discrepancies with neutral phrasing."""
    db = SessionLocal()
    try:
        recon = reconcile_measurements(db)
        assert len(recon) == 5

        discrepancies = [r for r in recon if r["discrepancy_detected"]]
        # Exactly 3 discrepancies were seeded (FPS-0012, GDN-003, FPS-0035)
        assert len(discrepancies) == 3

        for d in discrepancies:
            assert d["difference_pct"] > 2.0
            # Neutral phrasing rule: MUST say 'Verification requested' and NEVER blame
            assert "Verification requested" in d["status_label"]
            assert "fraud" not in d["status_label"].lower()
            assert "theft" not in d["status_label"].lower()
            assert "guilty" not in d["status_label"].lower()
    finally:
        db.close()


def test_dashboard_page_rendering():
    """Test dashboard HTML view with 6 cards, 4 charts, district links, and permanent banner."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.text

    # Permanent Banner
    assert "Demo Dataset — Not Official Government Data" in html

    # 6 Summary Cards presence
    assert "Godown Buffer Stock" in html
    assert "Fair-Price Shop Stock" in html
    assert "Rice Distributed (Month)" in html
    assert "Beneficiary Households" in html
    assert "In-Transit / Delayed" in html
    assert "Attention Flags" in html

    # 4 Canvas Chart IDs
    assert 'id="chartDistrictDist"' in html
    assert 'id="chartMonthlyTrend"' in html
    assert 'id="chartStockStatus"' in html
    assert 'id="chartReconciliation"' in html

    # District Table and Links
    assert "/districts/1" in html
    assert "Chennai" in html
    assert "Coimbatore" in html
    assert "Madurai" in html


def test_api_summary_endpoints():
    """Test GET /api/summary and GET /api/districts?include_summary=true."""
    # State summary endpoint
    res = client.get("/api/summary?month=2026-10")
    assert res.status_code == 200
    data = res.json()
    assert "cards" in data
    assert "stock_status" in data
    assert "monthly_trend" in data
    assert "districts_breakdown" in data
    assert len(data["districts_breakdown"]) == 5

    # Districts with live stock summary
    res_dist = client.get("/api/districts?include_summary=true&month=2026-10")
    assert res_dist.status_code == 200
    dist_data = res_dist.json()
    assert len(dist_data) == 5
    for d in dist_data:
        assert "total_godown_stock_kg" in d
        assert "total_shop_stock_kg" in d
        assert "total_stock_kg" in d
        assert d["total_stock_kg"] > 0


def test_live_drill_down_endpoints():
    """Verify 4-level hierarchical drill-down endpoints: State > District > Godown > Shop."""
    # Level 1: State
    res_state = client.get("/api/summary/live")
    assert res_state.status_code == 200
    state_data = res_state.json()
    assert "kpis" in state_data
    assert "district_health_map" in state_data
    assert "top_shortage_districts" in state_data
    assert state_data["kpis"]["total_stock_mt"] > 0

    # Level 2: District
    res_dist = client.get("/api/summary/district/1")
    assert res_dist.status_code == 200
    dist_data = res_dist.json()
    assert dist_data["district"]["id"] == 1
    assert "godowns" in dist_data
    assert "shops" in dist_data
    assert len(dist_data["godowns"]) > 0
    assert len(dist_data["shops"]) > 0

    # Level 3: Godown
    first_gdn = dist_data["godowns"][0]["id"]
    res_gdn = client.get(f"/api/summary/godown/{first_gdn}")
    assert res_gdn.status_code == 200
    gdn_data = res_gdn.json()
    assert gdn_data["godown"]["id"] == first_gdn
    assert "linked_shops" in gdn_data
    assert "commodities_stock" in gdn_data

    # Level 4: Shop
    first_shop = dist_data["shops"][0]["id"]
    res_shop = client.get(f"/api/summary/shop/{first_shop}")
    assert res_shop.status_code == 200
    shop_data = res_shop.json()
    assert shop_data["shop"]["id"] == first_shop
    assert "commodities" in shop_data
    assert "recent_transactions" in shop_data
    assert "prediction" in shop_data

