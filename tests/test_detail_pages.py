"""
Tests for Phase 4: Detail Pages & Closing Stock Formulas.
Validates:
1. Mathematical verification of Godown Closing Stock formula:
   expected_closing == opening + received - dispatched +/- adjustments
2. Mathematical verification of Shop Closing Stock formula:
   expected_closing == opening + confirmed_deliveries - distributed +/- adjustments
3. Breadcrumb hierarchy across all levels:
   Tamil Nadu > District > Godown > Shop
4. Godown page tables (incoming receipts, outgoing dispatches)
5. Shop page components (monthly chart, prediction placeholder, active alerts)
6. 404 error handling for non-existent entities
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models import Godown, Shop, District
from app.services.stock import get_godown_detail, get_shop_detail, get_district_detail
from app.main import app

client = TestClient(app)


def test_godown_closing_stock_formula_across_all_godowns():
    """Verify closing stock formula on all 10 godowns in the state."""
    db = SessionLocal()
    try:
        godowns = db.query(Godown).all()
        assert len(godowns) == 10

        for g in godowns:
            detail = get_godown_detail(db, g.id)
            metrics = detail["metrics"]

            opening = metrics["opening_stock_kg"]
            receipts = metrics["receipts_kg"]
            dispatches = metrics["dispatches_kg"]
            adjustments = metrics["adjustments_kg"]
            expected = metrics["expected_stock_kg"]

            calc = round(opening + receipts - dispatches + adjustments, 2)
            assert expected == calc, f"Godown {g.id} formula mismatch: expected {expected} vs calculated {calc}"
            assert expected >= 0, f"Godown {g.id} has negative stock: {expected}"
            assert len(detail["incoming_receipts"]) > 0
            assert len(detail["outgoing_dispatches"]) > 0
    finally:
        db.close()


def test_shop_closing_stock_formula_across_all_shops():
    """Verify closing stock formula on all 50 fair-price shops."""
    db = SessionLocal()
    try:
        shops = db.query(Shop).all()
        assert len(shops) == 50

        for s in shops:
            detail = get_shop_detail(db, s.id)
            metrics = detail["metrics"]

            opening = metrics["opening_stock_kg"]
            received = metrics["confirmed_deliveries_kg"]
            distributed = metrics["distributions_kg"]
            adjustments = metrics["adjustments_kg"]
            expected = metrics["expected_stock_kg"]

            calc = round(opening + received - distributed + adjustments, 2)
            assert expected == calc, f"Shop {s.id} formula mismatch: expected {expected} vs calculated {calc}"
            assert expected >= 0, f"Shop {s.id} has negative stock: {expected}"

            # Verify prediction formula
            pred = detail["prediction_placeholder"]
            expected_replenishment = max(0.0, round(
                pred["predicted_demand_kg"] + pred["safety_buffer_kg"] - pred["usable_stock_kg"] - pred["planned_incoming_kg"], 2
            ))
            assert pred["recommended_replenishment_kg"] == expected_replenishment
            assert "Planning recommendation" in pred["label"]
    finally:
        db.close()


def test_district_page_breadcrumbs_and_content():
    """Test District detail view with breadcrumbs: Tamil Nadu > District."""
    res = client.get("/districts/1")
    assert res.status_code == 200
    html = res.text

    # Permanent Banner
    assert "Demo Dataset — Not Official Government Data" in html

    # Breadcrumb check
    assert '<a href="/">Tamil Nadu</a>' in html
    assert "Chennai District" in html

    # Contents
    assert "Godown Buffer Stock" in html
    assert "Fair-Price Shop Stock" in html
    assert "/godowns/GDN-001" in html
    assert "/shops/FPS-0001" in html


def test_godown_page_breadcrumbs_and_content():
    """Test Godown detail view with breadcrumbs: Tamil Nadu > District > Godown."""
    res = client.get("/godowns/GDN-001")
    assert res.status_code == 200
    html = res.text

    # Breadcrumbs check
    assert '<a href="/">Tamil Nadu</a>' in html
    assert '<a href="/districts/1">Chennai District</a>' in html
    assert "Chennai Central Buffer Godown" in html

    # Metrics cards
    assert "Opening Stock" in html
    assert "Total Received" in html
    assert "Total Dispatched" in html
    assert "Stock Adjustments" in html
    assert "Expected Closing Stock" in html

    # Tables
    assert 'id="outgoingDispatchesTable"' in html
    assert 'id="incomingReceiptsTable"' in html


def test_shop_page_breadcrumbs_and_content():
    """Test Shop detail view with breadcrumbs: Tamil Nadu > District > Godown > Shop."""
    res = client.get("/shops/FPS-0001")
    assert res.status_code == 200
    html = res.text

    # Breadcrumbs check
    assert '<a href="/">Tamil Nadu</a>' in html
    assert '<a href="/districts/1">Chennai District</a>' in html
    assert '<a href="/godowns/GDN-001">' in html
    assert "FPS-0001" in html

    # Metrics
    assert "Opening Stock" in html
    assert "Confirmed Deliveries" in html
    assert "Distributed via POS" in html
    assert "Expected Closing Stock" in html

    # Components
    assert 'id="chartShopMonthlyHistory"' in html
    assert "Demand Prediction &amp; Replenishment" in html or "Demand Prediction & Replenishment" in html
    assert "Planning recommendation, not an official allocation" in html


def test_shop_alerts_on_seeded_edge_cases():
    """Verify detail pages render alerts for seeded low stock and delayed consignment shops."""
    # FPS-0007 is a seeded low-stock shop
    res_low = client.get("/shops/FPS-0007")
    assert res_low.status_code == 200
    assert "Stock Status: LOW" in res_low.text or "Stock Status: CRITICAL" in res_low.text
    assert "Low Stock Warning" in res_low.text or "Critical Stock" in res_low.text

    # FPS-0005 has a seeded delayed delivery
    res_delayed = client.get("/shops/FPS-0005")
    assert res_delayed.status_code == 200
    assert "Delayed Consignment" in res_delayed.text


def test_detail_pages_404_handling():
    """Verify invalid IDs return 404."""
    assert client.get("/districts/9999").status_code == 404
    assert client.get("/godowns/GDN-INVALID").status_code == 404
    assert client.get("/shops/FPS-INVALID").status_code == 404
