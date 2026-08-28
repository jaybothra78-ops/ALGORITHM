"""High-performance Strategy Tester and Trade Simulation Engine."""
from __future__ import annotations

import time
from typing import Any
import numpy as np
import pandas as pd

from core.logging import logger
from models.backtest import (
    BacktestRequest,
    BacktestResponse,
    BacktestSummary,
    BacktestTrade,
    ExitReason,
)
from services.indicators import ma200_signals, rb_knox_divergence, rsi_signals
from services.market_data import MarketDataProvider
from services.universe import load_universe


class BacktesterEngine:
    """Simulate and backtest technical trading strategies on historical market data."""

    @classmethod
    def run_backtest(cls, request: BacktestRequest) -> BacktestResponse:
        """Execute strategy simulation across the selected universe."""
        t_start = time.perf_counter()

        universe = load_universe()
        if request.index:
            target_universe = {s: m for s, m in universe.items() if request.index in m}
        else:
            target_universe = universe

        all_symbols = list(target_universe.keys())
        ohlc_data = MarketDataProvider.get_universe_ohlc(all_symbols)

        all_trades: list[BacktestTrade] = []
        strategy_filter = request.strategy.upper()

        for symbol in all_symbols:
            if symbol not in ohlc_data:
                continue

            df = ohlc_data[symbol]
            if len(df) < 50:
                continue

            # Run simulations per requested strategy
            if strategy_filter in ("RSI", "ALL"):
                all_trades.extend(cls._backtest_rsi(symbol, df, request))

            if strategy_filter in ("RB_KNOXDIV", "KNOXVILLE", "ALL"):
                all_trades.extend(cls._backtest_knoxville(symbol, df, request))

            if strategy_filter in ("SMA_200", "200MA", "ALL"):
                all_trades.extend(cls._backtest_ma200(symbol, df, request))

        # Sort trades chronologically by entry date
        all_trades.sort(key=lambda t: (t.entry_date, t.symbol))

        # Filter by signal_type if requested (buy vs sell)
        if request.signal_type:
            st_filter = request.signal_type.lower()
            all_trades = [t for t in all_trades if t.signal_type.lower() == st_filter]

        summary = cls._compute_summary(all_trades, request, universe_label=request.index or "All Universes")
        exec_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return BacktestResponse(
            summary=summary,
            trades=all_trades,
            execution_time_ms=exec_ms,
        )

    @classmethod
    def _backtest_rsi(
        cls, symbol: str, df: pd.DataFrame, req: BacktestRequest
    ) -> list[BacktestTrade]:
        """Simulate RSI Dual Extreme Strategy."""
        trades: list[BacktestTrade] = []
        sigs = rsi_signals(df)
        n = len(df)

        for i in range(1, n - 1):
            row_sig = sigs.iloc[i]
            # Buy condition: Both RSI and RSI-MA < 30
            if bool(row_sig["buy_signal"]):
                trade = cls._simulate_trade(
                    symbol=symbol,
                    strategy="RSI",
                    signal_type="buy",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                    max_holding_days=req.max_holding_days,
                )
                if trade:
                    trades.append(trade)

            # Sell condition: Both RSI and RSI-MA > 70
            elif bool(row_sig["sell_signal"]):
                trade = cls._simulate_trade(
                    symbol=symbol,
                    strategy="RSI",
                    signal_type="sell",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                    max_holding_days=req.max_holding_days,
                )
                if trade:
                    trades.append(trade)

        return trades

    @classmethod
    def _backtest_knoxville(
        cls, symbol: str, df: pd.DataFrame, req: BacktestRequest
    ) -> list[BacktestTrade]:
        """Simulate RB Knoxville Divergence with Next-Candle Confirmation."""
        trades: list[BacktestTrade] = []
        sigs = rb_knox_divergence(df)
        n = len(df)

        for i in range(1, n - 2):
            row_sig = sigs.iloc[i]
            # Buy Breakout Confirmation: Next close > signal close
            if bool(row_sig["buy_signal"]) and df["Close"].iloc[i + 1] > df["Close"].iloc[i]:
                trade = cls._simulate_trade(
                    symbol=symbol,
                    strategy="RB_KnoxDiv",
                    signal_type="buy",
                    df=df,
                    signal_idx=i,
                    entry_idx=i + 1,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                    max_holding_days=req.max_holding_days,
                )
                if trade:
                    trades.append(trade)

            # Sell Breakout Confirmation: Next close < signal close
            elif bool(row_sig["sell_signal"]) and df["Close"].iloc[i + 1] < df["Close"].iloc[i]:
                trade = cls._simulate_trade(
                    symbol=symbol,
                    strategy="RB_KnoxDiv",
                    signal_type="sell",
                    df=df,
                    signal_idx=i,
                    entry_idx=i + 1,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                    max_holding_days=req.max_holding_days,
                )
                if trade:
                    trades.append(trade)

        return trades

    @classmethod
    def _backtest_ma200(
        cls, symbol: str, df: pd.DataFrame, req: BacktestRequest
    ) -> list[BacktestTrade]:
        """Simulate 200-Day Moving Average Crossover / Touch."""
        trades: list[BacktestTrade] = []
        sigs = ma200_signals(df)
        n = len(df)

        for i in range(200, n - 1):
            row_sig = sigs.iloc[i]
            if bool(row_sig.get("cross_up", False)):
                trade = cls._simulate_trade(
                    symbol=symbol,
                    strategy="SMA_200",
                    signal_type="buy",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                    max_holding_days=req.max_holding_days,
                )
                if trade:
                    trades.append(trade)

            elif bool(row_sig.get("cross_down", False)):
                trade = cls._simulate_trade(
                    symbol=symbol,
                    strategy="SMA_200",
                    signal_type="sell",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                    max_holding_days=req.max_holding_days,
                )
                if trade:
                    trades.append(trade)

        return trades

    @staticmethod
    def _simulate_trade(
        symbol: str,
        strategy: str,
        signal_type: str,
        df: pd.DataFrame,
        signal_idx: int,
        entry_idx: int,
        target_pct: float | None,
        stop_loss_pct: float | None,
        max_holding_days: int,
    ) -> BacktestTrade | None:
        """Simulate the forward price action of an opened position."""
        n = len(df)
        if entry_idx >= n:
            return None

        entry_date = df.index[entry_idx].date().isoformat()
        signal_date = df.index[signal_idx].date().isoformat()
        entry_price = float(df["Close"].iloc[entry_idx])
        if entry_price <= 0:
            return None

        is_buy = signal_type.lower() == "buy"

        # Define targets and stops
        target_price = None
        if target_pct is not None and target_pct > 0:
            target_price = entry_price * (1.0 + target_pct / 100.0) if is_buy else entry_price * (1.0 - target_pct / 100.0)

        stop_price = None
        if stop_loss_pct is not None and stop_loss_pct > 0:
            stop_price = entry_price * (1.0 - stop_loss_pct / 100.0) if is_buy else entry_price * (1.0 + stop_loss_pct / 100.0)

        # Track forward sessions
        exit_idx = entry_idx
        exit_price = entry_price
        exit_reason = ExitReason.TIME_EXIT
        max_idx = min(entry_idx + max_holding_days, n - 1)

        # Forward scan day-by-day
        for step, cur_idx in enumerate(range(entry_idx + 1, max_idx + 1), start=1):
            cur_high = float(df["High"].iloc[cur_idx])
            cur_low = float(df["Low"].iloc[cur_idx])
            cur_close = float(df["Close"].iloc[cur_idx])

            if is_buy:
                # 1. Stop Loss Check (Low touches or pierces stop)
                if stop_price is not None and cur_low <= stop_price:
                    exit_idx = cur_idx
                    exit_price = min(stop_price, float(df["Open"].iloc[cur_idx]))
                    exit_reason = ExitReason.STOP_LOSS_HIT
                    break

                # 2. Target Check (High touches or exceeds target)
                if target_price is not None and cur_high >= target_price:
                    exit_idx = cur_idx
                    exit_price = max(target_price, float(df["Open"].iloc[cur_idx]))
                    exit_reason = ExitReason.TARGET_HIT
                    break
            else:
                # Short/Sell:
                # 1. Stop Loss Check (High touches or pierces stop)
                if stop_price is not None and cur_high >= stop_price:
                    exit_idx = cur_idx
                    exit_price = max(stop_price, float(df["Open"].iloc[cur_idx]))
                    exit_reason = ExitReason.STOP_LOSS_HIT
                    break

                # 2. Target Check (Low touches or pierces target)
                if target_price is not None and cur_low <= target_price:
                    exit_idx = cur_idx
                    exit_price = min(target_price, float(df["Open"].iloc[cur_idx]))
                    exit_reason = ExitReason.TARGET_HIT
                    break

            # If reached max holding days, exit at close
            if cur_idx == max_idx:
                exit_idx = cur_idx
                exit_price = cur_close
                exit_reason = ExitReason.TIME_EXIT

        # If trade could not step forward (e.g. at latest candle)
        if exit_idx == entry_idx:
            exit_idx = min(entry_idx + 1, n - 1)
            exit_price = float(df["Close"].iloc[exit_idx])

        exit_date = df.index[exit_idx].date().isoformat()
        holding_days = max(1, exit_idx - entry_idx)

        # Calculate PnL %
        if is_buy:
            pnl_amount = exit_price - entry_price
            pnl_pct = (pnl_amount / entry_price) * 100.0
        else:
            pnl_amount = entry_price - exit_price
            pnl_pct = (pnl_amount / entry_price) * 100.0

        pnl_pct = round(pnl_pct, 2)
        pnl_amount = round(pnl_amount, 2)
        outcome = "WIN" if pnl_pct > 0 else "LOSS"

        return BacktestTrade(
            symbol=symbol,
            strategy=strategy,
            signal_type=signal_type,
            signal_date=signal_date,
            entry_date=entry_date,
            entry_price=round(entry_price, 2),
            exit_date=exit_date,
            exit_price=round(exit_price, 2),
            pnl_pct=pnl_pct,
            pnl_amount=pnl_amount,
            target_price=round(target_price, 2) if target_price else None,
            stop_loss_price=round(stop_price, 2) if stop_price else None,
            exit_reason=exit_reason.value,
            holding_days=holding_days,
            outcome=outcome,
        )

    @classmethod
    def _compute_summary(
        cls, trades: list[BacktestTrade], req: BacktestRequest, universe_label: str
    ) -> BacktestSummary:
        """Aggregate statistical metrics for the simulated trade batch."""
        total = len(trades)
        if total == 0:
            return BacktestSummary(
                strategy=req.strategy,
                universe=universe_label,
                target_pct=req.target_pct,
                stop_loss_pct=req.stop_loss_pct,
                max_holding_days=req.max_holding_days,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                net_return_pct=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                avg_trade_pnl_pct=0.0,
                avg_win_pct=0.0,
                avg_loss_pct=0.0,
                avg_holding_days=0.0,
            )

        wins = [t.pnl_pct for t in trades if t.outcome == "WIN"]
        losses = [t.pnl_pct for t in trades if t.outcome == "LOSS"]

        winning_count = len(wins)
        losing_count = len(losses)
        win_rate = round((winning_count / total) * 100.0, 1)

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net_return = round(sum(t.pnl_pct for t in trades), 2)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        avg_trade_pnl = round(float(np.mean([t.pnl_pct for t in trades])), 2)
        avg_win = round(float(np.mean(wins)), 2) if wins else 0.0
        avg_loss = round(float(np.mean(losses)), 2) if losses else 0.0
        avg_holding = round(float(np.mean([t.holding_days for t in trades])), 1)

        # Max Drawdown computation on cumulative equity series
        cum_returns = np.cumsum([t.pnl_pct for t in trades])
        peak = np.maximum.accumulate(cum_returns)
        drawdowns = peak - cum_returns
        max_dd = round(float(np.max(drawdowns)), 2) if len(drawdowns) > 0 else 0.0

        return BacktestSummary(
            strategy=req.strategy,
            universe=universe_label,
            target_pct=req.target_pct,
            stop_loss_pct=req.stop_loss_pct,
            max_holding_days=req.max_holding_days,
            total_trades=total,
            winning_trades=winning_count,
            losing_trades=losing_count,
            win_rate_pct=win_rate,
            net_return_pct=net_return,
            profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            avg_trade_pnl_pct=avg_trade_pnl,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            avg_holding_days=avg_holding,
        )
