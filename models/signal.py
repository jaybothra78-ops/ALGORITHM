"""Domain data models and schemas for trading signals and screener items."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SignalType(str, Enum):
    """Trading signal direction."""
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


class StrategyType(str, Enum):
    """Supported technical strategies."""
    RSI = "RSI"
    RB_KNOXDIV = "RB_KnoxDiv"
    SMA_200 = "SMA_200"
    ALL = "ALL"


class ReasonCategory(str, Enum):
    """Classification for screener trigger reasons."""
    RSI_OVERSOLD = "RSI_Oversold"
    RSI_OVERBOUGHT = "RSI_Overbought"
    STRATEGY_SIGNAL = "Strategy_Signal"
    MA200 = "MA200"


class ReasonTag(BaseModel):
    """Structured trigger tag describing why an asset was flagged."""
    model_config = ConfigDict(frozen=True)

    category: str = Field(..., description="Category tag: RSI_Oversold, RSI_Overbought, Strategy_Signal, MA200")
    strategy: str | None = Field(default=None, description="Originating strategy name")
    type: str | None = Field(default=None, description="Signal type or sub-condition (e.g. touch, cross_up)")
    text: str = Field(..., description="Human-readable reason label")
    date: str | None = Field(default=None, description="Date the condition occurred (YYYY-MM-DD)")
    entry_price: float | None = Field(default=None, description="Reference price when condition occurred")


class LookbackItem(BaseModel):
    """Constituent result in the multi-condition lookback screener."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(..., description="Ticker symbol (e.g. RELIANCE, TCS)")
    status: str = Field(default="active", description="Status code")
    current_price: float = Field(..., description="Latest available closing price")
    rsi: float | None = Field(default=None, description="Latest RSI (14) value")
    rsi_ma: float | None = Field(default=None, description="Latest RSI Moving Average value")
    sma_200: float | None = Field(default=None, description="Latest 200-day Simple Moving Average")
    primary_type: str = Field(..., description="Primary classification: buy, sell, oversold, overbought, neutral")
    signal_date: str | None = Field(default=None, description="Most recent trigger date")
    reasons: list[ReasonTag] = Field(default_factory=list, description="List of all detected conditions")
    reason_summary: str = Field(default="", description="Consolidated summary string")
    index_membership: str = Field(default="", description="Universe memberships separated by '|'")


class LookbackResponse(BaseModel):
    """Payload returned by the lookback screener endpoint."""
    lookback_days: int = Field(..., description="Lookback window in trading sessions")
    rsi_length: int = Field(..., description="RSI period length")
    total_scanned: int = Field(..., description="Total universe symbols scanned")
    total_flagged: int = Field(..., description="Total symbols meeting at least one condition")
    items: list[LookbackItem] = Field(default_factory=list, description="Array of flagged stock opportunities")
    timestamp: float = Field(..., description="Epoch timestamp of generation")


class SignalRecord(BaseModel):
    """Database entity representing a confirmed daily trading signal."""
    id: int | None = Field(default=None, description="Database auto-increment primary key")
    strategy: str = Field(default="RSI", description="Strategy identifier")
    scan_date: str = Field(..., description="Date of the scan run")
    symbol: str = Field(..., description="Ticker symbol")
    signal_type: str = Field(..., description="buy or sell")
    signal_date: str = Field(..., description="Date the initial trigger condition occurred")
    signal_candle_low: float = Field(..., description="Low of the signal candle")
    confirmation_date: str = Field(..., description="Date signal confirmation was validated")
    entry_price: float = Field(..., description="Execution/entry price")
    stop_loss: float | None = Field(default=None, description="Calculated stop loss price")
    rsi_value: float | None = Field(default=None, description="RSI value at signal")
    rsi_ma_value: float | None = Field(default=None, description="RSI MA value at signal")
    index_membership: str = Field(default="", description="Universe memberships string")
    created_at: str | None = Field(default=None, description="Creation timestamp")


class ScanResponse(BaseModel):
    """Response returned upon completion of a daily scan execution."""
    scan_date: str = Field(..., description="Date scanned")
    strategy: str = Field(..., description="Strategy name scanned")
    stocks_scanned: int = Field(..., description="Count of stocks evaluated")
    signals_inserted: int = Field(..., description="Count of newly persisted signal records")
    errors: list[dict[str, Any]] = Field(default_factory=list, description="Non-fatal warning or error records")

