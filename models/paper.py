"""Data models and schemas for Paper Trading system."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PaperOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(..., description="Stock ticker (e.g. TVSMOTOR, RELIANCE)")
    side: OrderSide = Field(default=OrderSide.BUY, description="BUY or SELL")
    quantity: int = Field(default=10, gt=0, description="Number of shares")
    entry_price: float | None = Field(default=None, description="Custom entry price or None for live market price")
    target_price: float | None = Field(default=None, description="Take profit target price")
    stop_loss_price: float | None = Field(default=None, description="Stop loss price")
    strategy: str = Field(default="Manual", description="Strategy or signal reason (e.g. Knoxville, Dual RSI, AI News)")
    notes: str = Field(default="", description="Optional trade notes or rationale")


class PaperCloseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    position_id: int = Field(..., description="Unique ID of the open paper position")
    exit_price: float | None = Field(default=None, description="Custom exit price or None for live market price")
    exit_reason: str = Field(default="Manual Close", description="Reason for closing the position")


class PaperPosition(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: int
    entry_price: float
    current_price: float
    target_price: float | None = None
    stop_loss_price: float | None = None
    strategy: str = "Manual"
    notes: str = ""
    entry_time: str
    invested_amount: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class PaperTradeRecord(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: int
    entry_price: float
    entry_time: str
    exit_price: float
    exit_time: str
    exit_reason: str
    strategy: str
    notes: str
    pnl_amount: float
    pnl_pct: float
    holding_duration: str


class PaperPortfolioSummary(BaseModel):
    initial_capital: float
    cash_balance: float
    invested_amount: float
    total_equity: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float
    realized_pnl_pct: float
    total_pnl: float
    total_pnl_pct: float
    win_rate_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    open_positions_count: int
