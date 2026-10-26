"""
Standalone CLI Live Simulator for Smart Ration System (Tamil Nadu).
Pushes simulated transactions through POST /api/ingest/transaction every few seconds.
"""

import sys
import time
import random
import argparse
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    httpx = None

API_URL_DEFAULT = "http://localhost:8000"


def run_simulator(api_url: str = API_URL_DEFAULT, interval: float = 2.0, max_events: int = 0):
    print("=" * 70)
    print("🌾 SMART RATION TRACKER — TAMIL NADU LIVE TRANSACTION SIMULATOR")
    print(f"📡 Target Ingestion Endpoint: {api_url}/api/ingest/transaction")
    print(f"⏱️  Simulation Interval: {interval:.1f}s")
    print("=" * 70)

    # 1. Fetch available shops and commodities
    client = httpx.Client(base_url=api_url, timeout=10.0) if httpx else None
    if not client:
        print("[ERROR] 'httpx' is required to run the standalone CLI simulator. Please install via: pip install httpx")
        sys.exit(1)

    print(f">> Connecting to Smart Ration API at {api_url}...")
    try:
        health_resp = client.get("/api/ingest/sources")
        if health_resp.status_code == 200:
            print(f">> Connected successfully! Source status: {health_resp.json().get('active_source', 'simulator')}")
        else:
            print(f">> Warning: Server responded with HTTP {health_resp.status_code}")
    except Exception as e:
        print(f"[!] Warning: Could not connect to {api_url}: {e}")
        print("    Ensure the FastAPI dev server is running on localhost:8000 (uvicorn app.main:app --port 8000)")
        print("    The simulator will retry on each interval...")

    # Rapid drain shops: bias towards a few shops to trigger alerts
    rapid_drain_shops = ["FPS-0003", "FPS-0012", "FPS-0025", "FPS-0044", "FPS-0062"]
    event_count = 0

    commodities = [
        {"id": 1, "name": "Rice", "weights": [5.0, 10.0, 15.0, 20.0], "prob": 0.60},
        {"id": 2, "name": "Wheat", "weights": [2.0, 5.0], "prob": 0.15},
        {"id": 3, "name": "Sugar", "weights": [1.0, 2.0], "prob": 0.15},
        {"id": 4, "name": "Toor Dal", "weights": [1.0], "prob": 0.05},
        {"id": 5, "name": "Palm Oil", "weights": [1.0], "prob": 0.05},
    ]

    try:
        while True:
            # Pick shop
            if random.random() < 0.35:
                shop_id = random.choice(rapid_drain_shops)
            else:
                shop_idx = random.randint(1, 50)
                shop_id = f"FPS-{shop_idx:04d}"

            # Pick commodity
            com = random.choices(commodities, weights=[c["prob"] for c in commodities], k=1)[0]
            qty = random.choice(com["weights"])
            bags = max(1, int(qty / 5.0)) if com["id"] == 1 else 1
            dist_id = random.randint(1, 38)
            card_no = f"TN-{dist_id:02d}-{random.randint(1000000, 9999999)}"

            payload = {
                "shop_id": shop_id,
                "item_id": com["id"],
                "qty_kg": qty,
                "bags": bags,
                "card_no": card_no,
                "source": "simulator",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                resp = client.post("/api/ingest/transaction", json=payload)
                if resp.status_code == 201:
                    data = resp.json()
                    alert_tag = ""
                    if data.get("alert_triggered"):
                        alert_tag = f" 🚨 [ALERT TRIGGERED: {data['alert_triggered']['type']} - {data['alert_triggered']['severity']}]"

                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] "
                        f"✅ {data['transaction_id']} | Shop: {shop_id} | Card: {card_no} | "
                        f"{com['name']}: {qty} kg ({bags} bags) | Stock Left: {data['remaining_stock_kg']:,.1f} kg{alert_tag}"
                    )
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ HTTP {resp.status_code}: {resp.text}")
            except Exception as ex:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Connection error: {ex}")

            event_count += 1
            if max_events > 0 and event_count >= max_events:
                print(f">> Reached maximum requested events ({max_events}). Stopping simulator.")
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n>> Simulator interrupted by user. Exiting cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live Smart Ration Simulator")
    parser.add_argument("--url", default=API_URL_DEFAULT, help="FastAPI backend URL")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between transactions")
    parser.add_argument("--events", type=int, default=0, help="Max events to simulate (0 = infinite)")
    args = parser.parse_args()

    run_simulator(api_url=args.url, interval=args.interval, max_events=args.events)
