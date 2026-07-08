"""Simple username/password auth with JWT bearer tokens."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "168"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    if not SESSION_SECRET:
        return None
    try:
        return jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
