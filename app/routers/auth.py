"""
Authentication Endpoints & Web Views.
Provides:
- POST /api/auth/login (JWT token generation & HTTPOnly cookie session)
- POST /api/auth/logout (Session termination)
- GET /api/auth/me (Current user profile and jurisdiction)
- GET /login (Web login interface with 1-click demo role switches)
- GET /logout (Web logout redirect)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.entities import User, AuditLog
from app.schemas.auth import LoginRequest, TokenResponse, UserProfile
from app.services.auth import (
    verify_password,
    create_access_token,
    get_current_user,
    get_optional_current_user,
)

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")


@router.post("/api/auth/login", response_model=TokenResponse)
def api_login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Authenticates a user via username and password.
    Returns a signed JWT bearer token and attaches an HTTPOnly cookie.
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT token
    token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "district_id": user.district_id,
            "godown_id": user.godown_id,
            "shop_id": user.shop_id,
        }
    )

    # Set HTTPOnly session cookie for seamless web browsing
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )

    # Record login in audit log
    audit = AuditLog(
        user_id=user.id,
        username=user.username,
        action="LOGIN",
        entity_type="user",
        entity_id=str(user.id),
        details=f"User '{user.username}' logged in successfully with role '{user.role}'.",
    )
    db.add(audit)
    db.commit()

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserProfile.model_validate(user),
    )


@router.post("/api/auth/logout")
def api_logout(response: Response):
    """Terminates session and clears access token cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}


@router.get("/api/auth/me", response_model=UserProfile)
def api_get_current_user(current_user: User = Depends(get_current_user)):
    """Returns currently authenticated user profile and jurisdiction."""
    return UserProfile.model_validate(current_user)


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders the login page with pre-configured quick demo role selections."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "banner_text": settings.DEMO_BANNER_TEXT,
            "active_tab": "login",
            "current_user": current_user,
        },
    )


@router.get("/logout")
def logout_redirect(response: Response):
    """Redirects web users to login page and clears cookie."""
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key="access_token")
    return redirect
