"""Secret-scrub tests (task 0.12 AC: no secret leakage in logs)."""

from __future__ import annotations

from typing import Any

from icarus.common.logging import scrub_secrets

SECRET = "kite_live_abcdef123456"


def _scrub(d: dict[str, Any]) -> dict[str, Any]:
    return dict(scrub_secrets(None, "info", d))


def test_top_level_secret_redacted() -> None:
    out = _scrub({"event": "auth", "api_secret": SECRET, "user": "sujay"})
    assert out["api_secret"] == "***REDACTED***"
    assert out["user"] == "sujay"
    assert SECRET not in repr(out)


def test_nested_secret_redacted() -> None:
    out = _scrub({"event": "cfg", "broker": {"kite": {"access_token": SECRET, "id": "X"}}})
    assert SECRET not in repr(out)
    assert out["broker"]["kite"]["id"] == "X"


def test_secret_in_list_of_dicts_redacted() -> None:
    out = _scrub({"keys": [{"password": SECRET}, {"name": "ok"}]})
    assert SECRET not in repr(out)


def test_various_sensitive_key_names() -> None:
    for key in ["API_KEY", "Authorization", "private_key", "userToken", "db_passwd"]:
        out = _scrub({key: SECRET})
        assert out[key] == "***REDACTED***", key


def test_non_sensitive_untouched() -> None:
    out = _scrub({"symbol": "INFY", "qty": 5, "price": 1500.0})
    assert out == {"symbol": "INFY", "qty": 5, "price": 1500.0}
