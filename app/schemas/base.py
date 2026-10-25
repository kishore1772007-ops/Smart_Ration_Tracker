"""
Pydantic v2 Schemas for Smart Ration Tracker Base API.
Provides type validation, serialization, and ORM conversion.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


# -------------------------------------------------------------
# DISTRICT SCHEMAS
# -------------------------------------------------------------
class DistrictBase(BaseModel):
    code: str
    name: str
    headquarters: str


class DistrictRead(DistrictBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# GODOWN SCHEMAS
# -------------------------------------------------------------
class GodownBase(BaseModel):
    id: str
    code: str
    name: str
    district_id: int
    capacity_kg: float
    opening_stock_kg: float


class GodownRead(GodownBase):
    model_config = ConfigDict(from_attributes=True)


class GodownDetailRead(GodownRead):
    district: Optional[DistrictRead] = None


# -------------------------------------------------------------
# SHOP SCHEMAS
# -------------------------------------------------------------
class ShopBase(BaseModel):
    id: str
    code: str
    name: str
    district_id: int
    godown_id: str
    beneficiaries_count: int
    opening_stock_kg: float


class ShopRead(ShopBase):
    model_config = ConfigDict(from_attributes=True)


class ShopDetailRead(ShopRead):
    district: Optional[DistrictRead] = None
    godown: Optional[GodownRead] = None


# -------------------------------------------------------------
# STOCK MOVEMENT SCHEMAS
# -------------------------------------------------------------
class StockMovementBase(BaseModel):
    location_type: str = Field(..., description="'godown' or 'shop'")
    location_id: str
    movement_type: str = Field(..., description="RECEIPT, DISPATCH, CONFIRMED_DELIVERY, DISTRIBUTION, ADJUSTMENT")
    quantity_kg: float = Field(..., description="Movement quantity in kg")
    timestamp: datetime
    reference_id: Optional[str] = None
    created_by: str


class StockMovementRead(StockMovementBase):
    id: str
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# COMMODITY SCHEMA
# -------------------------------------------------------------
class CommodityRead(BaseModel):
    id: int
    code: str
    name: str
    unit: str
    buffer_pct: float
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# DELIVERY SCHEMA
# -------------------------------------------------------------
class DeliveryRead(BaseModel):
    id: str
    dispatch_movement_id: str
    from_godown_id: str
    to_shop_id: str
    dispatched_date: datetime
    expected_delivery_date: datetime
    status: str
    dispatched_qty_kg: float
    received_qty_kg: float
    received_date: Optional[datetime] = None
    notes: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
