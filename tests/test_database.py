"""Unit tests for SQLite database operations and repository."""
from db.connection import initialize_schema
from db.repository import SignalRepository


def test_save_and_retrieve_signal():
    initialize_schema()
    sig = {
        "strategy": "RSI",
        "scan_date": "2026-08-27",
        "symbol": "TEST_STOCK",
        "signal_type": "buy",
        "signal_date": "2026-08-27",
        "signal_candle_low": 100.0,
        "confirmation_date": "2026-08-27",
        "entry_price": 105.0,
        "stop_loss": 99.0,
        "rsi_value": 25.4,
        "rsi_ma_value": 26.1,
        "index_membership": "Watchlist",
    }
    inserted = SignalRepository.save(sig)
    assert inserted in (True, False)

    results = SignalRepository.get_signals("2026-08-27", strategy="RSI")
    assert any(r["symbol"] == "TEST_STOCK" for r in results)
