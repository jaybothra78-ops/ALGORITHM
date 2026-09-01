"""Data models and schemas for Paper Trading system."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class InstrumentType(str, Enum):
    EQUITY = "EQUITY"
    OPTION = "OPTION"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PaperOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    symbol: str = Field(..., description="Stock or Index ticker (e.g. TVSMOTOR, RELIANCE, NIFTY)")
    instrument_type: InstrumentType = Field(default=InstrumentType.EQUITY, description="EQUITY or OPTION")
    option_type: OptionType | None = Field(default=None, description="CE (Call) or PE (Put) if OPTION")
    strike_price: float | None = Field(default=None, description="Strike price if OPTION")
    expiry_date: str | None = Field(default=None, description="Expiry date string (YYYY-MM-DD) if OPTION")
    lot_size: int = Field(default=1, gt=0, description="Lot size per contract")
    contracts: int = Field(default=1, gt=0, description="Number of lots / contracts")

    side: OrderSide = Field(default=OrderSide.BUY, description="BUY or SELL")
    quantity: int = Field(default=10, gt=0, description="Total number of shares or total units (lots * lot_size)")
    entry_price: float | None = Field(default=None, description="Custom entry price/premium or None for live market price")
    target_price: float | None = Field(default=None, description="Take profit target price/premium")
    stop_loss_price: float | None = Field(default=None, description="Stop loss price/premium")
    strategy: str = Field(default="Manual", description="Strategy or signal reason (e.g. Knoxville, Dual RSI, Options Momentum)")
    notes: str = Field(default="", description="Optional trade notes or rationale")


class PaperCloseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    position_id: int = Field(..., description="Unique ID of the open paper position")
    exit_price: float | None = Field(default=None, description="Custom exit price/premium or None for live market price")
    exit_reason: str = Field(default="Manual Close", description="Reason for closing the position")


class PaperPosition(BaseModel):
    id: int
    symbol: str
    display_symbol: str
    instrument_type: str = "EQUITY"
    option_type: str | None = None
    strike_price: float | None = None
    expiry_date: str | None = None
    lot_size: int = 1
    contracts: int = 1
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
    display_symbol: str
    instrument_type: str = "EQUITY"
    option_type: str | None = None
    strike_price: float | None = None
    expiry_date: str | None = None
    lot_size: int = 1
    contracts: int = 1
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

