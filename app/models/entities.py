"""
SQLAlchemy 2.x ORM Models for Smart Ration Tracker.
Defines all entities for Tamil Nadu Public Distribution System.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    headquarters = Column(String(100), nullable=False)

    godowns = relationship("Godown", back_populates="district", cascade="all, delete-orphan")
    shops = relationship("Shop", back_populates="district", cascade="all, delete-orphan")


class Commodity(Base):
    __tablename__ = "commodities"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    unit = Column(String(20), default="kg", nullable=False)
    buffer_pct = Column(Float, default=10.0, nullable=False)


class Godown(Base):
    __tablename__ = "godowns"

    id = Column(String(30), primary_key=True, index=True)  # e.g., GDN-001
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False, index=True)
    capacity_kg = Column(Float, nullable=False)
    opening_stock_kg = Column(Float, nullable=False, default=0.0)

    district = relationship("District", back_populates="godowns")
    shops = relationship("Shop", back_populates="godown")
    outbound_deliveries = relationship("Delivery", back_populates="from_godown")


class Shop(Base):
    __tablename__ = "shops"

    id = Column(String(30), primary_key=True, index=True)  # e.g., FPS-0001
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False, index=True)
    godown_id = Column(String(30), ForeignKey("godowns.id"), nullable=False, index=True)
    beneficiaries_count = Column(Integer, default=0, nullable=False)
    opening_stock_kg = Column(Float, nullable=False, default=0.0)

    district = relationship("District", back_populates="shops")
    godown = relationship("Godown", back_populates="shops")
    inbound_deliveries = relationship("Delivery", back_populates="to_shop")
    monthly_distributions = relationship("MonthlyDistribution", back_populates="shop")
    predictions = relationship("Prediction", back_populates="shop")


class StockMovement(Base):
    """
    Immutable ledger of stock movements.
    Movement types:
      - Godown: RECEIPT, DISPATCH, ADJUSTMENT
      - Shop: CONFIRMED_DELIVERY, DISTRIBUTION, ADJUSTMENT
    """
    __tablename__ = "stock_movements"

    id = Column(String(50), primary_key=True, index=True)  # e.g., MOV-000001
    location_type = Column(String(20), nullable=False, index=True)  # 'godown' or 'shop'
    location_id = Column(String(30), nullable=False, index=True)
    movement_type = Column(String(30), nullable=False, index=True)  # RECEIPT, DISPATCH, etc.
    quantity_kg = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    reference_id = Column(String(100), nullable=True)  # delivery_id, order_no, adjustment reason
    created_by = Column(String(50), nullable=False)


class Delivery(Base):
    """
    Consignment tracking between Godown and Fair-Price Shop.
    Decoupled: A dispatch NEVER marks a delivery as received automatically.
    Statuses: PENDING, DELIVERED, DELAYED, RECEIVED_WITH_DIFFERENCE
    """
    __tablename__ = "deliveries"

    id = Column(String(50), primary_key=True, index=True)  # e.g., DEL-00001
    dispatch_movement_id = Column(String(50), nullable=False, index=True)
    from_godown_id = Column(String(30), ForeignKey("godowns.id"), nullable=False, index=True)
    to_shop_id = Column(String(30), ForeignKey("shops.id"), nullable=False, index=True)
    dispatched_date = Column(DateTime, nullable=False, index=True)
    expected_delivery_date = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), nullable=False, default="PENDING", index=True)
    dispatched_qty_kg = Column(Float, nullable=False)
    received_qty_kg = Column(Float, default=0.0, nullable=False)
    received_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    from_godown = relationship("Godown", back_populates="outbound_deliveries")
    to_shop = relationship("Shop", back_populates="inbound_deliveries")


class MonthlyDistribution(Base):
    __tablename__ = "monthly_distribution"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    shop_id = Column(String(30), ForeignKey("shops.id"), nullable=False, index=True)
    month_year = Column(String(7), nullable=False, index=True)  # YYYY-MM
    distributed_qty_kg = Column(Float, nullable=False)
    beneficiary_households_served = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shop = relationship("Shop", back_populates="monthly_distributions")


class Measurement(Base):
    """
    Physical inspection stock audit entries.
    """
    __tablename__ = "measurements"

    id = Column(String(50), primary_key=True, index=True)  # e.g., MEA-0001
    location_type = Column(String(20), nullable=False, index=True)  # 'godown' or 'shop'
    location_id = Column(String(30), nullable=False, index=True)
    measured_date = Column(DateTime, nullable=False, index=True)
    measured_stock_kg = Column(Float, nullable=False)
    inspector_name = Column(String(100), nullable=False)
    remarks = Column(Text, nullable=True)


class Prediction(Base):
    """
    Demand forecasts and replenishment recommendations.
    Always labeled as planning recommendations, not official allocations.
    """
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    shop_id = Column(String(30), ForeignKey("shops.id"), nullable=False, index=True)
    run_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    method = Column(String(50), default="rolling_average", nullable=False)
    lookback_months = Column(Integer, default=4, nullable=False)
    predicted_demand_kg = Column(Float, nullable=False)
    safety_buffer_kg = Column(Float, nullable=False)
    usable_stock_kg = Column(Float, nullable=False)
    planned_incoming_kg = Column(Float, nullable=False)
    recommended_replenishment_kg = Column(Float, nullable=False)
    inputs_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    shop = relationship("Shop", back_populates="predictions")


class Alert(Base):
    """
    System alerts for discrepancies, low stock, missing data, delays, etc.
    Neutral wording rule: Never blame any person or shop.
    Statuses: OPEN, UNDER_VERIFICATION, RESOLVED
    """
    __tablename__ = "alerts"

    id = Column(String(50), primary_key=True, index=True)  # e.g., ALT-00001
    location_type = Column(String(20), nullable=False, index=True)
    location_id = Column(String(30), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)  # LOW_STOCK, REPLENISHMENT_REQUIRED, etc.
    severity = Column(String(20), nullable=False)                # LOW, MEDIUM, HIGH, CRITICAL
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    explanation = Column(Text, nullable=False)
    assigned_role = Column(String(50), nullable=False)
    status = Column(String(30), default="OPEN", nullable=False, index=True)
    verification_notes = Column(Text, nullable=True)
    resolution_date = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, index=True)
    district_id = Column(Integer, nullable=True)
    godown_id = Column(String(30), nullable=True)
    shop_id = Column(String(30), nullable=True)
    full_name = Column(String(120), nullable=False)


class AuditLog(Base):
    """
    Immutable audit trail for every create, update, or reconciliation action.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(50), nullable=False, index=True)
    details = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
