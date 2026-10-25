"""
Pydantic Schemas for Authentication and Role Profiles.
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class LoginRequest(BaseModel):
    username: str = Field(..., description="Unique username")
    password: str = Field(..., description="Plaintext password")


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    full_name: str
    district_id: Optional[int] = None
    godown_id: Optional[str] = None
    shop_id: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile
