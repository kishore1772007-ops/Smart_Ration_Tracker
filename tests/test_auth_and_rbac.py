"""
Phase 9 Integration & Security Tests: Authentication, RBAC & Multi-Tier Location Scoping.
Validates:
1. Secure password hashing with bcrypt and verification against demo passwords.
2. User login (POST /api/auth/login), JWT token issuance, session cookies, and login audits.
3. Profile retrieval (GET /api/auth/me) with token and rejection without.
4. Protection of write endpoints: unauthenticated calls return 401 Unauthorized.
5. Role-based scoping:
   - CRITICAL REQUIREMENT: Shop manager CANNOT read another shop (403 Forbidden).
   - CRITICAL REQUIREMENT: Shop manager CANNOT modify another shop (403 Forbidden).
   - Shop manager CAN read and modify their own shop.
   - Godown manager CANNOT read or dispatch from another godown (403 Forbidden).
   - District officer CANNOT access another district (403 Forbidden).
   - State admin possesses unrestricted access across all locations and entities.
   - List endpoints (/api/shops, /api/godowns, /api/districts) automatically scope data by role.
"""

import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models.entities import User, AuditLog, Delivery
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.main import app

# Unauthenticated client for testing security boundaries
raw_client = TestClient(app)


def get_auth_token(username: str = "admin_tn", password: str = "demo123") -> str:
    """Helper to authenticate and retrieve access token."""
    res = raw_client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]


def test_password_hashing_and_verification():
    """Verify bcrypt password hashing and verification behavior."""
    plain = "demo123"
    hashed = hash_password(plain)
    assert hashed.startswith("$2b$")
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong_password", hashed) is False
    assert verify_password("", hashed) is False


def test_login_successful_and_jwt_issuance():
    """Verify login issuing JWT tokens, setting session cookie, and logging audit entry."""
    db = SessionLocal()
    try:
        initial_logins = db.query(AuditLog).filter(AuditLog.action == "LOGIN").count()

        res = raw_client.post("/api/auth/login", json={
            "username": "admin_tn",
            "password": "demo123",
        })
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "admin_tn"
        assert data["user"]["role"] == "state_admin"

        # Verify session cookie was attached
        assert "access_token" in res.cookies

        # Verify JWT payload
        payload = decode_access_token(data["access_token"])
        assert payload["sub"] == "admin_tn"
        assert payload["role"] == "state_admin"

        # Verify audit log entry
        after_logins = db.query(AuditLog).filter(AuditLog.action == "LOGIN").count()
        assert after_logins == initial_logins + 1
    finally:
        db.close()


def test_login_invalid_credentials_rejected():
    """Verify login rejection with 401 Unauthorized on invalid credentials."""
    # Wrong password
    res_wrong_pw = raw_client.post("/api/auth/login", json={
        "username": "admin_tn",
        "password": "incorrect_password",
    })
    assert res_wrong_pw.status_code == 401
    assert "Invalid username or password" in res_wrong_pw.json()["detail"]

    # Non-existent user
    res_no_user = raw_client.post("/api/auth/login", json={
        "username": "ghost_user",
        "password": "demo123",
    })
    assert res_no_user.status_code == 401


def test_get_current_user_profile():
    """Verify GET /api/auth/me returns profile when authenticated, and 401 when anonymous."""
    # 1. Anonymous request (fresh client without cookies)
    anon_client = TestClient(app)
    res_anon = anon_client.get("/api/auth/me")
    assert res_anon.status_code == 401

    # 2. Authenticated request as shop manager
    fps_token = get_auth_token("mgr_fps0001", "demo123")
    res_auth = anon_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {fps_token}"},
    )
    assert res_auth.status_code == 200
    user_data = res_auth.json()
    assert user_data["username"] == "mgr_fps0001"
    assert user_data["role"] == "shop_manager"
    assert user_data["shop_id"] == "FPS-0001"


def test_unauthenticated_requests_to_write_endpoints_rejected():
    """Verify that every write endpoint rejects unauthenticated requests with 401."""
    anon_client = TestClient(app)

    # 1. Dispatch
    res_disp = anon_client.post("/api/transactions/dispatch", json={
        "from_godown_id": "GDN-001",
        "to_shop_id": "FPS-0001",
        "quantity_kg": 100.0,
    })
    assert res_disp.status_code == 401

    # 2. Confirm Delivery
    res_conf = anon_client.post("/api/transactions/confirm-delivery", json={
        "delivery_id": "DEL-9999",
        "received_qty_kg": 100.0,
    })
    assert res_conf.status_code == 401

    # 3. POS Distribution
    res_dist = anon_client.post("/api/transactions/distribution", json={
        "shop_id": "FPS-0001",
        "quantity_kg": 50.0,
        "beneficiary_households": 10,
    })
    assert res_dist.status_code == 401

    # 4. Adjustment
    res_adj = anon_client.post("/api/transactions/adjustment", json={
        "location_type": "shop",
        "location_id": "FPS-0001",
        "quantity_kg": 10.0,
        "reason": "Test unauthenticated adjustment",
    })
    assert res_adj.status_code == 401

    # 5. Prediction Run
    res_pred = anon_client.post("/api/predictions/run", json={"shop_id": "FPS-0001"})
    assert res_pred.status_code == 401

    # 6. Alert Scan
    res_scan = anon_client.post("/api/alerts/scan")
    assert res_scan.status_code == 401


