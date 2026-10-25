"""
Pydantic v2 Schemas for Transaction Requests.
Enforces positive kg quantities and mandatory reasons.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class ReceiptCreate(BaseModel):
    godown_id: str = Field(..., min_length=1, description="Target Godown ID (e.g. GDN-001)")
    quantity_kg: float = Field(..., gt=0, description="Received quantity in kg (must be positive)")
    reference_id: str = Field(..., min_length=3, description="FCI Rake / Consignment reference")
    created_by: str = Field(default="godown_operator", min_length=2)


class DispatchCreate(BaseModel):
    from_godown_id: str = Field(..., min_length=1)
    to_shop_id: str = Field(..., min_length=1)
    quantity_kg: float = Field(..., gt=0, description="Dispatched quantity in kg (must be positive)")
    expected_delivery_date: Optional[datetime] = Field(None, description="Expected arrival timestamp")
    created_by: str = Field(default="godown_dispatcher", min_length=2)
    notes: Optional[str] = Field(None, description="Transport / carrier consignment notes")


class DeliveryConfirm(BaseModel):
    delivery_id: str = Field(..., min_length=1, description="Delivery consignment ID (e.g. DEL-00001)")
    received_qty_kg: float = Field(..., gt=0, description="Physically received quantity in kg (must be positive)")
    created_by: str = Field(default="shop_manager", min_length=2)
    notes: Optional[str] = Field(None, description="Receiving remarks or discrepancy reasons")


class DistributionCreate(BaseModel):
    shop_id: str = Field(..., min_length=1, description="Fair-Price Shop ID")
    quantity_kg: float = Field(..., gt=0, description="Quantity distributed to cardholders (must be positive)")
    beneficiary_households: int = Field(..., gt=0, description="Number of ration card households served")
    reference_id: str = Field(default="", description="EPOS / Sales transaction reference")
    created_by: str = Field(default="epos_machine", min_length=2)


class AdjustmentCreate(BaseModel):
    location_type: Literal["godown", "shop"] = Field(...)
    location_id: str = Field(..., min_length=1)
    quantity_kg: float = Field(..., description="Stock adjustment quantity (can be positive or negative, but non-zero)")
    reason: str = Field(..., min_length=5, description="Mandatory detailed explanation for adjustment")
    created_by: str = Field(default="system_auditor", min_length=2)

    @field_validator("quantity_kg")
    @classmethod
    def check_nonzero(cls, v: float) -> float:
        if v == 0:
            raise ValueError("Adjustment quantity cannot be zero")
        return v

    @field_validator("reason")
    @classmethod
    def check_reason_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Adjustment reason is strictly mandatory")
        return v.strip()


class MeasurementCreate(BaseModel):
    location_type: Literal["godown", "shop"] = Field(...)
    location_id: str = Field(..., min_length=1)
    measured_stock_kg: float = Field(..., ge=0, description="Physically weighed stock in kg")
    inspector_name: str = Field(..., min_length=2)
    remarks: Optional[str] = Field(None, description="Audit observations")
