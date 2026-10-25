"""
API endpoints for Monthly Reports and CSV Data Export.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.reports import generate_monthly_report, export_monthly_report_csv

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/monthly")
def get_monthly_report(
    month: Optional[str] = Query(None, description="Month filter (YYYY-MM, e.g. 2026-10)"),
    district_id: Optional[int] = Query(None, description="Filter by district ID"),
    shop_id: Optional[str] = Query(None, description="Filter by shop ID (e.g. FPS-0001)"),
    format: Optional[str] = Query("json", description="Output format: 'json' or 'csv'"),
    db: Session = Depends(get_db),
):
    """
    Returns monthly stock report with received, distributed, closing stock,
    and month-over-month comparisons by district and shop.
    Supports '?format=csv' download.
    """
    report_data = generate_monthly_report(
        db=db,
        month=month,
        district_id=district_id,
        shop_id=shop_id,
    )

    if format and format.lower() == "csv":
        csv_content = export_monthly_report_csv(report_data)
        filename = f"monthly_pds_report_{report_data['report_month']}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache",
            },
        )

    return report_data
