"""Repository layer for persisting and querying signal records."""
from __future__ import annotations

from typing import Any
from db.connection import get_db_connection
from models.signal import SignalRecord


class SignalRepository:
    """Database repository for trading signals."""

    @staticmethod
    def save(signal_data: dict[str, Any] | SignalRecord) -> bool:
        """Insert a signal record once. Returns True if inserted, False if duplicate."""
        data = signal_data.model_dump() if isinstance(signal_data, SignalRecord) else dict(signal_data)
        data.setdefault("strategy", "RSI")
        data.setdefault("rsi_value", None)
        data.setdefault("rsi_ma_value", None)

        columns = (
            "strategy, scan_date, symbol, signal_type, signal_date, signal_candle_low, "
            "confirmation_date, entry_price, stop_loss, rsi_value, rsi_ma_value, index_membership"
        )
        placeholders = ", ".join(["?"] * len(columns.split(", ")))

        with get_db_connection() as conn:
            cursor = conn.execute(
                f"INSERT OR IGNORE INTO signals ({columns}) VALUES ({placeholders})",
                tuple(data.get(k.strip()) for k in columns.split(", ")),
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_signals(
        scan_date: str,
        index: str | None = None,
        signal_type: str | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query signals with flexible filtering."""
        query = "SELECT * FROM signals WHERE scan_date = ?"
        params: list[str] = [scan_date]

        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        if index:
            query += " AND ('|' || index_membership || '|') LIKE ?"
            params.append(f"%|{index}|%")
        if signal_type:
            query += " AND signal_type = ?"
            params.append(signal_type)

        query += " ORDER BY symbol, signal_type"

        with get_db_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]
