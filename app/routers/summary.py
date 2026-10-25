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
