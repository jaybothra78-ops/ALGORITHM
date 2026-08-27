"""Application configuration and settings."""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment or defaults."""

    # Project paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATABASE_PATH: Path = BASE_DIR / "scanner.db"
    WATCHLIST_PATH: Path = BASE_DIR / "config" / "watchlist.txt"
    FNO_PATH: Path = BASE_DIR / "config" / "fno_watchlist.txt"
    FALLBACK_PATH: Path = BASE_DIR / "config" / "universe_fallback.json"
    CUSTOM_WATCHLISTS_PATH: Path = BASE_DIR / "config" / "custom_watchlists.json"


    # Market data settings
    DATA_PERIOD: str = "1y"
    DATA_INTERVAL: str = "1d"
    CACHE_TTL_SECONDS: float = 900.0  # 15 minutes in-memory cache
    YFINANCE_TIMEOUT: int = 30
    MIN_OHLC_ROWS: int = 80

    # Indicator defaults
    RSI_LENGTH: int = 14
    RSI_MA_LENGTH: int = 14
    RSI_OVERBOUGHT: float = 70.0
    RSI_OVERSOLD: float = 30.0

    # RB Knoxville defaults
    KNOX_LOOKBACK: int = 150
    KNOX_MOM_PERIOD: int = 20
    KNOX_RSI_PERIOD: int = 21

    # Server settings
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
