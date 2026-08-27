"""SQLite connection pool and WAL-mode transaction manager."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator
from core.config import settings
from core.logging import logger


@contextmanager
def get_db_connection() -> Iterator[sqlite3.Connection]:
    """Provide a thread-safe context-managed SQLite connection with WAL mode."""
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Database error: {exc}")
        raise
    finally:
        conn.close()


def initialize_schema() -> None:
    """Initialize signals table, indices, and apply backward-compatible column migrations."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL DEFAULT 'RSI',
                scan_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL CHECK(signal_type IN ('buy', 'sell')),
                signal_date TEXT NOT NULL,
                signal_candle_low REAL NOT NULL,
                confirmation_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                rsi_value REAL,
                rsi_ma_value REAL,
                index_membership TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy, symbol, signal_type, signal_date, confirmation_date)
            )
            """
        )
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        if "strategy" not in existing_cols:
            conn.execute("ALTER TABLE signals ADD COLUMN strategy TEXT NOT NULL DEFAULT 'RSI'")
        if "rsi_value" not in existing_cols:
            conn.execute("ALTER TABLE signals ADD COLUMN rsi_value REAL")
        if "rsi_ma_value" not in existing_cols:
            conn.execute("ALTER TABLE signals ADD COLUMN rsi_ma_value REAL")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_scan_date ON signals(scan_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
