"""
Pydantic Schemas for Prediction and Replenishment Requests & Responses.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class PredictionRunRequest(BaseModel):
    shop_id: Optional[str] = Field(None, description="Specific shop ID (e.g. FPS-0001) or null for all shops")
    lookback_months: int = Field(default=4, ge=2, le=12, description="Rolling average months (default 4)")
    buffer_pct: float = Field(default=10.0, ge=0.0, le=50.0, description="Safety buffer percentage (default 10%)")
    persist: bool = Field(default=True, description="Whether to store the run in predictions table")
