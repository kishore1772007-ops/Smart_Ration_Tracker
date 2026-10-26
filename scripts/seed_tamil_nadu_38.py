"""
Full Tamil Nadu 38-District Realistic Seed Generator.
Generates:
- All 38 Tamil Nadu districts with centroids, zones, headquarters, and GeoJSON boundaries
- 5 Essential PDS Commodities (Rice, Wheat, Sugar, Toor Dal, Palm Oil)
- 3 to 8 Godowns per district (total ~150 central buffer granaries)
- 20 to 60 Fair Price Shops per district (total ~1,100 retail shops)
- Multi-commodity Opening Stock & Materialized StockLevel snapshots
- Initial Data Source Settings (Simulator, Sensor, ML Camera)
- Deliberately seeded low-stock and replenishment edge cases
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import math
import random
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from app.database import engine, Base, SessionLocal
from app.models import (
    District,
    Commodity,
    Godown,
    Shop,
    StockLevel,
    StockMovement,
    Delivery,
    Alert,
    DataSourceSetting,
    User,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------------------------------------------------
# 38 TAMIL NADU DISTRICTS MASTER CATALOGUE
# -------------------------------------------------------------
TN_38_DISTRICTS = [
    {"id": 1, "code": "DIS-01", "name": "Chennai", "headquarters": "Chennai", "lat": 13.0827, "lng": 80.2707, "zone": "North Zone"},
    {"id": 2, "code": "DIS-02", "name": "Coimbatore", "headquarters": "Coimbatore", "lat": 11.0168, "lng": 76.9558, "zone": "West Zone"},
    {"id": 3, "code": "DIS-03", "name": "Madurai", "headquarters": "Madurai", "lat": 9.9252, "lng": 78.1198, "zone": "South Zone"},
    {"id": 4, "code": "DIS-04", "name": "Tiruchirappalli", "headquarters": "Tiruchirappalli", "lat": 10.7905, "lng": 78.7047, "zone": "Central Zone"},
    {"id": 5, "code": "DIS-05", "name": "Salem", "headquarters": "Salem", "lat": 11.6643, "lng": 78.1460, "zone": "West Zone"},
    {"id": 6, "code": "DIS-06", "name": "Tirunelveli", "headquarters": "Tirunelveli", "lat": 8.7139, "lng": 77.7567, "zone": "South Zone"},
    {"id": 7, "code": "DIS-07", "name": "Erode", "headquarters": "Erode", "lat": 11.3410, "lng": 77.7172, "zone": "West Zone"},
    {"id": 8, "code": "DIS-08", "name": "Vellore", "headquarters": "Vellore", "lat": 12.9165, "lng": 79.1325, "zone": "North Zone"},
    {"id": 9, "code": "DIS-09", "name": "Thanjavur", "headquarters": "Thanjavur", "lat": 10.7870, "lng": 79.1378, "zone": "Central Delta"},
    {"id": 10, "code": "DIS-10", "name": "Dindigul", "headquarters": "Dindigul", "lat": 10.3673, "lng": 77.9803, "zone": "Central Zone"},
    {"id": 11, "code": "DIS-11", "name": "Kanchipuram", "headquarters": "Kanchipuram", "lat": 12.8342, "lng": 79.7036, "zone": "North Zone"},
    {"id": 12, "code": "DIS-12", "name": "Tiruppur", "headquarters": "Tiruppur", "lat": 11.1085, "lng": 77.3411, "zone": "West Zone"},
    {"id": 13, "code": "DIS-13", "name": "Cuddalore", "headquarters": "Cuddalore", "lat": 11.7480, "lng": 79.7714, "zone": "Coastal Zone"},
    {"id": 14, "code": "DIS-14", "name": "Tiruvannamalai", "headquarters": "Tiruvannamalai", "lat": 12.2253, "lng": 79.0747, "zone": "North Zone"},
    {"id": 15, "code": "DIS-15", "name": "Viluppuram", "headquarters": "Viluppuram", "lat": 11.9401, "lng": 79.4861, "zone": "North Zone"},
    {"id": 16, "code": "DIS-16", "name": "Dharmapuri", "headquarters": "Dharmapuri", "lat": 12.1211, "lng": 78.1582, "zone": "North-West Zone"},
    {"id": 17, "code": "DIS-17", "name": "Krishnagiri", "headquarters": "Krishnagiri", "lat": 12.5186, "lng": 78.2137, "zone": "North-West Zone"},
    {"id": 18, "code": "DIS-18", "name": "Namakkal", "headquarters": "Namakkal", "lat": 11.2189, "lng": 78.1674, "zone": "West Zone"},
    {"id": 19, "code": "DIS-19", "name": "Karur", "headquarters": "Karur", "lat": 10.9601, "lng": 78.0766, "zone": "Central Zone"},
    {"id": 20, "code": "DIS-20", "name": "Perambalur", "headquarters": "Perambalur", "lat": 11.2342, "lng": 78.8817, "zone": "Central Zone"},
    {"id": 21, "code": "DIS-21", "name": "Ariyalur", "headquarters": "Ariyalur", "lat": 11.1401, "lng": 79.0786, "zone": "Central Delta"},
    {"id": 22, "code": "DIS-22", "name": "Nagapattinam", "headquarters": "Nagapattinam", "lat": 10.7672, "lng": 79.8449, "zone": "Coastal Delta"},
    {"id": 23, "code": "DIS-23", "name": "Tiruvarur", "headquarters": "Tiruvarur", "lat": 10.7725, "lng": 79.6368, "zone": "Central Delta"},
    {"id": 24, "code": "DIS-24", "name": "Mayiladuthurai", "headquarters": "Mayiladuthurai", "lat": 11.1018, "lng": 79.6522, "zone": "Coastal Delta"},
    {"id": 25, "code": "DIS-25", "name": "Pudukkottai", "headquarters": "Pudukkottai", "lat": 10.3797, "lng": 78.8208, "zone": "Central Zone"},
    {"id": 26, "code": "DIS-26", "name": "Sivaganga", "headquarters": "Sivaganga", "lat": 9.8433, "lng": 78.4809, "zone": "South Zone"},
    {"id": 27, "code": "DIS-27", "name": "Ramanathapuram", "headquarters": "Ramanathapuram", "lat": 9.3639, "lng": 78.8395, "zone": "Coastal South"},
    {"id": 28, "code": "DIS-28", "name": "Virudhunagar", "headquarters": "Virudhunagar", "lat": 9.5680, "lng": 77.9624, "zone": "South Zone"},
    {"id": 29, "code": "DIS-29", "name": "Theni", "headquarters": "Theni", "lat": 10.0104, "lng": 77.4768, "zone": "South Zone"},
    {"id": 30, "code": "DIS-30", "name": "Thoothukudi", "headquarters": "Thoothukudi", "lat": 8.7642, "lng": 78.1348, "zone": "Coastal South"},
    {"id": 31, "code": "DIS-31", "name": "Tenkasi", "headquarters": "Tenkasi", "lat": 8.9594, "lng": 77.3152, "zone": "South Zone"},
    {"id": 32, "code": "DIS-32", "name": "Kanyakumari", "headquarters": "Nagercoil", "lat": 8.1833, "lng": 77.4119, "zone": "Cape South"},
    {"id": 33, "code": "DIS-33", "name": "Nilgiris", "headquarters": "Udhagamandalam", "lat": 11.4102, "lng": 76.6950, "zone": "Western Ghats"},
    {"id": 34, "code": "DIS-34", "name": "Ranipet", "headquarters": "Ranipet", "lat": 12.9272, "lng": 79.3330, "zone": "North Zone"},
    {"id": 35, "code": "DIS-35", "name": "Tirupathur", "headquarters": "Tirupathur", "lat": 12.4996, "lng": 78.5736, "zone": "North Zone"},
    {"id": 36, "code": "DIS-36", "name": "Chengalpattu", "headquarters": "Chengalpattu", "lat": 12.6841, "lng": 79.9836, "zone": "North Zone"},
    {"id": 37, "code": "DIS-37", "name": "Kallakurichi", "headquarters": "Kallakurichi", "lat": 11.7384, "lng": 78.9639, "zone": "North-Central Zone"},
    {"id": 38, "code": "DIS-38", "name": "Tiruvallur", "headquarters": "Tiruvallur", "lat": 13.1432, "lng": 79.9083, "zone": "North Zone"},
]

# -------------------------------------------------------------
# 5 ESSENTIAL COMMODITIES
# -------------------------------------------------------------
COMMODITIES_CATALOGUE = [
    {"id": 1, "code": "RICE", "name": "Common PDS Rice (Boiled/Raw)", "unit": "kg", "buffer_pct": 10.0, "monthly_entitlement_per_card": 20.0},
    {"id": 2, "code": "WHEAT", "name": "Whole Wheat Grain", "unit": "kg", "buffer_pct": 10.0, "monthly_entitlement_per_card": 5.0},
    {"id": 3, "code": "SUGAR", "name": "Refined White Sugar", "unit": "kg", "buffer_pct": 10.0, "monthly_entitlement_per_card": 2.0},
    {"id": 4, "code": "TOOR_DAL", "name": "Special Grade Toor Dal", "unit": "kg", "buffer_pct": 10.0, "monthly_entitlement_per_card": 1.0},
    {"id": 5, "code": "PALM_OIL", "name": "Fortified Refined Palmolein Oil", "unit": "packet", "buffer_pct": 10.0, "monthly_entitlement_per_card": 1.0},
]


def generate_district_polygon(lat: float, lng: float, radius: float = 0.25, points: int = 12) -> List[List[float]]:
    """Generates an organic polygon around a centroid coordinate for GeoJSON representation."""
    coords = []
    for i in range(points):
        angle = (2 * math.pi / points) * i
        # slight variance for natural boundary look
        var = 0.85 + 0.3 * math.sin(i * 1.5)
        r = radius * var
        p_lat = round(lat + r * math.sin(angle), 5)
        p_lng = round(lng + (r / math.cos(math.radians(lat))) * math.cos(angle), 5)
        coords.append([p_lng, p_lat])
    # Close polygon
    coords.append(coords[0])
    return coords


def create_geojson_feature_collection() -> Dict[str, Any]:
    """Creates full Tamil Nadu GeoJSON FeatureCollection."""
    features = []
    for d in TN_38_DISTRICTS:
        poly = generate_district_polygon(d["lat"], d["lng"])
        feature = {
            "type": "Feature",
            "id": d["id"],
            "properties": {
                "id": d["id"],
                "code": d["code"],
                "name": d["name"],
                "headquarters": d["headquarters"],
                "zone": d["zone"],
                "centroid": [d["lat"], d["lng"]],
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [poly],
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def migrate_schema(engine):
    """Safely adds newly introduced columns to existing SQLite tables if not present."""
    from sqlalchemy import text
    with engine.connect() as conn:
        # Check and add columns
        migrations = [
            ("commodities", "monthly_entitlement_per_card", "FLOAT DEFAULT 20.0 NOT NULL"),
            ("districts", "lat", "FLOAT DEFAULT 11.1271"),
            ("districts", "lng", "FLOAT DEFAULT 78.6569"),
            ("districts", "geojson", "TEXT"),
            ("districts", "zone", "VARCHAR(50)"),
            ("godowns", "lat", "FLOAT"),
            ("godowns", "lng", "FLOAT"),
            ("shops", "card_count", "INTEGER DEFAULT 0 NOT NULL"),
            ("shops", "lat", "FLOAT"),
            ("shops", "lng", "FLOAT"),
            ("predictions", "item_id", "INTEGER DEFAULT 1"),
            ("predictions", "days_left", "FLOAT"),
            ("predictions", "predicted_stockout_date", "DATETIME"),
            ("predictions", "confidence", "FLOAT DEFAULT 0.95"),
            ("alerts", "item_id", "INTEGER"),
        ]
        for tbl, col, col_type in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}"))
                conn.commit()
                print(f"   [Migrate] Added {tbl}.{col}")
            except Exception:
                # Column already exists, ignore
                pass


def seed_database(scale: str = "demo"):
    """
    Seeds SQLite database with 38 districts, godowns, shops, and multi-commodity stock.
    scale: 'demo' generates ~100 godowns and ~800 shops for optimal speed and responsiveness.
           'full' generates ~180 godowns and ~1,500 shops.
    """
    print(">> Initializing Database Tables & Running Column Migrations...")
    migrate_schema(engine)
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    # Save GeoJSON file for frontend Leaflet rendering
    geojson_data = create_geojson_feature_collection()
    geojson_path = os.path.join(DATA_DIR, "tamil_nadu_districts.geojson")
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, indent=2)
    print(f">> Saved Tamil Nadu GeoJSON to {geojson_path}")

    # Set random seed
    random.seed(42)

    try:
        # 1. Commodities
        print(">> Seeding 5 Essential Commodities...")
        for c in COMMODITIES_CATALOGUE:
            existing = db.query(Commodity).filter(Commodity.id == c["id"]).first()
            if existing:
                existing.name = c["name"]
                existing.unit = c["unit"]
                existing.buffer_pct = c["buffer_pct"]
                existing.monthly_entitlement_per_card = c["monthly_entitlement_per_card"]
            else:
                db.add(Commodity(**c))
        db.commit()

        # 2. Districts
        print(">> Seeding 38 Tamil Nadu Districts...")
        district_objs = {}
        for d in TN_38_DISTRICTS:
            poly = generate_district_polygon(d["lat"], d["lng"])
            geojson_str = json.dumps({"type": "Polygon", "coordinates": [poly]})
            existing = db.query(District).filter(District.id == d["id"]).first()
            if existing:
                existing.name = d["name"]
                existing.headquarters = d["headquarters"]
                existing.lat = d["lat"]
                existing.lng = d["lng"]
                existing.geojson = geojson_str
                existing.zone = d["zone"]
                district_objs[d["id"]] = existing
            else:
                new_d = District(
                    id=d["id"],
                    code=d["code"],
                    name=d["name"],
                    headquarters=d["headquarters"],
                    lat=d["lat"],
                    lng=d["lng"],
                    geojson=geojson_str,
                    zone=d["zone"],
                )
                db.add(new_d)
                district_objs[d["id"]] = new_d
        db.commit()

        # 3. Godowns (3 to 6 per district)
        print(">> Seeding Central Buffer Granaries (Godowns)...")
        godown_count_per_district = 3 if scale == "demo" else 5
        godown_objs = []
        gdn_idx = 1

        for d in TN_38_DISTRICTS:
            d_id = d["id"]
            num_godowns = godown_count_per_district
            for i in range(1, num_godowns + 1):
                gdn_id = f"GDN-{gdn_idx:03d}"
                g_lat = round(d["lat"] + random.uniform(-0.10, 0.10), 5)
                g_lng = round(d["lng"] + random.uniform(-0.10, 0.10), 5)
                cap = random.choice([500000.0, 750000.0, 1000000.0, 1500000.0])
                opening = round(cap * random.uniform(0.35, 0.65), 0)

                existing = db.query(Godown).filter(Godown.id == gdn_id).first()
                if not existing:
                    g_name = f"{d['name']} Granary #{i} ({'Central' if i == 1 else 'Sub-Depot'})"
                    new_g = Godown(
                        id=gdn_id,
                        code=gdn_id,
                        name=g_name,
                        district_id=d_id,
                        capacity_kg=cap,
                        opening_stock_kg=opening,
                        lat=g_lat,
                        lng=g_lng,
                    )
                    db.add(new_g)
                    godown_objs.append(new_g)
                else:
                    existing.lat = g_lat
                    existing.lng = g_lng
                    godown_objs.append(existing)
                gdn_idx += 1
        db.commit()

        # 4. Fair Price Shops (15 to 25 per district)
        print(">> Seeding Fair Price Shops (FPS) with multi-commodity stock...")
        shops_per_godown = 5 if scale == "demo" else 8
        all_godowns = db.query(Godown).all()
        shop_idx = 1
        low_stock_counter = 0

        for g in all_godowns:
            for s_num in range(1, shops_per_godown + 1):
                s_id = f"FPS-{shop_idx:04d}"
                s_lat = round(g.lat + random.uniform(-0.06, 0.06), 5)
                s_lng = round(g.lng + random.uniform(-0.06, 0.06), 5)
                cards = random.randint(550, 1800)

                # Intentional edge cases: 8 shops in critical state
                is_critical = (low_stock_counter < 8 and random.random() < 0.15)
                if is_critical:
                    opening_rice = round(random.uniform(80.0, 220.0), 1)
                    low_stock_counter += 1
                else:
                    opening_rice = round(random.uniform(4000.0, 12000.0), 0)

                existing_s = db.query(Shop).filter(Shop.id == s_id).first()
                if not existing_s:
                    s_name = f"{g.name.split()[0]} FPS #{shop_idx}"
                    new_s = Shop(
                        id=s_id,
                        code=s_id,
                        name=s_name,
                        district_id=g.district_id,
                        godown_id=g.id,
                        beneficiaries_count=cards,
                        card_count=cards,
                        opening_stock_kg=opening_rice,
                        lat=s_lat,
                        lng=s_lng,
                    )
                    db.add(new_s)
                    target_shop = new_s
                else:
                    existing_s.lat = s_lat
                    existing_s.lng = s_lng
                    existing_s.card_count = cards
                    target_shop = existing_s

                # Seed stock levels for all 5 commodities for this shop
                for c in COMMODITIES_CATALOGUE:
                    com_id = c["id"]
                    if com_id == 1:
                        stock_qty = opening_rice
                    elif com_id == 2:  # Wheat
                        stock_qty = round(cards * 0.8 * random.uniform(0.4, 0.9), 1)
                    elif com_id == 3:  # Sugar
                        stock_qty = round(cards * 0.5 * random.uniform(0.3, 0.8), 1)
                    elif com_id == 4:  # Toor Dal
                        stock_qty = round(cards * 0.3 * random.uniform(0.3, 0.7), 1)
                    else:  # Palm Oil
                        stock_qty = round(cards * 0.4 * random.uniform(0.3, 0.7), 1)

                    existing_sl = db.query(StockLevel).filter(
                        StockLevel.location_type == "shop",
                        StockLevel.location_id == s_id,
                        StockLevel.item_id == com_id,
                    ).first()

                    if not existing_sl:
                        db.add(StockLevel(
                            location_type="shop",
                            location_id=s_id,
                            item_id=com_id,
                            qty_kg=stock_qty,
                            updated_at=datetime.now(timezone.utc),
                            source="system",
                        ))
                    else:
                        existing_sl.qty_kg = stock_qty

                shop_idx += 1

            if shop_idx % 100 == 0:
                db.commit()
                print(f"   ...seeded {shop_idx} shops")

        db.commit()

        # Seed Godown stock levels for all 5 commodities
        for g in all_godowns:
            for c in COMMODITIES_CATALOGUE:
                com_id = c["id"]
                mult = {1: 1.0, 2: 0.3, 3: 0.15, 4: 0.1, 5: 0.1}.get(com_id, 0.1)
                g_stock = round(g.opening_stock_kg * mult, 0)
                existing_sl = db.query(StockLevel).filter(
                    StockLevel.location_type == "godown",
                    StockLevel.location_id == g.id,
                    StockLevel.item_id == com_id,
                ).first()
                if not existing_sl:
                    db.add(StockLevel(
                        location_type="godown",
                        location_id=g.id,
                        item_id=com_id,
                        qty_kg=g_stock,
                        updated_at=datetime.now(timezone.utc),
                        source="system",
                    ))
        db.commit()

        # 5. Data Source Settings
        print(">> Setting up Data Source settings...")
        sources = [
            ("simulator", 1, "Simulated retail purchase and dispatch stream"),
            ("sensor", 0, "IoT Weighing Scale Electronic Sensor Feed"),
            ("ml_camera", 0, "Computer Vision Bag & Weight Detection Model"),
        ]
        for s_name, is_act, desc in sources:
            existing = db.query(DataSourceSetting).filter(DataSourceSetting.source_name == s_name).first()
            if not existing:
                db.add(DataSourceSetting(
                    source_name=s_name,
                    is_active=is_act,
                    config_json=json.dumps({"description": desc}),
                    updated_at=datetime.now(timezone.utc),
                ))
        db.commit()

        # 6. Trigger Critical Alerts for the 8 critical shops
        crit_shops = db.query(Shop).filter(Shop.opening_stock_kg < 300.0).limit(8).all()
        for s in crit_shops:
            alert_id = f"ALT-INIT-{uuid.uuid4().hex[:6].upper()}"
            if not db.query(Alert).filter(Alert.location_id == s.id, Alert.alert_type == "LOW_STOCK").first():
                db.add(Alert(
                    id=alert_id,
                    location_type="shop",
                    location_id=s.id,
                    item_id=1,
                    alert_type="LOW_STOCK",
                    severity="CRITICAL",
                    timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
                    explanation=f"Critical stock exhaustion: Only {s.opening_stock_kg:.1f} kg remaining. Restock recommended immediately.",
                    assigned_role="shop_manager",
                    status="OPEN",
                ))
        db.commit()

        print(f">> SUCCESS: Seeded {len(TN_38_DISTRICTS)} Districts, {len(all_godowns)} Godowns, {shop_idx - 1} Shops!")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database(scale="demo")
