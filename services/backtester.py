"""High-performance Strategy Tester and Trade Simulation Engine."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
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
        """Execute strategy simulation across the selected universe or a single stock."""
        t_start = time.perf_counter()

        single_sym = request.symbol.strip().upper() if request.symbol and request.symbol.strip() else None

        if single_sym:
            all_symbols = [single_sym]
            universe_label = f"{single_sym} (Single Stock)"
            ohlc_data = MarketDataProvider.get_universe_ohlc(all_symbols, period=request.period or "1y")
        else:
            from services.universe import load_custom_watchlists
            custom_lists = load_custom_watchlists()
            idx_param = (request.index or "").strip()
            idx_clean = idx_param.replace("custom:", "").strip()

            if idx_clean and idx_clean in custom_lists:
                all_symbols = custom_lists[idx_clean]
                universe_label = f"{idx_clean} (Watchlist)"

            elif idx_param:
                universe = load_universe()
                target_universe = {s: m for s, m in universe.items() if idx_param in m or idx_clean in m}
                all_symbols = list(target_universe.keys())
                universe_label = idx_clean
            else:
                universe = load_universe()
                all_symbols = list(universe.keys())
                universe_label = "All Universes"

            ohlc_data = MarketDataProvider.get_universe_ohlc(all_symbols, period=request.period or "1y")



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

        # Determine effective start date from requested time horizon or explicit start_date
        period_days_map = {
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "2y": 730,
            "3y": 1095,
            "5y": 1825,
            "10y": 3650,
            "max": None,
        }

        effective_start = request.start_date
        if not effective_start and request.period:
            p_clean = request.period.lower().strip()
            days = period_days_map.get(p_clean)
            if days:
                effective_start = (datetime.now().date() - timedelta(days=days)).isoformat()

        # Filter by effective date range
        if effective_start:
            all_trades = [t for t in all_trades if t.signal_date >= effective_start or t.entry_date >= effective_start]
        if request.end_date:
            all_trades = [t for t in all_trades if t.entry_date <= request.end_date]


        # Filter by signal_type if requested (buy vs sell)
        if request.signal_type:
            st_filter = request.signal_type.lower()
            all_trades = [t for t in all_trades if t.signal_type.lower() == st_filter]

        # Sort trades with MOST RECENT trades first (Newest -> Oldest)
        all_trades.sort(key=lambda t: (t.entry_date, t.symbol), reverse=True)

        summary = cls._compute_summary(all_trades, request, universe_label=universe_label)
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
        """Simulate Dual RSI Extremes (<30 oversold buy, >70 overbought sell)."""
        trades: list[BacktestTrade] = []
        sigs = rsi_signals(df)
        n = len(df)
        i = 1

        while i < n - 1:
            row_sig = sigs.iloc[i]
            # Buy condition: Both RSI and RSI-MA < 30
            if bool(row_sig["buy_signal"]):
                trade, exit_idx = cls._simulate_trade(
                    symbol=symbol,
                    strategy="RSI",
                    signal_type="buy",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                )
                if trade:
                    trades.append(trade)
                    i = max(i + 1, exit_idx + 1)
                    continue

            # Sell condition: Both RSI and RSI-MA > 70
            elif bool(row_sig["sell_signal"]):
                trade, exit_idx = cls._simulate_trade(
                    symbol=symbol,
                    strategy="RSI",
                    signal_type="sell",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                )
                if trade:
                    trades.append(trade)
                    i = max(i + 1, exit_idx + 1)
                    continue
            i += 1

        return trades

    @classmethod
    def _backtest_knoxville(
        cls, symbol: str, df: pd.DataFrame, req: BacktestRequest
    ) -> list[BacktestTrade]:
        """Simulate RB Knoxville Divergence with Sequential Confirmation & Price Crossing Entry:
        
        Buy Sequence:
        - Day 1 (Signal): Bullish Knoxville Divergence formed.
        - Day 2 (Trading Signal Confirmation): Candle breaks and closes at/above Day 1 high. Stop Loss is locked at Low[Day 2].
        - Day 3+ (Crossing Entry): Whenever the stock crosses above Day 2's High price (High >= High[Day 2]), enter BUY.
          - If the day opens above Day 2 High, entry is at Open; otherwise at Day 2 High.
          - Setup is invalidated if price drops below Day 2 Stop Loss (Low <= Low[Day 2]) before crossing.
        
        Sell Sequence:
        - Day 1 (Signal): Bearish Knoxville Divergence formed.
        - Day 2 (Trading Signal Confirmation): Candle breaks and closes at/below Day 1 low. Stop Loss is locked at High[Day 2].
        - Day 3+ (Crossing Entry): Whenever the stock crosses below Day 2's Low price (Low <= Low[Day 2]), enter SELL.
          - If the day opens below Day 2 Low, entry is at Open; otherwise at Day 2 Low.
          - Setup is invalidated if price rises above Day 2 Stop Loss (High >= High[Day 2]) before crossing.
        """
        trades: list[BacktestTrade] = []
        sigs = rb_knox_divergence(df)
        n = len(df)
        i = 1

        while i < n - 3:
            row_sig = sigs.iloc[i]
            h_day1 = float(df["High"].iloc[i])
            l_day1 = float(df["Low"].iloc[i])

            c_day2 = float(df["Close"].iloc[i + 1])
            h_day2 = float(df["High"].iloc[i + 1])
            l_day2 = float(df["Low"].iloc[i + 1])

            # BUY SEQUENCE:
            day2_breaks_high = (h_day2 > h_day1) and (c_day2 >= h_day1 * 0.99)
            if bool(row_sig["buy_signal"]) and day2_breaks_high:
                day2_low_stop = l_day2
                entry_found = False
                for offset in range(2, n - i):
                    idx_entry = i + offset
                    o_entry = float(df["Open"].iloc[idx_entry])
                    h_entry = float(df["High"].iloc[idx_entry])
                    l_entry = float(df["Low"].iloc[idx_entry])

                    # Invalidate setup if price drops below Day 2 Stop Loss before crossing
                    if l_entry <= day2_low_stop:
                        break

                    # Whenever the stock crosses or opens above Day 2 high price:
                    if h_entry >= h_day2:
                        exec_price = o_entry if o_entry >= h_day2 else h_day2
                        trade, exit_idx = cls._simulate_trade(
                            symbol=symbol,
                            strategy="RB_KnoxDiv",
                            signal_type="buy",
                            df=df,
                            signal_idx=i,
                            entry_idx=idx_entry,
                            target_pct=req.target_pct,
                            stop_loss_pct=req.stop_loss_pct,
                            override_stop_price=day2_low_stop,
                            override_entry_price=exec_price,
                        )
                        if trade:
                            trades.append(trade)
                            i = max(i + 1, exit_idx + 1)
                            entry_found = True
                            break

                if entry_found:
                    continue

            # SELL SEQUENCE:
            day2_breaks_low = (l_day2 < l_day1) and (c_day2 <= l_day1 * 1.01)
            if bool(row_sig["sell_signal"]) and day2_breaks_low:
                day2_high_stop = h_day2
                entry_found = False
                for offset in range(2, n - i):
                    idx_entry = i + offset
                    o_entry = float(df["Open"].iloc[idx_entry])
                    h_entry = float(df["High"].iloc[idx_entry])
                    l_entry = float(df["Low"].iloc[idx_entry])

                    # Invalidate setup if price rises above Day 2 Stop Loss before crossing
                    if h_entry >= day2_high_stop:
                        break

                    # Whenever the stock crosses or opens below Day 2 low price:
                    if l_entry <= l_day2:
                        exec_price = o_entry if o_entry <= l_day2 else l_day2
                        trade, exit_idx = cls._simulate_trade(
                            symbol=symbol,
                            strategy="RB_KnoxDiv",
                            signal_type="sell",
                            df=df,
                            signal_idx=i,
                            entry_idx=idx_entry,
                            target_pct=req.target_pct,
                            stop_loss_pct=req.stop_loss_pct,
                            override_stop_price=day2_high_stop,
                            override_entry_price=exec_price,
                        )
                        if trade:
                            trades.append(trade)
                            i = max(i + 1, exit_idx + 1)
                            entry_found = True
                            break

                if entry_found:
                    continue

            i += 1

        return trades




    @classmethod
    def _backtest_ma200(
        cls, symbol: str, df: pd.DataFrame, req: BacktestRequest
    ) -> list[BacktestTrade]:
        """Simulate 200-Day Moving Average Crossover / Touch."""
        trades: list[BacktestTrade] = []
        sigs = ma200_signals(df)
        n = len(df)
        i = 200

        while i < n - 1:
            row_sig = sigs.iloc[i]
            if bool(row_sig.get("cross_up", False)):
                trade, exit_idx = cls._simulate_trade(
                    symbol=symbol,
                    strategy="SMA_200",
                    signal_type="buy",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                )
                if trade:
                    trades.append(trade)
                    i = max(i + 1, exit_idx + 1)
                    continue

            elif bool(row_sig.get("cross_down", False)):
                trade, exit_idx = cls._simulate_trade(
                    symbol=symbol,
                    strategy="SMA_200",
                    signal_type="sell",
                    df=df,
                    signal_idx=i,
                    entry_idx=i,
                    target_pct=req.target_pct,
                    stop_loss_pct=req.stop_loss_pct,
                )
                if trade:
                    trades.append(trade)
                    i = max(i + 1, exit_idx + 1)
                    continue
            i += 1

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
        max_holding_days: int | None = None,
        override_stop_price: float | None = None,
        override_entry_price: float | None = None,
    ) -> tuple[BacktestTrade | None, int]:
        """Simulate the forward price action until Target Hit or Stop Loss Hit."""
        n = len(df)
        if entry_idx >= n:
            return None, entry_idx

        entry_date = df.index[entry_idx].date().isoformat()
        signal_date = df.index[signal_idx].date().isoformat()
        entry_price = float(override_entry_price if override_entry_price is not None and override_entry_price > 0 else df["Close"].iloc[entry_idx])
        if entry_price <= 0:
            return None, entry_idx

        is_buy = signal_type.lower() == "buy"

        # Define targets and stops
        target_price = None
        if target_pct is not None and target_pct > 0:
            target_price = entry_price * (1.0 + target_pct / 100.0) if is_buy else entry_price * (1.0 - target_pct / 100.0)

        # Stop loss: Use predetermined price if specified (e.g. Knoxville signal candle low/high), else percentage
        stop_price = None
        if override_stop_price is not None and override_stop_price > 0:
            stop_price = override_stop_price
        elif stop_loss_pct is not None and stop_loss_pct > 0:
            stop_price = entry_price * (1.0 - stop_loss_pct / 100.0) if is_buy else entry_price * (1.0 + stop_loss_pct / 100.0)

        # Track forward sessions
        exit_idx = entry_idx
        exit_price = entry_price
        exit_reason = ExitReason.OPEN_POSITION
        max_idx = min(entry_idx + max_holding_days, n - 1) if max_holding_days else (n - 1)

        # Forward scan day-by-day until Target Hit, Stop Loss Hit, or Smart Time Exits
        for cur_idx in range(entry_idx + 1, max_idx + 1):
            cur_high = float(df["High"].iloc[cur_idx])
            cur_low = float(df["Low"].iloc[cur_idx])
            cur_close = float(df["Close"].iloc[cur_idx])
            cur_open = float(df["Open"].iloc[cur_idx])
            holding_days = cur_idx - entry_idx

            if is_buy:
                # 1. Stop Loss Check (Low touches or pierces stop)
                if stop_price is not None and cur_low <= stop_price:
                    exit_idx = cur_idx
                    exit_price = min(stop_price, cur_open)
                    exit_reason = ExitReason.STOP_LOSS_HIT
                    break

                # 2. Target Check (High touches or exceeds target)
                if target_price is not None and cur_high >= target_price:
                    exit_idx = cur_idx
                    exit_price = max(target_price, cur_open)
                    exit_reason = ExitReason.TARGET_HIT
                    break

                cur_pnl_pct = ((cur_close - entry_price) / entry_price) * 100.0
            else:
                # Short/Sell:
                # 1. Stop Loss Check (High touches or pierces stop)
                if stop_price is not None and cur_high >= stop_price:
                    exit_idx = cur_idx
                    exit_price = max(stop_price, cur_open)
                    exit_reason = ExitReason.STOP_LOSS_HIT
                    break

                # 2. Target Check (Low touches or pierces target)
                if target_price is not None and cur_low <= target_price:
                    exit_idx = cur_idx
                    exit_price = min(target_price, cur_open)
                    exit_reason = ExitReason.TARGET_HIT
                    break

                cur_pnl_pct = ((entry_price - cur_close) / entry_price) * 100.0

            # 3. Profitable Trade Time Exit (12-15 Days):
            # If held for 12+ trading sessions and the trade is profitable (cur_pnl_pct > 0), lock in profit
            if holding_days >= 12 and cur_pnl_pct > 0.0:
                exit_idx = cur_idx
                exit_price = cur_close
                exit_reason = ExitReason.TIME_EXIT_PROFIT
                break

            # If reached max holding days (when configured) or end of dataset
            if cur_idx == max_idx:
                exit_idx = cur_idx
                exit_price = cur_close
                exit_reason = ExitReason.TIME_EXIT if max_holding_days else ExitReason.OPEN_POSITION


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

        trade = BacktestTrade(
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
        return trade, exit_idx

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
