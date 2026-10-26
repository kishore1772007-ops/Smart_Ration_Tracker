"""
Tests for Phase 1 & 2 Ingestion API and Data Contracts.
Validates:
- POST /api/ingest/transaction (contract for Simulator / Smart Scale / Camera ML)
- Derived stock balance reduction upon transaction ingestion
- Automatic low-stock alert triggers when stock is critically depleted
- POST /api/ingest/stock and sudden anomaly detection
- GET /api/transactions/live query and filtering
- Data source activation (simulator / sensor / ml_camera)
- GET /api/districts/geojson 38 districts GeoJSON delivery
"""

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models import Shop, Commodity, StockLevel, Transaction, Alert, StockMovement

client = TestClient(app)


def test_districts_geojson_endpoint():
    """Verify GeoJSON FeatureCollection serves all 38 Tamil Nadu districts."""
    response = client.get("/api/districts/geojson")
    assert response.status_code == 200
    data = response.json()
    assert data.get("type") == "FeatureCollection"
    features = data.get("features", [])
    assert len(features) == 38, f"Expected 38 district features in GeoJSON, got {len(features)}"
    for f in features:
        assert "geometry" in f
        assert f["geometry"]["type"] == "Polygon"
        assert "properties" in f
        assert "centroid" in f["properties"]


def test_ingest_transaction_valid():
    """Verify POST /api/ingest/transaction succeeds, reduces stock, and logs provenance."""
    db = SessionLocal()
    try:
        shop = db.query(Shop).first()
        assert shop is not None
        initial_stock = db.query(StockLevel).filter(
            StockLevel.location_type == "shop",
            StockLevel.location_id == shop.id,
            StockLevel.item_id == 1,
        ).first()
        initial_qty = initial_stock.qty_kg if initial_stock else shop.opening_stock_kg

        payload = {
            "shop_id": shop.id,
            "item_id": 1,
            "qty_kg": 15.0,
            "bags": 3,
            "card_no": "TN-01-9876543",
            "source": "sensor",
        }

        response = client.post("/api/ingest/transaction", json=payload)
        assert response.status_code == 201
        data = response.json()

        assert data["status"] == "success"
        assert data["shop_id"] == shop.id
        assert data["qty_kg"] == 15.0
        assert data["bags"] == 3
        assert data["source"] == "sensor"
        assert data["remaining_stock_kg"] == round(initial_qty - 15.0, 2)
        assert data["transaction_id"].startswith("TXN-")

        # Verify DB transaction persistence
        txn = db.query(Transaction).filter(Transaction.id == data["transaction_id"]).first()
        assert txn is not None
        assert txn.card_no == "TN-01-9876543"
        assert txn.source == "sensor"

        # Cleanup
        db.query(Transaction).filter(Transaction.id == data["transaction_id"]).delete()
        db.query(StockMovement).filter(StockMovement.reference_id == data["transaction_id"]).delete()
        if initial_stock:
            initial_stock.qty_kg = initial_qty
        db.commit()
    finally:
        db.close()


def test_ingest_transaction_invalid_shop():
    """Verify 404 is returned when attempting to ingest for a non-existent shop."""
    payload = {
        "shop_id": "FPS-NON-EXISTENT-9999",
        "item_id": 1,
        "qty_kg": 20.0,
        "bags": 4,
        "card_no": "TN-00-0000000",
        "source": "simulator",
    }
    response = client.post("/api/ingest/transaction", json=payload)
    assert response.status_code == 404


def test_ingest_transaction_triggers_low_stock_alert():
    """Verify transaction draining shop below 300kg triggers LOW_STOCK alert."""
    db = SessionLocal()
    try:
        # Create a test shop or use existing and set stock low
        shop = db.query(Shop).filter(Shop.id == "FPS-0002").first()
        if not shop:
            shop = db.query(Shop).first()

        stock_level = db.query(StockLevel).filter(
            StockLevel.location_type == "shop",
            StockLevel.location_id == shop.id,
            StockLevel.item_id == 1,
        ).first()

        if not stock_level:
            stock_level = StockLevel(
                location_type="shop",
                location_id=shop.id,
                item_id=1,
                qty_kg=250.0,
                source="system",
            )
            db.add(stock_level)
        else:
            stock_level.qty_kg = 250.0
        db.commit()

        # Delete any open alert for clean test state
        db.query(Alert).filter(
            Alert.location_type == "shop",
            Alert.location_id == shop.id,
            Alert.alert_type == "LOW_STOCK",
        ).delete()
        db.commit()

        payload = {
            "shop_id": shop.id,
            "item_id": 1,
            "qty_kg": 20.0,
            "bags": 4,
            "card_no": "TN-02-1111222",
            "source": "ml_camera",
        }
        response = client.post("/api/ingest/transaction", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["remaining_stock_kg"] == 230.0
        assert data["alert_triggered"] is not None
        assert data["alert_triggered"]["type"] == "LOW_STOCK"

        # Cleanup
        db.query(Transaction).filter(Transaction.id == data["transaction_id"]).delete()
        db.query(StockMovement).filter(StockMovement.reference_id == data["transaction_id"]).delete()
        if data.get("alert_triggered"):
            db.query(Alert).filter(Alert.id == data["alert_triggered"]["id"]).delete()
        db.commit()
    finally:
        db.close()


def test_ingest_stock_audit_and_anomaly_detection():
    """Verify physical audit ingestion and anomaly alert on sudden unexplained drop."""
    db = SessionLocal()
    try:
        shop = db.query(Shop).filter(Shop.id == "FPS-0001").first()

        # Set baseline high stock
        stock_level = db.query(StockLevel).filter(
            StockLevel.location_type == "shop",
            StockLevel.location_id == shop.id,
            StockLevel.item_id == 1,
        ).first()
        if not stock_level:
            stock_level = StockLevel(
                location_type="shop",
                location_id=shop.id,
                item_id=1,
                qty_kg=5000.0,
                source="system",
            )
            db.add(stock_level)
        else:
            stock_level.qty_kg = 5000.0
        db.commit()

        # Ingest a reading with sudden 1,000kg drop (> 500kg & > 20%)
        payload = {
            "location_type": "shop",
            "location_id": shop.id,
            "item_id": 1,
            "qty_kg": 4000.0,
            "source": "sensor",
        }
        response = client.post("/api/ingest/stock", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["anomaly_detected"] is True
        assert data["alert_triggered"] is not None
        assert data["alert_triggered"]["type"] == "STOCK_DISCREPANCY"
    finally:
        db.close()


def test_live_transactions_feed():
    """Verify GET /api/transactions/live returns recent transactions."""
    response = client.get("/api/transactions/live?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "transactions" in data
    assert "count" in data
    assert data["count"] <= 10


def test_data_sources_status_and_activation():
    """Verify active source reporting and switching."""
    resp = client.get("/api/ingest/sources")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_source" in data
    assert "available_sources" in data

    # Activate sensor
    activate_resp = client.post("/api/ingest/source/activate?source_name=sensor")
    assert activate_resp.status_code == 200
    assert activate_resp.json()["active_source"] == "sensor"

    # Switch back to simulator
    activate_resp2 = client.post("/api/ingest/source/activate?source_name=simulator")
    assert activate_resp2.status_code == 200
    assert activate_resp2.json()["active_source"] == "simulator"
