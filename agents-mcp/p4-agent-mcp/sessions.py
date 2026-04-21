"""In-memory session store with TTL-based expiry."""

import time
from typing import Optional

# Session TTL: 1 hour of inactivity
SESSION_TTL = 3600.0

_store: dict[str, dict] = {}


def get_or_create(session_id: str) -> list:
    """Return the message history for a session, creating it if needed."""
    _expire_stale()
    if session_id not in _store:
        _store[session_id] = {"messages": [], "last_used": time.monotonic()}
    else:
        _store[session_id]["last_used"] = time.monotonic()
    return _store[session_id]["messages"]


def update(session_id: str, messages: list) -> None:
    """Persist updated message history for a session."""
    _store[session_id] = {"messages": messages, "last_used": time.monotonic()}


def _expire_stale() -> None:
    now = time.monotonic()
    stale = [sid for sid, data in _store.items() if now - data["last_used"] > SESSION_TTL]
    for sid in stale:
        del _store[sid]
