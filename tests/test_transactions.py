"""
Integration Tests for Phase 5: Transactions, Business Rules & Auditing.
Validates:
1. Full Lifecycle Flow: Dispatch -> Confirm Delivery -> POS Distribution.
2. Delivery Confirmation with Quantity Difference -> marked 'RECEIVED_WITH_DIFFERENCE'.
3. Strict Enforcement of Domain Rules:
   - Rejection of non-positive kg quantities (<= 0).
   - Rejection of over-dispatch (exceeding godown expected stock).
   - Rejection of over-distribution (exceeding shop expected stock).
   - Rejection of missing reason on adjustments.
   - Rejection of negative stock adjustments (no negative balances permitted).
   - Rejection of duplicate delivery confirmation.
4. Verification that every mutation writes to audit_logs.
5. Operations & Transactions UI page rendering.
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models import Delivery, StockMovement, AuditLog, Measurement
from app.services.stock import compute_godown_stock, compute_shop_stock
from app.main import app

client = TestClient(app)
client.headers["X-Test-User"] = "admin_tn"


def test_full_dispatch_confirm_distribute_flow():
    """
    Test complete lifecycle:
    1. Dispatch from Godown to Shop -> Godown stock decreases, Pending Delivery created.
    2. Shop stock remains unchanged until explicit receipt confirmation.
    3. Delivery confirmed -> Shop stock increases by received quantity.
    4. Distribution to beneficiaries -> Shop stock decreases.
    5. Verify audit log entries.
    """
    db = SessionLocal()
    try:
        initial_gdn = compute_godown_stock(db, "GDN-001")["expected_stock_kg"]
        initial_fps = compute_shop_stock(db, "FPS-0001")["expected_stock_kg"]
        initial_audits_count = db.query(AuditLog).count()

        # Step 1: Create Dispatch of 1,200 kg from GDN-001 to FPS-0001
        dispatch_payload = {
            "from_godown_id": "GDN-001",
            "to_shop_id": "FPS-0001",
            "quantity_kg": 1200.0,
            "notes": "Test integration delivery batch #1",
            "created_by": "test_dispatcher",
        }
        res_disp = client.post("/api/transactions/dispatch", json=dispatch_payload)
        assert res_disp.status_code == 201
        disp_data = res_disp.json()
        del_id = disp_data["delivery_id"]
        assert disp_data["delivery_status"] == "PENDING"
        assert disp_data["dispatched_qty_kg"] == 1200.0

        # Verify Godown stock decreased by 1,200 kg
        gdn_after_disp = compute_godown_stock(db, "GDN-001")["expected_stock_kg"]
        assert gdn_after_disp == round(initial_gdn - 1200.0, 2)

        # Decoupled movement rule: Shop stock MUST NOT have changed yet!
        fps_after_disp = compute_shop_stock(db, "FPS-0001")["expected_stock_kg"]
        assert fps_after_disp == initial_fps

        # Step 2: Confirm Delivery Receipt at FPS-0001
        confirm_payload = {
            "delivery_id": del_id,
            "received_qty_kg": 1200.0,
            "notes": "Verified 1,200 kg in full condition",
            "created_by": "test_shop_mgr",
        }
        res_conf = client.post("/api/transactions/confirm-delivery", json=confirm_payload)
        assert res_conf.status_code == 200
        conf_data = res_conf.json()
        assert conf_data["delivery_status"] == "DELIVERED"
        assert conf_data["has_difference"] is False

        # Shop stock should now have increased by 1,200 kg
        fps_after_conf = compute_shop_stock(db, "FPS-0001")["expected_stock_kg"]
        assert fps_after_conf == round(initial_fps + 1200.0, 2)

        # Step 3: Record Distribution of 750 kg to 200 cardholders
        dist_payload = {
            "shop_id": "FPS-0001",
            "quantity_kg": 750.0,
            "beneficiary_households": 200,
            "reference_id": f"TEST-TX-{del_id}",
            "created_by": "test_epos",
        }
        res_dist = client.post("/api/transactions/distribution", json=dist_payload)
        assert res_dist.status_code == 201
        dist_data = res_dist.json()
        assert dist_data["distributed_qty_kg"] == 750.0

        # Shop stock should now be initial + 1200 - 750 = initial + 450
        fps_after_dist = compute_shop_stock(db, "FPS-0001")["expected_stock_kg"]
        assert fps_after_dist == round(initial_fps + 450.0, 2)

        # Step 4: Verify Audit Log entries were written for each action
        new_audits = db.query(AuditLog).filter(AuditLog.id > initial_audits_count).all()
        actions = [a.action for a in new_audits]
        assert "CREATE_DISPATCH" in actions
        assert "CONFIRM_DELIVERY" in actions
        assert "RECORD_DISTRIBUTION" in actions
    finally:
        db.close()


def test_delivery_confirmation_with_quantity_difference():
    """
    Test edge case:
    Dispatch 1,000 kg, but receive 960 kg (40 kg shortage).
    Delivery MUST be marked 'RECEIVED_WITH_DIFFERENCE' and shop receives only 960 kg.
    """
    db = SessionLocal()
    try:
        initial_fps = compute_shop_stock(db, "FPS-0002")["expected_stock_kg"]

        # Dispatch 1,000 kg from GDN-001 to FPS-0002
        disp_res = client.post("/api/transactions/dispatch", json={
            "from_godown_id": "GDN-001",
            "to_shop_id": "FPS-0002",
            "quantity_kg": 1000.0,
            "notes": "Dispatch for difference test",
            "created_by": "dispatcher_test",
        })
        del_id = disp_res.json()["delivery_id"]

        # Confirm with shortage: 960 kg received
        conf_res = client.post("/api/transactions/confirm-delivery", json={
            "delivery_id": del_id,
            "received_qty_kg": 960.0,
            "notes": "40 kg shortage due to bag puncture in transit",
            "created_by": "shop_mgr_test",
        })
        assert conf_res.status_code == 200
        conf_data = conf_res.json()

        assert conf_data["delivery_status"] == "RECEIVED_WITH_DIFFERENCE"
        assert conf_data["has_difference"] is True
        assert conf_data["difference_kg"] == -40.0
        assert conf_data["received_qty_kg"] == 960.0

        # Shop receives ONLY 960 kg
        fps_stock = compute_shop_stock(db, "FPS-0002")["expected_stock_kg"]
        assert fps_stock == round(initial_fps + 960.0, 2)

        # Verify delivery table status
        deliv_row = db.query(Delivery).filter(Delivery.id == del_id).first()
        assert deliv_row.status == "RECEIVED_WITH_DIFFERENCE"
    finally:
        db.close()


def test_rejection_of_over_dispatch():
    """Verify rejection when dispatch quantity exceeds available godown stock."""
    db = SessionLocal()
    try:
        current_gdn_stock = compute_godown_stock(db, "GDN-001")["expected_stock_kg"]
        excessive_qty = current_gdn_stock + 50000.0

        res = client.post("/api/transactions/dispatch", json={
            "from_godown_id": "GDN-001",
            "to_shop_id": "FPS-0001",
            "quantity_kg": excessive_qty,
            "notes": "Excessive dispatch",
            "created_by": "tester",
        })
        assert res.status_code == 400
        assert "Over-dispatch rejected" in res.json()["detail"]
    finally:
        db.close()


def test_rejection_of_over_distribution():
    """Verify rejection when distribution quantity exceeds shop stock."""
    db = SessionLocal()
    try:
        current_fps_stock = compute_shop_stock(db, "FPS-0001")["expected_stock_kg"]
        excessive_qty = current_fps_stock + 10000.0

        res = client.post("/api/transactions/distribution", json={
            "shop_id": "FPS-0001",
            "quantity_kg": excessive_qty,
            "beneficiary_households": 500,
            "reference_id": "EXCESS-POS-TX",
            "created_by": "tester",
        })
        assert res.status_code == 400
        assert "Over-distribution rejected" in res.json()["detail"]
    finally:
        db.close()


def test_rejection_of_negative_and_zero_quantities():
    """Verify validation error when quantities are <= 0."""
    # Negative receipt
    res_rec = client.post("/api/transactions/receipt", json={
        "godown_id": "GDN-001",
        "quantity_kg": -50.0,
        "reference_id": "NEG-FCI",
        "created_by": "tester",
    })
    assert res_rec.status_code == 422

    # Zero dispatch
    res_disp = client.post("/api/transactions/dispatch", json={
        "from_godown_id": "GDN-001",
        "to_shop_id": "FPS-0001",
        "quantity_kg": 0.0,
        "created_by": "tester",
    })
    assert res_disp.status_code == 422


def test_rejection_of_missing_reason_on_adjustment():
    """Verify that adjustments strictly require a non-empty reason."""
    # Empty reason
    res_empty = client.post("/api/transactions/adjustment", json={
        "location_type": "shop",
        "location_id": "FPS-0001",
        "quantity_kg": -10.0,
        "reason": "   ",
        "created_by": "tester",
    })
    assert res_empty.status_code == 422

    # Short reason (< 5 characters)
    res_short = client.post("/api/transactions/adjustment", json={
        "location_type": "shop",
        "location_id": "FPS-0001",
        "quantity_kg": -10.0,
        "reason": "loss",
        "created_by": "tester",
    })
    assert res_short.status_code == 422


def test_valid_adjustment_and_rejection_of_negative_balance():
    """Verify valid adjustments update balances, and excessive negative adjustments are rejected."""
    db = SessionLocal()
    try:
        initial_fps = compute_shop_stock(db, "FPS-0003")["expected_stock_kg"]

        # Valid adjustment of -15.0 kg with valid reason
        res_valid = client.post("/api/transactions/adjustment", json={
            "location_type": "shop",
            "location_id": "FPS-0003",
            "quantity_kg": -15.0,
            "reason": "Weighbridge moisture reduction confirmed on audit",
            "created_by": "test_auditor",
        })
        assert res_valid.status_code == 201
        fps_after = compute_shop_stock(db, "FPS-0003")["expected_stock_kg"]
        assert fps_after == round(initial_fps - 15.0, 2)

        # Attempt excessive deduction that would drive stock below zero
        res_excess = client.post("/api/transactions/adjustment", json={
            "location_type": "shop",
            "location_id": "FPS-0003",
            "quantity_kg": -(fps_after + 1000.0),
            "reason": "Excessive deduction test reason",
            "created_by": "test_auditor",
        })
        assert res_excess.status_code == 400
        assert "Adjustment rejected" in res_excess.json()["detail"]
    finally:
        db.close()


def test_rejection_of_duplicate_delivery_confirmation():
    """Verify that a consignment cannot be confirmed twice."""
    # Create dispatch
    disp = client.post("/api/transactions/dispatch", json={
        "from_godown_id": "GDN-001",
        "to_shop_id": "FPS-0004",
        "quantity_kg": 500.0,
        "created_by": "test_disp",
    }).json()
    del_id = disp["delivery_id"]

    # First confirmation -> succeeds
    res_conf1 = client.post("/api/transactions/confirm-delivery", json={
        "delivery_id": del_id,
        "received_qty_kg": 500.0,
        "created_by": "test_shop",
    })
    assert res_conf1.status_code == 200

    # Second confirmation -> rejected
    res_conf2 = client.post("/api/transactions/confirm-delivery", json={
        "delivery_id": del_id,
        "received_qty_kg": 500.0,
        "created_by": "test_shop",
    })
    assert res_conf2.status_code == 400
    assert "already been confirmed" in res_conf2.json()["detail"]


def test_transactions_page_html():
    """Verify Operations & Transactions page renders with forms, demo banner, and audit log."""
    res = client.get("/transactions")
    assert res.status_code == 200
    html = res.text

    # Permanent Banner
    assert "Demo Dataset — Not Official Government Data" in html

    # Forms
    assert 'id="formReceipt"' in html
    assert 'id="formDispatch"' in html
    assert 'id="confirmDeliveryId"' in html
    assert 'id="formDistribution"' in html
    assert 'id="formAdjustment"' in html
    assert 'id="formMeasurement"' in html

    # Audit stream table
    assert 'id="auditStreamTable"' in html
