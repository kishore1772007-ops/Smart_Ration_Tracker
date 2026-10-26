"""
Smart Ration Tracker - FastAPI Application Entry Point.
Tamil Nadu Public Distribution System Rice Stock Monitoring & Planning Dashboard.
Permanent Banner: 'Demo Dataset — Not Official Government Data'
"""

import json
import os
from typing import Optional
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services.stock import (
    compute_state_summary,
    get_godown_detail,
    get_shop_detail,
    get_district_detail,
)
from app.models import District, Godown, Shop, Delivery, AuditLog, Alert, User
from app.services.reports import generate_monthly_report
from app.services.alert_engine import scan_and_generate_alerts
from app.services.auth import get_optional_current_user, check_location_access
from app.routers import (
    districts_router,
    godowns_router,
    shops_router,
    movements_router,
    summary_router,
    transactions_router,
    reports_router,
    predictions_router,
    alerts_router,
    auth_router,
    ingest_router,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(
    title=settings.APP_NAME,
    description="Tamil Nadu PDS Rice Stock Monitoring, Planning & Replenishment Dashboard. (Demo Dataset — Not Official Government Data)",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Jinja2 Templates
templates_dir = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=templates_dir)

def filter_format_kg(val):
    try:
        if val is None:
            return "0.00 kg"
        return f"{float(val):,.2f} kg"
    except (ValueError, TypeError):
        return f"{val} kg"

def filter_format_number(val):
    try:
        if val is None:
            return "0.00"
        return f"{float(val):,.2f}"
    except (ValueError, TypeError):
        return str(val)

def filter_format_int(val):
    try:
        if val is None:
            return "0"
        return f"{int(val):,}"
    except (ValueError, TypeError):
        return str(val)

templates.env.filters["format_kg"] = filter_format_kg
templates.env.filters["format_number"] = filter_format_number
templates.env.filters["format_int"] = filter_format_int

# Include API Routers
app.include_router(districts_router)
app.include_router(godowns_router)
app.include_router(shops_router)
app.include_router(movements_router)
app.include_router(summary_router)
app.include_router(transactions_router)
app.include_router(reports_router)
app.include_router(predictions_router)
app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(ingest_router)


# -------------------------------------------------------------
# HTML PAGE ROUTES
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def get_dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders the Statewide Stock & Operations Dashboard page."""
    summary_data = compute_state_summary(db, month="2026-10")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "dashboard",
            "summary": summary_data,
            "summary_json": json.dumps(summary_data),
            "current_user": current_user,
        },
    )


@app.get("/alerts", response_class=HTMLResponse, tags=["Alerts"])
def get_alerts_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders the Alert Centre page."""
    # Ensure baseline alerts exist
    if db.query(Alert).count() == 0:
        scan_and_generate_alerts(db)

    query = db.query(Alert)
    if current_user:
        if current_user.role == "shop_manager" and current_user.shop_id:
            query = query.filter(Alert.location_type == "shop", Alert.location_id == current_user.shop_id)
        elif current_user.role == "godown_manager" and current_user.godown_id:
            query = query.filter(Alert.location_id == current_user.godown_id)

    alerts = query.order_by(Alert.timestamp.desc()).all()
    stats = {
        "open": sum(1 for a in alerts if a.status == "OPEN"),
        "under_verification": sum(1 for a in alerts if a.status == "UNDER_VERIFICATION"),
        "resolved": sum(1 for a in alerts if a.status == "RESOLVED"),
        "total": len(alerts),
    }

    return templates.TemplateResponse(
        request,
        "alerts.html",
        {
            "active_page": "alerts",
            "alerts": alerts,
            "stats": stats,
            "current_user": current_user,
        },
    )


@app.get("/reports", response_class=HTMLResponse, tags=["Reports"])
def get_reports_page(
    request: Request,
    month: Optional[str] = None,
    district_id: Optional[int] = None,
    shop_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders the Monthly Reports and MoM comparison page."""
    districts = db.query(District).order_by(District.id).all()
    
    # Scoping for reports page
    if current_user:
        if current_user.role == "shop_manager" and current_user.shop_id:
            shop_id = current_user.shop_id
        elif current_user.role == "district_officer" and current_user.district_id:
            district_id = current_user.district_id
            districts = [d for d in districts if d.id == current_user.district_id]

    report_data = generate_monthly_report(db, month=month, district_id=district_id, shop_id=shop_id)
    return templates.TemplateResponse(
        request,
        "reports.html",
        {
            "active_page": "reports",
            "report": report_data,
            "districts": districts,
            "current_user": current_user,
        },
    )


@app.get("/transactions", response_class=HTMLResponse, tags=["Operations"])
def get_transactions_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders the Operations & Transactions submission page."""
    godowns = db.query(Godown).order_by(Godown.id).all()
    shops = db.query(Shop).order_by(Shop.id).all()
    pending = db.query(Delivery).filter(Delivery.status.in_(["PENDING", "DELAYED"])).order_by(Delivery.dispatched_date.desc()).all()
    recent_audits = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(15).all()

    return templates.TemplateResponse(
        request,
        "transactions.html",
        {
            "active_page": "transactions",
            "godowns": godowns,
            "shops": shops,
            "pending_deliveries": pending,
            "recent_audits": recent_audits,
            "current_user": current_user,
        },
    )


@app.get("/districts/{district_id}", response_class=HTMLResponse, tags=["Detail Pages"])
def get_district_page(
    district_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders District detail page with breadcrumbs and linked godowns & shops."""
    if current_user:
        check_location_access(current_user, "district", district_id, db, action="view")

    try:
        detail_data = get_district_detail(db, district_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return templates.TemplateResponse(
        request,
        "district_detail.html",
        {
            "active_page": "dashboard",
            "detail": detail_data,
            "current_user": current_user,
        },
    )


@app.get("/godowns/{godown_id}", response_class=HTMLResponse, tags=["Detail Pages"])
def get_godown_page(
    godown_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders Godown detail page: opening, received, dispatched, expected closing, receipts & dispatches."""
    if current_user:
        check_location_access(current_user, "godown", godown_id, db, action="view")

    try:
        detail_data = get_godown_detail(db, godown_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return templates.TemplateResponse(
        request,
        "godown_detail.html",
        {
            "active_page": "dashboard",
            "detail": detail_data,
            "current_user": current_user,
        },
    )


@app.get("/shops/{shop_id}", response_class=HTMLResponse, tags=["Detail Pages"])
def get_shop_page(
    shop_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """Renders Shop detail page: opening, received, distributed, expected closing, monthly chart, prediction, alerts."""
    if current_user:
        check_location_access(current_user, "shop", shop_id, db, action="view")

    try:
        detail_data = get_shop_detail(db, shop_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return templates.TemplateResponse(
        request,
        "shop_detail.html",
        {
            "active_page": "dashboard",
            "detail": detail_data,
            "current_user": current_user,
        },
    )


@app.get("/api/health", tags=["Health"])
def health_check():
    """System health check and demo dataset notice."""
    return {
        "status": "healthy",
        "system": settings.APP_NAME,
        "banner": settings.DEMO_BANNER_TEXT,
    }
