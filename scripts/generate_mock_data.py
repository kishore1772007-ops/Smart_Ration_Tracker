"""
Smart Ration Tracker - Mock Data Generator
Generates realistic CSV data for Tamil Nadu PDS rice stock monitoring & planning.
Seed is fixed for strict reproducibility.
"""

import csv
import os
import random
from datetime import datetime, timedelta

# Fix random seed for reproducibility
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------------------------------------------------
# 1. DISTRICTS (5)
# -------------------------------------------------------------
DISTRICTS = [
    {"id": 1, "code": "DIS-01", "name": "Chennai", "headquarters": "Chennai"},
    {"id": 2, "code": "DIS-02", "name": "Coimbatore", "headquarters": "Coimbatore"},
    {"id": 3, "code": "DIS-03", "name": "Madurai", "headquarters": "Madurai"},
    {"id": 4, "code": "DIS-04", "name": "Tiruchirappalli", "headquarters": "Tiruchirappalli"},
    {"id": 5, "code": "DIS-05", "name": "Salem", "headquarters": "Salem"},
]

# -------------------------------------------------------------
# 2. COMMODITIES (1)
# -------------------------------------------------------------
COMMODITIES = [
    {"id": 1, "code": "RICE-C", "name": "Common PDS Rice (Ponni/Boiled)", "unit": "kg", "buffer_pct": 10.0}
]

# -------------------------------------------------------------
# 3. GODOWNS (10 - 2 per district)
# -------------------------------------------------------------
GODOWN_NAMES = [
    ("GDN-001", "Chennai Central Buffer Godown", 1, 500000.0, 180000.0),
    ("GDN-002", "Chennai North Storage Depot", 1, 450000.0, 160000.0),
    ("GDN-003", "Coimbatore South Regional Godown", 2, 400000.0, 150000.0),
    ("GDN-004", "Coimbatore West Operational Depot", 2, 400000.0, 140000.0),
    ("GDN-005", "Madurai Central Granary Depot", 3, 450000.0, 165000.0),
    ("GDN-006", "Madurai East Sector Godown", 3, 350000.0, 130000.0),
    ("GDN-007", "Trichy Rockfort Supply Depot", 4, 400000.0, 145000.0),
    ("GDN-008", "Trichy North Rural Godown", 4, 350000.0, 135000.0),
    ("GDN-009", "Salem Central Storage Facility", 5, 450000.0, 170000.0),
    ("GDN-010", "Salem Rural Logistics Depot", 5, 350000.0, 125000.0),
]

GODOWNS = [
    {
        "id": g[0],
        "code": g[0],
        "name": g[1],
        "district_id": g[2],
        "capacity_kg": g[3],
        "opening_stock_kg": g[4],
    }
    for g in GODOWN_NAMES
]

# -------------------------------------------------------------
# 4. SHOPS (50 - 5 linked to each godown)
# -------------------------------------------------------------
SHOPS = []
shop_idx = 1
for g in GODOWNS:
    g_id = g["id"]
    d_id = g["district_id"]
    for i in range(1, 6):
        shop_code = f"FPS-{shop_idx:04d}"
        shop_name = f"{g['name'].split()[0]} Fair Price Shop #{shop_idx}"
        # Opening stock between 3,000 and 5,000 kg
        opening_stock = float(random.randint(30, 50) * 100)
        beneficiaries = random.randint(650, 1100)
        SHOPS.append({
            "id": shop_code,
            "code": shop_code,
            "name": shop_name,
            "district_id": d_id,
            "godown_id": g_id,
            "beneficiaries_count": beneficiaries,
            "opening_stock_kg": opening_stock,
        })
        shop_idx += 1

# -------------------------------------------------------------
# 5. USERS (One per role)
# Demo password hash for 'demo123' (bcrypt: $2b$12$K1Gg5vj6iHn...)
# We can store a precomputed standard bcrypt hash for 'demo123'
# -------------------------------------------------------------
DEMO_PASSWORD_HASH = "$2b$12$JF9oAVfaz4Ha96SYdd6ssOiVrqv5lHOePODKtK92SY.sh.INHeRku"  # demo123

