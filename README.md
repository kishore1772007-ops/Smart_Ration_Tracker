# Smart Ration Tracker (Tamil Nadu PDS)

> **DEMO DATASET — NOT OFFICIAL GOVERNMENT DATA**  
> *This software is an educational prototype and reference implementation for monitoring and planning rice stock movements across the Tamil Nadu Public Distribution System (TNPDS). All data, locations, consignments, and metrics are simulated.*

---

## 🏛️ Project Overview

**Smart Ration Tracker** provides an end-to-end, full-stack, software-only dashboard for managing the rice supply chain across Tamil Nadu's Civil Supplies and Consumer Protection Department:
$$\text{Supplier / FCI Pool} \longrightarrow \text{District Buffer Godowns} \longrightarrow \text{Fair-Price Shops (FPS)} \longrightarrow \text{Beneficiaries}$$

### Core Architecture Invariants
1. **Derived Stock Balances**: Stock is **never** statically stored or duplicated. Every balance is strictly derived from verified baseline opening stock plus immutable stock movements:
   - **Godown Stock** = $\text{Opening Stock} + \text{Receipts} - \text{Dispatches} \pm \text{Adjustments}$
   - **Shop Stock** = $\text{Opening Stock} + \text{Confirmed Deliveries} - \text{POS Distributions} \pm \text{Adjustments}$
2. **Decoupled Dispatch & Receipt**: Outgoing consignments leave godown stock immediately upon dispatch, but do **not** enter retail shop inventory until explicit physical delivery confirmation.
3. **Difference Reconciliation**: In-transit shortages or damages flag consignments as `RECEIVED_WITH_DIFFERENCE` without disrupting supply continuity.
4. **Replenishment Recommendation Engine**: Standardized formula with a floor of zero:
   $$\text{Replenishment} = \max(0, \text{Predicted Demand} + 10\% \text{ Buffer} - \text{Usable Stock} - \text{Planned Incoming})$$
   *Permanently labeled: "Planning recommendation, not an official allocation."*
5. **Neutral Alert Phrasing**: Physical stock audit discrepancies exceeding the 2.0% tolerance strictly use the neutral phrase:  
   `"Verification requested on stock balance"` — eliminating punitive bias and promoting transparent reconciliation.
6. **Immutable Audit Trail**: Every write operation (dispatch, delivery confirmation, POS distribution, stock adjustment, inspector audit, alert resolution) automatically records a structured row in `audit_logs`.
7. **Role-Based Access Control (RBAC)**: Strict multi-tier scoping across 6 distinct user roles where shop managers can only access and modify their assigned shop.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite (`smart_ration.db`), Pydantic v2
- **Frontend**: Jinja2 HTML5 Templates, Vanilla Modern CSS, JavaScript (ES6+), Chart.js 4.x
- **Security**: Bcrypt password hashing (12 salt rounds), PyJWT bearer tokens, HTTPOnly session cookies
- **Testing**: Pytest, HTTPX, Starlette TestClient (60/60 automated tests passing)

---

## 📋 PRD Requirement Review & Verification

