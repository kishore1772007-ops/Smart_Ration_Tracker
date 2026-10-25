"""
Tests for Phase 6: Monthly Reports and CSV Export.
Validates:
1. GET /api/reports/monthly JSON response with received, distributed, closing stock, and MoM comparison.
2. Filtering by month, district_id, and shop_id.
3. CRITICAL SPEC TEST: Exact value parity between CSV export and JSON response.
4. Reports HTML view rendering with filters, tables, and permanent demo banner.
"""

import csv
import io
import os
import sys
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.main import app

client = TestClient(app)


def test_monthly_report_json_structure():
    """Verify JSON structure, received, distributed, closing stock, and MoM trend."""
    res = client.get("/api/reports/monthly?month=2026-10")
    assert res.status_code == 200
    data = res.json()

    assert data["report_month"] == "2026-10"
    assert data["previous_month"] == "2026-09"
    assert "totals" in data
    assert "districts_summary" in data
    assert "shops_detail" in data

    totals = data["totals"]
    assert totals["total_received_kg"] > 0
    assert totals["total_distributed_kg"] > 0
    assert totals["total_closing_stock_kg"] > 0
    assert totals["shops_count"] == 50

    # Districts summary checks
    assert len(data["districts_summary"]) == 5
    for d in data["districts_summary"]:
        assert d["total_received_kg"] > 0
        assert d["total_distributed_kg"] > 0
        assert d["closing_stock_kg"] > 0
        assert "mom_diff_kg" in d
        assert "mom_pct" in d

    # Shops detail checks
    assert len(data["shops_detail"]) == 50
    for s in data["shops_detail"]:
        assert s["opening_stock_kg"] > 0
        assert s["closing_stock_kg"] > 0
        assert "mom_diff_kg" in s
        assert "mom_pct" in s
        assert s["status"] in ["NORMAL", "LOW", "CRITICAL"]


def test_monthly_report_filtering():
    """Verify filtering by month, district, and shop."""
    # Filter by previous month
    res_sep = client.get("/api/reports/monthly?month=2026-09")
    assert res_sep.status_code == 200
    data_sep = res_sep.json()
    assert data_sep["report_month"] == "2026-09"
    assert data_sep["previous_month"] == "2026-08"

    # Filter by district_id=1 (Chennai)
    res_dist = client.get("/api/reports/monthly?month=2026-10&district_id=1")
    assert res_dist.status_code == 200
    data_dist = res_dist.json()
    assert len(data_dist["districts_summary"]) == 1
    assert data_dist["districts_summary"][0]["district_code"] == "DIS-01"
    assert len(data_dist["shops_detail"]) == 10
    for s in data_dist["shops_detail"]:
        assert s["district_id"] == 1

    # Filter by specific shop
    res_shop = client.get("/api/reports/monthly?month=2026-10&shop_id=FPS-0001")
    assert res_shop.status_code == 200
    data_shop = res_shop.json()
    assert len(data_shop["shops_detail"]) == 1
    assert data_shop["shops_detail"][0]["shop_id"] == "FPS-0001"


def test_csv_export_matches_json_values_exactly():
    """
    CRITICAL SPEC REQUIREMENT:
    Verify that every single numeric value in the exported CSV matches
    the JSON response values row-for-row without rounding discrepancy.
    """
    month = "2026-10"
    # 1. Fetch JSON
    res_json = client.get(f"/api/reports/monthly?month={month}&format=json")
    assert res_json.status_code == 200
    json_data = res_json.json()

    # 2. Fetch CSV
    res_csv = client.get(f"/api/reports/monthly?month={month}&format=csv")
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    assert f"monthly_pds_report_{month}.csv" in res_csv.headers.get("content-disposition", "")

    csv_text = res_csv.text
    # Mandatory demo banner in CSV header
    assert "DEMO DATASET — NOT OFFICIAL GOVERNMENT DATA" in csv_text

    # Parse CSV lines
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    # 3. Match Districts Comparison
    dist_header_idx = -1
    shop_header_idx = -1
    for idx, row in enumerate(rows):
        if row and row[0] == "=== DISTRICT SUMMARY COMPARISON ===":
            dist_header_idx = idx + 1
        elif row and row[0] == "=== FAIR-PRICE SHOP DETAILED REPORT ===":
            shop_header_idx = idx + 1

    assert dist_header_idx != -1, "District section missing from CSV"
    assert shop_header_idx != -1, "Shop section missing from CSV"

    # Compare district rows
    json_districts = {d["district_code"]: d for d in json_data["districts_summary"]}
    for i in range(dist_header_idx + 1, shop_header_idx - 2):
        row = rows[i]
        if not row or row[0].startswith("===") or row[0].startswith("#"):
            continue
        d_code = row[0]
        if d_code in json_districts:
            expected = json_districts[d_code]
            assert row[1] == expected["district_name"]
            assert int(row[2]) == expected["shops_count"]
            assert float(row[3]) == expected["total_received_kg"]
            assert float(row[4]) == expected["total_distributed_kg"]
            assert float(row[5]) == expected["prev_distributed_kg"]
            assert float(row[6]) == expected["mom_diff_kg"]
            assert float(row[7]) == expected["mom_pct"]
            assert float(row[8]) == expected["closing_stock_kg"]

    # Compare shop rows
    json_shops = {s["shop_id"]: s for s in json_data["shops_detail"]}
    for i in range(shop_header_idx + 1, len(rows)):
        row = rows[i]
        if not row or row[0].startswith("#"):
            continue
        s_id = row[0]
        if s_id in json_shops:
            exp_s = json_shops[s_id]
            assert row[1] == exp_s["shop_name"]
            assert row[2] == exp_s["district_name"]
            assert row[3] == exp_s["godown_id"]
            assert int(row[4]) == exp_s["beneficiaries_count"]
            assert float(row[5]) == exp_s["opening_stock_kg"]
            assert float(row[6]) == exp_s["received_kg"]
            assert float(row[7]) == exp_s["distributed_kg"]
            assert float(row[8]) == exp_s["prev_distributed_kg"]
            assert float(row[9]) == exp_s["mom_diff_kg"]
            assert float(row[10]) == exp_s["mom_pct"]
            assert float(row[11]) == exp_s["closing_stock_kg"]
            assert row[12] == exp_s["status"]


def test_reports_html_page_rendering():
    """Verify HTML Reports view renders with filters, tables, and permanent banner."""
    res = client.get("/reports?month=2026-10")
    assert res.status_code == 200
    html = res.text

    # Permanent Banner
    assert "Demo Dataset — Not Official Government Data" in html

    # Page Header and Filters
    assert "Monthly PDS Stock &amp; Distribution Reports" in html or "Monthly PDS Stock & Distribution Reports" in html
    assert 'id="filterMonth"' in html
    assert 'id="filterDistrict"' in html
    assert 'id="btnExportCsv"' in html
    assert "Export CSV" in html

    # Tables
    assert 'id="districtComparisonTable"' in html
    assert 'id="shopsDetailTable"' in html

    # Data elements
    assert "Chennai" in html
    assert "FPS-0001" in html
