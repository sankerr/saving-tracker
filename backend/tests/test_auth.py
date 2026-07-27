"""Backend unit tests."""

import os

# Required before importing auth (reads SESSION_SECRET at import time).
os.environ.setdefault("SESSION_SECRET", "ci-unit-test-secret")

import auth


def test_is_valid_email():
    assert auth.is_valid_email("you@example.com") is True
    assert auth.is_valid_email("bad") is False
    assert auth.is_valid_email("") is False
    assert auth.is_valid_email("a@b.c") is True


def test_password_hash_roundtrip():
    hashed = auth.hash_password("secret-password")
    assert hashed != "secret-password"
    assert auth.verify_password("secret-password", hashed) is True
    assert auth.verify_password("wrong", hashed) is False


def test_jwt_roundtrip():
    token = auth.create_token(42, "you@example.com")
    payload = auth.decode_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["username"] == "you@example.com"
