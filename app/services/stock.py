"""
Stock Calculation & Detail Retrieval Service.
Enforces core PDS business rules:
- Godown Stock = opening + receipts - dispatches +/- adjustments
- Shop Stock   = opening + confirmed_deliveries - distributions +/- adjustments
- All stock balances are derived dynamically from the movement ledger.
- Physical audit reconciliation with neutral verification requested alerts.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Godown,
    Shop,
    District,
    StockMovement,
    Delivery,
    MonthlyDistribution,
    Measurement,
    Alert,
)


def compute_godown_stock(
    db: Session,
    godown_id: str,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Computes derived stock balance for a Godown from its opening stock and movements.
    Formula: opening_stock + receipts - dispatches + adjustments
    """
    godown = db.query(Godown).filter(Godown.id == godown_id).first()
    if not godown:
        raise ValueError(f"Godown '{godown_id}' not found")

    query = db.query(
        StockMovement.movement_type,
        func.coalesce(func.sum(StockMovement.quantity_kg), 0.0).label("total_qty"),
    ).filter(
        StockMovement.location_type == "godown",
        StockMovement.location_id == godown_id,
    )

    if as_of:
        query = query.filter(StockMovement.timestamp <= as_of)

    movement_sums = dict(query.group_by(StockMovement.movement_type).all())

    receipts = float(movement_sums.get("RECEIPT", 0.0))
    dispatches = float(movement_sums.get("DISPATCH", 0.0))
    adjustments = float(movement_sums.get("ADJUSTMENT", 0.0))

    opening_stock = float(godown.opening_stock_kg)
    expected_stock = round(opening_stock + receipts - dispatches + adjustments, 2)

    return {
        "location_type": "godown",
        "location_id": godown_id,
        "godown_code": godown.code,
        "godown_name": godown.name,
        "district_id": godown.district_id,
        "capacity_kg": float(godown.capacity_kg),
        "opening_stock_kg": opening_stock,
        "receipts_kg": receipts,
        "dispatches_kg": dispatches,
        "adjustments_kg": adjustments,
        "expected_stock_kg": expected_stock,
        "utilization_pct": round((expected_stock / godown.capacity_kg) * 100, 2) if godown.capacity_kg > 0 else 0.0,
    }


