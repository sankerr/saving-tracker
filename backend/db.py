"""Storage for portfolio data and cache (JSON blobs).

Two interchangeable backends, selected from DATABASE_URL:

  - PostgreSQL (psycopg2) for production (Neon / Render): used when
    DATABASE_URL is a ``postgres://`` / ``postgresql://`` connection string.
  - SQLite (embedded, file-based) for zero-setup local development: used when
    DATABASE_URL is empty or starts with ``sqlite``. Think "H2 for Python" —
    no external service, data lives in a single local file (default
    ``backend/local.db``, override with ``LOCAL_DB_PATH`` or
    ``sqlite:////absolute/path.db``).

The public functions are backend-agnostic; SQL is adapted per backend.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _is_sqlite_url(url: str) -> bool:
    return (not url) or url.startswith("sqlite")


IS_SQLITE = _is_sqlite_url(DATABASE_URL)


def _default_sqlite_path() -> str:
    return os.environ.get("LOCAL_DB_PATH") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "local.db"
    )


def sqlite_path() -> str:
    """Filesystem path of the local SQLite database (SQLite backend only)."""
    url = DATABASE_URL
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):] or _default_sqlite_path()
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):] or _default_sqlite_path()
    return _default_sqlite_path()


# psycopg2 is only needed for the Postgres backend; importing it lazily means
# local SQLite development works without it installed.
if not IS_SQLITE:
    import psycopg2
    import psycopg2.extras


@contextmanager
def _conn():
    if IS_SQLITE:
        conn = sqlite3.connect(sqlite_path())
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _q(sql: str) -> str:
    """Adapt Postgres-flavored SQL to SQLite when running on the SQLite backend."""
    if not IS_SQLITE:
        return sql
    return (
        sql.replace("%s", "?")
        .replace("::jsonb", "")
        .replace("now()", "CURRENT_TIMESTAMP")
        .replace("= true", "= 1")
    )


def _dict_cursor(conn):
    if IS_SQLITE:
        conn.row_factory = sqlite3.Row
        return conn.cursor()
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _user_row(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    if "approved" in d:
        d["approved"] = bool(d["approved"])
    return d


_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    approved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_state (
    user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data_json JSONB NOT NULL,
    cache_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS shared_cache (
    id INT PRIMARY KEY DEFAULT 1,
    cache_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT shared_cache_singleton CHECK (id = 1)
);
"""

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_state (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data_json TEXT NOT NULL,
    cache_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shared_cache (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cache_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_schema() -> None:
    with _conn() as conn:
        cur = conn.cursor()
        if IS_SQLITE:
            cur.executescript(_SQLITE_SCHEMA)
            return
        cur.execute(_PG_SCHEMA)
        cur.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT true
            """
        )
        # Existing DBs may have been created without ON DELETE CASCADE.
        cur.execute(
            "ALTER TABLE app_state DROP CONSTRAINT IF EXISTS app_state_user_id_fkey"
        )
        cur.execute(
            """
            ALTER TABLE app_state
            ADD CONSTRAINT app_state_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            """
        )


def get_user_by_id(user_id: int) -> dict | None:
    with _conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            _q("SELECT id, username, password_hash, approved FROM users WHERE id = %s"),
            (user_id,),
        )
        return _user_row(cur.fetchone())


def get_user_by_username(username: str) -> dict | None:
    with _conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            _q("SELECT id, username, password_hash, approved FROM users WHERE username = %s"),
            (username,),
        )
        return _user_row(cur.fetchone())


DEMO_USERNAME = os.environ.get("DEMO_USERNAME", "demo@saving-tracker.app").strip().lower()


def is_demo_username(username: str) -> bool:
    return (username or "").strip().lower() == DEMO_USERNAME


def is_demo_user(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    return bool(user and is_demo_username(user.get("username") or ""))


def create_user(username: str, password_hash: str, *, approved: bool = False) -> int:
    with _conn() as conn:
        cur = conn.cursor()
        if IS_SQLITE:
            cur.execute(
                "INSERT INTO users (username, password_hash, approved) VALUES (?, ?, ?)",
                (username, password_hash, 1 if approved else 0),
            )
            user_id = cur.lastrowid
        else:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, approved)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (username, password_hash, approved),
            )
            user_id = cur.fetchone()[0]
        cur.execute(
            _q(
                "INSERT INTO app_state (user_id, data_json, cache_json) "
                "VALUES (%s, %s::jsonb, %s::jsonb)"
            ),
            (user_id, "{}", "{}"),
        )
        return user_id


def user_count() -> int:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


def sole_user_id() -> int | None:
    """Deprecated helper — kept for migration scripts."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        row = cur.fetchone()
        return row[0] if row else None


def list_approved_users() -> list[dict]:
    with _conn() as conn:
        cur = _dict_cursor(conn)
        cur.execute(_q("SELECT id, username FROM users WHERE approved = true ORDER BY id"))
        return [dict(row) for row in cur.fetchall()]


def load_state(user_id: int) -> tuple[dict, dict]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            _q("SELECT data_json, cache_json FROM app_state WHERE user_id = %s"),
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return {}, {}
        data, cache = row[0], row[1]
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(cache, str):
            cache = json.loads(cache)
        return data, cache


def save_data_state(user_id: int, data: dict) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            _q(
                """
                INSERT INTO app_state (user_id, data_json, cache_json, updated_at)
                VALUES (%s, %s::jsonb, (SELECT cache_json FROM app_state WHERE user_id = %s), now())
                ON CONFLICT (user_id) DO UPDATE
                SET data_json = EXCLUDED.data_json, updated_at = now()
                """
            ),
            (user_id, json.dumps(data), user_id),
        )


def save_cache_state(user_id: int, cache: dict) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            _q(
                """
                INSERT INTO app_state (user_id, data_json, cache_json, updated_at)
                VALUES (%s, (SELECT data_json FROM app_state WHERE user_id = %s), %s::jsonb, now())
                ON CONFLICT (user_id) DO UPDATE
                SET cache_json = EXCLUDED.cache_json, updated_at = now()
                """
            ),
            (user_id, user_id, json.dumps(cache)),
        )


