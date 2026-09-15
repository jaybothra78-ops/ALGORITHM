"""Repository layer for User-specific Custom Watchlists."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from core.config import settings
from core.logging import logger
from db.connection import get_db_connection


class WatchlistRepository:
    """Database repository for custom watchlists isolated per user."""

    _initialized: bool = False

    @classmethod
    def initialize_watchlist_tables(cls) -> None:
        """Create user_watchlists table and migrate any existing file-based watchlists into user 1."""
        if cls._initialized:
            return

        with get_db_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_watchlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    symbols TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_watchlists_user ON user_watchlists(user_id);")

            # Check if user 1 has watchlists; if not, migrate from custom_watchlists.json
            cnt_row = conn.execute("SELECT COUNT(*) as cnt FROM user_watchlists WHERE user_id = 1").fetchone()
            if cnt_row and cnt_row["cnt"] == 0 and settings.CUSTOM_WATCHLISTS_PATH.exists():
                try:
                    data = json.loads(settings.CUSTOM_WATCHLISTS_PATH.read_text(encoding="utf-8"))
                    for name, symbols in data.items():
                        if isinstance(symbols, list) and symbols:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO user_watchlists (user_id, name, symbols)
                                VALUES (1, ?, ?)
                                """,
                                (name, json.dumps(sorted(list(set(symbols))))),
                            )
                except Exception as exc:
                    logger.warning(f"Failed to migrate legacy custom_watchlists.json: {exc}")
            cls._initialized = True


    @classmethod
    def load_custom_watchlists(cls, user_id: int = 1) -> dict[str, list[str]]:
        """Load custom watchlists for a specific user."""
        cls.initialize_watchlist_tables()
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT name, symbols FROM user_watchlists WHERE user_id = ? ORDER BY name ASC",
                (user_id,),
            ).fetchall()
            result: dict[str, list[str]] = {}
            for r in rows:
                try:
                    result[r["name"]] = json.loads(r["symbols"])
                except Exception:
                    result[r["name"]] = []
            return result

    @classmethod
    def save_custom_watchlist(cls, name: str, symbols: list[str], user_id: int = 1) -> None:
        """Save or update an imported custom watchlist for a specific user."""
        cls.initialize_watchlist_tables()
        clean_name = name.strip()
        clean_symbols = sorted(list(set(s.strip().upper() for s in symbols if s.strip())))
        symbols_json = json.dumps(clean_symbols)

        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_watchlists (user_id, name, symbols)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, name) DO UPDATE SET symbols = excluded.symbols;
                """,
                (user_id, clean_name, symbols_json),
            )

    @classmethod
    def delete_custom_watchlist(cls, name: str, user_id: int = 1) -> bool:
        """Delete an imported custom watchlist for a specific user."""
        cls.initialize_watchlist_tables()
        with get_db_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM user_watchlists WHERE user_id = ? AND name = ?",
                (user_id, name.strip()),
            )
            return cursor.rowcount > 0
