"""
API endpoint for high-level State Stock and Operations Summary.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.stock import compute_state_summary, reconcile_measurements

router = APIRouter(prefix="/api/summary", tags=["Summary"])


@router.get("")
def get_state_summary(
    month: Optional[str] = Query(None, description="Filter by YYYY-MM (e.g. 2026-10)"),
    db: Session = Depends(get_db),
):
    """
    Returns state-wide aggregated rice stock, distributions, delivery statuses,
    alerts, and Chart.js dataset formats.
    """
    return compute_state_summary(db, month=month)


@router.get("/reconciliation")
def get_reconciliation_summary(
    location_type: Optional[str] = Query(None, description="'godown' or 'shop'"),
    location_id: Optional[str] = Query(None, description="Location ID"),
    db: Session = Depends(get_db),
):
    """
    Returns physical inspection stock audit comparison vs derived stock.
    Flags discrepancies (>2% tolerance) with neutral 'verification requested' status.
    """
    return reconcile_measurements(db, location_type=location_type, location_id=location_id)


# -------------------------------------------------------------
# 4-LEVEL HIERARCHICAL DRILL-DOWN ENDPOINTS
# -------------------------------------------------------------
@router.get("/live")
def get_live_state_dashboard(
    month: Optional[str] = Query("2026-10"),
    db: Session = Depends(get_db),
):
    """Returns Level 1 State Live Monitoring Dashboard."""
    from app.services.live_dashboard_service import get_state_live_dashboard
    return get_state_live_dashboard(db, month=month)


@router.get("/district/{district_id}")
def get_live_district_dashboard(
    district_id: int,
    db: Session = Depends(get_db),
):
    """Returns Level 2 District Live Monitoring Dashboard with Godowns & FPS Shops."""
    from app.services.live_dashboard_service import get_district_live_dashboard
    try:
        return get_district_live_dashboard(db, district_id=district_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/godown/{godown_id}")
def get_live_godown_dashboard(
    godown_id: str,
    db: Session = Depends(get_db),
):
    """Returns Level 3 Godown Granary Overview with linked supply lines."""
    from app.services.live_dashboard_service import get_godown_live_dashboard
    try:
        return get_godown_live_dashboard(db, godown_id=godown_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/shop/{shop_id}")
def get_live_shop_dashboard(
    shop_id: str,
    db: Session = Depends(get_db),
):
    """Returns Level 4 Fair Price Shop Detail with multi-commodity gauges and predictions."""
    from app.services.live_dashboard_service import get_shop_live_dashboard
    try:
        return get_shop_live_dashboard(db, shop_id=shop_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))
