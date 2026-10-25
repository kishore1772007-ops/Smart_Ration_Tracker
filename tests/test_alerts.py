"""
Tests for Phase 8: Alert Engine & Alert Centre.
Validates:
1. SPEC TEST: Every seeded edge case yields exactly one alert:
   - 4 Delayed Deliveries -> 4 DELAYED_DELIVERY alerts
   - 5 Low-Stock Shops -> 5 LOW_STOCK alerts
   - 3 Measured Stock Discrepancies -> 3 STOCK_DISCREPANCY alerts
   - 2 Stale-record cases -> 2 MISSING_DATA alerts
2. Duplicate Prevention: Running the alert scan multiple times does NOT generate duplicate open alerts.
3. Neutral Phrasing Rule: Discrepancy alerts strictly use 'verification requested' without blaming.
4. Alert Lifecycle Management:
   - Transition to UNDER_VERIFICATION and RESOLVED.
   - Rejection of empty/blank verification notes.
   - Resolution date timestamping and audit log creation.
5. Alert filtering API and HTML Alert Centre page rendering.
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models import Alert, AuditLog
from app.services.alert_engine import scan_and_generate_alerts, update_alert_status
from app.main import app

client = TestClient(app)
client.headers["X-Test-User"] = "admin_tn"


def test_seeded_edge_cases_yield_exactly_one_alert_each():
    """
    CRITICAL SPEC REQUIREMENT:
    Verify that every seeded edge case yields exactly one alert:
    - 4 delayed consignments
    - 5 low-stock shops
    - 3 physical audit discrepancies (>2%)
    - 2 stale-record reporting lapses
    """
    db = SessionLocal()
    try:
        # Clear any existing alerts for a pristine scan
        db.query(Alert).delete()
        db.commit()

        # Execute alert scan
        scan_result = scan_and_generate_alerts(db)
        assert scan_result["new_alerts_created"] == 14

        # 1. Delayed Deliveries (FPS-0005, FPS-0020, FPS-0038, FPS-0046)
        delayed_alerts = db.query(Alert).filter(Alert.alert_type == "DELAYED_DELIVERY").all()
        assert len(delayed_alerts) == 4, f"Expected 4 delayed alerts, found {len(delayed_alerts)}"
        delayed_locations = {a.location_id for a in delayed_alerts}
        assert delayed_locations == {"FPS-0005", "FPS-0020", "FPS-0038", "FPS-0046"}
        for a in delayed_alerts:
            assert a.severity in ["MEDIUM", "HIGH"]
            assert a.assigned_role == "godown_manager"
            assert a.status == "OPEN"

        # 2. Low Stock Shops (FPS-0007, FPS-0018, FPS-0029, FPS-0042, FPS-0048)
        low_stock_alerts = db.query(Alert).filter(Alert.alert_type == "LOW_STOCK").all()
        assert len(low_stock_alerts) == 5, f"Expected 5 low stock alerts, found {len(low_stock_alerts)}"
        low_stock_locations = {a.location_id for a in low_stock_alerts}
        assert low_stock_locations == {"FPS-0007", "FPS-0018", "FPS-0029", "FPS-0042", "FPS-0048"}
        for a in low_stock_alerts:
            assert a.severity in ["HIGH", "CRITICAL"]
            assert a.assigned_role == "shop_manager"

        # 3. Measured Stock Discrepancies (FPS-0012, GDN-001, FPS-0035)
        discrepancy_alerts = db.query(Alert).filter(Alert.alert_type == "STOCK_DISCREPANCY").all()
        assert len(discrepancy_alerts) == 3, f"Expected 3 discrepancy alerts, found {len(discrepancy_alerts)}"
        disc_locations = {a.location_id for a in discrepancy_alerts}
        assert disc_locations == {"FPS-0012", "GDN-001", "FPS-0035"}

        # 4. Missing Data Stale Shops (FPS-0049, FPS-0050)
        missing_data_alerts = db.query(Alert).filter(Alert.alert_type == "MISSING_DATA").all()
        assert len(missing_data_alerts) == 2, f"Expected 2 missing data alerts, found {len(missing_data_alerts)}"
        missing_locations = {a.location_id for a in missing_data_alerts}
        assert missing_locations == {"FPS-0049", "FPS-0050"}
        for a in missing_data_alerts:
            assert a.assigned_role == "data_entry_officer"
    finally:
        db.close()


def test_duplicate_open_alert_prevention():
    """Verify that rescanning the database produces zero duplicates for open alerts."""
    db = SessionLocal()
    try:
        initial_count = db.query(Alert).count()
        assert initial_count == 14

        # Rescan
        rescan_result = scan_and_generate_alerts(db)
        assert rescan_result["new_alerts_created"] == 0, "Duplicate alerts were incorrectly created!"

        # Count must remain exactly 14
        assert db.query(Alert).count() == initial_count
    finally:
        db.close()


def test_neutral_phrasing_rule_on_discrepancies():
    """
    CRITICAL RULE:
    Discrepancy alerts must say 'verification requested' and never blame any person or shop.
    """
    db = SessionLocal()
    try:
        disc_alerts = db.query(Alert).filter(Alert.alert_type == "STOCK_DISCREPANCY").all()
        assert len(disc_alerts) == 3

        for a in disc_alerts:
            exp = a.explanation.lower()
            assert "verification requested" in exp
            # Verify no culpability wording
            for forbidden_word in ["fraud", "theft", "corrupt", "stolen", "culprit", "guilty", "crime"]:
                assert forbidden_word not in exp, f"Forbidden non-neutral word '{forbidden_word}' found in explanation: {a.explanation}"
    finally:
        db.close()


def test_alert_status_transition_and_mandatory_notes():
    """Verify status transition (OPEN -> UNDER_VERIFICATION -> RESOLVED) and required notes."""
    db = SessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.alert_type == "LOW_STOCK").first()
        assert alert is not None
        assert alert.status == "OPEN"

        # 1. Attempt update with empty notes -> rejected 400
        res_empty = client.post(f"/api/alerts/{alert.id}/action", json={
            "status": "UNDER_VERIFICATION",
            "verification_notes": "   ",
            "operator": "test_officer",
        })
        assert res_empty.status_code == 422

        # 2. Valid transition to UNDER_VERIFICATION
        res_verify = client.post(f"/api/alerts/{alert.id}/action", json={
            "status": "UNDER_VERIFICATION",
            "verification_notes": "Assigning field inspector to check shop POS registers",
            "operator": "test_officer",
        })
        assert res_verify.status_code == 200
        data_ver = res_verify.json()
        assert data_ver["new_status"] == "UNDER_VERIFICATION"
        assert "Assigning field inspector" in data_ver["verification_notes"]

        # 3. Transition to RESOLVED
        res_resolve = client.post(f"/api/alerts/{alert.id}/action", json={
            "status": "RESOLVED",
            "verification_notes": "Emergency replenishment consignment DEL-00999 dispatched and verified",
            "operator": "test_officer",
        })
        assert res_resolve.status_code == 200
        data_res = res_resolve.json()
        assert data_res["new_status"] == "RESOLVED"
        assert data_res["resolution_date"] is not None

        # Verify audit log recorded the status change
        audit = db.query(AuditLog).filter(
            AuditLog.action == "UPDATE_ALERT_STATUS",
            AuditLog.entity_id == alert.id,
        ).order_by(AuditLog.timestamp.desc()).first()
        assert audit is not None
        assert "RESOLVED" in audit.details
    finally:
        db.close()


def test_alerts_api_filtering():
    """Test GET /api/alerts filters for status, type, severity, and role."""
    # Filter by type
    res_type = client.get("/api/alerts?alert_type=DELAYED_DELIVERY")
    assert res_type.status_code == 200
    for a in res_type.json():
        assert a["alert_type"] == "DELAYED_DELIVERY"

    # Filter by severity
    res_sev = client.get("/api/alerts?severity=CRITICAL")
    assert res_sev.status_code == 200
    for a in res_sev.json():
        assert a["severity"] == "CRITICAL"

    # Filter by location
    res_loc = client.get("/api/alerts?location_id=FPS-0007")
    assert res_loc.status_code == 200
    assert len(res_loc.json()) >= 1
    assert res_loc.json()[0]["location_id"] == "FPS-0007"


def test_alert_centre_html_page_rendering():
    """Verify Alert Centre HTML page renders with stats, filters, and permanent banner."""
    res = client.get("/alerts")
    assert res.status_code == 200
    html = res.text

    # Permanent Banner
    assert "Demo Dataset — Not Official Government Data" in html

    # Stat cards
    assert 'id="statOpen"' in html
    assert 'id="statUnderVerif"' in html
    assert 'id="statResolved"' in html

    # Filter controls
    assert 'id="filterStatus"' in html
    assert 'id="filterType"' in html
    assert 'id="filterSeverity"' in html

    # Modal and table
    assert 'id="actionModal"' in html
    assert 'id="alertsTable"' in html
