"""Vectorized technical indicator calculations (RSI, RSI-MA, RB Knoxville Divergence)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI) using Wilder smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def calculate_rsi_ma(rsi_series: pd.Series, length: int = 14) -> pd.Series:
    """Calculate Simple Moving Average of the RSI series."""
    return rsi_series.rolling(window=length, min_periods=1).mean()


def rsi_signals(
    ohlc: pd.DataFrame,
    length: int = 14,
    ma_length: int = 14,
    overbought: float = 70.0,
    oversold: float = 30.0,
) -> pd.DataFrame:
    """Dual-condition RSI strategy signals: Buy when both < oversold, Sell when both > overbought."""
    close = ohlc["Close"]
    rsi = calculate_rsi(close, length=length)
    rsi_ma = calculate_rsi_ma(rsi, length=ma_length)

    buy_signal = (rsi < oversold) & (rsi_ma < oversold)
    sell_signal = (rsi > overbought) & (rsi_ma > overbought)

    return pd.DataFrame(
        {
            "rsi": rsi,
            "rsi_ma": rsi_ma,
            "buy_signal": buy_signal,
            "sell_signal": sell_signal,
        },
        index=ohlc.index,
    )


def rb_knox_divergence(
    ohlc: pd.DataFrame,
    look_back: int = 150,
    mom_period: int = 20,
    rsi_period: int = 21,
    rsi_ob: float = 70.0,
    rsi_os: float = 30.0,
) -> pd.DataFrame:
    """Vectorized Rob Booker Knoxville Divergence indicator (150 21 20)."""
    close = ohlc["Close"]
    high = ohlc["High"]
    low = ohlc["Low"]

    momentum = close.diff(mom_period)
    rsi = calculate_rsi(close, length=rsi_period)

    n = len(ohlc)
    buy_signal = np.zeros(n, dtype=bool)
    sell_signal = np.zeros(n, dtype=bool)

    high_arr = high.to_numpy(dtype=float, copy=False)
    low_arr = low.to_numpy(dtype=float, copy=False)
    mom_arr = momentum.to_numpy(dtype=float, copy=False)
    rsi_arr = rsi.to_numpy(dtype=float, copy=False)

    start_idx = max(mom_period + 5, 20)
    for i in range(start_idx, n):
        # Bearish Divergence (Sell Line)
        if rsi_arr[i] >= rsi_ob:
            w_start = max(0, i - look_back)
            w_end = i - 5
            if w_end > w_start:
                cond = (high_arr[i] > high_arr[w_start:w_end]) & (mom_arr[i] < mom_arr[w_start:w_end]) & (rsi_arr[w_start:w_end] >= rsi_ob)
                if np.any(cond):
                    sell_signal[i] = True

        if rsi_arr[i] <= rsi_os:
            w_start = max(0, i - look_back)
            w_end = i - 5
            if w_end > w_start:
                cond = (low_arr[i] < low_arr[w_start:w_end]) & (mom_arr[i] > mom_arr[w_start:w_end]) & (rsi_arr[w_start:w_end] <= rsi_os)
                if np.any(cond):
                    buy_signal[i] = True

    return pd.DataFrame(
        {
            "rsi": rsi,
            "momentum": momentum,
            "buy_signal": buy_signal,
            "sell_signal": sell_signal,
        },
        index=ohlc.index,
    )


def calculate_sma(series: pd.Series, length: int = 200) -> pd.Series:
    """Calculate Simple Moving Average (SMA)."""
    return series.rolling(window=length, min_periods=length).mean()


def ma200_signals(
    ohlc: pd.DataFrame,
    length: int = 200,
    tolerance: float = 0.01,
) -> pd.DataFrame:
    """200-Day Moving Average Touch and Crossover signals.
    
    Conditions:
    - Crossed Up (Bullish): previous_close < prev_200ma and current_close > curr_200ma
    - Crossed Down (Bearish): previous_close > prev_200ma and current_close < curr_200ma
    - Touched: low <= curr_200ma * (1 + tolerance) and high >= curr_200ma * (1 - tolerance)
    """
    close = ohlc["Close"]
    high = ohlc["High"]
    low = ohlc["Low"]
    sma200 = calculate_sma(close, length=length)

    prev_close = close.shift(1)
    prev_sma = sma200.shift(1)

    cross_up = (prev_close < prev_sma) & (close > sma200)
    cross_down = (prev_close > prev_sma) & (close < sma200)

    # Touch: High or Low reaches within tolerance zone without crossing
    touch = (
        (low <= sma200 * (1.0 + tolerance)) &
        (high >= sma200 * (1.0 - tolerance)) &
        (~cross_up) &
        (~cross_down)
    )

    return pd.DataFrame(
        {
            "sma200": sma200,
            "cross_up": cross_up.fillna(False),
            "cross_down": cross_down.fillna(False),
            "touch": touch.fillna(False),
        },
        index=ohlc.index,
    )

