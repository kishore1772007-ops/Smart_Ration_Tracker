"""
Pydantic Schemas for Alert Engine & Alert Actions.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class AlertStatusUpdate(BaseModel):
    status: Literal["OPEN", "UNDER_VERIFICATION", "RESOLVED"] = Field(...)
    verification_notes: str = Field(..., min_length=5, description="Mandatory verification notes explaining action taken")
    operator: str = Field(default="system_operator", min_length=2)

    @field_validator("verification_notes")
    @classmethod
    def notes_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Verification notes are strictly required")
        return v.strip()


class AlertScanResponse(BaseModel):
    new_alerts_created: int
    open_alerts_count: int
    alerts_by_type: dict
