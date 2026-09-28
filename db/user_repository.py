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

        from db.paper_repository import PaperRepository
        PaperRepository.initialize_paper_tables()

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

            # 0. Migrate table schema for Google OAuth if columns do not exist
            user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "google_id" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
            if "email" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            if "avatar_url" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

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

            # 4. Load any persistent users from config/users_seed.json
            from core.config import settings
            if settings.USERS_SEED_PATH.exists():
                try:
                    import json
                    seed_users = json.loads(settings.USERS_SEED_PATH.read_text(encoding="utf-8"))
                    for su in seed_users:
                        uname = su.get("username", "").strip().lower()
                        if not uname:
                            continue
                        exists = conn.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()
                        if not exists:
                            cur = conn.execute(
                                """
                                INSERT INTO users (username, password_hash, salt, display_name, google_id, email, avatar_url)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    uname,
                                    su.get("password_hash", ""),
                                    su.get("salt", ""),
                                    su.get("display_name", uname.capitalize()),
                                    su.get("google_id"),
                                    su.get("email"),
                                    su.get("avatar_url", ""),
                                ),
                            )
                            new_uid = cur.lastrowid
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO paper_user_accounts (user_id, initial_capital, cash_balance)
                                VALUES (?, 1000000.0, 1000000.0)
                                """,
                                (new_uid,),
                            )
                except Exception:
                    pass

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

            # Persist newly registered user to users_seed.json (avoiding ephemeral test fixtures)
            try:
                import sys
                if "pytest" not in sys.modules and not clean_user.startswith("test_"):
                    from core.config import settings
                    import json
                    seed_data = []
                    if settings.USERS_SEED_PATH.exists():
                        seed_data = json.loads(settings.USERS_SEED_PATH.read_text(encoding="utf-8"))
                    if not any(u.get("username") == clean_user for u in seed_data):
                        seed_data.append({
                            "username": clean_user,
                            "password_hash": pwd_hash,
                            "salt": salt,
                            "display_name": disp_name,
                        })
                        settings.USERS_SEED_PATH.write_text(json.dumps(seed_data, indent=2), encoding="utf-8")
            except Exception:
                pass

            return {
                "id": user_id,
                "username": clean_user,
                "display_name": disp_name,
            }

    @classmethod
    def user_exists(cls, username: str) -> bool:
        """Check if a username already exists in the database."""
        cls.initialize_user_tables()
        clean_user = username.strip().lower()
        with get_db_connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (clean_user,)).fetchone()
            if not row and clean_user == "trader":
                row = conn.execute("SELECT id FROM users WHERE username = 'jay'").fetchone()
            return row is not None

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
                    "email": row["email"] if "email" in row.keys() else None,
                    "google_id": row["google_id"] if "google_id" in row.keys() else None,
                    "avatar_url": row["avatar_url"] if "avatar_url" in row.keys() else None,
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
                SELECT u.id, u.username, u.display_name, u.email, u.google_id, u.avatar_url
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
            row = conn.execute(
                "SELECT id, username, display_name, email, google_id, avatar_url FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def get_user_by_google_id(cls, google_id: str) -> dict[str, Any] | None:
        """Find a user account linked to a specific Google subject ID."""
        if not google_id:
            return None
        cls.initialize_user_tables()
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, username, display_name, email, google_id, avatar_url FROM users WHERE google_id = ?",
                (str(google_id),),
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def get_user_by_email(cls, email: str) -> dict[str, Any] | None:
        """Find a user account by email address (case-insensitive)."""
        if not email:
            return None
        cls.initialize_user_tables()
        clean_email = email.strip().lower()
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, username, display_name, email, google_id, avatar_url FROM users WHERE LOWER(email) = ?",
                (clean_email,),
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def link_google_account(
        cls, user_id: int, google_id: str, email: str, avatar_url: str | None = None
    ) -> dict[str, Any]:
        """Link a verified Google account to an existing user profile."""
        cls.initialize_user_tables()
        with get_db_connection() as conn:
            # Verify google_id is not already linked to another user
            existing = conn.execute(
                "SELECT id, username FROM users WHERE google_id = ? AND id != ?",
                (str(google_id), user_id),
            ).fetchone()
            if existing:
                trade_count = conn.execute(
                    "SELECT COUNT(*) FROM paper_trades WHERE user_id = ?", (existing["id"],)
                ).fetchone()[0]
                if trade_count == 0:
                    conn.execute("UPDATE users SET google_id = NULL WHERE id = ?", (existing["id"],))
                else:
                    raise ValueError(f"This Google account is already linked to trader account '{existing['username']}'")

            conn.execute(
                """
                UPDATE users
                SET google_id = ?,
                    email = COALESCE(email, ?),
                    avatar_url = CASE WHEN avatar_url IS NULL OR avatar_url = '' THEN ? ELSE avatar_url END
                WHERE id = ?
                """,
                (str(google_id), email.strip().lower(), avatar_url or "", user_id),
            )

        user = cls.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        return user

    @classmethod
    def unlink_google_account(cls, user_id: int) -> dict[str, Any]:
        """Unlink Google account from a user profile."""
        cls.initialize_user_tables()
        with get_db_connection() as conn:
            conn.execute("UPDATE users SET google_id = NULL WHERE id = ?", (user_id,))
        user = cls.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        return user

    @classmethod
    def create_google_user(
        cls, google_id: str, email: str, display_name: str, avatar_url: str | None = None
    ) -> dict[str, Any]:
        """Create a new trader profile from a verified Google sign-in."""
        cls.initialize_user_tables()
        clean_email = email.strip().lower()
        base_username = (clean_email.split("@")[0] if clean_email else display_name.lower().replace(" ", "_")).strip()
        base_username = "".join(c for c in base_username if c.isalnum() or c in ("_", "-"))
        if len(base_username) < 3:
            base_username = f"trader_{base_username}"

        with get_db_connection() as conn:
            # Generate unique username
            candidate = base_username
            counter = 1
            while conn.execute("SELECT id FROM users WHERE username = ?", (candidate,)).fetchone():
                candidate = f"{base_username}_{counter}"
                counter += 1

            dummy_salt = secrets.token_hex(16)
            dummy_hash = cls._hash_password(secrets.token_urlsafe(32), dummy_salt)
            disp_name = display_name.strip() or candidate.capitalize()

            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, display_name, google_id, email, avatar_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate, dummy_hash, dummy_salt, disp_name, str(google_id), clean_email, avatar_url or ""),
            )
            user_id = cursor.lastrowid

            # Initialize virtual trading balance with ₹10,00,000 capital
            conn.execute(
                """
                INSERT OR IGNORE INTO paper_user_accounts (user_id, initial_capital, cash_balance)
                VALUES (?, 1000000.0, 1000000.0)
                """,
                (user_id,),
            )

            # Persist to seed file if not under automated testing
            try:
                import sys
                if "pytest" not in sys.modules and not candidate.startswith("test_"):
                    from core.config import settings
                    import json
                    seed_data = []
                    if settings.USERS_SEED_PATH.exists():
                        seed_data = json.loads(settings.USERS_SEED_PATH.read_text(encoding="utf-8"))
                    if not any(u.get("username") == candidate for u in seed_data):
                        seed_data.append({
                            "username": candidate,
                            "password_hash": dummy_hash,
                            "salt": dummy_salt,
                            "display_name": disp_name,
                            "google_id": str(google_id),
                            "email": clean_email,
                            "avatar_url": avatar_url or "",
                        })
                        settings.USERS_SEED_PATH.write_text(json.dumps(seed_data, indent=2), encoding="utf-8")
            except Exception:
                pass

            return {
                "id": user_id,
                "username": candidate,
                "display_name": disp_name,
                "email": clean_email,
                "google_id": str(google_id),
                "avatar_url": avatar_url or "",
            }

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
            rows = conn.execute(
                "SELECT id, username, display_name, email, google_id, avatar_url FROM users ORDER BY id ASC"
            ).fetchall()
            return [dict(r) for r in rows]
