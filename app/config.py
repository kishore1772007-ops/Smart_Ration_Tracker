"""
Application Configuration and Business Thresholds.
Centralizes all PDS business rules and operational tolerances.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Smart Ration Tracker"
    DEMO_BANNER_TEXT: str = "Demo Dataset — Not Official Government Data"
    
    # Database
    DATABASE_URL: str = "sqlite:///./smart_ration.db"
    
    # Business Logic Thresholds (from PRD spec)
    SAFETY_BUFFER_PCT: float = 10.0            # 10% safety buffer for replenishment
    LOW_STOCK_THRESHOLD_PCT: float = 0.20      # < 20% of avg monthly distribution
    CRITICAL_STOCK_THRESHOLD_PCT: float = 0.10 # < 10% of avg monthly distribution
    DISCREPANCY_TOLERANCE_PCT: float = 0.02    # 2% tolerance on physical inspections
    DELAY_TOLERANCE_DAYS: int = 1              # 1 day overdue marks delivery as delayed
    DEFAULT_FORECAST_LOOKBACK_MONTHS: int = 4  # Default 4 months (configurable to 6)
    
    # Neutral wording standard
    DISCREPANCY_ALERT_LABEL: str = "Verification requested on stock balance"
    
    # Authentication & JWT Security
    SECRET_KEY: str = "tnpds-smart-ration-tracker-jwt-secret-key-2026-secure"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    DEMO_DEFAULT_PASSWORD: str = "demo123"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
