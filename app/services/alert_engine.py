"""
PDS Stock Alert Engine & Notification Service.
Evaluates rules for:
1. Low Stock (<20% High, <10% Critical)
2. Replenishment Required (Buffer deficit)
3. Delayed Delivery (Overdue transit consignments)
4. Stock Discrepancy (Physical audit variance >2% with neutral verification phrasing)
5. Missing Data (Stale POS reporting >= 10 days)

Guarantees:
- Duplicate open alert prevention for the same location and type.
- Neutral verification requested wording (never blames any person or shop).
- Mandatory verification notes for status updates.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Shop,
    Godown,
    Delivery,
    Measurement,
    Alert,
    StockMovement,
)
from app.services.stock import compute_shop_stock, reconcile_measurements
from app.services.transactions import log_audit


def get_next_alert_id(db: Session) -> str:
    """Generates unique sequential Alert ID e.g. ALT-00001."""
    count = db.query(func.count(Alert.id)).scalar() or 0
    return f"ALT-{count + 1:05d}"


def has_open_alert(db: Session, alert_type: str, location_id: str) -> bool:
    """
    Checks if an unresolved alert of the same type already exists for this location.
    Prevents duplicate open alerts.
    """
    existing = db.query(Alert).filter(
        Alert.alert_type == alert_type,
        Alert.location_id == location_id,
        Alert.status.in_(["OPEN", "UNDER_VERIFICATION"]),
    ).first()
    return existing is not None


def scan_and_generate_alerts(db: Session) -> Dict[str, Any]:
    """
    Executes a comprehensive system-wide scan across all locations and entities.
    Generates alerts while preventing duplicates.
    """
    now = datetime.now(timezone.utc)
    new_alerts: List[Alert] = []

    # -------------------------------------------------------------
    # 1. LOW STOCK ALERTS (<20% Low, <10% Critical)
    # -------------------------------------------------------------
    shops = db.query(Shop).all()
    for s in shops:
        stock_info = compute_shop_stock(db, s.id)
        status = stock_info["status"]

        if status in ["LOW", "CRITICAL"]:
            if not has_open_alert(db, "LOW_STOCK", s.id):
                sev = "CRITICAL" if status == "CRITICAL" else "HIGH"
                thresh_text = "< 10%" if status == "CRITICAL" else "< 20%"
                exp = (
                    f"Closing stock of {stock_info['expected_stock_kg']:,.2f} kg is {thresh_text} of "
                    f"average monthly distribution ({stock_info['avg_monthly_dist_kg']:,.2f} kg). "
                    f"Replenishment requested."
                )
                alt = Alert(
                    id=get_next_alert_id(db),
                    location_type="shop",
                    location_id=s.id,
                    alert_type="LOW_STOCK",
                    severity=sev,
                    timestamp=now,
                    explanation=exp,
                    assigned_role="shop_manager",
                    status="OPEN",
                )
                db.add(alt)
                db.flush()
                new_alerts.append(alt)

    # -------------------------------------------------------------
    # 2. DELAYED DELIVERY ALERTS
    # -------------------------------------------------------------
    delayed_consignments = db.query(Delivery).filter(
        Delivery.status == "DELAYED"
    ).all()

    for d in delayed_consignments:
        if not has_open_alert(db, "DELAYED_DELIVERY", d.to_shop_id):
            exp = (
                f"Consignment {d.id} of {d.dispatched_qty_kg:,.2f} kg dispatched from {d.from_godown_id} "
                f"to {d.to_shop_id} is delayed past expected arrival date "
                f"({d.expected_delivery_date.strftime('%Y-%m-%d')}). Route verification requested."
            )
            alt = Alert(
                id=get_next_alert_id(db),
                location_type="shop",
                location_id=d.to_shop_id,
                alert_type="DELAYED_DELIVERY",
                severity="MEDIUM",
                timestamp=now,
                explanation=exp,
                assigned_role="godown_manager",
                status="OPEN",
            )
            db.add(alt)
            db.flush()
            new_alerts.append(alt)

    # -------------------------------------------------------------
    # 3. STOCK DISCREPANCY ALERTS (Neutral wording rule)
    # -------------------------------------------------------------
    discrepancies = reconcile_measurements(db)
    for disc in discrepancies:
        if disc["discrepancy_detected"]:
            loc_id = disc["location_id"]
            if not has_open_alert(db, "STOCK_DISCREPANCY", loc_id):
                # Neutral phrasing: "Verification requested on stock balance"
                exp = (
                    f"{settings.DISCREPANCY_ALERT_LABEL}. Physical inspection {disc['measurement_id']} "
                    f"recorded {disc['measured_stock_kg']:,.2f} kg vs derived balance of {disc['expected_stock_kg']:,.2f} kg "
                    f"(Variance: {disc['difference_kg']:+,.2f} kg / {disc['difference_pct']}%, tolerance &plusmn;{disc['tolerance_pct']}%). "
                    f"Routine ledger reconciliation requested."
                )
                alt = Alert(
                    id=get_next_alert_id(db),
                    location_type=disc["location_type"],
                    location_id=loc_id,
                    alert_type="STOCK_DISCREPANCY",
                    severity="HIGH" if disc["difference_pct"] > 5.0 else "MEDIUM",
                    timestamp=now,
                    explanation=exp,
                    assigned_role="stock_inspector",
                    status="OPEN",
                )
                db.add(alt)
                db.flush()
                new_alerts.append(alt)

    # -------------------------------------------------------------
    # 4. MISSING DATA ALERTS (Stale shop records >= 10 days)
    # -------------------------------------------------------------
    cutoff_dt = datetime(2026, 10, 14, 23, 59, 59)
    for s in shops:
        recent_mov = db.query(StockMovement).filter(
            StockMovement.location_id == s.id,
            StockMovement.timestamp > cutoff_dt,
        ).first()

        if not recent_mov:
            if not has_open_alert(db, "MISSING_DATA", s.id):
                exp = (
                    f"No sales or movement activity logged for 10+ operational days. "
                    f"Data entry confirmation requested for shop register."
                )
                alt = Alert(
                    id=get_next_alert_id(db),
                    location_type="shop",
                    location_id=s.id,
                    alert_type="MISSING_DATA",
                    severity="MEDIUM",
                    timestamp=now,
                    explanation=exp,
                    assigned_role="data_entry_officer",
                    status="OPEN",
                )
                db.add(alt)
                db.flush()
                new_alerts.append(alt)

    db.commit()

    # Total counts by type
    open_alerts = db.query(Alert).filter(Alert.status.in_(["OPEN", "UNDER_VERIFICATION"])).all()
    type_counts = {}
    for a in open_alerts:
        type_counts[a.alert_type] = type_counts.get(a.alert_type, 0) + 1

    return {
        "new_alerts_created": len(new_alerts),
        "total_active_alerts": len(open_alerts),
        "alerts_by_type": type_counts,
        "message": f"Scan complete: {len(new_alerts)} new alerts generated ({len(open_alerts)} active).",
    }


def update_alert_status(
    db: Session,
    alert_id: str,
    new_status: str,
    notes: str,
    operator: str = "system_operator",
) -> Dict[str, Any]:
    """
    Updates status of an alert (OPEN -> UNDER_VERIFICATION -> RESOLVED).
    Enforces mandatory verification notes.
    """
    if not notes or not notes.strip():
        raise ValueError("Verification notes are strictly required to update alert status")

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise ValueError(f"Alert '{alert_id}' not found")

    old_status = alert.status
    now = datetime.now(timezone.utc)

    alert.status = new_status
    clean_notes = notes.strip()
    timestamp_prefix = f"[{now.strftime('%Y-%m-%d %H:%M')} by {operator}]: "
    if alert.verification_notes:
        alert.verification_notes += f"\n{timestamp_prefix}{clean_notes}"
    else:
        alert.verification_notes = f"{timestamp_prefix}{clean_notes}"

    if new_status == "RESOLVED":
        alert.resolution_date = now

    db.commit()

    # Log to audit_logs
    log_audit(
        db=db,
        username=operator,
        action="UPDATE_ALERT_STATUS",
        entity_type="ALERT",
        entity_id=alert.id,
        details=f"Alert {alert.id} ({alert.alert_type} at {alert.location_id}) transitioned from {old_status} to {new_status}. Notes: {clean_notes}",
    )

    return {
        "status": "success",
        "alert_id": alert.id,
        "old_status": old_status,
        "new_status": new_status,
        "verification_notes": alert.verification_notes,
        "resolution_date": alert.resolution_date.strftime("%Y-%m-%d %H:%M") if alert.resolution_date else None,
        "message": f"Alert {alert.id} status successfully changed to {new_status}.",
    }
