"""Unit tests for indicator calculations."""
import numpy as np
import pandas as pd
from services.indicators import calculate_rsi, calculate_rsi_ma, rb_knox_divergence, rsi_signals


def _dummy_ohlc(n=200):
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    prices = 100.0 + np.cumsum(np.random.randn(n) * 2.0)
    return pd.DataFrame(
        {
            "Open": prices,
            "High": prices + 2.0,
            "Low": prices - 2.0,
            "Close": prices,
        },
        index=dates,
    )


def test_rsi_bounds():
    df = _dummy_ohlc(100)
    rsi = calculate_rsi(df["Close"], length=14)
    assert len(rsi) == 100
    assert (rsi >= 0.0).all()
    assert (rsi <= 100.0).all()


def test_rsi_ma():
    df = _dummy_ohlc(100)
    rsi = calculate_rsi(df["Close"], length=14)
    rsi_ma = calculate_rsi_ma(rsi, length=14)
    assert len(rsi_ma) == 100
    assert not rsi_ma.isna().all()


def test_rb_knox_divergence_shape():
    df = _dummy_ohlc(200)
    res = rb_knox_divergence(df, look_back=50, mom_period=10, rsi_period=14)
    assert "buy_signal" in res.columns
    assert "sell_signal" in res.columns
    assert len(res) == 200