# =========================================================================
# CRITICAL SPEC REQUIREMENTS: SHOP MANAGER RESTRICTIONS
# =========================================================================

def test_shop_manager_can_read_and_modify_own_shop():
    """Verify shop manager CAN access and mutate their assigned shop (FPS-0001)."""
    token = get_auth_token("mgr_fps0001", "demo123")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Read API for own shop
    res_api = raw_client.get("/api/shops/FPS-0001", headers=headers)
    assert res_api.status_code == 200
    assert res_api.json()["id"] == "FPS-0001"

    # 2. Read HTML page for own shop
    res_html = raw_client.get("/shops/FPS-0001", headers=headers)
    assert res_html.status_code == 200
    assert "FPS-0001" in res_html.text

    # 3. Modify own shop: Record POS Distribution
    res_dist = raw_client.post(
        "/api/transactions/distribution",
        headers=headers,
        json={
            "shop_id": "FPS-0001",
            "quantity_kg": 25.0,
            "beneficiary_households": 5,
            "reference_id": "AUTH-OWN-TEST",
            "created_by": "mgr_fps0001",
        },
    )
    assert res_dist.status_code == 201
    assert res_dist.json()["shop_id"] == "FPS-0001"


def test_shop_manager_CANNOT_read_another_shop():
    """
    CRITICAL SPEC REQUIREMENT:
    Verify shop manager (FPS-0001) CANNOT read another shop (FPS-0002).
    Must return 403 Forbidden.
    """
    token = get_auth_token("mgr_fps0001", "demo123")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. API Read Attempt on another shop
    res_api = raw_client.get("/api/shops/FPS-0002", headers=headers)
    assert res_api.status_code == 403, f"Expected 403 Forbidden, got {res_api.status_code}"
    assert "Access Denied" in res_api.json()["detail"]
    assert "cannot view shop 'FPS-0002'" in res_api.json()["detail"]

    # 2. Web HTML Page Read Attempt on another shop
    res_html = raw_client.get("/shops/FPS-0002", headers=headers)
    assert res_html.status_code == 403, f"Expected 403 Forbidden on HTML page, got {res_html.status_code}"


def test_shop_manager_CANNOT_modify_another_shop():
    """
    CRITICAL SPEC REQUIREMENT:
    Verify shop manager (FPS-0001) CANNOT modify another shop (FPS-0002).
    Must return 403 Forbidden on all mutation endpoints.
    """
    token = get_auth_token("mgr_fps0001", "demo123")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Attempt to record distribution on another shop (FPS-0002)
    res_dist = raw_client.post(
        "/api/transactions/distribution",
        headers=headers,
        json={
            "shop_id": "FPS-0002",
            "quantity_kg": 50.0,
            "beneficiary_households": 10,
            "reference_id": "MALICIOUS-DIST-ATTEMPT",
            "created_by": "mgr_fps0001",
        },
    )
    assert res_dist.status_code == 403, f"Expected 403 Forbidden, got {res_dist.status_code}"
    assert "Access Denied" in res_dist.json()["detail"]

    # 2. Attempt to apply adjustment on another shop (FPS-0002)
    res_adj = raw_client.post(
        "/api/transactions/adjustment",
        headers=headers,
        json={
            "location_type": "shop",
            "location_id": "FPS-0002",
            "quantity_kg": -10.0,
            "reason": "Unauthorized cross-shop deduction",
            "created_by": "mgr_fps0001",
        },
    )
    assert res_adj.status_code == 403, f"Expected 403 Forbidden, got {res_adj.status_code}"

    # 3. Attempt to confirm delivery intended for another shop
    db = SessionLocal()
    try:
        # Find a pending delivery for FPS-0002
        deliv = db.query(Delivery).filter(
            Delivery.to_shop_id == "FPS-0002",
            Delivery.status.in_(["PENDING", "DELAYED"]),
        ).first()
        if deliv:
            res_conf = raw_client.post(
                "/api/transactions/confirm-delivery",
                headers=headers,
                json={
                    "delivery_id": deliv.id,
                    "received_qty_kg": deliv.dispatched_qty_kg,
                    "notes": "Unauthorized confirmation attempt",
                },
            )
            assert res_conf.status_code == 403, f"Expected 403 Forbidden, got {res_conf.status_code}"
    finally:
        db.close()

    # 4. Attempt to run demand forecast for another shop (FPS-0002)
    res_pred = raw_client.post(
        "/api/predictions/run",
        headers=headers,
        json={"shop_id": "FPS-0002"},
    )
    assert res_pred.status_code == 403, f"Expected 403 Forbidden, got {res_pred.status_code}"