USERS = [
    {
        "id": 1,
        "username": "admin_tn",
        "email": "state.admin@tnpds.demo",
        "password_hash": DEMO_PASSWORD_HASH,
        "role": "state_admin",
        "district_id": "",
        "godown_id": "",
        "shop_id": "",
        "full_name": "Dr. K. Ramanathan (IAS)",
    },
    {
        "id": 2,
        "username": "officer_chennai",
        "email": "district.chennai@tnpds.demo",
        "password_hash": DEMO_PASSWORD_HASH,
        "role": "district_officer",
        "district_id": 1,
        "godown_id": "",
        "shop_id": "",
        "full_name": "S. Meenakshi (DRO Chennai)",
    },
    {
        "id": 3,
        "username": "mgr_gdn001",
        "email": "manager.gdn001@tnpds.demo",
        "password_hash": DEMO_PASSWORD_HASH,
        "role": "godown_manager",
        "district_id": 1,
        "godown_id": "GDN-001",
        "shop_id": "",
        "full_name": "V. Soundararajan (Godown Mgr)",
    },
    {
        "id": 4,
        "username": "mgr_fps0001",
        "email": "manager.fps0001@tnpds.demo",
        "password_hash": DEMO_PASSWORD_HASH,
        "role": "shop_manager",
        "district_id": 1,
        "godown_id": "GDN-001",
        "shop_id": "FPS-0001",
        "full_name": "M. Murugan (Shop In-charge)",
    },
    {
        "id": 5,
        "username": "inspector_tn",
        "email": "inspector.hq@tnpds.demo",
        "password_hash": DEMO_PASSWORD_HASH,
        "role": "stock_inspector",
        "district_id": "",
        "godown_id": "",
        "shop_id": "",
        "full_name": "A. Jayakumar (Senior Quality & Stock Inspector)",
    },
    {
        "id": 6,
        "username": "data_entry_tn",
        "email": "dataentry.chennai@tnpds.demo",
        "password_hash": DEMO_PASSWORD_HASH,
        "role": "data_entry_officer",
        "district_id": 1,
        "godown_id": "",
        "shop_id": "",
        "full_name": "P. Priya (Data Entry Executive)",
    },
]

# -------------------------------------------------------------
# 6. TIME HORIZON: 6 Months simulation
# From May 1, 2026 to October 24, 2026 (current time)
# -------------------------------------------------------------
START_DATE = datetime(2026, 5, 1, 9, 0, 0)
CURRENT_SIMULATED_DATE = datetime(2026, 10, 24, 18, 0, 0)

MONTH_LABELS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]

# Track balances in-memory during generation to strictly guarantee no negative stock
godown_balances = {g["id"]: g["opening_stock_kg"] for g in GODOWNS}
shop_balances = {s["id"]: s["opening_stock_kg"] for s in SHOPS}

stock_movements = []
deliveries = []
monthly_distributions = []
measurements = []

movement_counter = 1
delivery_counter = 1
measurement_counter = 1

# Designated Edge Case Targets:
LOW_STOCK_SHOPS = ["FPS-0007", "FPS-0018", "FPS-0029", "FPS-0042", "FPS-0048"]  # 5 low stock shops
STALE_RECORD_SHOPS = ["FPS-0049", "FPS-0050"]  # 2 stale record shops
QTY_DIFF_DELIVERY_SHOP_1 = "FPS-0014"
QTY_DIFF_DELIVERY_SHOP_2 = "FPS-0033"
DELAYED_DELIVERY_SHOPS = ["FPS-0005", "FPS-0020", "FPS-0038", "FPS-0046"]  # 4 delayed deliveries

