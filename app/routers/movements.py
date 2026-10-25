"""
API endpoints for Stock Movements ledger.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StockMovement
from app.schemas import StockMovementRead

router = APIRouter(prefix="/api/movements", tags=["Movements"])


@router.get("", response_model=List[StockMovementRead])
def get_all_movements(
    location_type: Optional[str] = Query(None, description="Filter by 'godown' or 'shop'"),
    location_id: Optional[str] = Query(None, description="Filter by specific location ID (e.g. GDN-001, FPS-0001)"),
    movement_type: Optional[str] = Query(None, description="Filter by movement type (RECEIPT, DISPATCH, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Records offset"),
    db: Session = Depends(get_db),
):
    """Retrieve stock movement history from immutable ledger."""
    query = db.query(StockMovement)
    if location_type:
        query = query.filter(StockMovement.location_type == location_type.lower())
    if location_id:
        query = query.filter(StockMovement.location_id == location_id)
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type.upper())
    
    return query.order_by(StockMovement.timestamp.desc()).offset(offset).limit(limit).all()


@router.get("/{movement_id}", response_model=StockMovementRead)
def get_movement_by_id(movement_id: str, db: Session = Depends(get_db)):
    """Retrieve a single movement by its identifier."""
    movement = db.query(StockMovement).filter(StockMovement.id == movement_id).first()
    if not movement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Movement {movement_id} not found")
    return movement
