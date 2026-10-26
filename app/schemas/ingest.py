"""
Pydantic Schemas for Ingestion API.
Source-agnostic contract for Simulator, Smart Weighing Scales (IoT), and Camera ML bag/weight detection.
"""

from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class TransactionIngestRequest(BaseModel):
    shop_id: str = Field(..., min_length=1, description="Fair Price Shop ID, e.g., FPS-0001")
    item_id: int = Field(default=1, description="Commodity ID (1: Rice, 2: Wheat, 3: Sugar, 4: Toor Dal, 5: Palm Oil)")
    qty_kg: float = Field(..., gt=0, description="Measured transaction weight in kg or units")
    bags: int = Field(default=1, ge=1, description="Number of bags/packets dispensed")
    card_no: str = Field(..., min_length=4, description="Ration Card Number, e.g., TN-02-1984210")
    source: Literal["simulator", "sensor", "ml_camera"] = Field(
        default="simulator",
        description="Data provenance: simulator, weighing scale sensor, or camera ML"
    )
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))


class StockIngestRequest(BaseModel):
    location_type: Literal["godown", "shop"] = Field(...)
    location_id: str = Field(..., min_length=1, description="Godown ID or Shop ID")
    item_id: int = Field(default=1, description="Commodity ID")
    qty_kg: float = Field(..., ge=0, description="Audited or measured stock level")
    source: Literal["simulator", "sensor", "ml_camera"] = Field(
        default="simulator",
        description="Data provenance: simulator, weighing scale sensor, or camera ML"
    )
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransactionIngestResponse(BaseModel):
    status: str = "success"
    transaction_id: str
    shop_id: str
    item_id: int
    item_name: str
    qty_kg: float
    bags: int
    card_no: str
    remaining_stock_kg: float
    source: str
    timestamp: datetime
    alert_triggered: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class StockIngestResponse(BaseModel):
    status: str = "success"
    location_type: str
    location_id: str
    item_id: int
    item_name: str
    updated_stock_kg: float
    source: str
    timestamp: datetime
    anomaly_detected: bool = False
    alert_triggered: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class DataSourceStatusResponse(BaseModel):
    active_source: str
    available_sources: list[str] = ["simulator", "sensor", "ml_camera"]
    last_ingest_timestamp: Optional[datetime] = None
    total_transactions_ingested: int
    simulator_running: bool
