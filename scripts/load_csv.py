"""
Smart Ration Tracker - CSV Loader Script
Populates SQLite database from the generated CSV files in data/ directory.
Ensures date parsing and proper type conversions for SQLAlchemy 2.x models.
"""

import csv
import os
import sys
from datetime import datetime

# Add root directory to sys.path so app imports work seamlessly
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import Base, engine, SessionLocal
from app.models import (
    District,
    Commodity,
    Godown,
    Shop,
    StockMovement,
    Delivery,
    MonthlyDistribution,
    Measurement,
    User,
    AuditLog,
)

DATA_DIR = os.path.join(BASE_DIR, "data")


def parse_dt(dt_str: str) -> datetime | None:
    if not dt_str or dt_str.strip() == "":
        return None
    try:
        return datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.fromisoformat(dt_str.strip())


def load_all_csvs():
    print("=" * 60)
    print("SMART RATION TRACKER - SQLITE DATABASE POPULATION")
    print("=" * 60)

    # 1. Recreate tables
    print("Creating database schema...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        # Districts
        with open(os.path.join(DATA_DIR, "districts.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            districts = [
                District(
                    id=int(r["id"]),
                    code=r["code"],
                    name=r["name"],
                    headquarters=r["headquarters"],
                )
                for r in reader
            ]
            session.add_all(districts)
            session.commit()
            print(f"Loaded {len(districts)} districts")

        # Commodities
        with open(os.path.join(DATA_DIR, "commodities.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            commodities = [
                Commodity(
                    id=int(r["id"]),
                    code=r["code"],
                    name=r["name"],
                    unit=r["unit"],
                    buffer_pct=float(r["buffer_pct"]),
                )
                for r in reader
            ]
            session.add_all(commodities)
            session.commit()
            print(f"Loaded {len(commodities)} commodities")

        # Godowns
        with open(os.path.join(DATA_DIR, "godowns.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            godowns = [
                Godown(
                    id=r["id"],
                    code=r["code"],
                    name=r["name"],
                    district_id=int(r["district_id"]),
                    capacity_kg=float(r["capacity_kg"]),
                    opening_stock_kg=float(r["opening_stock_kg"]),
                )
                for r in reader
            ]
            session.add_all(godowns)
            session.commit()
            print(f"Loaded {len(godowns)} godowns")

        # Shops
        with open(os.path.join(DATA_DIR, "shops.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            shops = [
                Shop(
                    id=r["id"],
                    code=r["code"],
                    name=r["name"],
                    district_id=int(r["district_id"]),
                    godown_id=r["godown_id"],
                    beneficiaries_count=int(r["beneficiaries_count"]),
                    opening_stock_kg=float(r["opening_stock_kg"]),
                )
                for r in reader
            ]
            session.add_all(shops)
            session.commit()
            print(f"Loaded {len(shops)} shops")

        # Users
        with open(os.path.join(DATA_DIR, "users.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            users = [
                User(
                    id=int(r["id"]),
                    username=r["username"],
                    email=r["email"],
                    password_hash=r["password_hash"],
                    role=r["role"],
                    district_id=int(r["district_id"]) if r["district_id"] else None,
                    godown_id=r["godown_id"] if r["godown_id"] else None,
                    shop_id=r["shop_id"] if r["shop_id"] else None,
                    full_name=r["full_name"],
                )
                for r in reader
            ]
            session.add_all(users)
            session.commit()
            print(f"Loaded {len(users)} users")

        # Stock Movements
        with open(os.path.join(DATA_DIR, "stock_movements.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            movements = [
                StockMovement(
                    id=r["id"],
                    location_type=r["location_type"],
                    location_id=r["location_id"],
                    movement_type=r["movement_type"],
                    quantity_kg=float(r["quantity_kg"]),
                    timestamp=parse_dt(r["timestamp"]),
                    reference_id=r["reference_id"],
                    created_by=r["created_by"],
                )
                for r in reader
            ]
            session.add_all(movements)
            session.commit()
            print(f"Loaded {len(movements)} stock movements")

        # Deliveries
        with open(os.path.join(DATA_DIR, "deliveries.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            deliveries = [
                Delivery(
                    id=r["id"],
                    dispatch_movement_id=r["dispatch_movement_id"],
                    from_godown_id=r["from_godown_id"],
                    to_shop_id=r["to_shop_id"],
                    dispatched_date=parse_dt(r["dispatched_date"]),
                    expected_delivery_date=parse_dt(r["expected_delivery_date"]),
                    status=r["status"],
                    dispatched_qty_kg=float(r["dispatched_qty_kg"]),
                    received_qty_kg=float(r["received_qty_kg"]),
                    received_date=parse_dt(r["received_date"]),
                    notes=r["notes"],
                )
                for r in reader
            ]
            session.add_all(deliveries)
            session.commit()
            print(f"Loaded {len(deliveries)} deliveries")

        # Monthly Distributions
        with open(os.path.join(DATA_DIR, "monthly_distribution.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            monthly_dist = [
                MonthlyDistribution(
                    id=int(r["id"]),
                    shop_id=r["shop_id"],
                    month_year=r["month_year"],
                    distributed_qty_kg=float(r["distributed_qty_kg"]),
                    beneficiary_households_served=int(r["beneficiary_households_served"]),
                    created_at=parse_dt(r["created_at"]),
                )
                for r in reader
            ]
            session.add_all(monthly_dist)
            session.commit()
            print(f"Loaded {len(monthly_dist)} monthly distribution records")

        # Measurements
        with open(os.path.join(DATA_DIR, "measurements.csv"), mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            measurements = [
                Measurement(
                    id=r["id"],
                    location_type=r["location_type"],
                    location_id=r["location_id"],
                    measured_date=parse_dt(r["measured_date"]),
                    measured_stock_kg=float(r["measured_stock_kg"]),
                    inspector_name=r["inspector_name"],
                    remarks=r["remarks"],
                )
                for r in reader
            ]
            session.add_all(measurements)
            session.commit()
            print(f"Loaded {len(measurements)} physical measurements")

        from datetime import timezone
        initial_audit = AuditLog(
            user_id=1,
            username="system_bootstrap",
            action="INITIALIZE_DATABASE",
            entity_type="SYSTEM",
            entity_id="ALL",
            details="Seeded initial 6-month historical baseline from mock CSV datasets.",
            timestamp=datetime.now(timezone.utc),
        )
        session.add(initial_audit)
        session.commit()
        print("Logged initialization in audit_logs")

    except Exception as e:
        session.rollback()
        print(f"Error loading CSV data: {e}")
        raise
    finally:
        session.close()

    print("=" * 60)
    print("Database population complete: smart_ration.db is ready.")
    print("=" * 60)


if __name__ == "__main__":
    load_all_csvs()
