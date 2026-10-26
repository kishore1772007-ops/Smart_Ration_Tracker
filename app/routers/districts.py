"""
API endpoints for Districts.
Supports role-based scoping (e.g. district officers see only their district).
"""

from typing import List, Optional, Union, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import District, User
from app.schemas import DistrictRead
from app.services.stock import compute_district_summary
from app.services.auth import get_optional_current_user, check_location_access

router = APIRouter(prefix="/api/districts", tags=["Districts"])


@router.get("")
def get_all_districts(
    include_summary: bool = Query(False, description="Include live stock and distribution metrics"),
    month: Optional[str] = Query(None, description="Month filter (YYYY-MM)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve districts in Tamil Nadu, optionally with live stock summaries.
    Automatically scopes returned districts if user is a district_officer.
    """
    query = db.query(District)
    if current_user and current_user.role == "district_officer" and current_user.district_id:
        query = query.filter(District.id == current_user.district_id)

    districts = query.order_by(District.id).all()
    if not include_summary:
        return [DistrictRead.model_validate(d) for d in districts]
    return [compute_district_summary(db, d.id, month=month) for d in districts]


@router.get("/geojson")
def get_districts_geojson():
    """Returns Tamil Nadu 38 districts GeoJSON FeatureCollection for interactive Leaflet map."""
    import os
    import json
    geojson_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "tamil_nadu_districts.geojson")
    if os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Tamil Nadu GeoJSON map dataset not found")


@router.get("/{district_id}")
def get_district_by_id(
    district_id: int,
    include_summary: bool = Query(False, description="Include live stock and distribution metrics"),
    month: Optional[str] = Query(None, description="Month filter (YYYY-MM)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Retrieve details for a specific district.
    Raises 403 Forbidden if authenticated as a district officer for another district.
    """
    if current_user:
        check_location_access(current_user, "district", district_id, db, action="view")

    district = db.query(District).filter(District.id == district_id).first()
    if not district:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"District {district_id} not found")
    if include_summary:
        return compute_district_summary(db, district_id, month=month)
    return DistrictRead.model_validate(district)
