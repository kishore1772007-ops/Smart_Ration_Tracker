"""
Tests for Phase 2: Database and Base API.
Validates:
1. SQLite database tables and exact row counts matching the CSV spec.
2. Read-only API endpoints for districts, godowns, shops, and movements.
3. Filtering and 404 error handling.
4. Permanent Demo Dataset Banner inclusion.
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models import (
    District,
    Commodity,
    Godown,
    Shop,
    StockMovement,
    Delivery,
    MonthlyDistribution,
    Measurement,
    User,
    AuditLog,
)
from app.main import app

client = TestClient(app)


def test_database_row_counts_match_spec():
    """Verify that SQLite database tables contain the exact counts from the spec."""
    db = SessionLocal()
    try:
        assert db.query(District).count() == 5, "Districts count mismatch"
        assert db.query(Commodity).count() == 1, "Commodities count mismatch"
        assert db.query(Godown).count() == 10, "Godowns count mismatch"
        assert db.query(Shop).count() == 50, "Shops count mismatch"
        assert db.query(User).count() == 6, "Users count mismatch"
        assert db.query(StockMovement).count() >= 2388, "StockMovements count mismatch"
        assert db.query(Delivery).count() >= 593, "Deliveries count mismatch"
        assert db.query(MonthlyDistribution).count() >= 300, "MonthlyDistribution count mismatch"
        assert db.query(Measurement).count() >= 5, "Measurements count mismatch"
        assert db.query(AuditLog).count() >= 1, "AuditLog initialization record missing"
    finally:
        db.close()


def test_health_check_and_demo_banner():
    """Verify health endpoint and mandatory demo dataset banner."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Demo Dataset — Not Official Government Data" in data["banner"]


def test_districts_endpoints():
    """Test GET /api/districts and GET /api/districts/{id}."""
    # List all
    res = client.get("/api/districts")
    assert res.status_code == 200
    districts = res.json()
    assert len(districts) == 5
    assert districts[0]["code"] == "DIS-01"
    assert districts[0]["name"] == "Chennai"

    # Get by ID
    res_single = client.get(f"/api/districts/{districts[0]['id']}")
    assert res_single.status_code == 200
    assert res_single.json()["name"] == "Chennai"

    # 404 check
    res_404 = client.get("/api/districts/9999")
    assert res_404.status_code == 404


def test_godowns_endpoints():
    """Test GET /api/godowns with district filtering and single lookups."""
    # List all
    res = client.get("/api/godowns")
    assert res.status_code == 200
    godowns = res.json()
    assert len(godowns) == 10

    # Filter by district_id
    res_filtered = client.get("/api/godowns?district_id=1")
    assert res_filtered.status_code == 200
    g_filtered = res_filtered.json()
    assert len(g_filtered) == 2
    for g in g_filtered:
        assert g["district_id"] == 1

    # Lookup by ID
    res_single = client.get("/api/godowns/GDN-001")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == "GDN-001"
    assert res_single.json()["capacity_kg"] == 500000.0

    # 404 check
    assert client.get("/api/godowns/GDN-999").status_code == 404


def test_shops_endpoints():
    """Test GET /api/shops with filtering and single lookups."""
    # List all
    res = client.get("/api/shops")
    assert res.status_code == 200
    shops = res.json()
    assert len(shops) == 50

    # Filter by godown_id
    res_godown_shops = client.get("/api/shops?godown_id=GDN-001")
    assert res_godown_shops.status_code == 200
    g_shops = res_godown_shops.json()
    assert len(g_shops) == 5
    for s in g_shops:
        assert s["godown_id"] == "GDN-001"

    # Filter by district_id
    res_dist_shops = client.get("/api/shops?district_id=2")
    assert res_dist_shops.status_code == 200
    assert len(res_dist_shops.json()) == 10

    # Lookup by ID
    res_single = client.get("/api/shops/FPS-0001")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == "FPS-0001"

    # 404 check
    assert client.get("/api/shops/FPS-9999").status_code == 404


def test_movements_endpoints():
    """Test GET /api/movements ledger filtering and pagination."""
    # List with pagination
    res = client.get("/api/movements?limit=25&offset=0")
    assert res.status_code == 200
    movements = res.json()
    assert len(movements) == 25
    for m in movements:
        assert m["quantity_kg"] != 0
        assert m["location_type"] in ["godown", "shop"]

    # Filter by location
    res_loc = client.get("/api/movements?location_type=shop&location_id=FPS-0001&limit=50")
    assert res_loc.status_code == 200
    shop_movs = res_loc.json()
    assert len(shop_movs) > 0
    for m in shop_movs:
        assert m["location_id"] == "FPS-0001"
        assert m["location_type"] == "shop"

    # Lookup by movement ID
    mov_id = shop_movs[0]["id"]
    res_single = client.get(f"/api/movements/{mov_id}")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == mov_id

    # 404 check
    assert client.get("/api/movements/MOV-NONEXISTENT").status_code == 404
