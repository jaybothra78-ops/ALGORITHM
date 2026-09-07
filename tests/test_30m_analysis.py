"""Unit and integration tests for 30min Analysis strategy."""
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from main import app
from models.backtest import BacktestRequest, ExitReason
from services.backtester import BacktesterEngine


def _create_synthetic_30m_day(date_str: str, base_price: float = 1000.0) -> pd.DataFrame:
    """Create a single-day 30-minute dataframe (09:15 to 15:15, 13 candles) in Asia/Kolkata."""
    times = [
        "09:15", "09:45", "10:15", "10:45", "11:15", "11:45",
        "12:15", "12:45", "13:15", "13:45", "14:15", "14:45", "15:15"
    ]
    dts = pd.to_datetime([f"{date_str} {t}:00" for t in times]).tz_localize("Asia/Kolkata")

    df = pd.DataFrame(
        {
            "Open": [base_price] * len(times),
            "High": [base_price + 2.0] * len(times),
            "Low": [base_price - 2.0] * len(times),
            "Close": [base_price] * len(times),
            "Volume": [10000] * len(times),
        },
        index=dts,
    )
    return df


def test_30m_buy_breakout_target_hit():
    """Test BUY breakout when price breaks above 09:15 candle High and hits target."""
    df = _create_synthetic_30m_day("2026-09-01", base_price=1000.0)
    # 09:15 candle: High = 1010.0, Low = 990.0
    df.loc[df.index[0], "High"] = 1010.0
    df.loc[df.index[0], "Low"] = 990.0

    # 09:45 candle: Breaks High at 1010.0, reaches 1016.0 (target is 1010 * 1.005 = 1015.05)
    df.loc[df.index[1], "Open"] = 1005.0
    df.loc[df.index[1], "High"] = 1016.0
    df.loc[df.index[1], "Low"] = 1004.0
    df.loc[df.index[1], "Close"] = 1014.0

    req = BacktestRequest(strategy="30MIN_ANALYSIS", target_pct=0.5, stop_loss_pct=0.8)
    trades = BacktesterEngine._backtest_30m_analysis("TEST", df, req)

    assert len(trades) == 1
    t = trades[0]
    assert t.strategy == "30min Analysis"
    assert t.signal_type == "buy"
    assert t.entry_price == 1010.0
    assert t.outcome == "WIN"
    assert t.exit_reason == ExitReason.TARGET_HIT.value
    assert t.pnl_pct >= 0.5


def test_30m_sell_breakdown_stop_loss_hit():
    """Test SELL breakdown when price breaks below 09:15 candle Low and hits stop loss."""
    df = _create_synthetic_30m_day("2026-09-02", base_price=1000.0)
    # 09:15 candle: High = 1010.0, Low = 990.0
    df.loc[df.index[0], "High"] = 1010.0
    df.loc[df.index[0], "Low"] = 990.0

    # 09:45 candle: Breaks Low at 990.0 (entry = 990.0, target = 985.05, SL = 990 * 1.008 = 997.92)
    df.loc[df.index[1], "Open"] = 995.0
    df.loc[df.index[1], "High"] = 996.0
    df.loc[df.index[1], "Low"] = 988.0
    df.loc[df.index[1], "Close"] = 989.0

    # 10:15 candle: Price reverses upward and hits SL (High = 999.0 >= 997.92)
    df.loc[df.index[2], "Open"] = 990.0
    df.loc[df.index[2], "High"] = 999.0
    df.loc[df.index[2], "Low"] = 989.0
    df.loc[df.index[2], "Close"] = 998.0

    req = BacktestRequest(strategy="30MIN_ANALYSIS", target_pct=0.5, stop_loss_pct=0.8)
    trades = BacktesterEngine._backtest_30m_analysis("TEST", df, req)

    assert len(trades) == 1
    t = trades[0]
    assert t.strategy == "30min Analysis"
    assert t.signal_type == "sell"
    assert t.entry_price == 990.0
    assert t.outcome == "LOSS"
    assert t.exit_reason == ExitReason.STOP_LOSS_HIT.value
    assert t.pnl_pct < 0


def test_30m_intraday_eod_square_off():
    """Test intraday square-off on final candle if neither target nor stop loss is triggered."""
    df = _create_synthetic_30m_day("2026-09-03", base_price=1000.0)
    # 09:15 candle
    df.loc[df.index[0], "High"] = 1005.0
    df.loc[df.index[0], "Low"] = 995.0

    # 09:45 candle breaks High to 1006.0 -> BUY entry at 1005.0 (Target: 1010.025, SL: 996.96)
    df.loc[df.index[1], "Open"] = 1002.0
    df.loc[df.index[1], "High"] = 1006.0
    df.loc[df.index[1], "Low"] = 1001.0
    df.loc[df.index[1], "Close"] = 1004.0

    # Remaining candles stay strictly within (998.0, 1008.0)
    for k in range(2, len(df)):
        df.loc[df.index[k], "Open"] = 1003.0
        df.loc[df.index[k], "High"] = 1007.0
        df.loc[df.index[k], "Low"] = 998.0
        df.loc[df.index[k], "Close"] = 1004.0

    req = BacktestRequest(strategy="30MIN_ANALYSIS", target_pct=0.5, stop_loss_pct=0.8)
    trades = BacktesterEngine._backtest_30m_analysis("TEST", df, req)

    assert len(trades) == 1
    t = trades[0]
    assert t.strategy == "30min Analysis"
    assert t.signal_type == "buy"
    assert t.exit_reason == ExitReason.TIME_EXIT.value
    assert t.exit_date.endswith("15:15")


def test_run_backtest_30m_analysis_engine():
    """Test full engine run_backtest with 30MIN_ANALYSIS strategy on cached symbol."""
    req = BacktestRequest(symbol="TCS", strategy="30MIN_ANALYSIS", target_pct=0.5, stop_loss_pct=0.8)
    resp = BacktesterEngine.run_backtest(req)

    assert resp.summary is not None
    assert resp.summary.strategy == "30MIN_ANALYSIS"
    assert resp.summary.total_trades > 0
    assert resp.summary.win_rate_pct > 0
    assert len(resp.trades) == resp.summary.total_trades
    assert resp.trades[0].strategy == "30min Analysis"


def test_ohlc_endpoint_30m_interval():
    """Test /market/ohlc/{symbol}?interval=30m returns valid candles with unix timestamp."""
    client = TestClient(app)
    res = client.get("/market/ohlc/TCS?interval=30m")
    assert res.status_code == 200
    candles = res.json()
    assert len(candles) > 0
    first = candles[0]
    assert "time" in first
    assert isinstance(first["time"], int)
    assert "datetime" in first
    assert "open" in first
    assert "high" in first
    assert "low" in first
    assert "close" in first