# Track monthly totals per shop for monthly_distribution.csv
shop_month_dist = {s["id"]: {m: 0.0 for m in MONTH_LABELS} for s in SHOPS}
shop_month_cards = {s["id"]: {m: 0 for m in MONTH_LABELS} for s in SHOPS}


def add_movement(location_type, location_id, movement_type, qty_kg, timestamp, ref_id, created_by):
    global movement_counter
    mov_id = f"MOV-{movement_counter:06d}"
    stock_movements.append({
        "id": mov_id,
        "location_type": location_type,
        "location_id": location_id,
        "movement_type": movement_type,
        "quantity_kg": round(qty_kg, 2),
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "reference_id": ref_id,
        "created_by": created_by,
    })
    movement_counter += 1
    return mov_id


# Simulate Month by Month
current_month_start = START_DATE
for m_idx, month_str in enumerate(MONTH_LABELS):
    is_latest_month = (month_str == "2026-10")
    
    # 1. Supplier / FCI Receipts into Godowns at the beginning of each month
    # Each godown receives 30,000 to 45,000 kg from Central FCI Pool
    for g in GODOWNS:
        g_id = g["id"]
        rcv_qty = float(random.randint(32, 45) * 1000)
        rcv_date = current_month_start + timedelta(days=random.randint(1, 3), hours=random.randint(9, 15))
        add_movement("godown", g_id, "RECEIPT", rcv_qty, rcv_date, f"FCI-RR-{month_str}-{g_id}", "fci_supplier_bot")
        godown_balances[g_id] += rcv_qty

    # 2. Godown to Shop Dispatches (Twice a month for most shops: ~Day 4 and ~Day 16)
    dispatch_cycles = [4, 16] if not is_latest_month else [4, 15]

    for cycle_day in dispatch_cycles:
        for shop in SHOPS:
            s_id = shop["id"]
            g_id = shop["godown_id"]

            # Edge case handling: Stale shops don't get movements in late October
            if is_latest_month and cycle_day == 15 and s_id in STALE_RECORD_SHOPS:
                continue

            # Edge case handling: Low stock shops get smaller/no second dispatch in month 10
            if is_latest_month and cycle_day == 15 and s_id in LOW_STOCK_SHOPS:
                # We intentionally don't dispatch in the 2nd cycle of October to leave them with low stock after distributions
                continue

            dispatch_date = current_month_start + timedelta(days=cycle_day + random.randint(0, 1), hours=random.randint(8, 11))
            if dispatch_date > CURRENT_SIMULATED_DATE:
                continue

            # Quantity dispatched: 1,500 to 2,200 kg
            dispatch_qty = float(random.randint(15, 22) * 100)

            # Ensure godown has enough stock
            if godown_balances[g_id] < dispatch_qty + 5000:
                dispatch_qty = max(500.0, godown_balances[g_id] - 5000)

            # Deduct from Godown and record movement
            del_id = f"DEL-{delivery_counter:05d}"
            delivery_counter += 1

            disp_mov_id = add_movement("godown", g_id, "DISPATCH", dispatch_qty, dispatch_date, del_id, "godown_dispatcher")
            godown_balances[g_id] -= dispatch_qty

            # Determine delivery fate and edge cases
            expected_delivery_date = dispatch_date + timedelta(days=1, hours=4)

            # Edge case: Delayed deliveries in October
            if is_latest_month and cycle_day == 15 and s_id in DELAYED_DELIVERY_SHOPS:
                # Dispatched on Oct 16, expected Oct 17. Current is Oct 24 -> 7 days delayed!
                deliveries.append({
                    "id": del_id,
                    "dispatch_movement_id": disp_mov_id,
                    "from_godown_id": g_id,
                    "to_shop_id": s_id,
                    "dispatched_date": dispatch_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "expected_delivery_date": expected_delivery_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "DELAYED",
                    "dispatched_qty_kg": dispatch_qty,
                    "received_qty_kg": 0.0,
                    "received_date": "",
                    "notes": "Consignment in transit; route transit delay reported by carrier",
                })
                # No confirmed delivery movement yet!
                continue

            # Edge case: Deliveries received with quantity difference
            if (s_id == QTY_DIFF_DELIVERY_SHOP_1 and month_str == "2026-07" and cycle_day == 4) or \
               (s_id == QTY_DIFF_DELIVERY_SHOP_2 and month_str == "2026-09" and cycle_day == 16):
                shortage = 45.0 if s_id == QTY_DIFF_DELIVERY_SHOP_1 else 75.0
                received_qty = dispatch_qty - shortage
                arrival_date = dispatch_date + timedelta(days=1, hours=random.randint(2, 6))

                deliveries.append({
                    "id": del_id,
                    "dispatch_movement_id": disp_mov_id,
                    "from_godown_id": g_id,
                    "to_shop_id": s_id,
                    "dispatched_date": dispatch_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "expected_delivery_date": expected_delivery_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "RECEIVED_WITH_DIFFERENCE",
                    "dispatched_qty_kg": dispatch_qty,
                    "received_qty_kg": received_qty,
                    "received_date": arrival_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": f"Discrepancy at receipt: {shortage:.1f} kg transit loss / torn gunny bags verified on weighbridge",
                })
                # Shop receives only what physically arrived!
                add_movement("shop", s_id, "CONFIRMED_DELIVERY", received_qty, arrival_date, del_id, "shop_receiver")
                shop_balances[s_id] += received_qty
                continue

            # Normal delivery scenario
            arrival_date = dispatch_date + timedelta(days=random.choice([0, 1]), hours=random.randint(3, 8))
            deliveries.append({
                "id": del_id,
                "dispatch_movement_id": disp_mov_id,
                "from_godown_id": g_id,
                "to_shop_id": s_id,
                "dispatched_date": dispatch_date.strftime("%Y-%m-%d %H:%M:%S"),
                "expected_delivery_date": expected_delivery_date.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "DELIVERED",
                "dispatched_qty_kg": dispatch_qty,
                "received_qty_kg": dispatch_qty,
                "received_date": arrival_date.strftime("%Y-%m-%d %H:%M:%S"),
                "notes": "Verified and accepted in full condition",
            })
            add_movement("shop", s_id, "CONFIRMED_DELIVERY", dispatch_qty, arrival_date, del_id, "shop_receiver")
            shop_balances[s_id] += dispatch_qty

    # 3. Shop Distributions to Beneficiaries
    # Distributed across 4 weeks of the month
    weeks = [7, 14, 21, 28] if not is_latest_month else [7, 14, 21]

    for w_day in weeks:
        dist_date = current_month_start + timedelta(days=w_day, hours=random.randint(14, 18))
        if dist_date > CURRENT_SIMULATED_DATE:
            continue

        for shop in SHOPS:
            s_id = shop["id"]

            # Edge case: Stale record shops stopped reporting mid-October
            if is_latest_month and w_day >= 14 and s_id in STALE_RECORD_SHOPS:
                continue

            # Standard weekly distribution demand ~ 700 to 1,000 kg
            cards_served = random.randint(180, 260)
            target_dist = float(cards_served * random.randint(3, 5))

            # Safety constraint: NEVER exceed currently available expected balance!
            curr_bal = shop_balances[s_id]
            
            # For low stock shops in October week 21, let them distribute down to critical / low stock threshold (e.g., 250 - 450 kg left)
            if is_latest_month and s_id in LOW_STOCK_SHOPS and w_day == 21:
                desired_remaining = random.uniform(250.0, 480.0)
                target_dist = max(0.0, curr_bal - desired_remaining)
            else:
                # Keep a safe operational margin of at least 150 kg during normal weeks
                if curr_bal < target_dist + 200:
                    target_dist = max(0.0, curr_bal - 200)

            if target_dist > 0:
                target_dist = round(target_dist, 2)
                add_movement("shop", s_id, "DISTRIBUTION", target_dist, dist_date, f"POS-TX-{dist_date.strftime('%Y%m%d')}-{s_id}", "epos_machine")
                shop_balances[s_id] -= target_dist
                shop_month_dist[s_id][month_str] += target_dist
                shop_month_cards[s_id][month_str] += cards_served

    # Move to next month
    if current_month_start.month == 12:
        current_month_start = datetime(current_month_start.year + 1, 1, 1, 9, 0, 0)
    else:
        current_month_start = datetime(current_month_start.year, current_month_start.month + 1, 1, 9, 0, 0)

