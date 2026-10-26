"""
Live Ration Transaction Simulator Service.
Generates realistic purchases at Fair Price Shops across Tamil Nadu.
Acts as one interchangeable data source feeding into POST /api/ingest/transaction.
"""

import threading
import time
import random
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Shop, Godown, Commodity, StockLevel, Transaction, StockMovement, Delivery, Alert


class LiveSimulatorManager:
    """
    Manages background simulation of shop transactions and godown dispatches.
    Can be started, stopped, and tuned dynamically via API.
    """
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_running: bool = False
        self.interval_seconds: float = 2.0
        self.transactions_generated: int = 0
        self.rapid_drain_shops: List[str] = []
        self.last_event: Optional[Dict[str, Any]] = None

    def start(self, interval_seconds: float = 2.0, rapid_drain_shop_count: int = 3):
        if self.is_running:
            return {"status": "already_running", "message": "Simulator is already active."}

        self.interval_seconds = max(0.5, interval_seconds)
        self._stop_event.clear()
        self.is_running = True

        # Pick random shops to drain faster to simulate edge-case alerts
        db: Session = SessionLocal()
        try:
            shop_ids = [s.id for s in db.query(Shop.id).limit(50).all()]
            if shop_ids:
                self.rapid_drain_shops = random.sample(shop_ids, min(rapid_drain_shop_count, len(shop_ids)))
        finally:
            db.close()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return {
            "status": "started",
            "interval_seconds": self.interval_seconds,
            "rapid_drain_shops": self.rapid_drain_shops,
        }

    def stop(self):
        if not self.is_running:
            return {"status": "not_running", "message": "Simulator is not currently running."}

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self.is_running = False
        return {
            "status": "stopped",
            "total_transactions_generated": self.transactions_generated,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "total_transactions_generated": self.transactions_generated,
            "rapid_drain_shops": self.rapid_drain_shops,
            "last_event": self.last_event,
        }

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.generate_single_step()
            except Exception as e:
                print(f"[LiveSimulator] Error in simulation step: {e}")

            # Sleep in small increments to allow fast stop
            wait_remaining = self.interval_seconds
            while wait_remaining > 0 and not self._stop_event.is_set():
                sleep_chunk = min(0.2, wait_remaining)
                time.sleep(sleep_chunk)
                wait_remaining -= sleep_chunk

    def generate_single_step(self) -> Optional[Dict[str, Any]]:
        """
        Executes one atomic simulated transaction or dispatch event.
        """
        db: Session = SessionLocal()
        try:
            # 88% chance: Shop Purchase Transaction
            # 12% chance: Godown Dispatch / Refill to Low Stock Shop
            event_type = "transaction" if random.random() < 0.88 else "refill_dispatch"

            if event_type == "transaction":
                return self._simulate_purchase(db)
            else:
                return self._simulate_refill(db)
        finally:
            db.close()

    def _simulate_purchase(self, db: Session) -> Optional[Dict[str, Any]]:
        # Pick shop (bias towards rapid-drain shops 35% of the time)
        if self.rapid_drain_shops and random.random() < 0.35:
            target_shop_id = random.choice(self.rapid_drain_shops)
            shop = db.query(Shop).filter(Shop.id == target_shop_id).first()
        else:
            shop = db.query(Shop).order_by(Shop.id).offset(random.randint(0, max(0, db.query(Shop).count() - 1))).first()

        if not shop:
            return None

        # Pick commodity: 60% Rice, 15% Sugar, 10% Wheat, 10% Toor Dal, 5% Palm Oil
        commodities = db.query(Commodity).all()
        if not commodities:
            return None

        com_weights = {
            "RICE": 0.60,
            "SUGAR": 0.15,
            "WHEAT": 0.10,
            "TOOR_DAL": 0.10,
            "PALM_OIL": 0.05,
        }
        chosen_com = random.choices(
            commodities,
            weights=[com_weights.get(c.code, 0.1) for c in commodities],
            k=1
        )[0]

        # Weights per commodity
        if chosen_com.code == "RICE":
            qty = random.choice([5.0, 10.0, 15.0, 20.0])
            bags = int(qty / 5.0) if qty >= 5 else 1
        elif chosen_com.code == "WHEAT":
            qty = random.choice([2.0, 5.0])
            bags = 1
        elif chosen_com.code == "SUGAR":
            qty = random.choice([1.0, 2.0])
            bags = 1
        elif chosen_com.code == "TOOR_DAL":
            qty = 1.0
            bags = 1
        else:  # PALM_OIL
            qty = 1.0
            bags = 1

        # Rapid drain shop buys slightly more
        if shop.id in self.rapid_drain_shops and chosen_com.code == "RICE":
            qty = min(35.0, qty * 1.5)
            bags = max(1, int(qty / 5.0))

        # Card number: TN-District-Card
        card_no = f"TN-{shop.district_id:02d}-{random.randint(1000000, 9999999)}"
        txn_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc)

        # Record Transaction
        txn = Transaction(
            id=txn_id,
            shop_id=shop.id,
            item_id=chosen_com.id,
            qty_kg=qty,
            bags=bags,
            card_no=card_no,
            source="simulator",
            timestamp=now,
        )
        db.add(txn)

        # Record Stock Movement for derived ledger
        mov = StockMovement(
            id=f"MOV-{uuid.uuid4().hex[:10].upper()}",
            location_type="shop",
            location_id=shop.id,
            movement_type="DISTRIBUTION",
            quantity_kg=qty,
            timestamp=now,
            reference_id=txn_id,
            created_by="simulator",
        )
        db.add(mov)

        # Update or create StockLevel snapshot
        stock_level = db.query(StockLevel).filter(
            StockLevel.location_type == "shop",
            StockLevel.location_id == shop.id,
            StockLevel.item_id == chosen_com.id,
        ).first()

        if stock_level:
            stock_level.qty_kg = max(0.0, stock_level.qty_kg - qty)
            stock_level.updated_at = now
            current_stock = stock_level.qty_kg
        else:
            current_stock = max(0.0, shop.opening_stock_kg - qty)
            stock_level = StockLevel(
                location_type="shop",
                location_id=shop.id,
                item_id=chosen_com.id,
                qty_kg=current_stock,
                updated_at=now,
                source="simulator",
            )
            db.add(stock_level)

        # Alert evaluation if stock is critically low
        alert_data = None
        if current_stock < 300.0:
            existing_alert = db.query(Alert).filter(
                Alert.location_type == "shop",
                Alert.location_id == shop.id,
                Alert.alert_type == "LOW_STOCK",
                Alert.status == "OPEN",
            ).first()
            if not existing_alert:
                alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
                alert_obj = Alert(
                    id=alert_id,
                    location_type="shop",
                    location_id=shop.id,
                    item_id=chosen_com.id,
                    alert_type="LOW_STOCK",
                    severity="CRITICAL" if current_stock < 150.0 else "HIGH",
                    timestamp=now,
                    explanation=f"Critical low stock of {chosen_com.name} ({current_stock:.1f} kg remaining). Restock recommended.",
                    assigned_role="shop_manager",
                    status="OPEN",
                )
                db.add(alert_obj)
                alert_data = {"id": alert_id, "type": "LOW_STOCK", "severity": alert_obj.severity}

        db.commit()
        self.transactions_generated += 1

        event_payload = {
            "event": "transaction",
            "transaction_id": txn_id,
            "shop_id": shop.id,
            "shop_name": shop.name,
            "district_id": shop.district_id,
            "item_id": chosen_com.id,
            "item_name": chosen_com.name,
            "qty_kg": qty,
            "bags": bags,
            "card_no": card_no,
            "remaining_stock_kg": current_stock,
            "source": "simulator",
            "timestamp": now.isoformat(),
            "alert": alert_data,
        }
        self.last_event = event_payload
        return event_payload

    def _simulate_refill(self, db: Session) -> Optional[Dict[str, Any]]:
        """Simulates Godown dispatch refilling a depleted shop."""
        low_stock_record = db.query(StockLevel).filter(
            StockLevel.location_type == "shop",
            StockLevel.qty_kg < 800.0,
        ).order_by(StockLevel.qty_kg.asc()).first()

        if not low_stock_record:
            return None

        shop = db.query(Shop).filter(Shop.id == low_stock_record.location_id).first()
        if not shop or not shop.godown_id:
            return None

        refill_qty = random.choice([2000.0, 3000.0, 5000.0])
        now = datetime.now(timezone.utc)

        # Replenish shop stock level
        low_stock_record.qty_kg += refill_qty
        low_stock_record.updated_at = now

        # Deduct from Godown stock level if present
        godown_stock = db.query(StockLevel).filter(
            StockLevel.location_type == "godown",
            StockLevel.location_id == shop.godown_id,
            StockLevel.item_id == low_stock_record.item_id,
        ).first()
        if godown_stock:
            godown_stock.qty_kg = max(0.0, godown_stock.qty_kg - refill_qty)
            godown_stock.updated_at = now

        # Create Delivery and Movement
        del_id = f"DEL-SIM-{uuid.uuid4().hex[:8].upper()}"
        delivery = Delivery(
            id=del_id,
            dispatch_movement_id=f"MOV-DISP-{uuid.uuid4().hex[:8].upper()}",
            from_godown_id=shop.godown_id,
            to_shop_id=shop.id,
            dispatched_date=now,
            expected_delivery_date=now,
            status="DELIVERED",
            dispatched_qty_kg=refill_qty,
            received_qty_kg=refill_qty,
            received_date=now,
            notes="Automated replenishment consignment from central buffer",
        )
        db.add(delivery)

        # Record Movements
        db.add(StockMovement(
            id=f"MOV-G-{uuid.uuid4().hex[:8].upper()}",
            location_type="godown",
            location_id=shop.godown_id,
            movement_type="DISPATCH",
            quantity_kg=refill_qty,
            timestamp=now,
            reference_id=del_id,
            created_by="simulator",
        ))
        db.add(StockMovement(
            id=f"MOV-S-{uuid.uuid4().hex[:8].upper()}",
            location_type="shop",
            location_id=shop.id,
            movement_type="CONFIRMED_DELIVERY",
            quantity_kg=refill_qty,
            timestamp=now,
            reference_id=del_id,
            created_by="simulator",
        ))

        # Auto-resolve any LOW_STOCK alert for this shop if restocked
        open_alerts = db.query(Alert).filter(
            Alert.location_type == "shop",
            Alert.location_id == shop.id,
            Alert.alert_type == "LOW_STOCK",
            Alert.status == "OPEN",
        ).all()
        for a in open_alerts:
            a.status = "RESOLVED"
            a.resolution_date = now
            a.verification_notes = f"Auto-resolved: Replenished with {refill_qty:.0f} kg from {shop.godown_id}"

        db.commit()

        event_payload = {
            "event": "refill_dispatch",
            "delivery_id": del_id,
            "godown_id": shop.godown_id,
            "shop_id": shop.id,
            "refill_qty_kg": refill_qty,
            "new_shop_stock_kg": low_stock_record.qty_kg,
            "timestamp": now.isoformat(),
        }
        self.last_event = event_payload
        return event_payload


# Singleton simulator instance
simulator_manager = LiveSimulatorManager()
