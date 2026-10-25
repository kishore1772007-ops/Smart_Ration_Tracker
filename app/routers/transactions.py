"""
API endpoints for Stock Mutations & Operational Transactions.
Protected by Role-Based Access Control and strict location scoping.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Delivery, User
from app.schemas.transactions import (
    ReceiptCreate,
    DispatchCreate,
    DeliveryConfirm,
    DistributionCreate,
    AdjustmentCreate,
    MeasurementCreate,
)
from app.services.transactions import (
    record_receipt,
    create_dispatch,
    confirm_delivery,
    record_distribution,
    record_adjustment,
    record_measurement,
)
from app.services.auth import require_roles, check_location_access

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


@router.post("/receipt", status_code=status.HTTP_201_CREATED)
def post_receipt(
    payload: ReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "godown_manager")),
):
    """
    Record an incoming rice receipt into a Godown from FCI / central supplier.
    Authorized: state_admin, godown_manager (assigned to the godown).
    """
    check_location_access(current_user, "godown", payload.godown_id, db, action="record receipt for")
    try:
        return record_receipt(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/dispatch", status_code=status.HTTP_201_CREATED)
def post_dispatch(
    payload: DispatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "godown_manager")),
):
    """
    Dispatch rice from Godown to Fair-Price Shop.
    Enforces positive kg and prevents over-dispatch. Creates a pending delivery consignment.
    Authorized: state_admin, godown_manager (assigned to the source godown).
    """
    check_location_access(current_user, "godown", payload.from_godown_id, db, action="dispatch from")
    try:
        return create_dispatch(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/confirm-delivery")
def post_confirm_delivery(
    payload: DeliveryConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "shop_manager", "godown_manager")),
):
    """
    Confirm arrival of a delivery consignment at a Fair-Price Shop.
    Records actual received quantity in the shop ledger.
    Authorized: state_admin, or shop_manager (assigned strictly to the receiving shop).
    """
    delivery = db.query(Delivery).filter(Delivery.id == payload.delivery_id).first()
    if delivery:
        check_location_access(current_user, "shop", delivery.to_shop_id, db, action="confirm delivery for")

    try:
        return confirm_delivery(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/distribution", status_code=status.HTTP_201_CREATED)
def post_distribution(
    payload: DistributionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "shop_manager", "data_entry_officer")),
):
    """
    Record rice distribution from Fair-Price Shop to cardholders via POS.
    Enforces positive kg and prevents over-distribution beyond available stock.
    Authorized: state_admin, or shop_manager (strictly for their assigned shop).
    """
    check_location_access(current_user, "shop", payload.shop_id, db, action="record distribution for")
    try:
        return record_distribution(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/adjustment", status_code=status.HTTP_201_CREATED)
def post_adjustment(
    payload: AdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "district_officer", "godown_manager", "shop_manager")),
):
    """
    Apply a stock adjustment to Godown or Shop.
    Mandatory reason required; deductions cannot yield negative balances.
    Authorized: state_admin, district_officer, or location manager for their location.
    """
    check_location_access(current_user, payload.location_type, payload.location_id, db, action="apply adjustment to")
    try:
        return record_adjustment(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/measurement", status_code=status.HTTP_201_CREATED)
def post_measurement(
    payload: MeasurementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("state_admin", "stock_inspector")),
):
    """
    Record an official physical inspection stock audit by a Stock Inspector.
    Authorized: state_admin, stock_inspector.
    """
    try:
        return record_measurement(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