| PRD Requirement | Specification Standard | Implementation Details | Status |
| :--- | :--- | :--- | :---: |
| **Demo Notice** | Banner on every view | Persistent yellow warning banner in `base.html` | ✅ Met |
| **Hierarchy** | State > District > Godown > Shop | 5 Districts, 10 Godowns, 50 Shops | ✅ Met |
| **Terminology** | Received, Dispatched, Distributed, Expected, Measured | Applied across all templates, schemas, and services | ✅ Met |
| **Stock Invariant** | Derived balances, no duplication | `app/services/stock.py` computes stock dynamically | ✅ Met |
| **Seed Edge Cases** | 3-4 Delayed, 4-5 Low Stock, 2-3 Discrepancies, 1-2 Differences, 1-2 Stale | 4 Delayed, 5 Low-Stock, 3 Discrepancies, 2 Diff Deliveries, 2 Stale Shops | ✅ Met |
| **Summary Dashboard** | 6 KPI cards, District table, Month filter, 4 Chart.js charts | `app/templates/dashboard.html` with real-time updates | ✅ Met |
| **State Total Invariant** | State stock = sum of districts | Verified mathematically & in test suite | ✅ Met |
| **Detail Pages** | Breadcrumbs, closing stock formula, tables | District, Godown, and Shop detail views | ✅ Met |
| **Mutation Engine** | Positive kg, no over-dispatch, no over-distribution, reason required | `app/services/transactions.py` with validation | ✅ Met |
| **Monthly Reports** | Month/District/Shop filters, MoM delta, CSV export | `app/routers/reports.py` (?format=csv matching JSON) | ✅ Met |
| **Forecasting** | 4-month rolling avg, 10% buffer, 0 floor, 2,265 kg unit test | `app/services/forecast.py` passing unit & backtest | ✅ Met |
| **Alert Engine** | Low stock, Replenishment, Delay, Discrepancy, Missing Data | `app/services/alert_engine.py` with neutral phrasing | ✅ Met |
| **Duplicate Prevention** | Prevent duplicate open alerts for same type & location | `has_open_alert()` ensures exactly 1 alert per case | ✅ Met |
| **Authentication & RBAC** | Hashed passwords, 6 roles, strict location scoping | `app/services/auth.py` with 403 Forbidden enforcement | ✅ Met |
| **Cross-Shop Security** | Shop manager cannot read or modify another shop | Tested in `tests/test_auth_and_rbac.py` | ✅ Met |

*All specifications established in the PRD are 100% satisfied.*

---

## 🚀 Quickstart & Setup Guide

### 1. Prerequisites
- Python 3.11 or higher installed (`python --version`)
- Git / PowerShell / Terminal

### 2. Environment Setup
```powershell
# Navigate to the project root
cd C:\Users\Dell\.gemini\antigravity-ide\scratch\smart_ration_tracker

# Create and activate virtual environment (optional but recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install project dependencies
pip install fastapi uvicorn sqlalchemy pydantic pydantic-settings jinja2 httpx pytest bcrypt pyjwt
```

### 3. Generate Mock Data & Seed SQLite Database
```powershell
# Generate CSV datasets in /data using fixed random seed (seed=42)
python scripts/generate_mock_data.py

# Seed SQLite database (smart_ration.db)
python scripts/load_csv.py
```

