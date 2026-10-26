"""
Ingestion API Router & Live Data Source Handlers.
Contract endpoint for Simulator, Smart Weighing Scales (IoT), and Camera ML models.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import (
    Shop,
    Godown,
    Commodity,
    StockLevel,
    Transaction,
    StockMovement,
    Alert,
    DataSourceSetting,
    User,
)
from app.schemas.ingest import (
    TransactionIngestRequest,
    TransactionIngestResponse,
    StockIngestRequest,
    StockIngestResponse,
    DataSourceStatusResponse,
)
from app.services.simulator_service import simulator_manager
from app.services.auth import get_optional_current_user

router = APIRouter(prefix="/api", tags=["Ingestion & Live Feed"])


@router.post(
    "/ingest/transaction",
    response_model=TransactionIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Retail Purchase Transaction (Simulator / Sensor / Camera ML)"
)
def ingest_transaction(
    payload: TransactionIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Core data contract for point-of-sale transactions.
    Works identically for the dummy simulator, weighing sensor scale, or camera ML bag detector.
    - Decrements stock balance
    - Appends to immutable movement ledger
    - Triggers real-time low-stock alerts if critical
    """
    shop = db.query(Shop).filter(Shop.id == payload.shop_id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop '{payload.shop_id}' not found in registry."
        )

    commodity = db.query(Commodity).filter(Commodity.id == payload.item_id).first()
    if not commodity:
        # Fallback to commodity 1 (Rice)
        commodity = db.query(Commodity).filter(Commodity.id == 1).first()
        if not commodity:
            commodity = db.query(Commodity).first()

    txn_id = f"TXN-{uuid.uuid4().hex[:10].upper()}"
    ts = payload.timestamp or datetime.now(timezone.utc)

    # 1. Record transaction
    txn = Transaction(
        id=txn_id,
        shop_id=shop.id,
        item_id=commodity.id if commodity else 1,
        qty_kg=payload.qty_kg,
        bags=payload.bags,
        card_no=payload.card_no,
        source=payload.source,
        timestamp=ts,
    )
    db.add(txn)

    # 2. Append to derived stock movement ledger
    mov = StockMovement(
        id=f"MOV-{uuid.uuid4().hex[:10].upper()}",
        location_type="shop",
        location_id=shop.id,
        movement_type="DISTRIBUTION",
        quantity_kg=payload.qty_kg,
        timestamp=ts,
        reference_id=txn_id,
        created_by=payload.source,
    )
    db.add(mov)

    # 3. Update or initialize stock_levels snapshot
    stock_level = db.query(StockLevel).filter(
        StockLevel.location_type == "shop",
        StockLevel.location_id == shop.id,
        StockLevel.item_id == (commodity.id if commodity else 1),
    ).first()

    if stock_level:
        stock_level.qty_kg = max(0.0, stock_level.qty_kg - payload.qty_kg)
        stock_level.updated_at = ts
        remaining_stock = stock_level.qty_kg
    else:
        remaining_stock = max(0.0, shop.opening_stock_kg - payload.qty_kg)
        stock_level = StockLevel(
            location_type="shop",
            location_id=shop.id,
            item_id=commodity.id if commodity else 1,
            qty_kg=remaining_stock,
            updated_at=ts,
            source=payload.source,
        )
        db.add(stock_level)

    # 4. Alert Engine: check low stock condition
    alert_info = None
    if remaining_stock < 300.0:
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
                item_id=commodity.id if commodity else 1,
                alert_type="LOW_STOCK",
                severity="CRITICAL" if remaining_stock < 150.0 else "HIGH",
                timestamp=ts,
                explanation=f"Critical stock exhaustion: {remaining_stock:.1f} kg of {commodity.name if commodity else 'stock'} remaining.",
                assigned_role="shop_manager",
                status="OPEN",
            )
            db.add(alert_obj)
            alert_info = {"id": alert_id, "type": "LOW_STOCK", "severity": alert_obj.severity}

    db.commit()

    return TransactionIngestResponse(
        status="success",
        transaction_id=txn_id,
        shop_id=shop.id,
        item_id=commodity.id if commodity else 1,
        item_name=commodity.name if commodity else "Commodity",
        qty_kg=payload.qty_kg,
        bags=payload.bags,
        card_no=payload.card_no,
        remaining_stock_kg=round(remaining_stock, 2),
        source=payload.source,
        timestamp=ts,
        alert_triggered=alert_info,
    )