def compute_shop_stock(
    db: Session,
    shop_id: str,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Computes derived stock balance for a Fair-Price Shop from opening stock and movements.
    Formula: opening_stock + confirmed_deliveries - distributions + adjustments
    """
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop '{shop_id}' not found")

    query = db.query(
        StockMovement.movement_type,
        func.coalesce(func.sum(StockMovement.quantity_kg), 0.0).label("total_qty"),
    ).filter(
        StockMovement.location_type == "shop",
        StockMovement.location_id == shop_id,
    )

    if as_of:
        query = query.filter(StockMovement.timestamp <= as_of)

    movement_sums = dict(query.group_by(StockMovement.movement_type).all())

    confirmed_deliveries = float(movement_sums.get("CONFIRMED_DELIVERY", 0.0))
    distributions = float(movement_sums.get("DISTRIBUTION", 0.0))
    adjustments = float(movement_sums.get("ADJUSTMENT", 0.0))

    opening_stock = float(shop.opening_stock_kg)
    expected_stock = round(opening_stock + confirmed_deliveries - distributions + adjustments, 2)

    # Calculate average monthly distribution for threshold evaluation
    avg_dist_query = db.query(
        func.coalesce(func.avg(MonthlyDistribution.distributed_qty_kg), 0.0)
    ).filter(MonthlyDistribution.shop_id == shop_id).scalar()
    avg_monthly_dist = float(avg_dist_query or 0.0)

    # Determine status: normal, low, critical
    low_threshold = avg_monthly_dist * settings.LOW_STOCK_THRESHOLD_PCT
    crit_threshold = avg_monthly_dist * settings.CRITICAL_STOCK_THRESHOLD_PCT

    if expected_stock < crit_threshold:
        status_label = "CRITICAL"
    elif expected_stock < low_threshold:
        status_label = "LOW"
    else:
        status_label = "NORMAL"

    return {
        "location_type": "shop",
        "location_id": shop_id,
        "shop_code": shop.code,
        "shop_name": shop.name,
        "district_id": shop.district_id,
        "godown_id": shop.godown_id,
        "beneficiaries_count": shop.beneficiaries_count,
        "opening_stock_kg": opening_stock,
        "confirmed_deliveries_kg": confirmed_deliveries,
        "distributions_kg": distributions,
        "adjustments_kg": adjustments,
        "expected_stock_kg": expected_stock,
        "avg_monthly_dist_kg": round(avg_monthly_dist, 2),
        "low_stock_threshold_kg": round(low_threshold, 2),
        "critical_threshold_kg": round(crit_threshold, 2),
        "status": status_label,
    }


def get_godown_detail(db: Session, godown_id: str) -> Dict[str, Any]:
    """
    Retrieves full detail view for a godown:
    - Opening, Received, Dispatched, Adjustments, Expected Closing Stock
    - Incoming Receipts table
    - Outgoing Dispatches table (with destination shops and delivery status)
    """
    godown = db.query(Godown).filter(Godown.id == godown_id).first()
    if not godown:
        raise ValueError(f"Godown '{godown_id}' not found")

    district = db.query(District).filter(District.id == godown.district_id).first()
    stock_metrics = compute_godown_stock(db, godown_id)

    # Incoming receipts (FCI / Supplier pool)
    incoming_receipts = db.query(StockMovement).filter(
        StockMovement.location_type == "godown",
        StockMovement.location_id == godown_id,
        StockMovement.movement_type == "RECEIPT",
    ).order_by(StockMovement.timestamp.desc()).all()

    # Outgoing dispatches to shops
    outgoing_dispatches = db.query(Delivery).filter(
        Delivery.from_godown_id == godown_id
    ).order_by(Delivery.dispatched_date.desc()).all()

    # Linked shops
    shops = db.query(Shop).filter(Shop.godown_id == godown_id).all()
    shops_map = {s.id: s.name for s in shops}

    dispatches_list = [
        {
            "delivery_id": d.id,
            "shop_id": d.to_shop_id,
            "shop_name": shops_map.get(d.to_shop_id, d.to_shop_id),
            "dispatched_date": d.dispatched_date.strftime("%Y-%m-%d %H:%M") if d.dispatched_date else "",
            "expected_delivery_date": d.expected_delivery_date.strftime("%Y-%m-%d %H:%M") if d.expected_delivery_date else "",
            "dispatched_qty_kg": d.dispatched_qty_kg,
            "received_qty_kg": d.received_qty_kg,
            "status": d.status,
            "notes": d.notes or "",
        }
        for d in outgoing_dispatches
    ]

    receipts_list = [
        {
            "id": r.id,
            "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M"),
            "reference_id": r.reference_id or "",
            "quantity_kg": r.quantity_kg,
            "created_by": r.created_by,
        }
        for r in incoming_receipts
    ]

    return {
        "godown": godown,
        "district": district,
        "metrics": stock_metrics,
        "incoming_receipts": receipts_list,
        "outgoing_dispatches": dispatches_list,
        "linked_shops": shops,
    }


def get_shop_detail(db: Session, shop_id: str) -> Dict[str, Any]:
    """
    Retrieves full detail view for a Fair-Price Shop:
    - Opening, Received (confirmed), Distributed, Adjustments, Expected Closing Stock
    - Monthly distribution history (for Chart.js)
    - Prediction placeholder (4-month rolling average + 10% safety buffer)
    - Current alerts for this shop
    """
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop '{shop_id}' not found")

    district = db.query(District).filter(District.id == shop.district_id).first()
    godown = db.query(Godown).filter(Godown.id == shop.godown_id).first()
    stock_metrics = compute_shop_stock(db, shop_id)

    # Monthly distribution history
    monthly_records = db.query(MonthlyDistribution).filter(
        MonthlyDistribution.shop_id == shop_id
    ).order_by(MonthlyDistribution.month_year.asc()).all()

    month_labels = [m.month_year for m in monthly_records]
    month_values = [round(float(m.distributed_qty_kg), 2) for m in monthly_records]

    # Calculate 4-month rolling average for the prediction placeholder
    recent_4 = month_values[-4:] if len(month_values) >= 4 else month_values
    predicted_avg = round(sum(recent_4) / len(recent_4), 2) if recent_4 else 0.0
    buffer_kg = round(predicted_avg * 0.10, 2)  # 10% buffer
    usable_stock = stock_metrics["expected_stock_kg"]

    # Incoming pending deliveries
    pending_deliveries = db.query(Delivery).filter(
        Delivery.to_shop_id == shop_id,
        Delivery.status.in_(["PENDING", "DELAYED"]),
    ).all()
    planned_incoming = round(sum(float(d.dispatched_qty_kg) for d in pending_deliveries), 2)

    recommended_replenishment = max(0.0, round(predicted_avg + buffer_kg - usable_stock - planned_incoming, 2))

    # Current Alerts (Low stock, delayed delivery, inspection discrepancy)
    alerts = []
    if stock_metrics["status"] == "CRITICAL":
        alerts.append({
            "type": "CRITICAL_STOCK",
            "severity": "CRITICAL",
            "title": "Critical Stock Balance (< 10%)",
            "explanation": f"Current closing stock ({stock_metrics['expected_stock_kg']} kg) is critically below 10% of monthly average distribution ({stock_metrics['avg_monthly_dist_kg']} kg).",
            "action": "Immediate replenishment dispatch requested.",
        })
    elif stock_metrics["status"] == "LOW":
        alerts.append({
            "type": "LOW_STOCK",
            "severity": "HIGH",
            "title": "Low Stock Warning (< 20%)",
            "explanation": f"Current closing stock ({stock_metrics['expected_stock_kg']} kg) is below 20% of monthly average distribution.",
            "action": "Consignment dispatch scheduled.",
        })

    for d in pending_deliveries:
        if d.status == "DELAYED":
            alerts.append({
                "type": "DELAYED_DELIVERY",
                "severity": "MEDIUM",
                "title": f"Delayed Consignment: {d.id}",
                "explanation": f"Consignment of {d.dispatched_qty_kg} kg dispatched from {godown.name} is overdue. Expected: {d.expected_delivery_date.strftime('%Y-%m-%d')}.",
                "action": "Carrier route verification requested.",
            })

    # Check for inspection discrepancies on this shop
    shop_measurements = db.query(Measurement).filter(
        Measurement.location_type == "shop",
        Measurement.location_id == shop_id,
    ).all()
    for sm in shop_measurements:
        as_of_stock = compute_shop_stock(db, shop_id, as_of=sm.measured_date)["expected_stock_kg"]
        diff = abs(sm.measured_stock_kg - as_of_stock)
        if as_of_stock > 0 and (diff / as_of_stock) > settings.DISCREPANCY_TOLERANCE_PCT:
            alerts.append({
                "type": "STOCK_DISCREPANCY",
                "severity": "MEDIUM",
                "title": f"Physical Audit Discrepancy ({sm.id})",
                "explanation": f"Inspection recorded {sm.measured_stock_kg} kg vs derived {as_of_stock} kg (variance: {diff:.1f} kg). {settings.DISCREPANCY_ALERT_LABEL}.",
                "action": "Routine verification requested on ledger counterfoil.",
            })

    # Recent shop deliveries
    recent_deliveries = db.query(Delivery).filter(
        Delivery.to_shop_id == shop_id
    ).order_by(Delivery.dispatched_date.desc()).limit(15).all()

    return {
        "shop": shop,
        "district": district,
        "godown": godown,
        "metrics": stock_metrics,
        "monthly_history": {
            "labels": month_labels,
            "quantities": month_values,
        },
        "prediction_placeholder": {
            "method": "4-Month Rolling Average (Configurable to 6)",
            "predicted_demand_kg": round(predicted_avg, 2),
            "safety_buffer_kg": round(buffer_kg, 2),
            "usable_stock_kg": usable_stock,
            "planned_incoming_kg": planned_incoming,
            "recommended_replenishment_kg": recommended_replenishment,
            "label": "Planning recommendation, not an official allocation.",
        },
        "alerts": alerts,
        "recent_deliveries": recent_deliveries,
    }


def get_district_detail(db: Session, district_id: int) -> Dict[str, Any]:
    """
    Retrieves full detail view for a district:
    - Summary metrics
    - Godowns in the district (with individual derived stocks)
    - Shops in the district (with individual derived stocks and statuses)
    """
    district = db.query(District).filter(District.id == district_id).first()
    if not district:
        raise ValueError(f"District {district_id} not found")

    godowns = db.query(Godown).filter(Godown.district_id == district_id).all()
    shops = db.query(Shop).filter(Shop.district_id == district_id).all()

    godown_summaries = [compute_godown_stock(db, g.id) for g in godowns]
    shop_summaries = [compute_shop_stock(db, s.id) for s in shops]

    total_godown_stock = sum(g["expected_stock_kg"] for g in godown_summaries)
    total_shop_stock = sum(s["expected_stock_kg"] for s in shop_summaries)
    total_beneficiaries = sum(s.beneficiaries_count for s in shops)

    # Monthly distribution for latest month
    dist_total = db.query(
        func.coalesce(func.sum(MonthlyDistribution.distributed_qty_kg), 0.0)
    ).join(Shop).filter(
        Shop.district_id == district_id,
        MonthlyDistribution.month_year == "2026-10",
    ).scalar() or 0.0

    return {
        "district": district,
        "godowns_count": len(godowns),
        "shops_count": len(shops),
        "total_godown_stock_kg": round(total_godown_stock, 2),
        "total_shop_stock_kg": round(total_shop_stock, 2),
        "total_stock_kg": round(total_godown_stock + total_shop_stock, 2),
        "total_beneficiaries": total_beneficiaries,
        "monthly_distributed_kg": round(float(dist_total), 2),
        "godowns": godown_summaries,
        "shops": shop_summaries,
    }


def compute_district_summary(
    db: Session,
    district_id: int,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes aggregated derived stock and distribution metrics for a single district.
    """
    district = db.query(District).filter(District.id == district_id).first()
    if not district:
        raise ValueError(f"District {district_id} not found")

    godowns = db.query(Godown).filter(Godown.district_id == district_id).all()
    shops = db.query(Shop).filter(Shop.district_id == district_id).all()

    total_godown_stock = sum(compute_godown_stock(db, g.id)["expected_stock_kg"] for g in godowns)
    shop_summaries = [compute_shop_stock(db, s.id) for s in shops]
    total_shop_stock = sum(s["expected_stock_kg"] for s in shop_summaries)

    dist_query = db.query(
        func.coalesce(func.sum(MonthlyDistribution.distributed_qty_kg), 0.0)
    ).join(Shop).filter(Shop.district_id == district_id)

    if month:
        dist_query = dist_query.filter(MonthlyDistribution.month_year == month)

    monthly_dist_total = float(dist_query.scalar() or 0.0)

    normal_count = sum(1 for s in shop_summaries if s["status"] == "NORMAL")
    low_count = sum(1 for s in shop_summaries if s["status"] == "LOW")
    critical_count = sum(1 for s in shop_summaries if s["status"] == "CRITICAL")

    return {
        "district_id": district.id,
        "district_code": district.code,
        "district_name": district.name,
        "headquarters": district.headquarters,
        "godowns_count": len(godowns),
        "shops_count": len(shops),
        "total_godown_stock_kg": round(total_godown_stock, 2),
        "total_shop_stock_kg": round(total_shop_stock, 2),
        "total_stock_kg": round(total_godown_stock + total_shop_stock, 2),
        "monthly_distributed_kg": round(monthly_dist_total, 2),
        "shops_normal": normal_count,
        "shops_low": low_count,
        "shops_critical": critical_count,
        "status_badge": "Critical" if critical_count > 0 else ("Low" if low_count > 0 else "Normal"),
    }


def compute_state_summary(
    db: Session,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes overarching state-level metrics and data for dashboard charts.
    Guarantees state total == sum of districts.
    """
    districts = db.query(District).order_by(District.id).all()
    district_summaries = [compute_district_summary(db, d.id, month=month) for d in districts]

    total_godown_stock = round(sum(d["total_godown_stock_kg"] for d in district_summaries), 2)
    total_shop_stock = round(sum(d["total_shop_stock_kg"] for d in district_summaries), 2)
    total_combined_stock = round(total_godown_stock + total_shop_stock, 2)
    total_distributed = round(sum(d["monthly_distributed_kg"] for d in district_summaries), 2)

    total_beneficiaries = db.query(func.coalesce(func.sum(Shop.beneficiaries_count), 0)).scalar() or 0

    delayed_deliveries_count = db.query(Delivery).filter(Delivery.status == "DELAYED").count()
    pending_deliveries_count = db.query(Delivery).filter(Delivery.status == "PENDING").count()

    total_normal = sum(d["shops_normal"] for d in district_summaries)
    total_low = sum(d["shops_low"] for d in district_summaries)
    total_critical = sum(d["shops_critical"] for d in district_summaries)

    monthly_trend_query = db.query(
        MonthlyDistribution.month_year,
        func.coalesce(func.sum(MonthlyDistribution.distributed_qty_kg), 0.0).label("qty"),
    ).group_by(MonthlyDistribution.month_year).order_by(MonthlyDistribution.month_year).all()

    trend_labels = [row[0] for row in monthly_trend_query]
    trend_values = [round(float(row[1]), 2) for row in monthly_trend_query]

    discrepancies = reconcile_measurements(db)
    discrepancies_count = sum(1 for m in discrepancies if m["discrepancy_detected"])

    return {
        "banner": settings.DEMO_BANNER_TEXT,
        "selected_month": month or "Latest (2026-10)",
        "cards": {
            "total_godown_stock_kg": total_godown_stock,
            "total_godown_stock_mt": round(total_godown_stock / 1000.0, 2),
            "total_shop_stock_kg": total_shop_stock,
            "total_shop_stock_mt": round(total_shop_stock / 1000.0, 2),
            "total_combined_stock_kg": total_combined_stock,
            "total_combined_stock_mt": round(total_combined_stock / 1000.0, 2),
            "total_distributed_kg": total_distributed,
            "total_distributed_mt": round(total_distributed / 1000.0, 2),
            "total_beneficiaries": int(total_beneficiaries),
            "deliveries_delayed": delayed_deliveries_count,
            "deliveries_pending": pending_deliveries_count,
            "attention_flags": total_low + total_critical + discrepancies_count,
            "discrepancies_count": discrepancies_count,
        },
        "stock_status": {
            "normal": total_normal,
            "low": total_low,
            "critical": total_critical,
        },
        "monthly_trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "districts_breakdown": district_summaries,
        "measurements_reconciliation": discrepancies,
    }


def reconcile_measurements(
    db: Session,
    location_type: Optional[str] = None,
    location_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Compares physical inspector measurements with expected stock derived as of the audit date.
    Strictly applies neutral phrasing: 'Verification requested on stock balance'.
    Never names or blames any person or shop.
    """
    query = db.query(Measurement)
    if location_type:
        query = query.filter(Measurement.location_type == location_type.lower())
    if location_id:
        query = query.filter(Measurement.location_id == location_id)

    records = query.order_by(Measurement.measured_date.desc()).all()
    results = []

    for m in records:
        if m.location_type == "godown":
            stk_info = compute_godown_stock(db, m.location_id, as_of=m.measured_date)
            expected_stock = stk_info["expected_stock_kg"]
            location_label = stk_info["godown_name"]
        else:
            stk_info = compute_shop_stock(db, m.location_id, as_of=m.measured_date)
            expected_stock = stk_info["expected_stock_kg"]
            location_label = stk_info["shop_name"]

        measured_stock = float(m.measured_stock_kg)
        diff_kg = round(measured_stock - expected_stock, 2)
        diff_pct = round((abs(diff_kg) / expected_stock) * 100, 2) if expected_stock > 0 else 0.0

        is_discrepant = (diff_pct > (settings.DISCREPANCY_TOLERANCE_PCT * 100))

        results.append({
            "measurement_id": m.id,
            "location_type": m.location_type,
            "location_id": m.location_id,
            "location_label": location_label,
            "measured_date": m.measured_date.strftime("%Y-%m-%d %H:%M"),
            "expected_stock_kg": expected_stock,
            "measured_stock_kg": measured_stock,
            "difference_kg": diff_kg,
            "difference_pct": diff_pct,
            "tolerance_pct": round(settings.DISCREPANCY_TOLERANCE_PCT * 100, 1),
            "discrepancy_detected": is_discrepant,
            "status_label": settings.DISCREPANCY_ALERT_LABEL if is_discrepant else "Verified within normal tolerance",
            "inspector_name": m.inspector_name,
            "remarks": m.remarks,
        })

    return results
