"""Data schemas and domain models for signals and screener results."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"


class StrategyType(str, Enum):
    RSI = "RSI"
    RB_KNOXDIV = "RB_KnoxDiv"
    SMA_200 = "SMA_200"
    ALL = "ALL"


class ReasonTag(BaseModel):
    category: str = Field(..., description="Category: RSI_Oversold, RSI_Overbought, Strategy_Signal, MA200")
    strategy: str | None = None
    type: str | None = None
    text: str
    date: str | None = None
    entry_price: float | None = None


class LookbackItem(BaseModel):
    symbol: str
    status: str = "active"
    current_price: float
    rsi: float | None = None
    rsi_ma: float | None = None
    sma_200: float | None = None
    primary_type: str
    signal_date: str | None = None
    reasons: list[ReasonTag] = Field(default_factory=list)
    reason_summary: str = ""
    index_membership: str = ""



class LookbackResponse(BaseModel):
    lookback_days: int
    rsi_length: int
    total_scanned: int
    total_flagged: int
    items: list[LookbackItem]
    timestamp: float


class SignalRecord(BaseModel):
    id: int | None = None
    strategy: str = "RSI"
    scan_date: str
    symbol: str
    signal_type: str
    signal_date: str
    signal_candle_low: float
    confirmation_date: str
    entry_price: float
    stop_loss: float | None = None
    rsi_value: float | None = None
    rsi_ma_value: float | None = None
    index_membership: str = ""
    created_at: str | None = None


class ScanResponse(BaseModel):
    scan_date: str
    strategy: str
    stocks_scanned: int
    signals_inserted: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