def test_godown_manager_scoped_to_assigned_godown():
    """Verify godown manager (GDN-001) cannot access or dispatch from another godown (GDN-002)."""
    token = get_auth_token("mgr_gdn001", "demo123")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Can view own godown
    res_own = raw_client.get("/api/godowns/GDN-001", headers=headers)
    assert res_own.status_code == 200

    # 2. CANNOT view another godown
    res_other = raw_client.get("/api/godowns/GDN-002", headers=headers)
    assert res_other.status_code == 403
    assert "Access Denied" in res_other.json()["detail"]

    # 3. CANNOT dispatch from another godown
    res_disp = raw_client.post(
        "/api/transactions/dispatch",
        headers=headers,
        json={
            "from_godown_id": "GDN-002",
            "to_shop_id": "FPS-0011",
            "quantity_kg": 500.0,
            "notes": "Unauthorized cross-godown dispatch",
            "created_by": "mgr_gdn001",
        },
    )
    assert res_disp.status_code == 403


def test_district_officer_scoped_to_assigned_district():
    """Verify district officer (Chennai / District 1) cannot access District 2."""
    token = get_auth_token("officer_chennai", "demo123")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Can view assigned District 1
    res_own = raw_client.get("/api/districts/1", headers=headers)
    assert res_own.status_code == 200

    # 2. CANNOT view District 2
    res_other = raw_client.get("/api/districts/2", headers=headers)
    assert res_other.status_code == 403
    assert "Access Denied" in res_other.json()["detail"]

    # 3. CANNOT view HTML page of District 2
    res_html = raw_client.get("/districts/2", headers=headers)
    assert res_html.status_code == 403


def test_state_admin_unrestricted_universal_access():
    """Verify state admin possesses unrestricted access across all districts, godowns, and shops."""
    token = get_auth_token("admin_tn", "demo123")
    headers = {"Authorization": f"Bearer {token}"}

    # Districts 1 and 2
    assert raw_client.get("/api/districts/1", headers=headers).status_code == 200
    assert raw_client.get("/api/districts/2", headers=headers).status_code == 200

    # Godowns 1 and 2
    assert raw_client.get("/api/godowns/GDN-001", headers=headers).status_code == 200
    assert raw_client.get("/api/godowns/GDN-002", headers=headers).status_code == 200

    # Shops 1 and 2
    assert raw_client.get("/api/shops/FPS-0001", headers=headers).status_code == 200
    assert raw_client.get("/api/shops/FPS-0002", headers=headers).status_code == 200


def test_data_scoping_on_list_endpoints():
    """Verify list endpoints (/api/shops, /api/godowns, /api/districts) scope returned entities by role."""
    # 1. Shop Manager: GET /api/shops returns ONLY their 1 shop
    token_fps = get_auth_token("mgr_fps0001", "demo123")
    res_fps = raw_client.get("/api/shops", headers={"Authorization": f"Bearer {token_fps}"})
    assert res_fps.status_code == 200
    fps_list = res_fps.json()
    assert len(fps_list) == 1
    assert fps_list[0]["id"] == "FPS-0001"

    # 2. Godown Manager: GET /api/godowns returns ONLY their 1 godown
    token_gdn = get_auth_token("mgr_gdn001", "demo123")
    res_gdn = raw_client.get("/api/godowns", headers={"Authorization": f"Bearer {token_gdn}"})
    assert res_gdn.status_code == 200
    gdn_list = res_gdn.json()
    assert len(gdn_list) == 1
    assert gdn_list[0]["id"] == "GDN-001"

    # 3. District Officer: GET /api/districts returns ONLY their 1 district
    token_dist = get_auth_token("officer_chennai", "demo123")
    res_dist = raw_client.get("/api/districts", headers={"Authorization": f"Bearer {token_dist}"})
    assert res_dist.status_code == 200
    dist_list = res_dist.json()
    assert len(dist_list) == 1
    assert dist_list[0]["id"] == 1
    assert dist_list[0]["name"] == "Chennai"
