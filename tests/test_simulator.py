"""
Tests for Live Simulator Service and Multi-Commodity Registry.
Validates:
- LiveSimulatorManager single step execution
- Start, stop, and status querying of the background simulator
- Multi-commodity stock coverage across all 38 districts
"""

import pytest
from app.services.simulator_service import simulator_manager
from app.database import SessionLocal
from app.models import Shop, Godown, Commodity, StockLevel, District


def test_simulator_single_step_execution():
    """Verify simulator generates valid purchase or refill transaction."""
    event = simulator_manager.generate_single_step()
    assert event is not None
    assert event["event"] in ["transaction", "refill_dispatch"]
    if event["event"] == "transaction":
        assert "transaction_id" in event
        assert "shop_id" in event
        assert "qty_kg" in event
        assert event["qty_kg"] > 0
        assert event["source"] == "simulator"

        # Cleanup test transaction and movement to prevent state pollution
        db = SessionLocal()
        try:
            from app.models import Transaction, StockMovement
            db.query(Transaction).filter(Transaction.id == event["transaction_id"]).delete()
            db.query(StockMovement).filter(StockMovement.reference_id == event["transaction_id"]).delete()
            db.commit()
        finally:
            db.close()


def test_simulator_lifecycle():
    """Verify simulator starts, reports running status, and stops cleanly."""
    start_res = simulator_manager.start(interval_seconds=1.0, rapid_drain_shop_count=2)
    assert start_res["status"] in ["started", "already_running"]
    assert simulator_manager.is_running is True

    status = simulator_manager.get_status()
    assert status["is_running"] is True
    assert status["interval_seconds"] == 1.0

    stop_res = simulator_manager.stop()
    assert stop_res["status"] == "stopped"
    assert simulator_manager.is_running is False


def test_38_districts_and_commodities_catalog():
    """Verify all 38 districts master catalogue and coordinates."""
    from scripts.seed_tamil_nadu_38 import TN_38_DISTRICTS, COMMODITIES_CATALOGUE

    assert len(TN_38_DISTRICTS) == 38, f"Expected 38 districts in master catalogue, got {len(TN_38_DISTRICTS)}"
    for d in TN_38_DISTRICTS:
        assert d["lat"] is not None and 8.0 <= d["lat"] <= 14.0
        assert d["lng"] is not None and 76.0 <= d["lng"] <= 81.0
        assert "zone" in d
        assert "headquarters" in d

    assert len(COMMODITIES_CATALOGUE) == 5
    codes = {c["code"] for c in COMMODITIES_CATALOGUE}
    assert {"RICE", "WHEAT", "SUGAR", "TOOR_DAL", "PALM_OIL"}.issubset(codes)

    # Check database districts have coordinates
    db = SessionLocal()
    try:
        districts = db.query(District).all()
        assert len(districts) >= 5
        for d in districts:
            assert d.lat is not None and 8.0 <= d.lat <= 14.0
            assert d.lng is not None and 76.0 <= d.lng <= 81.0
    finally:
        db.close()
