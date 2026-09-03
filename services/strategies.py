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
    """3-Day Sequential trade confirmation for Knoxville Divergence."""
    if not ohlc.index.equals(signals.index):
        raise ValueError("OHLC and signal indexes must match")
    n = len(ohlc)
    start_pos = max(0, n - 2 - max_lookback) if max_lookback is not None else 0
    rows: list[dict] = []
    for position in range(start_pos, n - 2):
        row_day1 = ohlc.iloc[position]
        row_day2 = ohlc.iloc[position + 1]

        signal_date = ohlc.index[position].date().isoformat()
        break_date = ohlc.index[position + 1].date().isoformat()

        rsi_val = round(float(signals.iloc[position]["rsi"]), 2) if "rsi" in signals.columns and pd.notna(signals.iloc[position]["rsi"]) else None

        h_day1 = float(row_day1["High"])
        l_day1 = float(row_day1["Low"])

        c_day2 = float(row_day2["Close"])
        h_day2 = float(row_day2["High"])
        l_day2 = float(row_day2["Low"])

        # Bullish Sequence: Day 1 (Knox) -> Day 2 (Breaks High) -> Days 3-7 (Green candle opening >= Day 2 close)
        day2_breaks_high = (h_day2 > h_day1) and (c_day2 >= h_day1 * 0.99)
        if bool(signals.iloc[position]["buy_signal"]) and day2_breaks_high:
            day2_low_stop = l_day2
            for offset in range(2, min(7, n - position)):
                idx_entry = position + offset
                o_e = float(ohlc["Open"].iloc[idx_entry])
                c_e = float(ohlc["Close"].iloc[idx_entry])
                l_e = float(ohlc["Low"].iloc[idx_entry])
                if l_e <= day2_low_stop:
                    break
                if o_e >= c_day2 and c_e > o_e:
                    entry_date = ohlc.index[idx_entry].date().isoformat()
                    rows.append({
                        "strategy": "RB_KnoxDiv",
                        "signal_type": "buy",
                        "signal_date": signal_date,
                        "signal_candle_low": day2_low_stop,
                        "confirmation_date": entry_date,
                        "entry_price": c_e,
                        "stop_loss": round(day2_low_stop, 2),
                        "rsi_value": rsi_val,
                    })
                    break

        # Bearish Sequence: Day 1 (Knox) -> Day 2 (Breaks Low) -> Days 3-7 (Red candle opening <= Day 2 close)
        day2_breaks_low = (l_day2 < l_day1) and (c_day2 <= l_day1 * 1.01)
        if bool(signals.iloc[position]["sell_signal"]) and day2_breaks_low:
            day2_high_stop = h_day2
            for offset in range(2, min(7, n - position)):
                idx_entry = position + offset
                o_e = float(ohlc["Open"].iloc[idx_entry])
                c_e = float(ohlc["Close"].iloc[idx_entry])
                h_e = float(ohlc["High"].iloc[idx_entry])
                if h_e >= day2_high_stop:
                    break
                if o_e <= c_day2 and c_e < o_e:
                    entry_date = ohlc.index[idx_entry].date().isoformat()
                    rows.append({
                        "strategy": "RB_KnoxDiv",
                        "signal_type": "sell",
                        "signal_date": signal_date,
                        "signal_candle_low": day2_high_stop,
                        "confirmation_date": entry_date,
                        "entry_price": c_e,
                        "stop_loss": round(day2_high_stop, 2),
                        "rsi_value": rsi_val,
                    })
                    break

    return rows





def ma200_trades(ohlc: pd.DataFrame, signals: pd.DataFrame, max_lookback: int | None = None) -> list[dict]:
    """Generate trade records for 200-Day Moving Average Touch and Crossover strategy."""
    if not ohlc.index.equals(signals.index):
        raise ValueError("OHLC and signal indexes must match")
    n = len(ohlc)
    start_pos = max(0, n - max_lookback) if max_lookback is not None else 0
    rows: list[dict] = []
    for position in range(start_pos, n):
        signal_row = ohlc.iloc[position]
        sig = signals.iloc[position]
        signal_date = ohlc.index[position].date().isoformat()
        sma200_val = round(float(sig["sma200"]), 2) if "sma200" in sig and pd.notna(sig["sma200"]) else None

        if bool(sig.get("cross_up", False)):
            rows.append({
                "strategy": "SMA_200",
                "signal_type": "buy",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": signal_date,
                "entry_price": float(signal_row["Close"]),
                "stop_loss": round(float(signal_row["Low"] * 0.99), 2),
                "rsi_value": sma200_val,
            })
        elif bool(sig.get("cross_down", False)):
            rows.append({
                "strategy": "SMA_200",
                "signal_type": "sell",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": signal_date,
                "entry_price": float(signal_row["Close"]),
                "stop_loss": None,
                "rsi_value": sma200_val,
            })
        elif bool(sig.get("touch", False)):
            rows.append({
                "strategy": "SMA_200",
                "signal_type": "buy" if float(signal_row["Close"]) >= (sma200_val or 0) else "sell",
                "signal_date": signal_date,
                "signal_candle_low": float(signal_row["Low"]),
                "confirmation_date": signal_date,
                "entry_price": float(signal_row["Close"]),
                "stop_loss": round(float(signal_row["Low"] * 0.99), 2),
                "rsi_value": sma200_val,
            })
    return rows

