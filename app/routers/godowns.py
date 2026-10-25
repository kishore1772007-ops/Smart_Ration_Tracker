"""
API endpoints for Godowns.
Supports role-based scoping (e.g. godown managers see only their godown).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Godown, User
from app.schemas import GodownRead
from app.services.auth import get_optional_current_user, check_location_access

router = APIRouter(prefix="/api/godowns", tags=["Godowns"])


@router.get("", response_model=List[GodownRead])
def get_all_godowns(
    district_id: Optional[int] = Query(None, description="Filter by district ID"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve buffer godowns.
    Automatically scopes returned godowns based on authenticated user's role:
    - godown_manager: Returns only their assigned godown.
    - district_officer: Returns godowns in their district.
    - state_admin: Returns all godowns.
    """
    query = db.query(Godown)

    if current_user:
        if current_user.role == "godown_manager" and current_user.godown_id:
            query = query.filter(Godown.id == current_user.godown_id)
        elif current_user.role == "district_officer" and current_user.district_id:
            query = query.filter(Godown.district_id == current_user.district_id)

    if district_id is not None:
        query = query.filter(Godown.district_id == district_id)
    return query.order_by(Godown.id).all()


@router.get("/{godown_id}", response_model=GodownRead)
def get_godown_by_id(
    godown_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve details for a specific godown.
    Raises 403 Forbidden if authenticated as a godown_manager for another godown.
    """
    if current_user:
        check_location_access(current_user, "godown", godown_id, db, action="view")

    godown = db.query(Godown).filter(Godown.id == godown_id).first()
    if not godown:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Godown {godown_id} not found")
    return godown
