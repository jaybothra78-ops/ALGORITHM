"""Data models and schemas for the Strategy Tester / Backtesting engine."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ExitReason(str, Enum):
    """Reason a simulated trade was closed."""
    TARGET_HIT = "Target Hit"
    STOP_LOSS_HIT = "Stop Loss Hit"
    OPEN_POSITION = "Open / Current Close"
    TIME_EXIT = "Time Exit"
    OPPOSITE_SIGNAL = "Opposite Signal"


class BacktestRequest(BaseModel):
    """Parameters for running a strategy backtest simulation."""
    model_config = ConfigDict(extra="ignore")

    symbol: str | None = Field(default=None, description="Specific single stock ticker to test (e.g. TVSMOTOR, RELIANCE)")
    strategy: str = Field(default="RSI", description="Strategy: RSI, RB_KnoxDiv, SMA_200, ALL")
    index: str | None = Field(default=None, description="Universe / Watchlist filter (FNO, Watchlist, custom, etc.)")
    target_pct: float | None = Field(default=5.0, ge=0.1, le=100.0, description="Take profit target percentage")
    stop_loss_pct: float | None = Field(default=2.0, ge=0.1, le=50.0, description="Stop loss percentage")
    max_holding_days: int | None = Field(default=None, description="Optional max days to hold position before market exit")
    signal_type: str | None = Field(default=None, description="Filter: buy, sell, or all")
    start_date: str | None = Field(default=None, description="Earliest entry date (YYYY-MM-DD)")
    end_date: str | None = Field(default=None, description="Latest entry date (YYYY-MM-DD)")
    period: str | None = Field(default="1y", description="Historical period window (e.g. 3mo, 6mo, 1y, 2y, 3y, 5y, max)")





class BacktestTrade(BaseModel):
    """Record of a single simulated trade execution."""
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Ticker symbol")
    strategy: str = Field(..., description="Strategy name")
    signal_type: str = Field(..., description="buy or sell")
    signal_date: str = Field(..., description="Date signal triggered (YYYY-MM-DD)")
    entry_date: str = Field(..., description="Date position was opened (YYYY-MM-DD)")
    entry_price: float = Field(..., description="Price at entry")
    exit_date: str = Field(..., description="Date position was closed (YYYY-MM-DD)")
    exit_price: float = Field(..., description="Price at exit")
    pnl_pct: float = Field(..., description="Percentage profit/loss on trade")
    pnl_amount: float = Field(..., description="Absolute price difference per share")
    target_price: float | None = Field(default=None, description="Take profit target price")
    stop_loss_price: float | None = Field(default=None, description="Stop loss price")
    exit_reason: str = Field(..., description="Reason for trade exit")
    holding_days: int = Field(..., description="Number of trading sessions position was open")
    outcome: str = Field(..., description="WIN or LOSS")


class BacktestSummary(BaseModel):
    """Consolidated performance metrics for the backtest run."""
    strategy: str = Field(..., description="Strategy evaluated")
    universe: str = Field(default="All Universes", description="Universe evaluated")
    target_pct: float | None = Field(default=None, description="Configured target percentage")
    stop_loss_pct: float | None = Field(default=None, description="Configured stop loss percentage")
    max_holding_days: int | None = Field(default=None, description="Configured max holding window")

    total_trades: int = Field(..., description="Total trades simulated")
    winning_trades: int = Field(..., description="Count of profitable trades")
    losing_trades: int = Field(..., description="Count of unprofitable trades")
    win_rate_pct: float = Field(..., description="Percentage of winning trades")
    net_return_pct: float = Field(..., description="Cumulative sum of trade returns (%)")
    profit_factor: float = Field(..., description="Gross Profit / Gross Loss ratio")
    max_drawdown_pct: float = Field(..., description="Maximum peak-to-trough drawdown (%)")
    avg_trade_pnl_pct: float = Field(..., description="Average trade return (%)")
    avg_win_pct: float = Field(..., description="Average winning trade return (%)")
    avg_loss_pct: float = Field(..., description="Average losing trade return (%)")
    avg_holding_days: float = Field(..., description="Average days in trade")


class BacktestResponse(BaseModel):
    """Full payload returned by the backtest execution endpoint."""
    summary: BacktestSummary
    trades: list[BacktestTrade] = Field(default_factory=list)
    execution_time_ms: float = Field(..., description="Calculation time in milliseconds")