### 4. Run Development Server
```powershell
uvicorn app.main:app --reload --port 8000
```
Open your browser at: **[http://localhost:8000](http://localhost:8000)**  
Interactive Swagger API Docs: **[http://localhost:8000/docs](http://localhost:8000/docs)**

### 5. Run Test Suite
```powershell
# Run the complete test suite (60 tests)
python -m pytest tests/ -v
```

---

## 👥 Demo User Personas & Credentials

All demo accounts share the password: `demo123` (hashed with bcrypt). The login screen includes 1-click quick credentials.

| Role | Username | Password | Full Name & Title | Assigned Scope |
| :--- | :--- | :--- | :--- | :--- |
| **State Admin** | `admin_tn` | `demo123` | Dr. K. Ramanathan (IAS) | Universal (All Tamil Nadu) |
| **District Officer** | `officer_chennai` | `demo123` | S. Meenakshi (DRO Chennai) | District 1 (Chennai) |
| **Godown Manager** | `mgr_gdn001` | `demo123` | V. Soundararajan (Godown Mgr) | Godown GDN-001 |
| **Shop Manager** | `mgr_fps0001` | `demo123` | M. Murugan (Shop In-charge) | Fair-Price Shop FPS-0001 |
| **Stock Inspector** | `inspector_tn` | `demo123` | A. Jayakumar (Senior Inspector)| State Audit & Inspection |
| **Data Entry Officer**| `data_entry_tn` | `demo123` | P. Priya (Data Entry Executive)| District 1 Data Operations |

---

## ⏱️ 10-Minute Live Demo Script

Follow this structured script for live presentations or stakeholder walkthroughs.

### Minute 0:00 – 1:30 | Act 1: The High-Level Statewide Executive Overview
1. Navigate to `http://localhost:8000/` as guest or State Admin (`admin_tn`).
2. Point out the permanent warning banner: `Demo Dataset — Not Official Government Data`.
3. Highlight the **Six KPI Summary Cards**:
   - Total Godown Buffer Stock (~2,829,000 kg / ~2,829 MT)
   - Total Fair-Price Shop Stock (~287,000 kg / ~287 MT)
   - Monthly Rice Distributed (~196,000 kg / ~196 MT)
   - Beneficiary Households Served (~43,000 active cards)
   - In-Transit / Delayed Deliveries (4 overdue consignments flagged)
   - Attention Flags (5 low-stock shops + 3 physical audit discrepancy requests)
4. Demonstrate the **Month Selector**: switch from October 2026 to September 2026. Watch the KPI cards, charts, and district table update in real time.
5. Review the **4 Chart.js Visualizations**:
   - Rice Distribution by District (Bar)
   - 6-Month Statewide Trend (Line)
   - Shop Stock Status Health (Doughnut: Normal, Low, Critical)
   - Expected vs. Measured Stock Physical Audit (Bar showing inspector variances)
6. Verify the footer of the District Table: note that the sum of the 5 districts strictly equals the State Total.

### Minute 1:30 – 3:30 | Act 2: Hierarchical Navigation & Architectural Stock Invariants
1. Click on **Chennai** in the district table to open `/districts/1`.
2. Observe the breadcrumb trail: `Tamil Nadu > Chennai District`.
3. Review the breakdown: 2 Central Granaries (`GDN-001`, `GDN-002`) and 10 Fair-Price Shops (`FPS-0001` to `FPS-0010`).
4. Click on **Chennai Central Buffer Godown (`GDN-001`)** to open `/godowns/GDN-001`.
5. Point out the **Closing Stock Formula Banner**:
   $$\text{Expected Closing Stock} = \text{Opening} + \text{Received} - \text{Dispatched} \pm \text{Adjustments}$$
   Show that all numbers reconcile to the exact gram.
6. Scroll down to the **Outgoing Dispatches** and **Incoming Receipts** tables. Note that consignments in transit have not yet entered retail shop stock (decoupled events).

### Minute 3:30 – 5:00 | Act 3: Retail Fair-Price Shop & 4-Month Demand Forecasting
1. From the breadcrumb or dispatches table, click **Shop FPS-0001** (`/shops/FPS-0001`).
2. Examine the 6-month historical monthly distribution bar chart.
3. Review the **Replenishment Recommendation Card**:
   - Predicted Monthly Demand (4-month rolling average): `3,150 kg`
   - Safety Buffer (10%): `+315 kg`
   - Usable Stock on Floor: `-7,471 kg`
   - Planned Incoming: `-1,200 kg`
   - Recommended Replenishment: `0.00 kg` (demonstrating the floor of zero).
   - Point out the mandatory label: *"Planning recommendation, not an official allocation."*
4. Click the purple button **"Run Model →"** to trigger a live run of the forecast engine via `POST /api/predictions/run`, observing the instant toast confirmation and audit entry.

### Minute 5:00 – 6:30 | Act 4: Operational Transactions & In-Transit Difference Handling
1. Click **Operations & Log** in the top navigation bar (`/transactions`).
2. **Step 1 (Dispatch)**:
   - Select Godown `GDN-001` and Shop `FPS-0001`.
   - Enter `500 kg` and submit.
   - Note the pending delivery generated in the pending deliveries table.
3. **Step 2 (Delivery Shortage Handling)**:
   - Click the "Confirm Delivery" tab.
   - Choose the pending consignment of 500 kg.
   - Enter `480 kg` (a 20 kg in-transit shortage due to handling).
   - Submit confirmation.
   - The consignment is flagged as `RECEIVED_WITH_DIFFERENCE`. Shop stock increases by exactly 480 kg, preserving financial and inventory integrity.
4. **Step 3 (Audit Trail)**:
   - Scroll down to the **Live System Audit Log** table. Observe the new immutable log entries recording the user, action, timestamp, and payload.

### Minute 6:30 – 8:00 | Act 5: Neutral Alert Centre & Physical Audit Discrepancies
1. Click **Alert Centre** in the top navigation bar (`/alerts`).
2. Point out the KPI counters: 14 Open alerts matching all seeded edge cases:
   - 4 Delayed Consignments
   - 5 Low Stock Shops
   - 3 Stock Discrepancies
   - 2 Stale Reporting Lapses
3. Find an alert for **Stock Discrepancy** (e.g. `FPS-0012`).
4. Read the explanation aloud: note the strict neutral protocol:  
   `"Verification requested on stock balance. Routine ledger reconciliation requested."`  
   *(No blame, accusations, or defamatory language).*
5. Click **"Verify / Resolve"** on the alert:
   - Try submitting with empty notes: note the client and server validation error.
   - Enter: `"Joint physical weighment and counterfoil tally verified with DRO"` and set status to `UNDER_VERIFICATION`.
   - Submit. Watch the badge transition smoothly and the audit log record the resolution notes.

### Minute 8:00 – 9:00 | Act 6: Role-Based Access Control & Cross-Shop Security Boundaries
1. Click **Sign Out** in the top navbar and click **Sign In** (`/login`).
2. In the **Quick Demo Role Selection** panel, click **M. Murugan (Shop Mgr FPS-0001)**.
3. Click **Sign In**. The system logs in with `demo123`, sets an HTTPOnly cookie, and redirects to `/shops/FPS-0001`.
4. Point out the navbar badge: `M. Murugan (shop_manager: FPS-0001)`.
5. Now attempt to view another shop by navigating to `http://localhost:8000/shops/FPS-0002` or `http://localhost:8000/api/shops/FPS-0002`.
6. **Result**: The browser displays **403 Forbidden**:  
   `Access Denied: Shop Manager 'mgr_fps0001' is assigned to shop 'FPS-0001' and cannot access shop 'FPS-0002'.`
7. Demonstrate that modifying another shop via API is rejected with 403 Forbidden.

### Minute 9:00 – 10:00 | Act 7: Monthly Reports & CSV Export
1. Log back in as **Dr. Ramanathan (State Admin)**.
2. Click **Monthly Reports** (`/reports`).
3. View the state and district-level Month-over-Month (MoM) distribution comparisons.
4. Click the green button **"Export CSV"** (`/api/reports/monthly?format=csv`).
5. Open the downloaded CSV file and verify that every figure matches the JSON response and web table with 100% precision.

---

## 🧪 Automated Test Suite Summary

The automated test suite covers all 9 implementation phases:

```powershell
python -m pytest tests/ -v
```

```
tests/test_alerts.py ......................... [6 PASSED]
tests/test_auth_and_rbac.py ................. [12 PASSED]
tests/test_database_and_api.py .............. [6 PASSED]
tests/test_detail_pages.py .................. [7 PASSED]
tests/test_forecast.py ...................... [5 PASSED]
tests/test_mock_data.py ..................... [5 PASSED]
tests/test_reports.py ....................... [4 PASSED]
tests/test_stock_service_and_dashboard.py ... [6 PASSED]
tests/test_transactions.py .................. [9 PASSED]
========================= 60 passed in 28.02s =========================
```

---

## 📂 Project Directory Structure

```
smart_ration_tracker/
├── app/
│   ├── config.py             # Domain rules, thresholds, JWT settings
│   ├── database.py           # SQLite connection and session maker
│   ├── main.py               # FastAPI entry point, Jinja2 filters, web routes
│   ├── models/
│   │   └── entities.py       # 12 SQLAlchemy models
│   ├── schemas/
│   │   ├── auth.py           # Auth & profile schemas
│   │   ├── base.py           # Core entity schemas
│   │   ├── transactions.py   # Mutation schemas
│   │   ├── predictions.py    # Forecasting schemas
│   │   └── alerts.py         # Alert schemas
│   ├── services/
│   │   ├── stock.py          # Derived stock calculation & reconciliation
│   │   ├── transactions.py   # Business rules, movements, deliveries
│   │   ├── forecast.py       # Rolling average & buffer replenishment
│   │   ├── alert_engine.py   # Rule-based alert generation & scanning
│   │   ├── reports.py        # Monthly reporting & CSV exporter
│   │   └── auth.py           # Bcrypt hashing, JWT tokens & RBAC scoping
│   ├── routers/              # 10 modular APIRouters
│   ├── templates/            # 8 Jinja2 HTML5 views with breadcrumbs
│   └── static/               # Vanilla CSS design system & Chart.js controllers
├── data/                     # 9 generated CSV datasets (seed=42)
├── scripts/
│   ├── generate_mock_data.py # Deterministic mock data generator
│   └── load_csv.py           # Database loader & validator
├── tests/                    # 9 test files (60 tests)
└── README.md                 # Complete documentation & demo script
```
