"""
Tests for Phase 7: Demand Forecasting and Replenishment Planning.
Validates:
1. SPEC UNIT TEST: Demands [3000, 3200, 3100, 3300] with stock 1200 must return 2265 kg.
2. Floor of zero constraint when stock + incoming exceeds requirement.
3. Database persistence in 'predictions' table and audit logging.
4. Historical back-test reporting Mean Absolute Error (MAE) and MAPE on the last mock month.
5. Official mandatory label: 'Planning recommendation, not an official allocation.'
"""

import json
import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models import Prediction, AuditLog
from app.services.forecast import (
    calculate_replenishment,
    backtest_forecast_accuracy,
    PLANNING_RECOMMENDATION_LABEL,
)
from app.main import app

client = TestClient(app)
client.headers["X-Test-User"] = "admin_tn"


def test_spec_replenishment_2265_kg_unit_test():
    """
    CRITICAL SPEC UNIT TEST:
    Demands: [3000, 3200, 3100, 3300]
    Usable Stock: 1200 kg
    Planned Incoming: 0 kg
    Buffer: 10%
    Requirement:
      Avg = (3000 + 3200 + 3100 + 3300) / 4 = 3150 kg
      Buffer = 3150 * 0.10 = 315 kg
      Gross Requirement = 3150 + 315 = 3465 kg
      Replenishment = 3465 - 1200 = 2265 kg.
    MUST return exactly 2265 kg.
    """
    demands = [3000.0, 3200.0, 3100.0, 3300.0]
    stock = 1200.0

    result = calculate_replenishment(
        demands=demands,
        usable_stock=stock,
        planned_incoming=0.0,
        buffer_pct=10.0,
    )

    assert result["predicted_demand_kg"] == 3150.0
    assert result["safety_buffer_kg"] == 315.0
    assert result["gross_requirement_kg"] == 3465.0
    assert result["recommended_replenishment_kg"] == 2265.0, (
        f"Spec unit test failed: expected 2265.0 kg, got {result['recommended_replenishment_kg']}"
    )
    assert result["label"] == "Planning recommendation, not an official allocation."


def test_replenishment_floor_of_zero():
    """Verify that when stock + incoming exceeds predicted gross requirement, replenishment is 0 kg."""
    demands = [2000.0, 2000.0, 2000.0, 2000.0]  # Demand = 2000, buffer = 200 -> total = 2200 kg
    usable_stock = 3000.0                         # Stock 3000 kg > 2200 kg
    planned_incoming = 500.0

    result = calculate_replenishment(
        demands=demands,
        usable_stock=usable_stock,
        planned_incoming=planned_incoming,
        buffer_pct=10.0,
    )

    assert result["gross_requirement_kg"] == 2200.0
    # Raw is 2200 - 3500 = -1300 kg, but floor of zero guarantees 0.0
    assert result["recommended_replenishment_kg"] == 0.0


def test_post_predictions_run_and_persistence():
    """Verify POST /api/predictions/run persists record with method and inputs JSON and writes audit log."""
    db = SessionLocal()
    try:
        initial_preds = db.query(Prediction).filter(Prediction.shop_id == "FPS-0001").count()
        initial_audits = db.query(AuditLog).filter(AuditLog.action == "RUN_DEMAND_FORECAST").count()

        payload = {
            "shop_id": "FPS-0001",
            "lookback_months": 4,
            "buffer_pct": 10.0,
            "persist": True,
        }
        res = client.post("/api/predictions/run", json=payload)
        assert res.status_code == 201
        data = res.json()

        assert data["shop_id"] == "FPS-0001"
        assert data["predicted_demand_kg"] > 0
        assert data["recommended_replenishment_kg"] >= 0
        assert data["label"] == "Planning recommendation, not an official allocation."
        assert data["prediction_id"] is not None

        # Verify database record
        pred_row = db.query(Prediction).filter(Prediction.id == data["prediction_id"]).first()
        assert pred_row is not None
        assert pred_row.method == "rolling_average"
        assert pred_row.lookback_months == 4
        assert pred_row.inputs_json is not None

        inputs_data = json.loads(pred_row.inputs_json)
        assert inputs_data["shop_id"] == "FPS-0001"
        assert len(inputs_data["demands"]) == 4

        # Verify audit log
        audits_after = db.query(AuditLog).filter(AuditLog.action == "RUN_DEMAND_FORECAST").count()
        assert audits_after == initial_audits + 1

        # Test latest lookup endpoint
        res_latest = client.get("/api/predictions/latest/FPS-0001")
        assert res_latest.status_code == 200
        latest_data = res_latest.json()
        assert latest_data["prediction_id"] == pred_row.id
        assert latest_data["label"] == PLANNING_RECOMMENDATION_LABEL
    finally:
        db.close()


def test_batch_prediction_run_for_all_shops():
    """Verify batch forecast execution across all 50 shops."""
    payload = {
        "shop_id": None,
        "lookback_months": 4,
        "buffer_pct": 10.0,
        "persist": True,
    }
    res = client.post("/api/predictions/run", json=payload)
    assert res.status_code == 201
    data = res.json()

    assert data["status"] == "success"
    assert data["shops_forecasted"] == 50
    assert data["total_predicted_demand_kg"] > 0
    assert data["total_recommended_replenishment_kg"] >= 0
    assert len(data["predictions"]) == 50


def test_backtest_reporting_mean_absolute_error():
    """
    SPEC REQUIREMENT:
    Run historical back-test evaluating predicted vs actual demand for the last mock month (2026-10).
    Verifies and reports Mean Absolute Error (MAE).
    """
    db = SessionLocal()
    try:
        report = backtest_forecast_accuracy(db, target_month="2026-10", lookback_months=4)
        assert report["target_month"] == "2026-10"
        assert report["shops_evaluated"] == 50
        assert report["mean_absolute_error_kg"] > 0
        assert report["mean_absolute_percentage_error_pct"] > 0

        # Log MAE evaluation result
        print(f"\n[BACK-TEST REPORT] MAE: {report['mean_absolute_error_kg']:,.2f} kg | MAPE: {report['mean_absolute_percentage_error_pct']:.2f}%")

        # HTTP Endpoint check
        res = client.get("/api/predictions/backtest?target_month=2026-10&lookback_months=4")
        assert res.status_code == 200
        endpoint_data = res.json()
        assert endpoint_data["shops_evaluated"] == 50
        assert endpoint_data["mean_absolute_error_kg"] == report["mean_absolute_error_kg"]
    finally:
        db.close()
