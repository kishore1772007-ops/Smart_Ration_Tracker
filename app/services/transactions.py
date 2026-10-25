"""
Transaction Service for Smart Ration Tracker.
Enforces core PDS integrity rules:
1. Positive kg quantities.
2. No over-dispatch: Dispatches cannot exceed current expected godown stock.
3. No over-distribution: Distributions cannot exceed current expected shop stock.
4. Dispatch creates a pending delivery.
5. Confirmation records the received quantity into shop stock, marking 'Received with Difference' if quantities mismatch.
6. Adjustments strictly require a valid reason.
7. Every create/update writes an audit log entry.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Godown,
    Shop,
    StockMovement,
    Delivery,
    MonthlyDistribution,
    Measurement,
    AuditLog,
)
from app.schemas.transactions import (
    ReceiptCreate,
    DispatchCreate,
    DeliveryConfirm,
    DistributionCreate,
    AdjustmentCreate,
    MeasurementCreate,
)
from app.services.stock import compute_godown_stock, compute_shop_stock


def log_audit(
    db: Session,
    username: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: str,
    user_id: Optional[int] = None,
) -> AuditLog:
    """Writes an immutable record to the audit_logs table."""
    audit_entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry


def generate_id(prefix: str, db: Session, model, id_column) -> str:
    """Generates sequential fictional IDs like MOV-002389 or DEL-000594."""
    count = db.query(func.count(id_column)).scalar() or 0
    return f"{prefix}-{count + 1:06d}" if prefix == "MOV" else f"{prefix}-{count + 1:05d}"


def record_receipt(db: Session, payload: ReceiptCreate) -> Dict[str, Any]:
    """
    Records an incoming rice receipt into a Godown (e.g. from FCI Central Pool).
    Updates Godown stock through an immutable RECEIPT movement.
    """
    godown = db.query(Godown).filter(Godown.id == payload.godown_id).first()
    if not godown:
        raise ValueError(f"Godown '{payload.godown_id}' not found")

    if payload.quantity_kg <= 0:
        raise ValueError("Receipt quantity must be positive kg")

    mov_id = generate_id("MOV", db, StockMovement, StockMovement.id)
    now = datetime.now(timezone.utc)

    movement = StockMovement(
        id=mov_id,
        location_type="godown",
        location_id=godown.id,
        movement_type="RECEIPT",
        quantity_kg=round(payload.quantity_kg, 2),
        timestamp=now,
        reference_id=payload.reference_id,
        created_by=payload.created_by,
    )
    db.add(movement)
    db.commit()

    # Derived stock after receipt
    updated_stock = compute_godown_stock(db, godown.id)["expected_stock_kg"]

    # Write Audit Log
    log_audit(
        db=db,
        username=payload.created_by,
        action="RECORD_RECEIPT",
        entity_type="GODOWN",
        entity_id=godown.id,
        details=f"Received {payload.quantity_kg:.2f} kg into {godown.id}. Ref: {payload.reference_id}. New stock: {updated_stock:.2f} kg.",
    )

    return {
        "status": "success",
        "movement_id": mov_id,
        "godown_id": godown.id,
        "received_qty_kg": payload.quantity_kg,
        "new_expected_stock_kg": updated_stock,
        "message": f"Successfully recorded receipt of {payload.quantity_kg:,.2f} kg at {godown.name}.",
    }


def create_dispatch(db: Session, payload: DispatchCreate) -> Dict[str, Any]:
    """
    Dispatches rice from Godown to a Fair-Price Shop.
    Rules:
    - Rejects over-dispatch if requested quantity exceeds current godown stock.
    - Decoupled: Creates a PENDING delivery consignment without modifying shop stock yet.
    """
    godown = db.query(Godown).filter(Godown.id == payload.from_godown_id).first()
    if not godown:
        raise ValueError(f"Godown '{payload.from_godown_id}' not found")

    shop = db.query(Shop).filter(Shop.id == payload.to_shop_id).first()
    if not shop:
        raise ValueError(f"Shop '{payload.to_shop_id}' not found")

    if payload.quantity_kg <= 0:
        raise ValueError("Dispatch quantity must be positive kg")

    # Check available stock at godown
    godown_stock = compute_godown_stock(db, godown.id)["expected_stock_kg"]
    if payload.quantity_kg > godown_stock:
        raise ValueError(
            f"Over-dispatch rejected: requested {payload.quantity_kg:,.2f} kg exceeds available "
            f"stock of {godown_stock:,.2f} kg at {godown.name}."
        )

    now = datetime.now(timezone.utc)
    delivery_id = generate_id("DEL", db, Delivery, Delivery.id)
    mov_id = generate_id("MOV", db, StockMovement, StockMovement.id)

    # 1. Record Godown DISPATCH movement
    dispatch_movement = StockMovement(
        id=mov_id,
        location_type="godown",
        location_id=godown.id,
        movement_type="DISPATCH",
        quantity_kg=round(payload.quantity_kg, 2),
        timestamp=now,
        reference_id=delivery_id,
        created_by=payload.created_by,
    )
    db.add(dispatch_movement)

    # 2. Create PENDING delivery consignment
    expected_arrival = payload.expected_delivery_date or (now + timedelta(days=1, hours=4))
    delivery = Delivery(
        id=delivery_id,
        dispatch_movement_id=mov_id,
        from_godown_id=godown.id,
        to_shop_id=shop.id,
        dispatched_date=now,
        expected_delivery_date=expected_arrival,
        status="PENDING",
        dispatched_qty_kg=round(payload.quantity_kg, 2),
        received_qty_kg=0.0,
        received_date=None,
        notes=payload.notes or "Consignment in transit",
    )
    db.add(delivery)
    db.commit()

    # Derived stock after dispatch
    new_godown_stock = compute_godown_stock(db, godown.id)["expected_stock_kg"]

    # Write Audit Log
    log_audit(
        db=db,
        username=payload.created_by,
        action="CREATE_DISPATCH",
        entity_type="DELIVERY",
        entity_id=delivery_id,
        details=f"Dispatched {payload.quantity_kg:.2f} kg from {godown.id} to {shop.id}. Delivery ID: {delivery_id}. Godown stock: {new_godown_stock:.2f} kg.",
    )

    return {
        "status": "success",
        "delivery_id": delivery_id,
        "dispatch_movement_id": mov_id,
        "from_godown_id": godown.id,
        "to_shop_id": shop.id,
        "dispatched_qty_kg": payload.quantity_kg,
        "expected_delivery_date": expected_arrival.strftime("%Y-%m-%d %H:%M"),
        "delivery_status": "PENDING",
        "godown_remaining_stock_kg": new_godown_stock,
        "message": f"Consignment {delivery_id} created for {payload.quantity_kg:,.2f} kg to {shop.name}.",
    }


def confirm_delivery(db: Session, payload: DeliveryConfirm) -> Dict[str, Any]:
    """
    Confirms physical receipt of a delivery consignment at a Fair-Price Shop.
    Rules:
    - Records actual received quantity in the shop's movement ledger via CONFIRMED_DELIVERY.
    - If received_qty != dispatched_qty, flags delivery as 'RECEIVED_WITH_DIFFERENCE'.
    - Double confirmation is rejected.
    """
    delivery = db.query(Delivery).filter(Delivery.id == payload.delivery_id).first()
    if not delivery:
        raise ValueError(f"Delivery '{payload.delivery_id}' not found")

    if delivery.status in ["DELIVERED", "RECEIVED_WITH_DIFFERENCE"]:
        raise ValueError(f"Consignment {payload.delivery_id} has already been confirmed as received.")

    if payload.received_qty_kg <= 0:
        raise ValueError("Received quantity must be positive kg")

    now = datetime.now(timezone.utc)
    diff = round(payload.received_qty_kg - delivery.dispatched_qty_kg, 2)
    has_mismatch = abs(diff) > 0.001

    final_status = "RECEIVED_WITH_DIFFERENCE" if has_mismatch else "DELIVERED"

    # Update Delivery Record
    delivery.status = final_status
    delivery.received_qty_kg = round(payload.received_qty_kg, 2)
    delivery.received_date = now
    if payload.notes:
        delivery.notes = f"{delivery.notes or ''} | Note: {payload.notes}".strip(" |")

    # Create CONFIRMED_DELIVERY movement for the shop
    mov_id = generate_id("MOV", db, StockMovement, StockMovement.id)
    movement = StockMovement(
        id=mov_id,
        location_type="shop",
        location_id=delivery.to_shop_id,
        movement_type="CONFIRMED_DELIVERY",
        quantity_kg=round(payload.received_qty_kg, 2),
        timestamp=now,
        reference_id=delivery.id,
        created_by=payload.created_by,
    )
    db.add(movement)
    db.commit()

    # Derived shop stock after confirmation
    shop_stock = compute_shop_stock(db, delivery.to_shop_id)["expected_stock_kg"]

    # Write Audit Log
    mismatch_note = f" (Variance: {diff:+.2f} kg, Status: {final_status})" if has_mismatch else ""
    log_audit(
        db=db,
        username=payload.created_by,
        action="CONFIRM_DELIVERY",
        entity_type="DELIVERY",
        entity_id=delivery.id,
        details=f"Confirmed delivery {delivery.id} at {delivery.to_shop_id}: received {payload.received_qty_kg:.2f} kg of {delivery.dispatched_qty_kg:.2f} kg dispatched{mismatch_note}. Shop stock: {shop_stock:.2f} kg.",
    )

    return {
        "status": "success",
        "delivery_id": delivery.id,
        "movement_id": mov_id,
        "to_shop_id": delivery.to_shop_id,
        "dispatched_qty_kg": delivery.dispatched_qty_kg,
        "received_qty_kg": payload.received_qty_kg,
        "delivery_status": final_status,
        "has_difference": has_mismatch,
        "difference_kg": diff,
        "shop_new_expected_stock_kg": shop_stock,
        "message": f"Consignment {delivery.id} confirmed with status '{final_status.replace('_', ' ')}'.",
    }


def record_distribution(db: Session, payload: DistributionCreate) -> Dict[str, Any]:
    """
    Records rice distributed from a Fair-Price Shop to cardholders via POS.
    Rules:
    - Rejects over-distribution if requested quantity exceeds current shop stock.
    - Adds a DISTRIBUTION movement and updates monthly distribution aggregates.
    """
    shop = db.query(Shop).filter(Shop.id == payload.shop_id).first()
    if not shop:
        raise ValueError(f"Shop '{payload.shop_id}' not found")

    if payload.quantity_kg <= 0:
        raise ValueError("Distribution quantity must be positive kg")

    current_stock = compute_shop_stock(db, shop.id)["expected_stock_kg"]
    if payload.quantity_kg > current_stock:
        raise ValueError(
            f"Over-distribution rejected: requested {payload.quantity_kg:,.2f} kg exceeds available "
            f"stock of {current_stock:,.2f} kg at {shop.name}."
        )

    now = datetime.now(timezone.utc)
    mov_id = generate_id("MOV", db, StockMovement, StockMovement.id)
    ref = payload.reference_id or f"POS-TX-{now.strftime('%Y%m%d%H%M')}-{shop.id}"

    # 1. Record shop DISTRIBUTION movement
    movement = StockMovement(
        id=mov_id,
        location_type="shop",
        location_id=shop.id,
        movement_type="DISTRIBUTION",
        quantity_kg=round(payload.quantity_kg, 2),
        timestamp=now,
        reference_id=ref,
        created_by=payload.created_by,
    )
    db.add(movement)

    # 2. Update or insert MonthlyDistribution record for current month
    current_month_str = now.strftime("%Y-%m")
    m_record = db.query(MonthlyDistribution).filter(
        MonthlyDistribution.shop_id == shop.id,
        MonthlyDistribution.month_year == current_month_str,
    ).first()

    if m_record:
        m_record.distributed_qty_kg = round(m_record.distributed_qty_kg + payload.quantity_kg, 2)
        m_record.beneficiary_households_served += payload.beneficiary_households
    else:
        m_record = MonthlyDistribution(
            shop_id=shop.id,
            month_year=current_month_str,
            distributed_qty_kg=round(payload.quantity_kg, 2),
            beneficiary_households_served=payload.beneficiary_households,
            created_at=now,
        )
        db.add(m_record)

    db.commit()

    # Derived stock after distribution
    new_shop_stock = compute_shop_stock(db, shop.id)["expected_stock_kg"]

    # Write Audit Log
    log_audit(
        db=db,
        username=payload.created_by,
        action="RECORD_DISTRIBUTION",
        entity_type="SHOP",
        entity_id=shop.id,
        details=f"Distributed {payload.quantity_kg:.2f} kg to {payload.beneficiary_households} cardholders at {shop.id}. Ref: {ref}. New stock: {new_shop_stock:.2f} kg.",
    )

    return {
        "status": "success",
        "movement_id": mov_id,
        "shop_id": shop.id,
        "distributed_qty_kg": payload.quantity_kg,
        "beneficiaries_served": payload.beneficiary_households,
        "shop_remaining_stock_kg": new_shop_stock,
        "message": f"Successfully recorded distribution of {payload.quantity_kg:,.2f} kg at {shop.name}.",
    }


def record_adjustment(db: Session, payload: AdjustmentCreate) -> Dict[str, Any]:
    """
    Applies a stock adjustment to a Godown or Shop (e.g. moisture loss, physical inventory alignment).
    Rules:
    - Reason is strictly mandatory.
    - If deduction, cannot exceed current expected balance (no negative balances permitted).
    """
    if not payload.reason or not payload.reason.strip():
        raise ValueError("Adjustment reason is strictly mandatory")

    if payload.location_type == "godown":
        loc = db.query(Godown).filter(Godown.id == payload.location_id).first()
        if not loc:
            raise ValueError(f"Godown '{payload.location_id}' not found")
        curr_stock = compute_godown_stock(db, payload.location_id)["expected_stock_kg"]
    else:
        loc = db.query(Shop).filter(Shop.id == payload.location_id).first()
        if not loc:
            raise ValueError(f"Shop '{payload.location_id}' not found")
        curr_stock = compute_shop_stock(db, payload.location_id)["expected_stock_kg"]

    # Prevent negative closing stock
    if payload.quantity_kg < 0 and abs(payload.quantity_kg) > curr_stock:
        raise ValueError(
            f"Adjustment rejected: deduction of {abs(payload.quantity_kg):,.2f} kg exceeds available "
            f"balance of {curr_stock:,.2f} kg at {loc.name}."
        )

    now = datetime.now(timezone.utc)
    mov_id = generate_id("MOV", db, StockMovement, StockMovement.id)

    movement = StockMovement(
        id=mov_id,
        location_type=payload.location_type,
        location_id=payload.location_id,
        movement_type="ADJUSTMENT",
        quantity_kg=round(payload.quantity_kg, 2),
        timestamp=now,
        reference_id=f"REASON: {payload.reason.strip()}",
        created_by=payload.created_by,
    )
    db.add(movement)
    db.commit()

    # Derived stock after adjustment
    new_stock = (
        compute_godown_stock(db, payload.location_id)["expected_stock_kg"]
        if payload.location_type == "godown"
        else compute_shop_stock(db, payload.location_id)["expected_stock_kg"]
    )

    # Write Audit Log
    log_audit(
        db=db,
        username=payload.created_by,
        action="RECORD_ADJUSTMENT",
        entity_type=payload.location_type.upper(),
        entity_id=payload.location_id,
        details=f"Stock adjustment of {payload.quantity_kg:+.2f} kg at {payload.location_id}. Reason: {payload.reason.strip()}. Resulting balance: {new_stock:.2f} kg.",
    )

    return {
        "status": "success",
        "movement_id": mov_id,
        "location_type": payload.location_type,
        "location_id": payload.location_id,
        "adjustment_qty_kg": payload.quantity_kg,
        "reason": payload.reason.strip(),
        "new_expected_stock_kg": new_stock,
        "message": f"Successfully applied adjustment of {payload.quantity_kg:+.2f} kg to {loc.name}.",
    }


def record_measurement(db: Session, payload: MeasurementCreate) -> Dict[str, Any]:
    """
    Records an official physical inspection stock audit by a Stock Inspector.
    """
    if payload.location_type == "godown":
        loc = db.query(Godown).filter(Godown.id == payload.location_id).first()
        if not loc:
            raise ValueError(f"Godown '{payload.location_id}' not found")
        expected_stock = compute_godown_stock(db, payload.location_id)["expected_stock_kg"]
    else:
        loc = db.query(Shop).filter(Shop.id == payload.location_id).first()
        if not loc:
            raise ValueError(f"Shop '{payload.location_id}' not found")
        expected_stock = compute_shop_stock(db, payload.location_id)["expected_stock_kg"]

    now = datetime.now(timezone.utc)
    meas_id = f"MEA-{db.query(func.count(Measurement.id)).scalar() + 1:04d}"

    measurement = Measurement(
        id=meas_id,
        location_type=payload.location_type,
        location_id=payload.location_id,
        measured_date=now,
        measured_stock_kg=round(payload.measured_stock_kg, 2),
        inspector_name=payload.inspector_name,
        remarks=payload.remarks or "Routine physical weighment audit",
    )
    db.add(measurement)
    db.commit()

    diff_kg = round(payload.measured_stock_kg - expected_stock, 2)
    diff_pct = round((abs(diff_kg) / expected_stock) * 100, 2) if expected_stock > 0 else 0.0

    # Write Audit Log
    log_audit(
        db=db,
        username=payload.inspector_name,
        action="RECORD_MEASUREMENT",
        entity_type=payload.location_type.upper(),
        entity_id=payload.location_id,
        details=f"Physical stock audit {meas_id} logged by {payload.inspector_name}: measured {payload.measured_stock_kg:.2f} kg vs expected {expected_stock:.2f} kg (Variance: {diff_kg:+.2f} kg / {diff_pct:.2f}%).",
    )

    return {
        "status": "success",
        "measurement_id": meas_id,
        "location_type": payload.location_type,
        "location_id": payload.location_id,
        "measured_stock_kg": payload.measured_stock_kg,
        "expected_stock_kg": expected_stock,
        "variance_kg": diff_kg,
        "variance_pct": diff_pct,
        "discrepancy_detected": diff_pct > 2.0,
        "message": f"Physical measurement {meas_id} recorded for {loc.name}.",
    }