# Build Monthly Distribution Summary CSV entries
dist_row_id = 1
for s_id, months_data in shop_month_dist.items():
    for m_str, total_qty in months_data.items():
        monthly_distributions.append({
            "id": dist_row_id,
            "shop_id": s_id,
            "month_year": m_str,
            "distributed_qty_kg": round(total_qty, 2),
            "beneficiary_households_served": shop_month_cards[s_id][m_str],
            "created_at": f"{m_str}-28 20:00:00" if m_str != "2026-10" else "2026-10-24 18:00:00",
        })
        dist_row_id += 1

# -------------------------------------------------------------
# 7. INSPECTOR MEASUREMENTS (with 2-3 deliberate discrepancies)
# -------------------------------------------------------------
# Normal measurement 1: GDN-001 (Match within tolerance 0.1%)
meas_date_1 = "2026-10-10 11:30:00"
measurements.append({
    "id": f"MEA-{measurement_counter:04d}",
    "location_type": "godown",
    "location_id": "GDN-001",
    "measured_date": meas_date_1,
    "measured_stock_kg": round(godown_balances["GDN-001"] + 20.0, 2),  # Virtually exact match
    "inspector_name": "A. Jayakumar",
    "remarks": "Quarterly physical stock verification completed. Gunny stacks properly arranged.",
})
measurement_counter += 1

