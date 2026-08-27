"""Unified scanning and lookback screening engine."""
from __future__ import annotations

import time
from datetime import date
from typing import Any
import pandas as pd
from core.config import settings
from core.logging import logger
from db.repository import SignalRepository
from models.signal import LookbackItem, LookbackResponse, ReasonTag, ScanResponse
from services.indicators import rb_knox_divergence, rsi_signals
from services.market_data import MarketDataProvider
from services.strategies import confirmed_trades, rsi_trades
from services.universe import load_universe


class ScannerEngine:
    """Core analytical engine for scheduled confirmation scans and interactive lookback screener."""

    _LOOKBACK_CACHE: dict[str, Any] = {}

    @classmethod
    def run_daily_scan(cls, strategy_name: str = "RSI") -> ScanResponse:
        """Run daily scan across all active universe symbols and persist newly confirmed signals."""
        universe = load_universe()
        if not universe:
            raise RuntimeError("Universe is empty.")

        scan_date_str = date.today().isoformat()
        inserted = 0
        errors: list[dict[str, Any]] = []
        strategies = ["RSI", "RB_KnoxDiv"] if strategy_name.upper() in ("ALL", "*", "") else [strategy_name]

        all_symbols = list(universe.keys())
        ohlc_by_symbol = MarketDataProvider.get_universe_ohlc(all_symbols)

        for symbol, memberships in universe.items():
            if symbol not in ohlc_by_symbol:
                errors.append({"symbol": symbol, "error": "Insufficient OHLC data"})
                continue

            ohlc = ohlc_by_symbol[symbol]
            latest_date_str = ohlc.index[-1].date().isoformat()

            for strat in strategies:
                try:
                    if strat.upper() == "RSI":
                        signals = rsi_signals(ohlc)
                        trades = rsi_trades(ohlc, signals, max_lookback=2)
                    elif strat.upper() in ("RB_KNOXDIV", "RB_KNOXVILLE", "KNOXVILLE"):
                        signals = rb_knox_divergence(ohlc)
                        trades = confirmed_trades(ohlc, signals, max_lookback=3)
                    else:
                        continue

                    for trade in trades:
                        if trade["confirmation_date"] != latest_date_str:
                            continue
                        record = {
                            "strategy": strat,
                            "scan_date": scan_date_str,
                            "symbol": symbol,
                            "index_membership": "|".join(sorted(memberships)),
                            **trade,
                        }
                        if SignalRepository.save(record):
                            inserted += 1
                except Exception as exc:
                    errors.append({"symbol": symbol, "strategy": strat, "error": str(exc)})

        return ScanResponse(
            scan_date=scan_date_str,
            strategy=strategy_name,
            stocks_scanned=len(universe),
            signals_inserted=inserted,
            errors=errors,
        )

    @classmethod
    def screen_lookback(
        cls,
        lookback_days: int = 1,
        rsi_length: int = 14,
        index_filter: str | None = None,
        signal_filter: str | None = None,
        force_refresh: bool = False,
    ) -> LookbackResponse:
        """Perform high-speed lookback screening with in-memory caching."""
        cache_key = f"{lookback_days}_{rsi_length}_{index_filter}_{signal_filter}"
        if not force_refresh and cache_key in cls._LOOKBACK_CACHE:
            cached_data, timestamp = cls._LOOKBACK_CACHE[cache_key]
            if time.time() - timestamp < settings.CACHE_TTL_SECONDS:
                return cached_data

        universe = load_universe()
        if index_filter:
            filtered_universe = {s: m for s, m in universe.items() if index_filter in m}
        else:
            filtered_universe = universe

        ohlc_data = MarketDataProvider.get_universe_ohlc(list(filtered_universe.keys()), force_refresh=force_refresh)
        flagged_items: list[LookbackItem] = []

        for symbol, memberships in filtered_universe.items():
            if symbol not in ohlc_data:
                continue
            df = ohlc_data[symbol]
            if len(df) < max(rsi_length + 5, 20):
                continue

            item = cls._analyze_symbol(symbol, df, lookback_days, rsi_length, "|".join(sorted(memberships)))
            if item:
                # Apply signal_filter if present
                if signal_filter:
                    sf = signal_filter.lower()
                    if sf == "oversold" and item.primary_type != "oversold":
                        continue
                    elif sf == "overbought" and item.primary_type != "overbought":
                        continue
                    elif sf == "buy" and item.primary_type not in ("buy", "oversold"):
                        continue
                    elif sf == "sell" and item.primary_type not in ("sell", "overbought"):
                        continue
                    elif sf == "signals_only" and not any(r.category == "Strategy_Signal" for r in item.reasons):
                        continue
                flagged_items.append(item)

        response = LookbackResponse(
            lookback_days=lookback_days,
            rsi_length=rsi_length,
            total_scanned=len(filtered_universe),
            total_flagged=len(flagged_items),
            items=flagged_items,
            timestamp=time.time(),
        )

        cls._LOOKBACK_CACHE[cache_key] = (response, time.time())
        return response

    @staticmethod
    def _analyze_symbol(
        symbol: str,
        df: pd.DataFrame,
        lookback_days: int,
        rsi_length: int,
        index_membership: str,
    ) -> LookbackItem | None:
        window_df = df.iloc[-lookback_days:]
        latest_close = float(df["Close"].iloc[-1])
        latest_date_str = df.index[-1].date().isoformat()
        window_dates = {idx.date().isoformat() for idx in window_df.index}

        reasons: list[ReasonTag] = []
        is_flagged = False
        primary_type = "neutral"
        most_recent_signal_date = latest_date_str

        # 1. Check RSI Dual-Condition (Both RSI & RSI MA < 30 for Oversold, Both > 70 for Overbought)
        latest_rsi = None
        try:
            from services.indicators import calculate_rsi, calculate_rsi_ma
            rsi_series = calculate_rsi(df["Close"], length=rsi_length)
            rsi_ma_series = calculate_rsi_ma(rsi_series, length=rsi_length)
            latest_rsi = round(float(rsi_series.iloc[-1]), 2)
            
            # Check dual condition within the selected lookback window
            for idx in window_df.index:
                dt_str = idx.date().isoformat()
                r_val = float(rsi_series.loc[idx])
                rma_val = float(rsi_ma_series.loc[idx])
                
                # Both below 30 -> Dual Oversold Buy
                if r_val < settings.RSI_OVERSOLD and rma_val < settings.RSI_OVERSOLD:
                    is_flagged = True
                    primary_type = "oversold"
                    most_recent_signal_date = dt_str
                    reasons.append(ReasonTag(
                        category="RSI_Oversold",
                        strategy="RSI_Dual",
                        type="buy",
                        text=f"RSI: {r_val:.2f} & MA: {rma_val:.2f} (Dual < 30) on {dt_str}",
                        date=dt_str,
                        entry_price=float(df.loc[idx, "Close"]),
                    ))
                # Both above 70 -> Dual Overbought Sell
                elif r_val > settings.RSI_OVERBOUGHT and rma_val > settings.RSI_OVERBOUGHT:
                    is_flagged = True
                    primary_type = "overbought"
                    most_recent_signal_date = dt_str
                    reasons.append(ReasonTag(
                        category="RSI_Overbought",
                        strategy="RSI_Dual",
                        type="sell",
                        text=f"RSI: {r_val:.2f} & MA: {rma_val:.2f} (Dual > 70) on {dt_str}",
                        date=dt_str,
                        entry_price=float(df.loc[idx, "Close"]),
                    ))
        except Exception:
            pass

        # 2. Check RB Knoxville Divergence Strategy Confirmed Signals in Lookback Window
        try:
            knox_sigs = rb_knox_divergence(df)
            knox_trade_list = confirmed_trades(df, knox_sigs, max_lookback=lookback_days + 2)
            for trade in knox_trade_list:
                c_date = trade["confirmation_date"]
                s_type = trade["signal_type"]
                if c_date in window_dates:
                    is_flagged = True
                    primary_type = s_type
                    most_recent_signal_date = c_date
                    reasons.append(ReasonTag(
                        category="Strategy_Signal",
                        strategy="RB_KnoxDiv",
                        type=s_type,
                        text=f"Knoxville {s_type.upper()} on {c_date}",
                        date=c_date,
                        entry_price=trade["entry_price"],
                    ))
        except Exception:
            pass


        if not is_flagged:
            return None

        return LookbackItem(
            symbol=symbol,
            status="active",
            current_price=round(latest_close, 2),
            rsi=latest_rsi,
            primary_type=primary_type,
            signal_date=most_recent_signal_date,
            reasons=reasons,
            reason_summary=" | ".join(r.text for r in reasons),
            index_membership=index_membership,
        )
