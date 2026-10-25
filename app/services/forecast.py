"""
Demand Forecasting & Replenishment Planning Service.
Implements:
- Average of previous N months (default 4, configurable to 6)
- 10% safety buffer
- Usable derived stock & planned incoming deliveries
- Replenishment recommendation with floor of zero:
    max(0, predicted_demand + 10% buffer - usable_stock - planned_incoming)
- Official label: "Planning recommendation, not an official allocation."
- Persists runs to 'predictions' table with method and inputs.
- Historical back-test reporting Mean Absolute Error (MAE).
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Shop, Delivery, MonthlyDistribution, Prediction
from app.services.stock import compute_shop_stock
from app.services.transactions import log_audit


PLANNING_RECOMMENDATION_LABEL = "Planning recommendation, not an official allocation."


def calculate_replenishment(
    demands: List[float],
    usable_stock: float,
    planned_incoming: float = 0.0,
    buffer_pct: float = 10.0,
) -> Dict[str, Any]:
    """
    Pure algorithmic calculation of demand prediction and replenishment recommendation.
    Formula: max(0, predicted + safety_buffer - usable_stock - planned_incoming)
    """
    if not demands:
        raise ValueError("Historical distribution demands list cannot be empty")

    n = len(demands)
    predicted_demand = round(sum(demands) / n, 2)
    safety_buffer = round(predicted_demand * (buffer_pct / 100.0), 2)
    gross_requirement = round(predicted_demand + safety_buffer, 2)

    total_available = round(usable_stock + planned_incoming, 2)
    raw_replenishment = round(gross_requirement - total_available, 2)
    recommended_replenishment = max(0.0, raw_replenishment)

    return {
        "lookback_months_used": n,
        "historical_demands_kg": demands,
        "predicted_demand_kg": predicted_demand,
        "buffer_pct": buffer_pct,
        "safety_buffer_kg": safety_buffer,
        "usable_stock_kg": round(usable_stock, 2),
        "planned_incoming_kg": round(planned_incoming, 2),
        "gross_requirement_kg": gross_requirement,
        "recommended_replenishment_kg": recommended_replenishment,
        "label": PLANNING_RECOMMENDATION_LABEL,
    }


def run_forecast_for_shop(
    db: Session,
    shop_id: str,
    lookback_months: int = 4,
    buffer_pct: float = 10.0,
    persist: bool = True,
    operator: str = "forecast_engine",
) -> Dict[str, Any]:
    """
    Retrieves shop data, calculates forecast and replenishment, and optionally persists
    the run into the predictions table with complete input audit metadata.
    """
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise ValueError(f"Shop '{shop_id}' not found")

    # 1. Retrieve recent N monthly distributions
    records = db.query(MonthlyDistribution).filter(
        MonthlyDistribution.shop_id == shop_id
    ).order_by(MonthlyDistribution.month_year.desc()).limit(lookback_months).all()

    if not records:
        raise ValueError(f"No monthly distribution records found for shop '{shop_id}'")

    # Sort chronologically
    records = sorted(records, key=lambda r: r.month_year)
    demands = [float(r.distributed_qty_kg) for r in records]

    # 2. Derived usable stock
    stock_info = compute_shop_stock(db, shop_id)
    usable_stock = stock_info["expected_stock_kg"]

    # 3. Planned incoming deliveries (PENDING or DELAYED)
    pending_deliveries = db.query(Delivery).filter(
        Delivery.to_shop_id == shop_id,
        Delivery.status.in_(["PENDING", "DELAYED"]),
    ).all()
    planned_incoming = sum(float(d.dispatched_qty_kg) for d in pending_deliveries)

    # 4. Compute forecast
    result = calculate_replenishment(
        demands=demands,
        usable_stock=usable_stock,
        planned_incoming=planned_incoming,
        buffer_pct=buffer_pct,
    )

    now = datetime.now(timezone.utc)
    inputs_dict = {
        "shop_id": shop_id,
        "shop_name": shop.name,
        "lookback_months": lookback_months,
        "months_evaluated": [r.month_year for r in records],
        "demands": demands,
        "buffer_pct": buffer_pct,
        "usable_stock_kg": usable_stock,
        "planned_incoming_kg": planned_incoming,
        "pending_delivery_ids": [d.id for d in pending_deliveries],
    }

    prediction_id = None
    if persist:
        pred_record = Prediction(
            shop_id=shop_id,
            run_date=now,
            method="rolling_average",
            lookback_months=len(demands),
            predicted_demand_kg=result["predicted_demand_kg"],
            safety_buffer_kg=result["safety_buffer_kg"],
            usable_stock_kg=result["usable_stock_kg"],
            planned_incoming_kg=result["planned_incoming_kg"],
            recommended_replenishment_kg=result["recommended_replenishment_kg"],
            inputs_json=json.dumps(inputs_dict),
            created_at=now,
        )
        db.add(pred_record)
        db.commit()
        db.refresh(pred_record)
        prediction_id = pred_record.id

        # Write to audit_logs
        log_audit(
            db=db,
            username=operator,
            action="RUN_DEMAND_FORECAST",
            entity_type="SHOP",
            entity_id=shop_id,
            details=f"Ran {lookback_months}-mo demand forecast for {shop_id}. Demand: {result['predicted_demand_kg']} kg, Buffer: {result['safety_buffer_kg']} kg, Replenishment: {result['recommended_replenishment_kg']} kg. (Prediction #{prediction_id}).",
        )

    result["prediction_id"] = prediction_id
    result["shop_id"] = shop_id
    result["shop_name"] = shop.name
    return result


def run_forecast_for_all_shops(
    db: Session,
    lookback_months: int = 4,
    buffer_pct: float = 10.0,
    persist: bool = True,
    operator: str = "batch_forecast_bot",
) -> List[Dict[str, Any]]:
    """Runs demand prediction batch for all 50 fair-price shops."""
    shops = db.query(Shop).order_by(Shop.id).all()
    results = []
    for s in shops:
        res = run_forecast_for_shop(
            db=db,
            shop_id=s.id,
            lookback_months=lookback_months,
            buffer_pct=buffer_pct,
            persist=persist,
            operator=operator,
        )
        results.append(res)
    return results


def backtest_forecast_accuracy(
    db: Session,
    target_month: str = "2026-10",
    lookback_months: int = 4,
) -> Dict[str, Any]:
    """
    Historical Back-Test:
    Evaluates forecast model against actual mock distributions of the last month (2026-10)
    using the preceding N months (e.g., June, July, August, September 2026).
    Computes:
    - Mean Absolute Error (MAE)
    - Mean Absolute Percentage Error (MAPE)
    """
    shops = db.query(Shop).order_by(Shop.id).all()

    absolute_errors = []
    percentage_errors = []
    shop_comparisons = []

    for s in shops:
        # Actual distribution in target month
        actual_dist_record = db.query(MonthlyDistribution).filter(
            MonthlyDistribution.shop_id == s.id,
            MonthlyDistribution.month_year == target_month,
        ).first()

        if not actual_dist_record:
            continue

        actual_kg = float(actual_dist_record.distributed_qty_kg)

        # Preceding N months before target_month
        prior_records = db.query(MonthlyDistribution).filter(
            MonthlyDistribution.shop_id == s.id,
            MonthlyDistribution.month_year < target_month,
        ).order_by(MonthlyDistribution.month_year.desc()).limit(lookback_months).all()

        if len(prior_records) < lookback_months:
            continue

        prior_demands = [float(r.distributed_qty_kg) for r in prior_records]
        predicted_kg = round(sum(prior_demands) / len(prior_demands), 2)

        error_kg = round(abs(predicted_kg - actual_kg), 2)
        error_pct = round((error_kg / actual_kg) * 100, 2) if actual_kg > 0 else 0.0

        absolute_errors.append(error_kg)
        percentage_errors.append(error_pct)

        shop_comparisons.append({
            "shop_id": s.id,
            "shop_name": s.name,
            "predicted_kg": predicted_kg,
            "actual_kg": actual_kg,
            "abs_error_kg": error_kg,
            "abs_error_pct": error_pct,
        })

    mae = round(sum(absolute_errors) / len(absolute_errors), 2) if absolute_errors else 0.0
    mape = round(sum(percentage_errors) / len(percentage_errors), 2) if percentage_errors else 0.0

    return {
        "target_month": target_month,
        "lookback_months": lookback_months,
        "shops_evaluated": len(absolute_errors),
        "mean_absolute_error_kg": mae,
        "mean_absolute_percentage_error_pct": mape,
        "evaluation_summary": f"Back-test on {target_month} across {len(absolute_errors)} shops achieved an MAE of {mae:,.2f} kg ({mape:.1f}% error).",
        "sample_shop_results": shop_comparisons[:10],
    }