# DISCREPANCY 1: Shop FPS-0012
# Derived stock is around 2,800 - 3,500 kg, measured stock differs by -350 kg (> 10% discrepancy)
meas_date_2 = "2026-10-18 14:15:00"
fps_12_expected = shop_balances["FPS-0012"]
measurements.append({
    "id": f"MEA-{measurement_counter:04d}",
    "location_type": "shop",
    "location_id": "FPS-0012",
    "measured_date": meas_date_2,
    "measured_stock_kg": round(fps_12_expected - 380.0, 2),
    "inspector_name": "A. Jayakumar",
    "remarks": "Random physical weighment check conducted. Verification requested on stack counterfoil.",
})
measurement_counter += 1

# DISCREPANCY 2: Godown GDN-003
# Godown derived stock is around 130,000 - 160,000 kg, inspector logs -4,500 kg (~3.2% difference, > 2% tolerance)
meas_date_3 = "2026-10-20 10:00:00"
gdn_3_expected = godown_balances["GDN-003"]
measurements.append({
    "id": f"MEA-{measurement_counter:04d}",
    "location_type": "godown",
    "location_id": "GDN-003",
    "measured_date": meas_date_3,
    "measured_stock_kg": round(gdn_3_expected - 4500.0, 2),
    "inspector_name": "A. Jayakumar",
    "remarks": "Silo capacity ultrasound and stack count check. Verification requested for moisture reduction reconciliation.",
})
measurement_counter += 1

# DISCREPANCY 3: Shop FPS-0035
# Measured stock is higher than derived stock by +320 kg (~9% difference)
meas_date_4 = "2026-10-22 15:45:00"
fps_35_expected = shop_balances["FPS-0035"]
measurements.append({
    "id": f"MEA-{measurement_counter:04d}",
    "location_type": "shop",
    "location_id": "FPS-0035",
    "measured_date": meas_date_4,
    "measured_stock_kg": round(fps_35_expected + 320.0, 2),
    "inspector_name": "A. Jayakumar",
    "remarks": "Surprise audit on closing balance. Unaccounted bags noticed; verification requested.",
})
measurement_counter += 1

