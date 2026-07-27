"""Structured logging with secret scrubbing (task 0.12, CLAUDE.md §7, PRD §19).

Secrets must never be logged (CLAUDE.md §6/§7). The scrub processor redacts values of any
structured key whose name looks sensitive (api_key, secret, token, password, access_token,
authorization, private_key, ...), recursing into nested dicts/lists. Put secrets in structured
fields, never interpolated into the free-text message — the message string is not scrubbable.
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

_REDACTED = "***REDACTED***"

# Substrings that mark a field as sensitive (case-insensitive).
_SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "access_token",
    "authorization",
    "private_key",
    "passwd",
)


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(marker in k for marker in _SENSITIVE_MARKERS)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (_REDACTED if _is_sensitive(str(k)) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub(v) for v in value)
    return value


def scrub_secrets(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """structlog processor: redact sensitive keys anywhere in the event dict."""
    return {k: (_REDACTED if _is_sensitive(str(k)) else _scrub(v)) for k, v in event_dict.items()}


def configure_logging(*, json_output: bool = True, level: str = "INFO") -> None:
    """Configure structlog once at startup. JSON in prod; the scrub processor is always on."""
    renderer: Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            scrub_secrets,  # last line of defense before rendering
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a bound logger for ``name``."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
