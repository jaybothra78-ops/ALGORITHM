"""Unit and integration tests for Strategy Tester."""
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from main import app
from models.backtest import BacktestRequest
from services.backtester import BacktesterEngine


def _dummy_ohlc(n=250):
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    prices = 100.0 + np.cumsum(np.random.randn(n) * 2.0)
    return pd.DataFrame(
        {
            "Open": prices,
            "High": prices + 3.0,
            "Low": prices - 3.0,
            "Close": prices,
        },
        index=dates,
    )


def test_simulate_trade_target_exit():
    df = _dummy_ohlc(50)
    entry_price = float(df["Close"].iloc[5])
    # Keep low above stop loss for days 6, 7, 8
    df.loc[df.index[6]:df.index[8], "Low"] = entry_price * 0.99
    # Force a 6% gain on day 8
    df.loc[df.index[8], "High"] = entry_price * 1.06

    trade, _ = BacktesterEngine._simulate_trade(
        symbol="TEST",
        strategy="RSI",
        signal_type="buy",
        df=df,
        signal_idx=5,
        entry_idx=5,
        target_pct=5.0,
        stop_loss_pct=2.0,
    )

    assert trade is not None
    assert trade.outcome == "WIN"
    assert trade.exit_reason == "Target Hit"
    assert trade.pnl_pct >= 5.0



def test_simulate_trade_stop_loss_exit():
    df = _dummy_ohlc(50)
    entry_price = float(df["Close"].iloc[5])
    # Keep high below target and force a 3% drop on day 6
    df.loc[df.index[6]:df.index[8], "High"] = entry_price * 1.01
    df.loc[df.index[6], "Low"] = entry_price * 0.97

    trade, _ = BacktesterEngine._simulate_trade(
        symbol="TEST",
        strategy="RSI",
        signal_type="buy",
        df=df,
        signal_idx=5,
        entry_idx=5,
        target_pct=5.0,
        stop_loss_pct=2.0,
    )

    assert trade is not None
    assert trade.outcome == "LOSS"
    assert trade.exit_reason == "Stop Loss Hit"
    assert trade.pnl_pct <= -2.0



def test_backtest_api_endpoint():
    with TestClient(app) as c:
        payload = {
            "strategy": "RSI",
            "target_pct": 5.0,
            "stop_loss_pct": 2.0,
            "max_holding_days": 10,
        }
        resp = c.post("/backtest/run", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "trades" in data
        assert "win_rate_pct" in data["summary"]
        assert "net_return_pct" in data["summary"]
        assert "execution_time_ms" in data


def test_backtest_single_symbol_and_dates():
    with TestClient(app) as c:
        payload = {
            "symbol": "TVSMOTOR",
            "strategy": "RSI",
            "target_pct": 5.0,
            "stop_loss_pct": 2.0,
            "max_holding_days": 10,
            "start_date": "2026-01-01",
            "end_date": "2026-08-28",
        }
        resp = c.post("/backtest/run", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["universe"] == "TVSMOTOR (Single Stock)"

