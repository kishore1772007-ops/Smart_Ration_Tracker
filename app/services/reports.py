"""
Monthly Reporting & CSV Export Service.
Computes received, distributed, closing stock, month-over-month comparisons,
and formats data for interactive tables and CSV export.
"""

import csv
import io
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    District,
    Godown,
    Shop,
    StockMovement,
    Delivery,
    MonthlyDistribution,
)
from app.services.stock import compute_shop_stock


def get_previous_month(month_str: str) -> Optional[str]:
    """Given '2026-10', returns '2026-09'. Returns None if invalid."""
    try:
        dt = datetime.strptime(month_str, "%Y-%m")
        if dt.month == 1:
            prev_dt = datetime(dt.year - 1, 12, 1)
        else:
            prev_dt = datetime(dt.year, dt.month - 1, 1)
        return prev_dt.strftime("%Y-%m")
    except Exception:
        return None


def get_month_date_range(month_str: str):
    """Returns (start_datetime, end_datetime) for a YYYY-MM string."""
    dt = datetime.strptime(month_str, "%Y-%m")
    start = datetime(dt.year, dt.month, 1, 0, 0, 0)
    if dt.month == 12:
        end = datetime(dt.year + 1, 1, 1, 0, 0, 0)
    else:
        end = datetime(dt.year, dt.month + 1, 1, 0, 0, 0)
    return start, end


