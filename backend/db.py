"""PostgreSQL storage for portfolio data and cache (JSONB blobs)."""

import json
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")


@contextmanager
def _conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
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
                """
            )
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
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, password_hash, approved FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_username(username: str) -> dict | None:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, password_hash, approved FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def create_user(username: str, password_hash: str, *, approved: bool = False) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, approved)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (username, password_hash, approved),
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO app_state (user_id, data_json, cache_json)
                VALUES (%s, %s::jsonb, %s::jsonb)
                """,
                (user_id, "{}", "{}"),
            )
            return user_id


def user_count() -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]


def sole_user_id() -> int | None:
    """Deprecated helper — kept for migration scripts."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None


def list_approved_users() -> list[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username FROM users WHERE approved = true ORDER BY id"
            )
            return [dict(row) for row in cur.fetchall()]


def load_state(user_id: int) -> tuple[dict, dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data_json, cache_json FROM app_state WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return {}, {}
            data, cache = row
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(cache, str):
                cache = json.loads(cache)
            return data, cache


def save_data_state(user_id: int, data: dict) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (user_id, data_json, cache_json, updated_at)
                VALUES (%s, %s::jsonb, (SELECT cache_json FROM app_state WHERE user_id = %s), now())
                ON CONFLICT (user_id) DO UPDATE
                SET data_json = EXCLUDED.data_json, updated_at = now()
                """,
                (user_id, json.dumps(data), user_id),
            )


def save_cache_state(user_id: int, cache: dict) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (user_id, data_json, cache_json, updated_at)
                VALUES (%s, (SELECT data_json FROM app_state WHERE user_id = %s), %s::jsonb, now())
                ON CONFLICT (user_id) DO UPDATE
                SET cache_json = EXCLUDED.cache_json, updated_at = now()
                """,
                (user_id, user_id, json.dumps(cache)),
            )


def upsert_state(user_id: int, data: dict, cache: dict) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_state (user_id, data_json, cache_json, updated_at)
                VALUES (%s, %s::jsonb, %s::jsonb, now())
                ON CONFLICT (user_id) DO UPDATE
                SET data_json = EXCLUDED.data_json,
                    cache_json = EXCLUDED.cache_json,
                    updated_at = now()
                """,
                (user_id, json.dumps(data), json.dumps(cache)),
            )


def delete_user(user_id: int) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_state WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE id = %s RETURNING id", (user_id,))
            return cur.fetchone() is not None


def update_password_hash(user_id: int, password_hash: str) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (password_hash, user_id),
            )
            return cur.rowcount > 0
