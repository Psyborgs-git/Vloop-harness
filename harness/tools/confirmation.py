"""ConfirmationStore — in-memory store for short-lived destructive-action tokens.

Tokens are single-use and expire after TTL_SECONDS (default 60 s).
They are never persisted to disk or DB.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

TTL_SECONDS = 60


@dataclass
class PendingConfirmation:
    """A pending destructive action waiting for human approval."""

    token: str
    description: str
    risk_level: str          # "caution" | "destructive"
    action_name: str         # e.g. "delete", "terminal"
    action_params: dict[str, Any]
    created_at: float        # time.monotonic()
    expires_at: float        # created_at + TTL_SECONDS


class ConfirmationStore:
    """Thread-safe in-memory token store.

    All public methods are synchronous and safe to call from async contexts
    (no I/O; only dict operations).
    """

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl = ttl
        self._pending: dict[str, PendingConfirmation] = {}

    # ── Issuance ──────────────────────────────────────────────────────────────

    def create(
        self,
        description: str,
        risk_level: str,
        action_name: str,
        action_params: dict[str, Any],
    ) -> PendingConfirmation:
        """Issue a new confirmation token and store the pending action.

        Returns the ``PendingConfirmation`` so the caller can include the token
        and description in the HTTP 202 response.
        """
        self._evict_expired()
        now = time.monotonic()
        token = secrets.token_urlsafe(24)
        entry = PendingConfirmation(
            token=token,
            description=description,
            risk_level=risk_level,
            action_name=action_name,
            action_params=action_params,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._pending[token] = entry
        return entry

    # ── Confirmation ──────────────────────────────────────────────────────────

    def confirm(self, token: str) -> PendingConfirmation:
        """Consume the token and return the pending action params.

        Raises
        ------
        KeyError
            If the token is unknown or has already been used.
        TimeoutError
            If the token has expired.
        """
        self._evict_expired()
        entry = self._pending.pop(token, None)
        if entry is None:
            raise KeyError(f"Unknown or already-used confirmation token: {token!r}")
        if time.monotonic() > entry.expires_at:
            raise TimeoutError(f"Confirmation token {token!r} has expired.")
        return entry

    # ── Cancellation ──────────────────────────────────────────────────────────

    def cancel(self, token: str) -> bool:
        """Cancel (discard) a pending confirmation without executing it.

        Returns True if the token existed, False if already gone/expired.
        """
        self._evict_expired()
        return self._pending.pop(token, None) is not None

    # ── Introspection ─────────────────────────────────────────────────────────

    def get(self, token: str) -> PendingConfirmation | None:
        """Look up a pending confirmation without consuming it."""
        self._evict_expired()
        entry = self._pending.get(token)
        if entry and time.monotonic() > entry.expires_at:
            del self._pending[token]
            return None
        return entry

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [t for t, e in self._pending.items() if now > e.expires_at]
        for t in expired:
            del self._pending[t]
