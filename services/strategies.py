"""Strategy confirmation and trade execution rules."""
from __future__ import annotations

import pandas as pd


def rsi_trades(ohlc: pd.DataFrame, signals: pd.DataFrame, max_lookback: int | None = None) -> list[dict]:
    """Generate trade records for RSI strategy."""
    if not ohlc.index.equals(signals.index):
        raise ValueError("OHLC and signal indexes must match")
    n = len(ohlc)
    start_pos = max(0, n - max_lookback) if max_lookback is not None else 0
    rows: list[dict] = []
    for position in range(start_pos, n):
        signal_row = ohlc.iloc[position]
        sig = signals.iloc[position]
        signal_date = ohlc.index[position].date().isoformat()
        rsi_val = round(float(sig["rsi"]), 2) if "rsi" in sig and pd.notna(sig["rsi"]) else None
        rsi_ma_val = round(float(sig["rsi_ma"]), 2) if "rsi_ma" in sig and pd.notna(sig["rsi_ma"]) else None

        if bool(sig["buy_signal"]):
            rows.append({
                "strategy": "RSI",
                "signal_type": "buy",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": signal_date,
                "entry_price": float(signal_row["Close"]),
                "stop_loss": round(float(signal_row["Low"] * 0.99), 2),
                "rsi_value": rsi_val,
                "rsi_ma_value": rsi_ma_val,
            })
        elif bool(sig["sell_signal"]):
            rows.append({
                "strategy": "RSI",
                "signal_type": "sell",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": signal_date,
                "entry_price": float(signal_row["Close"]),
                "stop_loss": None,
                "rsi_value": rsi_val,
                "rsi_ma_value": rsi_ma_val,
            })
    return rows


def confirmed_trades(ohlc: pd.DataFrame, signals: pd.DataFrame, max_lookback: int | None = None) -> list[dict]:
    """Next-candle trade confirmation for Knoxville Divergence."""
    if not ohlc.index.equals(signals.index):
        raise ValueError("OHLC and signal indexes must match")
    n = len(ohlc)
    start_pos = max(0, n - 1 - max_lookback) if max_lookback is not None else 0
    rows: list[dict] = []
    for position in range(start_pos, n - 1):
        signal_row = ohlc.iloc[position]
        confirmation_row = ohlc.iloc[position + 1]
        signal_date = ohlc.index[position].date().isoformat()
        confirmation_date = ohlc.index[position + 1].date().isoformat()
        rsi_val = round(float(signals.iloc[position]["rsi"]), 2) if "rsi" in signals.columns and pd.notna(signals.iloc[position]["rsi"]) else None

        # Buy Confirmation: Day T+1 Close > Day T Close
        if bool(signals.iloc[position]["buy_signal"]) and confirmation_row["Close"] > signal_row["Close"]:
            rows.append({
                "strategy": "RB_KnoxDiv",
                "signal_type": "buy",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": confirmation_date,
                "entry_price": float(confirmation_row["Close"]),
                "stop_loss": round(float(signal_row["Low"] * 0.99), 2),
                "rsi_value": rsi_val,
            })

        # Sell Confirmation: Day T+1 Close < Day T Close
        if bool(signals.iloc[position]["sell_signal"]) and confirmation_row["Close"] < signal_row["Close"]:
            rows.append({
                "strategy": "RB_KnoxDiv",
                "signal_type": "sell",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": confirmation_date,
                "entry_price": float(confirmation_row["Close"]),
                "stop_loss": None,
                "rsi_value": rsi_val,
            })
    return rows