def generate_monthly_report(
    db: Session,
    month: Optional[str] = None,
    district_id: Optional[int] = None,
    shop_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates monthly PDS rice stock and distribution report.
    Includes:
    - Received, Distributed, Derived Closing Stock
    - Month-to-Month (MoM) distribution comparison
    - District summary rollup table
    - Shop detailed table
    """
    target_month = month or "2026-10"
    prev_month = get_previous_month(target_month)
    month_start, month_end = get_month_date_range(target_month)

    # 1. Base query for shops
    shop_query = db.query(Shop)
    if district_id:
        shop_query = shop_query.filter(Shop.district_id == district_id)
    if shop_id:
        shop_query = shop_query.filter(Shop.id == shop_id)

    shops = shop_query.order_by(Shop.id).all()
    districts = db.query(District).order_by(District.id).all()
    dist_map = {d.id: d.name for d in districts}

    # 2. Compute per-shop monthly metrics
    shop_rows: List[Dict[str, Any]] = []

    for s in shops:
        # Received in this month: sum of CONFIRMED_DELIVERY movements in [month_start, month_end)
        rcv_query = db.query(
            func.coalesce(func.sum(StockMovement.quantity_kg), 0.0)
        ).filter(
            StockMovement.location_type == "shop",
            StockMovement.location_id == s.id,
            StockMovement.movement_type == "CONFIRMED_DELIVERY",
            StockMovement.timestamp >= month_start,
            StockMovement.timestamp < month_end,
        ).scalar()
        received_kg = round(float(rcv_query or 0.0), 2)

        # Distributed in this month: from MonthlyDistribution or movements
        dist_query = db.query(
            func.coalesce(func.sum(MonthlyDistribution.distributed_qty_kg), 0.0)
        ).filter(
            MonthlyDistribution.shop_id == s.id,
            MonthlyDistribution.month_year == target_month,
        ).scalar()
        distributed_kg = round(float(dist_query or 0.0), 2)

        # Distributed in previous month for MoM calculation
        prev_dist_query = db.query(
            func.coalesce(func.sum(MonthlyDistribution.distributed_qty_kg), 0.0)
        ).filter(
            MonthlyDistribution.shop_id == s.id,
            MonthlyDistribution.month_year == prev_month,
        ).scalar() if prev_month else 0.0
        prev_dist_kg = round(float(prev_dist_query or 0.0), 2)

        # MoM comparison
        mom_diff_kg = round(distributed_kg - prev_dist_kg, 2)
        if prev_dist_kg > 0:
            mom_pct = round(((distributed_kg - prev_dist_kg) / prev_dist_kg) * 100, 1)
        else:
            mom_pct = 0.0

        # Derived closing stock as of month_end
        closing_stock_info = compute_shop_stock(db, s.id, as_of=month_end)
        closing_stock_kg = closing_stock_info["expected_stock_kg"]
        status = closing_stock_info["status"]

        # Opening stock at the beginning of the month: closing - received + distributed
        opening_calc = round(closing_stock_kg - received_kg + distributed_kg, 2)

        shop_rows.append({
            "shop_id": s.id,
            "shop_code": s.code,
            "shop_name": s.name,
            "district_id": s.district_id,
            "district_name": dist_map.get(s.district_id, f"District {s.district_id}"),
            "godown_id": s.godown_id,
            "beneficiaries_count": s.beneficiaries_count,
            "opening_stock_kg": opening_calc,
            "received_kg": received_kg,
            "distributed_kg": distributed_kg,
            "prev_distributed_kg": prev_dist_kg,
            "mom_diff_kg": mom_diff_kg,
            "mom_pct": mom_pct,
            "closing_stock_kg": closing_stock_kg,
            "status": status,
        })

    # 3. Aggregate District Comparison Table
    district_summaries: List[Dict[str, Any]] = []
    for d in districts:
        if district_id and d.id != district_id:
            continue

        d_shops = [r for r in shop_rows if r["district_id"] == d.id]
        if not d_shops:
            continue

        d_rcv = round(sum(r["received_kg"] for r in d_shops), 2)
        d_dist = round(sum(r["distributed_kg"] for r in d_shops), 2)
        d_prev = round(sum(r["prev_distributed_kg"] for r in d_shops), 2)
        d_close = round(sum(r["closing_stock_kg"] for r in d_shops), 2)

        d_mom_diff = round(d_dist - d_prev, 2)
        d_mom_pct = round(((d_dist - d_prev) / d_prev) * 100, 1) if d_prev > 0 else 0.0

        district_summaries.append({
            "district_id": d.id,
            "district_code": d.code,
            "district_name": d.name,
            "shops_count": len(d_shops),
            "total_received_kg": d_rcv,
            "total_distributed_kg": d_dist,
            "prev_distributed_kg": d_prev,
            "mom_diff_kg": d_mom_diff,
            "mom_pct": d_mom_pct,
            "closing_stock_kg": d_close,
        })

    # 4. Total Scope Rollups
    total_received = round(sum(r["received_kg"] for r in shop_rows), 2)
    total_distributed = round(sum(r["distributed_kg"] for r in shop_rows), 2)
    total_prev_distributed = round(sum(r["prev_distributed_kg"] for r in shop_rows), 2)
    total_closing = round(sum(r["closing_stock_kg"] for r in shop_rows), 2)
    scope_mom_diff = round(total_distributed - total_prev_distributed, 2)
    scope_mom_pct = round(((total_distributed - total_prev_distributed) / total_prev_distributed) * 100, 1) if total_prev_distributed > 0 else 0.0

    return {
        "report_month": target_month,
        "previous_month": prev_month or "None",
        "filter_district_id": district_id,
        "filter_shop_id": shop_id,
        "totals": {
            "total_received_kg": total_received,
            "total_distributed_kg": total_distributed,
            "total_closing_stock_kg": total_closing,
            "prev_month_distributed_kg": total_prev_distributed,
            "mom_diff_kg": scope_mom_diff,
            "mom_pct": scope_mom_pct,
            "shops_count": len(shop_rows),
        },
        "districts_summary": district_summaries,
        "shops_detail": shop_rows,
    }


def export_monthly_report_csv(report_data: Dict[str, Any]) -> str:
    """
    Serializes report into RFC-4180 compliant CSV format.
    Values match the JSON response fields exactly.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Permanent Demo Dataset Notice
    writer.writerow(["# DEMO DATASET — NOT OFFICIAL GOVERNMENT DATA"])
    writer.writerow(["# Tamil Nadu Public Distribution System - Monthly Rice Stock & Distribution Report"])
    writer.writerow([f"# Report Month: {report_data['report_month']}", f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"])
    writer.writerow([])

    # SECTION 1: DISTRICT COMPARISON SUMMARY
    writer.writerow(["=== DISTRICT SUMMARY COMPARISON ==="])
    writer.writerow([
        "District Code",
        "District Name",
        "Shops Count",
        "Received (kg)",
        "Distributed (kg)",
        "Previous Month Distributed (kg)",
        "MoM Change (kg)",
        "MoM Change (%)",
        "Closing Stock (kg)",
    ])

    for d in report_data["districts_summary"]:
        writer.writerow([
            d["district_code"],
            d["district_name"],
            d["shops_count"],
            d["total_received_kg"],
            d["total_distributed_kg"],
            d["prev_distributed_kg"],
            d["mom_diff_kg"],
            d["mom_pct"],
            d["closing_stock_kg"],
        ])

    writer.writerow([])

    # SECTION 2: FAIR-PRICE SHOP DETAILED TABLE
    writer.writerow(["=== FAIR-PRICE SHOP DETAILED REPORT ==="])
    writer.writerow([
        "Shop ID",
        "Shop Name",
        "District",
        "Linked Godown",
        "Beneficiaries",
        "Opening Stock (kg)",
        "Received (kg)",
        "Distributed (kg)",
        "Prev Month Distributed (kg)",
        "MoM Change (kg)",
        "MoM Change (%)",
        "Closing Stock (kg)",
        "Stock Status",
    ])

    for s in report_data["shops_detail"]:
        writer.writerow([
            s["shop_id"],
            s["shop_name"],
            s["district_name"],
            s["godown_id"],
            s["beneficiaries_count"],
            s["opening_stock_kg"],
            s["received_kg"],
            s["distributed_kg"],
            s["prev_distributed_kg"],
            s["mom_diff_kg"],
            s["mom_pct"],
            s["closing_stock_kg"],
            s["status"],
        ])

    return output.getvalue()
