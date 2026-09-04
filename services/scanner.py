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
from services.indicators import ma200_signals, rb_knox_divergence, rsi_signals
from services.market_data import MarketDataProvider
from services.strategies import confirmed_trades, ma200_trades, rsi_trades
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
        strategies = ["RSI", "RB_KnoxDiv", "SMA_200"] if strategy_name.upper() in ("ALL", "*", "") else [strategy_name]

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
                    elif strat.upper() in ("SMA_200", "200MA", "MA200"):
                        signals = ma200_signals(ohlc)
                        trades = ma200_trades(ohlc, signals, max_lookback=2)
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
        symbol: str | None = None,
        include_neutral: bool = False,
        force_refresh: bool = False,
    ) -> LookbackResponse:
        """Perform high-speed lookback screening with in-memory caching."""
        clean_sym = symbol.strip().upper() if symbol else None
        cache_key = f"{lookback_days}_{rsi_length}_{index_filter}_{signal_filter}_{clean_sym}_{include_neutral}"
        if not force_refresh and cache_key in cls._LOOKBACK_CACHE:
            cached_data, timestamp = cls._LOOKBACK_CACHE[cache_key]
            if time.time() - timestamp < settings.CACHE_TTL_SECONDS:
                return cached_data

        universe = load_universe()
        if clean_sym:
            if clean_sym in universe:
                filtered_universe = {clean_sym: universe[clean_sym]}
            else:
                filtered_universe = {clean_sym: {"Custom"}}
            include_neutral = True
        elif index_filter:
            filtered_universe = {s: m for s, m in universe.items() if index_filter in m}
        else:
            filtered_universe = universe

        ohlc_data = MarketDataProvider.get_universe_ohlc(list(filtered_universe.keys()), force_refresh=force_refresh)
        flagged_items: list[LookbackItem] = []

        for sym, memberships in filtered_universe.items():
            if sym not in ohlc_data:
                continue
            df = ohlc_data[sym]
            if len(df) < max(rsi_length + 5, 20):
                continue

            item = cls._analyze_symbol(sym, df, lookback_days, rsi_length, "|".join(sorted(memberships)), include_neutral=include_neutral)
            if item:
                # Apply signal_filter if present
                if signal_filter and not clean_sym:
                    sf = signal_filter.lower()
                    if sf == "oversold" and item.primary_type != "oversold":
                        continue
                    elif sf == "overbought" and item.primary_type != "overbought":
                        continue
                    elif sf == "buy" and item.primary_type not in ("buy", "oversold"):
                        continue
                    elif sf == "sell" and item.primary_type not in ("sell", "overbought"):
                        continue
                    elif sf in ("signals_only", "knoxville", "knox", "rb_knoxdiv", "knox_div") and not any(r.category == "Strategy_Signal" for r in item.reasons):
                        continue
                    elif sf in ("ma200", "200ma", "ma_200") and not any(r.category == "MA200" for r in item.reasons):
                        continue
                    elif sf in ("ma200_touch", "touch") and not any(r.category == "MA200" and r.type == "touch" for r in item.reasons):
                        continue
                    elif sf in ("ma200_cross_up", "cross_up", "crossed_up") and not any(r.category == "MA200" and r.type == "cross_up" for r in item.reasons):
                        continue
                    elif sf in ("ma200_cross_down", "cross_down", "crossed_down") and not any(r.category == "MA200" and r.type == "cross_down" for r in item.reasons):
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
        include_neutral: bool = False,
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

        # 2. Check RB Knoxville Divergence in Lookback Window (CONFIRMED SIGNALS ONLY)
        # Buy confirmed: Day T+1 Close > Day T Close
        # Sell confirmed: Day T+1 Close < Day T Close
        try:
            knox_sigs = rb_knox_divergence(df)
            n_bars = len(df)
            start_pos = max(0, n_bars - lookback_days - 1)
            for i in range(start_pos, n_bars - 1):
                sig_dt_str = df.index[i].date().isoformat()
                conf_dt_str = df.index[i + 1].date().isoformat()

                # Check if confirmation date or signal date falls within the selected lookback window
                if conf_dt_str not in window_dates and sig_dt_str not in window_dates:
                    continue

                sig_row = knox_sigs.iloc[i]
                h_day1 = float(df["High"].iloc[i])
                l_day1 = float(df["Low"].iloc[i])

                c_day2 = float(df["Close"].iloc[i + 1])
                h_day2 = float(df["High"].iloc[i + 1])
                l_day2 = float(df["Low"].iloc[i + 1])

                # BUY SEQUENCE:
                day2_breaks_high = (h_day2 > h_day1) and (c_day2 >= h_day1 * 0.99)
                if bool(sig_row.get("buy_signal", False)) and day2_breaks_high:
                    day2_low_stop = l_day2
                    for offset in range(2, len(df) - i):
                        idx_entry = i + offset
                        o_e = float(df["Open"].iloc[idx_entry])
                        h_e = float(df["High"].iloc[idx_entry])
                        l_e = float(df["Low"].iloc[idx_entry])
                        if l_e <= day2_low_stop:
                            break
                        if h_e >= h_day2:
                            exec_price = o_e if o_e >= h_day2 else h_day2
                            entry_dt_str = df.index[idx_entry].date().isoformat()
                            is_flagged = True
                            if primary_type == "neutral":
                                primary_type = "buy"
                            most_recent_signal_date = entry_dt_str
                            reasons.append(ReasonTag(
                                category="Strategy_Signal",
                                strategy="RB_KnoxDiv",
                                type="buy",
                                text=f"Knoxville Confirmed Buy (Knox: {sig_dt_str}, Break: {conf_dt_str}, Entry [Day {offset+1}]: ₹{exec_price:.2f} on {entry_dt_str} | SL: ₹{day2_low_stop:.2f})",
                                date=entry_dt_str,
                                entry_price=exec_price,
                            ))
                            break

                # SELL SEQUENCE:
                day2_breaks_low = (l_day2 < l_day1) and (c_day2 <= l_day1 * 1.01)
                if bool(sig_row.get("sell_signal", False)) and day2_breaks_low:
                    day2_high_stop = h_day2
                    for offset in range(2, len(df) - i):
                        idx_entry = i + offset
                        o_e = float(df["Open"].iloc[idx_entry])
                        h_e = float(df["High"].iloc[idx_entry])
                        l_e = float(df["Low"].iloc[idx_entry])
                        if h_e >= day2_high_stop:
                            break
                        if l_e <= l_day2:
                            exec_price = o_e if o_e <= l_day2 else l_day2
                            entry_dt_str = df.index[idx_entry].date().isoformat()
                            is_flagged = True
                            if primary_type == "neutral":
                                primary_type = "sell"
                            most_recent_signal_date = entry_dt_str
                            reasons.append(ReasonTag(
                                category="Strategy_Signal",
                                strategy="RB_KnoxDiv",
                                type="sell",
                                text=f"Knoxville Confirmed Sell (Knox: {sig_dt_str}, Break: {conf_dt_str}, Entry [Day {offset+1}]: ₹{exec_price:.2f} on {entry_dt_str} | SL: ₹{day2_high_stop:.2f})",
                                date=entry_dt_str,
                                entry_price=exec_price,
                            ))
                            break






        except Exception:
            pass



        # 3. Check 200-Day Moving Average Touch and Crossover in Lookback Window
        latest_sma200 = None
        try:
            ma_df = ma200_signals(df)
            if len(ma_df) >= 200 and pd.notna(ma_df["sma200"].iloc[-1]):
                latest_sma200 = round(float(ma_df["sma200"].iloc[-1]), 2)

            for idx in window_df.index:
                dt_str = idx.date().isoformat()
                if idx in ma_df.index:
                    row_ma = ma_df.loc[idx]
                    sma_val = float(row_ma["sma200"]) if pd.notna(row_ma["sma200"]) else None
                    if sma_val is None:
                        continue

                    if bool(row_ma["cross_up"]):
                        is_flagged = True
                        if primary_type == "neutral":
                            primary_type = "buy"
                        most_recent_signal_date = dt_str
                        reasons.append(ReasonTag(
                            category="MA200",
                            strategy="SMA_200",
                            type="cross_up",
                            text=f"200 MA Crossed Up (₹{sma_val:.2f}) on {dt_str}",
                            date=dt_str,
                            entry_price=float(df.loc[idx, "Close"]),
                        ))
                    elif bool(row_ma["cross_down"]):
                        is_flagged = True
                        if primary_type == "neutral":
                            primary_type = "sell"
                        most_recent_signal_date = dt_str
                        reasons.append(ReasonTag(
                            category="MA200",
                            strategy="SMA_200",
                            type="cross_down",
                            text=f"200 MA Crossed Down (₹{sma_val:.2f}) on {dt_str}",
                            date=dt_str,
                            entry_price=float(df.loc[idx, "Close"]),
                        ))
                    elif bool(row_ma["touch"]):
                        is_flagged = True
                        if primary_type == "neutral":
                            primary_type = "buy" if float(df.loc[idx, "Close"]) >= sma_val else "sell"
                        most_recent_signal_date = dt_str
                        reasons.append(ReasonTag(
                            category="MA200",
                            strategy="SMA_200",
                            type="touch",
                            text=f"200 MA Touch (₹{sma_val:.2f}) on {dt_str}",
                            date=dt_str,
                            entry_price=float(df.loc[idx, "Close"]),
                        ))
        except Exception:
            pass

        if not is_flagged:
            if not include_neutral:
                return None
            reasons.append(ReasonTag(
                category="Status",
                strategy="Monitor",
                type="neutral",
                text=f"No active breakout signals in {lookback_days}D lookback",
                date=latest_date_str,
                entry_price=round(latest_close, 2),
            ))

        return LookbackItem(
            symbol=symbol,
            status="active",
            current_price=round(latest_close, 2),
            rsi=latest_rsi,
            sma_200=latest_sma200,
            primary_type=primary_type,
            signal_date=most_recent_signal_date,
            reasons=reasons,
            reason_summary=" | ".join(r.text for r in reasons),
            index_membership=index_membership,
        )