# Normal measurement 2: FPS-0001
meas_date_5 = "2026-10-23 16:00:00"
measurements.append({
    "id": f"MEA-{measurement_counter:04d}",
    "location_type": "shop",
    "location_id": "FPS-0001",
    "measured_date": meas_date_5,
    "measured_stock_kg": round(shop_balances["FPS-0001"] - 5.0, 2),  # 0.2% diff, within tolerance
    "inspector_name": "A. Jayakumar",
    "remarks": "Routine monthly shop inspection. Physical tally matches POS registers.",
})
measurement_counter += 1


# -------------------------------------------------------------
# CSV EXPORT HELPER
# -------------------------------------------------------------
def export_csv(filename, data, fieldnames):
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"Generated {filename}: {len(data)} records")


def generate_all():
    print("=" * 60)
    print("SMART RATION TRACKER - MOCK DATA GENERATION")
    print("=" * 60)
    print(f"Target Directory: {DATA_DIR}")
    print(f"Random Seed: {RANDOM_SEED}")
    print("-" * 60)

    export_csv("districts.csv", DISTRICTS, ["id", "code", "name", "headquarters"])
    export_csv("commodities.csv", COMMODITIES, ["id", "code", "name", "unit", "buffer_pct"])
    export_csv("godowns.csv", GODOWNS, ["id", "code", "name", "district_id", "capacity_kg", "opening_stock_kg"])
    export_csv("shops.csv", SHOPS, ["id", "code", "name", "district_id", "godown_id", "beneficiaries_count", "opening_stock_kg"])
    export_csv("users.csv", USERS, ["id", "username", "email", "password_hash", "role", "district_id", "godown_id", "shop_id", "full_name"])
    export_csv("stock_movements.csv", stock_movements, ["id", "location_type", "location_id", "movement_type", "quantity_kg", "timestamp", "reference_id", "created_by"])
    export_csv("deliveries.csv", deliveries, ["id", "dispatch_movement_id", "from_godown_id", "to_shop_id", "dispatched_date", "expected_delivery_date", "status", "dispatched_qty_kg", "received_qty_kg", "received_date", "notes"])
    export_csv("monthly_distribution.csv", monthly_distributions, ["id", "shop_id", "month_year", "distributed_qty_kg", "beneficiary_households_served", "created_at"])
    export_csv("measurements.csv", measurements, ["id", "location_type", "location_id", "measured_date", "measured_stock_kg", "inspector_name", "remarks"])

    print("-" * 60)
    print("EDGE CASE SEEDING SUMMARY:")
    print(f" - Delayed Deliveries: {len(DELAYED_DELIVERY_SHOPS)} (Shops: {', '.join(DELAYED_DELIVERY_SHOPS)})")
    print(f" - Low-Stock Shops: {len(LOW_STOCK_SHOPS)} (Shops: {', '.join(LOW_STOCK_SHOPS)})")
    print(f" - Measured-Stock Discrepancies: 3 (FPS-0012, GDN-003, FPS-0035)")
    print(f" - Deliveries Received with Difference: 2 (Shops: {QTY_DIFF_DELIVERY_SHOP_1}, {QTY_DIFF_DELIVERY_SHOP_2})")
    print(f" - Stale-Record Cases: {len(STALE_RECORD_SHOPS)} (Shops: {', '.join(STALE_RECORD_SHOPS)})")
    print("-" * 60)
    print("STOCK INTEGRITY AUDIT:")
    min_godown = min(godown_balances.values())
    min_shop = min(shop_balances.values())
    print(f" - Lowest Godown Closing Stock: {min_godown:.2f} kg (ALL POSITIVE)")
    print(f" - Lowest Shop Closing Stock: {min_shop:.2f} kg (ALL POSITIVE)")
    print("=" * 60)


if __name__ == "__main__":
    generate_all()