@router.post(
    "/ingest/stock",
    response_model=StockIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest Stock Audit or Sensor Level (Godown or Shop)"
)
def ingest_stock(
    payload: StockIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingests physical stock reading from electronic weighing scale or physical audit.
    Detects abnormal sudden drops (leakage/theft anomalies) without matching transactions.
    """
    ts = payload.timestamp or datetime.now(timezone.utc)
    item_id = payload.item_id or 1
    commodity = db.query(Commodity).filter(Commodity.id == item_id).first()

    stock_level = db.query(StockLevel).filter(
        StockLevel.location_type == payload.location_type,
        StockLevel.location_id == payload.location_id,
        StockLevel.item_id == item_id,
    ).first()

    anomaly = False
    alert_info = None

    if stock_level:
        prev_qty = stock_level.qty_kg
        diff = prev_qty - payload.qty_kg
        # If sudden drop > 500kg or >= 20% without matching transactions
        if diff >= 500.0 or (prev_qty > 0 and (diff / prev_qty) >= 0.20):
            anomaly = True
            existing_alert = db.query(Alert).filter(
                Alert.location_type == payload.location_type,
                Alert.location_id == payload.location_id,
                Alert.alert_type == "STOCK_DISCREPANCY",
                Alert.status == "OPEN",
            ).first()
            if not existing_alert:
                alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
                alert_obj = Alert(
                    id=alert_id,
                    location_type=payload.location_type,
                    location_id=payload.location_id,
                    item_id=item_id,
                    alert_type="STOCK_DISCREPANCY",
                    severity="CRITICAL",
                    timestamp=ts,
                    explanation=f"Verification requested on stock balance: Unexplained stock reduction of {diff:,.1f} kg detected.",
                    assigned_role="district_officer" if payload.location_type == "godown" else "shop_manager",
                    status="OPEN",
                )
                db.add(alert_obj)
                alert_info = {"id": alert_id, "type": "STOCK_DISCREPANCY", "severity": "CRITICAL"}
            else:
                alert_info = {"id": existing_alert.id, "type": existing_alert.alert_type, "severity": existing_alert.severity, "status": "existing"}

        stock_level.qty_kg = payload.qty_kg
        stock_level.updated_at = ts
        stock_level.source = payload.source
    else:
        stock_level = StockLevel(
            location_type=payload.location_type,
            location_id=payload.location_id,
            item_id=item_id,
            qty_kg=payload.qty_kg,
            updated_at=ts,
            source=payload.source,
        )
        db.add(stock_level)

    db.commit()

    return StockIngestResponse(
        status="success",
        location_type=payload.location_type,
        location_id=payload.location_id,
        item_id=item_id,
        item_name=commodity.name if commodity else "Commodity",
        updated_stock_kg=round(payload.qty_kg, 2),
        source=payload.source,
        timestamp=ts,
        anomaly_detected=anomaly,
        alert_triggered=alert_info,
    )


@router.get(
    "/transactions/live",
    summary="Get Real-Time Transactions Feed"
)
def get_live_transactions(
    limit: int = Query(50, ge=1, le=200),
    shop_id: Optional[str] = None,
    item_id: Optional[int] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns live stream of purchases with shop details, item, bag count, and weight.
    """
    query = db.query(Transaction, Shop, Commodity).join(
        Shop, Transaction.shop_id == Shop.id
    ).join(
        Commodity, Transaction.item_id == Commodity.id
    )

    if shop_id:
        query = query.filter(Transaction.shop_id == shop_id)
    if item_id:
        query = query.filter(Transaction.item_id == item_id)
    if source:
        query = query.filter(Transaction.source == source)

    records = query.order_by(desc(Transaction.timestamp)).limit(limit).all()

    results = []
    for txn, shop, com in records:
        results.append({
            "id": txn.id,
            "shop_id": shop.id,
            "shop_name": shop.name,
            "district_id": shop.district_id,
            "item_id": com.id,
            "item_name": com.name,
            "item_unit": com.unit,
            "qty_kg": txn.qty_kg,
            "bags": txn.bags,
            "card_no": txn.card_no,
            "source": txn.source,
            "timestamp": txn.timestamp.isoformat() if txn.timestamp else None,
        })

    return {
        "count": len(results),
        "transactions": results,
    }


@router.get(
    "/ingest/sources",
    response_model=DataSourceStatusResponse,
    summary="Get Data Source Settings & Ingest Stats"
)
def get_data_sources_status(db: Session = Depends(get_db)):
    active_setting = db.query(DataSourceSetting).filter(DataSourceSetting.is_active == 1).first()
    active_name = active_setting.source_name if active_setting else "simulator"

    total_txns = db.query(Transaction).count()
    last_txn = db.query(Transaction.timestamp).order_by(desc(Transaction.timestamp)).first()

    return DataSourceStatusResponse(
        active_source=active_name,
        available_sources=["simulator", "sensor", "ml_camera"],
        last_ingest_timestamp=last_txn[0] if last_txn else None,
        total_transactions_ingested=total_txns,
        simulator_running=simulator_manager.is_running,
    )


@router.post(
    "/ingest/source/activate",
    summary="Switch Active Data Source (Simulator / Sensor / Camera ML)"
)
def activate_data_source(
    source_name: str = Query(..., pattern="^(simulator|sensor|ml_camera)$"),
    db: Session = Depends(get_db),
):
    # Reset all to inactive
    db.query(DataSourceSetting).update({DataSourceSetting.is_active: 0})
    setting = db.query(DataSourceSetting).filter(DataSourceSetting.source_name == source_name).first()
    if setting:
        setting.is_active = 1
        setting.updated_at = datetime.now(timezone.utc)
    else:
        setting = DataSourceSetting(
            source_name=source_name,
            is_active=1,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(setting)

    db.commit()
    return {
        "status": "success",
        "active_source": source_name,
        "message": f"Data source switched to '{source_name}'. Future transactions will tag this provenance."
    }


# -------------------------------------------------------------------------
# SIMULATOR CONTROLS
# -------------------------------------------------------------------------
@router.post("/simulator/start", summary="Start Live Background Simulator")
def start_simulator(
    interval: float = Query(2.0, ge=0.5, le=10.0, description="Seconds between generated transactions"),
    rapid_drain_count: int = Query(3, ge=1, le=10, description="Number of shops to drain rapidly to create alerts"),
):
    return simulator_manager.start(interval_seconds=interval, rapid_drain_shop_count=rapid_drain_count)


@router.post("/simulator/stop", summary="Stop Live Background Simulator")
def stop_simulator():
    return simulator_manager.stop()


@router.get("/simulator/status", summary="Check Live Simulator Status")
def get_simulator_status():
    return simulator_manager.get_status()


@router.post("/simulator/tick", summary="Trigger Single Simulated Transaction Step (For Testing)")
def trigger_simulator_tick():
    result = simulator_manager.generate_single_step()
    return {"status": "success", "event": result}
