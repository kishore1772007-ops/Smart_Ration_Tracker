"""
API endpoints for Demand Forecasting and Replenishment Recommendations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Prediction, User
from app.schemas.predictions import PredictionRunRequest
from app.services.forecast import (
    run_forecast_for_shop,
    run_forecast_for_all_shops,
    backtest_forecast_accuracy,
    PLANNING_RECOMMENDATION_LABEL,
)
from app.services.auth import require_roles, check_location_access

router = APIRouter(prefix="/api/predictions", tags=["Predictions & Forecasting"])


@router.post("/run", status_code=status.HTTP_201_CREATED)
def post_run_prediction(
    payload: PredictionRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "district_officer", "shop_manager")),
):
    """
    Executes demand forecast and replenishment recommendation.
    Stores the run in 'predictions' table with method and inputs.
    Labels result: 'Planning recommendation, not an official allocation.'
    """
    if payload.shop_id:
        check_location_access(current_user, "shop", payload.shop_id, db, action="run forecast for")
    elif current_user.role == "shop_manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shop Managers cannot trigger batch forecasts across all shops.",
        )
    try:
        if payload.shop_id:
            result = run_forecast_for_shop(
                db=db,
                shop_id=payload.shop_id,
                lookback_months=payload.lookback_months,
                buffer_pct=payload.buffer_pct,
                persist=payload.persist,
            )
            return result
        else:
            results = run_forecast_for_all_shops(
                db=db,
                lookback_months=payload.lookback_months,
                buffer_pct=payload.buffer_pct,
                persist=payload.persist,
            )
            total_replenishment = round(sum(r["recommended_replenishment_kg"] for r in results), 2)
            total_predicted_demand = round(sum(r["predicted_demand_kg"] for r in results), 2)
            return {
                "status": "success",
                "label": PLANNING_RECOMMENDATION_LABEL,
                "shops_forecasted": len(results),
                "total_predicted_demand_kg": total_predicted_demand,
                "total_recommended_replenishment_kg": total_replenishment,
                "predictions": results,
            }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/backtest")
def get_backtest_accuracy(
    target_month: str = Query("2026-10", description="Month to evaluate against actual distribution (YYYY-MM)"),
    lookback_months: int = Query(4, ge=2, le=6, description="Prior months lookback window"),
    db: Session = Depends(get_db),
):
    """
    Historical back-test evaluating forecast model accuracy on mock data.
    Reports Mean Absolute Error (MAE) and Mean Absolute Percentage Error (MAPE).
    """
    return backtest_forecast_accuracy(
        db=db,
        target_month=target_month,
        lookback_months=lookback_months,
    )


@router.get("/latest/{shop_id}")
def get_latest_prediction(
    shop_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieves the most recent persisted prediction for a shop.
    """
    pred = db.query(Prediction).filter(
        Prediction.shop_id == shop_id
    ).order_by(Prediction.created_at.desc()).first()

    if not pred:
        # Run live on-demand if no persisted run exists
        return run_forecast_for_shop(db, shop_id, lookback_months=4, persist=False)

    return {
        "prediction_id": pred.id,
        "shop_id": pred.shop_id,
        "run_date": pred.run_date.strftime("%Y-%m-%d %H:%M"),
        "method": pred.method,
        "lookback_months": pred.lookback_months,
        "predicted_demand_kg": pred.predicted_demand_kg,
        "safety_buffer_kg": pred.safety_buffer_kg,
        "usable_stock_kg": pred.usable_stock_kg,
        "planned_incoming_kg": pred.planned_incoming_kg,
        "recommended_replenishment_kg": pred.recommended_replenishment_kg,
        "label": PLANNING_RECOMMENDATION_LABEL,
    }
