"""Repository layer for Paper Trading and Virtual Account persistence."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from db.connection import get_db_connection


class PaperRepository:
    """Database repository for managing paper trades and portfolio account."""

    @staticmethod
    def initialize_paper_tables() -> None:
        """Create tables for paper trading and virtual account if they do not exist."""
        with get_db_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initial_capital REAL NOT NULL DEFAULT 1000000.0,
                    cash_balance REAL NOT NULL DEFAULT 1000000.0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO paper_account (id, initial_capital, cash_balance)
                VALUES (1, 1000000.0, 1000000.0);
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                    product_type TEXT NOT NULL DEFAULT 'CNC',
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    target_price REAL,
                    stop_loss_price REAL,
                    strategy TEXT DEFAULT 'Manual',
                    notes TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED')),
                    entry_time TEXT NOT NULL,
                    exit_price REAL,
                    exit_time TEXT,
                    exit_reason TEXT,
                    pnl_amount REAL,
                    pnl_pct REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(paper_trades)").fetchall()}
            if "product_type" not in existing_cols:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN product_type TEXT NOT NULL DEFAULT 'CNC'")

    @staticmethod
    def get_account() -> dict[str, Any]:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
            if row:
                return dict(row)
            return {"initial_capital": 1000000.0, "cash_balance": 1000000.0}

    @staticmethod
    def update_cash_balance(new_balance: float) -> None:
        with get_db_connection() as conn:
            conn.execute("UPDATE paper_account SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (new_balance,))

    @staticmethod
    def reset_account(capital: float = 1000000.0) -> None:
        with get_db_connection() as conn:
            conn.execute("UPDATE paper_account SET initial_capital = ?, cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (capital, capital))
            conn.execute("DELETE FROM paper_trades")

    @staticmethod
    def create_trade(data: dict[str, Any]) -> int:
        PaperRepository.initialize_paper_tables()
        columns = "symbol, side, product_type, quantity, entry_price, target_price, stop_loss_price, strategy, notes, status, entry_time"
        placeholders = "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
        values = (
            data["symbol"],
            data["side"],
            data.get("product_type", "CNC"),
            data["quantity"],
            data["entry_price"],
            data.get("target_price"),
            data.get("stop_loss_price"),
            data.get("strategy", "Manual"),
            data.get("notes", ""),
            "OPEN",
            data.get("entry_time") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        )

        with get_db_connection() as conn:
            cursor = conn.execute(f"INSERT INTO paper_trades ({columns}) VALUES ({placeholders})", values)
            return cursor.lastrowid

    @staticmethod
    def get_open_positions() -> list[dict[str, Any]]:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM paper_trades WHERE status = 'OPEN' ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_position(position_id: int) -> dict[str, Any] | None:
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM paper_trades WHERE id = ? AND status = 'OPEN'", (position_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def close_trade(position_id: int, exit_price: float, exit_reason: str, pnl_amount: float, pnl_pct: float) -> bool:
        exit_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE paper_trades
                SET status = 'CLOSED', exit_price = ?, exit_time = ?, exit_reason = ?, pnl_amount = ?, pnl_pct = ?
                WHERE id = ? AND status = 'OPEN'
                """,
                (exit_price, exit_time, exit_reason, pnl_amount, pnl_pct, position_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_closed_trades() -> list[dict[str, Any]]:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            rows = conn.execute("SELECT * FROM paper_trades WHERE status = 'CLOSED' ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]