def upsert_state(user_id: int, data: dict, cache: dict) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            _q(
                """
                INSERT INTO app_state (user_id, data_json, cache_json, updated_at)
                VALUES (%s, %s::jsonb, %s::jsonb, now())
                ON CONFLICT (user_id) DO UPDATE
                SET data_json = EXCLUDED.data_json,
                    cache_json = EXCLUDED.cache_json,
                    updated_at = now()
                """
            ),
            (user_id, json.dumps(data), json.dumps(cache)),
        )


def delete_user(user_id: int) -> bool:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(_q("DELETE FROM app_state WHERE user_id = %s"), (user_id,))
        if IS_SQLITE:
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0
        cur.execute("DELETE FROM users WHERE id = %s RETURNING id", (user_id,))
        return cur.fetchone() is not None


def load_shared_cache() -> dict:
    """Return the single shared market-cache blob, or {} if not yet stored."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT cache_json FROM shared_cache WHERE id = 1")
        row = cur.fetchone()
        if not row:
            return {}
        cache = row[0]
        if isinstance(cache, str):
            cache = json.loads(cache)
        return cache or {}


def save_shared_cache(cache: dict) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            _q(
                """
                INSERT INTO shared_cache (id, cache_json, updated_at)
                VALUES (1, %s::jsonb, now())
                ON CONFLICT (id) DO UPDATE
                SET cache_json = EXCLUDED.cache_json, updated_at = now()
                """
            ),
            (json.dumps(cache),),
        )


def load_seed_cache_from_users() -> dict:
    """Pick the most-recently-synced user's cache blob to seed the shared cache.

    Used once when `shared_cache` is empty so the first cron isn't a full cold
    refetch. Returns {} when no user has synced yet.
    """
    with _conn() as conn:
        cur = conn.cursor()
        if IS_SQLITE:
            cur.execute("SELECT cache_json FROM app_state")
            best, best_ts = None, None
            for (raw,) in cur.fetchall():
                cache = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(cache, dict):
                    continue
                ts = cache.get("last_full_sync_ts")
                try:
                    ts = float(ts)
                except (TypeError, ValueError):
                    continue
                if best_ts is None or ts > best_ts:
                    best, best_ts = cache, ts
            return best or {}
        cur.execute(
            """
            SELECT cache_json FROM app_state
            WHERE (cache_json ->> 'last_full_sync_ts') IS NOT NULL
            ORDER BY (cache_json ->> 'last_full_sync_ts')::float DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return {}
        cache = row[0]
        if isinstance(cache, str):
            cache = json.loads(cache)
        return cache or {}


def update_password_hash(user_id: int, password_hash: str) -> bool:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            _q("UPDATE users SET password_hash = %s WHERE id = %s"),
            (password_hash, user_id),
        )
        return cur.rowcount > 0
