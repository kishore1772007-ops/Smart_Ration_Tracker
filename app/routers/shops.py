"""
API endpoints for Fair Price Shops.
Supports role-based scoping (e.g. shop managers see only their shop).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Shop, User
from app.schemas import ShopRead
from app.services.auth import get_optional_current_user, check_location_access

router = APIRouter(prefix="/api/shops", tags=["Shops"])


@router.get("", response_model=List[ShopRead])
def get_all_shops(
    district_id: Optional[int] = Query(None, description="Filter by district ID"),
    godown_id: Optional[str] = Query(None, description="Filter by linked godown ID"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve fair price shops.
    Automatically scopes returned shops based on authenticated user's role:
    - shop_manager: Returns only their assigned shop.
    - godown_manager: Returns shops linked to their godown.
    - district_officer: Returns shops in their district.
    - state_admin: Returns all requested shops.
    """
    query = db.query(Shop)

    if current_user:
        if current_user.role == "shop_manager" and current_user.shop_id:
            query = query.filter(Shop.id == current_user.shop_id)
        elif current_user.role == "godown_manager" and current_user.godown_id:
            query = query.filter(Shop.godown_id == current_user.godown_id)
        elif current_user.role == "district_officer" and current_user.district_id:
            query = query.filter(Shop.district_id == current_user.district_id)

    if district_id is not None:
        query = query.filter(Shop.district_id == district_id)
    if godown_id is not None:
        query = query.filter(Shop.godown_id == godown_id)
    return query.order_by(Shop.id).all()


@router.get("/{shop_id}", response_model=ShopRead)
def get_shop_by_id(
    shop_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve details for a specific shop.
    Raises 403 Forbidden if authenticated as a shop_manager for another shop.
    """
    if current_user:
        check_location_access(current_user, "shop", shop_id, db, action="view")

    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shop {shop_id} not found")
    return shop
