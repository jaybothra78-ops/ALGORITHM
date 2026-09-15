"""Repository layer for Paper Trading and Virtual Account persistence with Multi-User isolation."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from db.connection import get_db_connection


class PaperRepository:
    """Database repository for managing paper trades and portfolio accounts per user."""

    _initialized: bool = False

    @classmethod
    def initialize_paper_tables(cls) -> None:
        """Create tables for paper trading and virtual accounts if they do not exist, and migrate columns."""
        if cls._initialized:
            return

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
                CREATE TABLE IF NOT EXISTS paper_user_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    initial_capital REAL NOT NULL DEFAULT 1000000.0,
                    cash_balance REAL NOT NULL DEFAULT 1000000.0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Migrate existing legacy single-account data into user 1
            existing_legacy = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
            init_cap = float(existing_legacy["initial_capital"]) if existing_legacy else 1000000.0
            cash_bal = float(existing_legacy["cash_balance"]) if existing_legacy else 1000000.0

            conn.execute(
                """
                INSERT OR IGNORE INTO paper_user_accounts (user_id, initial_capital, cash_balance)
                VALUES (1, ?, ?);
                """,
                (init_cap, cash_bal),
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    symbol TEXT NOT NULL,
                    display_symbol TEXT,
                    instrument_type TEXT NOT NULL DEFAULT 'EQUITY',
                    option_type TEXT,
                    strike_price REAL,
                    expiry_date TEXT,
                    lot_size INTEGER NOT NULL DEFAULT 1,
                    contracts INTEGER NOT NULL DEFAULT 1,
                    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
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
            # Safe schema migration for existing SQLite databases
            cursor = conn.execute("PRAGMA table_info(paper_trades);")
            existing_cols = {row["name"] for row in cursor.fetchall()}

            migrations = [
                ("user_id", "INTEGER NOT NULL DEFAULT 1"),
                ("display_symbol", "TEXT"),
                ("instrument_type", "TEXT DEFAULT 'EQUITY'"),
                ("option_type", "TEXT"),
                ("strike_price", "REAL"),
                ("expiry_date", "TEXT"),
                ("lot_size", "INTEGER DEFAULT 1"),
                ("contracts", "INTEGER DEFAULT 1"),
            ]
            for col_name, col_type in migrations:
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE paper_trades ADD COLUMN {col_name} {col_type};")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_trades_user_status ON paper_trades(user_id, status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_user_accounts_user ON paper_user_accounts(user_id);")
            cls._initialized = True


    @staticmethod
    def get_account(user_id: int = 1) -> dict[str, Any]:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM paper_user_accounts WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return dict(row)
            # Create default account for new user
            conn.execute(
                "INSERT OR IGNORE INTO paper_user_accounts (user_id, initial_capital, cash_balance) VALUES (?, 1000000.0, 1000000.0)",
                (user_id,),
            )
            return {"user_id": user_id, "initial_capital": 1000000.0, "cash_balance": 1000000.0}

    @staticmethod
    def update_cash_balance(new_balance: float, user_id: int = 1) -> None:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO paper_user_accounts (user_id, initial_capital, cash_balance, updated_at)
                VALUES (?, 1000000.0, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP;
                """,
                (user_id, new_balance, new_balance),
            )

    @staticmethod
    def reset_account(capital: float = 1000000.0, user_id: int = 1) -> None:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO paper_user_accounts (user_id, initial_capital, cash_balance, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET initial_capital = ?, cash_balance = ?, updated_at = CURRENT_TIMESTAMP;
                """,
                (user_id, capital, capital, capital, capital),
            )
            conn.execute("DELETE FROM paper_trades WHERE user_id = ?", (user_id,))

    @staticmethod
    def create_trade(data: dict[str, Any], user_id: int = 1) -> int:
        PaperRepository.initialize_paper_tables()
        columns = (
            "user_id, symbol, display_symbol, instrument_type, option_type, strike_price, expiry_date, "
            "lot_size, contracts, side, quantity, entry_price, target_price, stop_loss_price, "
            "strategy, notes, status, entry_time"
        )
        placeholders = "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
        values = (
            user_id,
            data["symbol"],
            data.get("display_symbol") or data["symbol"],
            data.get("instrument_type", "EQUITY"),
            data.get("option_type"),
            data.get("strike_price"),
            data.get("expiry_date"),
            data.get("lot_size", 1),
            data.get("contracts", 1),
            data["side"],
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
    def get_open_positions(user_id: int = 1) -> list[dict[str, Any]]:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_trades WHERE user_id = ? AND status = 'OPEN' ORDER BY id DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_position(position_id: int, user_id: int = 1) -> dict[str, Any] | None:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM paper_trades WHERE id = ? AND user_id = ? AND status = 'OPEN'",
                (position_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def close_trade(
        position_id: int,
        exit_price: float,
        exit_reason: str,
        pnl_amount: float,
        pnl_pct: float,
        user_id: int = 1,
    ) -> bool:
        PaperRepository.initialize_paper_tables()
        exit_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE paper_trades
                SET status = 'CLOSED', exit_price = ?, exit_time = ?, exit_reason = ?, pnl_amount = ?, pnl_pct = ?
                WHERE id = ? AND user_id = ? AND status = 'OPEN'
                """,
                (exit_price, exit_time, exit_reason, pnl_amount, pnl_pct, position_id, user_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_trade(position_id: int, updates: dict[str, Any], user_id: int = 1) -> bool:
        """Update mutable fields of an active open trade for a specific user."""
        if not updates:
            return False

        allowed = {"quantity", "contracts", "target_price", "stop_loss_price", "notes", "strategy"}
        clean_updates = {k: v for k, v in updates.items() if k in allowed}
        if not clean_updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in clean_updates.keys())
        params = list(clean_updates.values())
        params.extend([position_id, user_id])

        with get_db_connection() as conn:
            cursor = conn.execute(
                f"UPDATE paper_trades SET {set_clause} WHERE id = ? AND user_id = ? AND status = 'OPEN'",
                params,
            )
            return cursor.rowcount > 0

    @staticmethod
    def get_closed_trades(user_id: int = 1) -> list[dict[str, Any]]:
        PaperRepository.initialize_paper_tables()
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_trades WHERE user_id = ? AND status = 'CLOSED' ORDER BY id DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]
