"""
API endpoints for Alert Centre & Notification Engine.
Protected by Role-Based Access Control and location scoping.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Alert, User
from app.schemas.alerts import AlertStatusUpdate
from app.services.alert_engine import scan_and_generate_alerts, update_alert_status
from app.services.auth import (
    require_roles,
    get_optional_current_user,
    check_location_access,
)

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("")
def get_alerts(
    status: Optional[str] = Query(None, description="Filter by status (OPEN, UNDER_VERIFICATION, RESOLVED)"),
    alert_type: Optional[str] = Query(None, description="Filter by type (LOW_STOCK, DELAYED_DELIVERY, etc.)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, MEDIUM, LOW)"),
    location_id: Optional[str] = Query(None, description="Filter by location ID (e.g. FPS-0007)"),
    assigned_role: Optional[str] = Query(None, description="Filter by assigned role"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve system alerts with optional multidimensional filters.
    If authenticated as a scoped role (shop_manager, godown_manager), automatically scopes results.
    """
    query = db.query(Alert)

    # Scoping by authenticated role
    if current_user:
        if current_user.role == "shop_manager" and current_user.shop_id:
            query = query.filter(Alert.location_type == "shop", Alert.location_id == current_user.shop_id)
        elif current_user.role == "godown_manager" and current_user.godown_id:
            query = query.filter(Alert.location_id == current_user.godown_id)

    if status:
        query = query.filter(Alert.status == status.upper())
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type.upper())
    if severity:
        query = query.filter(Alert.severity == severity.upper())
    if location_id:
        query = query.filter(Alert.location_id == location_id)
    if assigned_role:
        query = query.filter(Alert.assigned_role == assigned_role.lower())

    alerts = query.order_by(Alert.timestamp.desc()).all()
    return [
        {
            "id": a.id,
            "location_type": a.location_type,
            "location_id": a.location_id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "timestamp": a.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "explanation": a.explanation,
            "assigned_role": a.assigned_role,
            "status": a.status,
            "verification_notes": a.verification_notes or "",
            "resolution_date": a.resolution_date.strftime("%Y-%m-%d %H:%M:%S") if a.resolution_date else None,
        }
        for a in alerts
    ]


@router.post("/scan")
def trigger_alert_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "district_officer", "stock_inspector")),
):
    """
    Triggers system-wide evaluation to detect low stock, delayed deliveries,
    inspection discrepancies, and missing data while preventing duplicate open alerts.
    Authorized: state_admin, district_officer, stock_inspector.
    """
    return scan_and_generate_alerts(db)


@router.post("/{alert_id}/action")
def post_alert_action(
    alert_id: str,
    payload: AlertStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "district_officer", "godown_manager", "shop_manager", "stock_inspector", "data_entry_officer")),
):
    """
    Transitions an alert's status (OPEN -> UNDER_VERIFICATION -> RESOLVED).
    Enforces mandatory verification notes, role scoping, and writes to audit_logs.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alert '{alert_id}' not found")

    check_location_access(current_user, alert.location_type, alert.location_id, db, action="act on alert for")

    try:
        return update_alert_status(
            db=db,
            alert_id=alert_id,
            new_status=payload.status,
            notes=payload.verification_notes,
            operator=current_user.username if current_user else payload.operator,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
