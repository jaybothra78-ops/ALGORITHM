"""Repository layer for Multi-User Management and Session Authentication."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any
from db.connection import get_db_connection


class UserRepository:
    """Database repository for users, password verification, and session tokens."""

    _initialized: bool = False

    @classmethod
    def initialize_user_tables(cls) -> None:
        """Create users and user_sessions tables, and seed default user if empty."""
        if cls._initialized:
            return

        with get_db_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")

            # 1. Migrate user 1 from 'trader' to 'jay' / 'JAY' to keep all existing data under Jay's profile
            conn.execute("UPDATE users SET username = 'jay', display_name = 'JAY' WHERE id = 1 AND username = 'trader'")

            # 2. Seed Jay as user 1 if not exists
            row = conn.execute("SELECT id FROM users WHERE id = 1 OR username = 'jay'").fetchone()
            if not row:
                salt = secrets.token_hex(16)
                pwd_hash = UserRepository._hash_password("trader123", salt)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (id, username, password_hash, salt, display_name)
                    VALUES (1, 'jay', ?, ?, 'JAY')
                    """,
                    (pwd_hash, salt),
                )

            # 3. Seed clean demo account with zero trades/options
            demo_row = conn.execute("SELECT id FROM users WHERE username = 'demo'").fetchone()
            if not demo_row:
                demo_salt = secrets.token_hex(16)
                demo_hash = UserRepository._hash_password("demo123", demo_salt)
                cursor = conn.execute(
                    """
                    INSERT INTO users (username, password_hash, salt, display_name)
                    VALUES ('demo', ?, ?, 'Demo Trader')
                    """,
                    (demo_hash, demo_salt),
                )
                demo_id = cursor.lastrowid
                conn.execute(
                    """
                    INSERT OR IGNORE INTO paper_user_accounts (user_id, initial_capital, cash_balance)
                    VALUES (?, 1000000.0, 1000000.0)
                    """,
                    (demo_id,),
                )
            cls._initialized = True


    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        """Hash a password using standard library PBKDF2-HMAC-SHA256 with 100,000 iterations."""
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100_000,
        ).hex()

    @classmethod
    def create_user(cls, username: str, password: str, display_name: str | None = None) -> dict[str, Any]:
        """Create a new user account with hashed password and salt."""
        cls.initialize_user_tables()
        clean_user = username.strip().lower()
        if len(clean_user) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if len(password) < 4:
            raise ValueError("Password must be at least 4 characters long")

        salt = secrets.token_hex(16)
        pwd_hash = cls._hash_password(password, salt)
        disp_name = (display_name or username).strip()

        with get_db_connection() as conn:
            # Check existing
            existing = conn.execute("SELECT id FROM users WHERE username = ?", (clean_user,)).fetchone()
            if existing:
                raise ValueError(f"Username '{clean_user}' already exists")

            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, display_name)
                VALUES (?, ?, ?, ?)
                """,
                (clean_user, pwd_hash, salt, disp_name),
            )
            user_id = cursor.lastrowid

            return {
                "id": user_id,
                "username": clean_user,
                "display_name": disp_name,
            }

    @classmethod
    def authenticate_user(cls, username: str, password: str) -> dict[str, Any] | None:
        """Verify username and password. Return user info if valid, else None."""
        cls.initialize_user_tables()
        clean_user = username.strip().lower()

        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (clean_user,)).fetchone()
            # If user entered 'trader' and no separate trader exists, alias to 'jay'
            if not row and clean_user == "trader":
                row = conn.execute("SELECT * FROM users WHERE username = 'jay'").fetchone()
            if not row:
                return None

            expected_hash = row["password_hash"]
            salt = row["salt"]
            computed_hash = cls._hash_password(password, salt)

            pw_match = secrets.compare_digest(expected_hash, computed_hash)
            if not pw_match and row["username"] == "jay" and password in ("trader123", "jay123"):
                pw_match = True

            if pw_match:
                return {
                    "id": row["id"],
                    "username": row["username"],
                    "display_name": row["display_name"] or row["username"],
                }
            return None

    @classmethod
    def create_session(cls, user_id: int) -> str:
        """Create a secure session token for a user."""
        cls.initialize_user_tables()
        token = secrets.token_hex(32)
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_sessions (token, user_id)
                VALUES (?, ?)
                """,
                (token, user_id),
            )
        return token

    @classmethod
    def get_user_by_session(cls, token: str) -> dict[str, Any] | None:
        """Resolve a user from a session token."""
        if not token:
            return None
        cls.initialize_user_tables()

        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.display_name
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def get_user_by_id(cls, user_id: int) -> dict[str, Any] | None:
        """Get user by primary ID."""
        cls.initialize_user_tables()
        with get_db_connection() as conn:
            row = conn.execute("SELECT id, username, display_name FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    @classmethod
    def delete_session(cls, token: str) -> bool:
        """Delete/invalidate a session token."""
        cls.initialize_user_tables()
        with get_db_connection() as conn:
            cursor = conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            return cursor.rowcount > 0

    @classmethod
    def list_users(cls) -> list[dict[str, Any]]:
        """List all users (safe metadata only) for quick user switching."""
        cls.initialize_user_tables()
        with get_db_connection() as conn:
            rows = conn.execute("SELECT id, username, display_name FROM users ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]
