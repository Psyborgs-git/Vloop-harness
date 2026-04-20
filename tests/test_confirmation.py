"""Tests for ConfirmationStore — token issuance, expiry, one-time use."""

from __future__ import annotations

import time

import pytest

from harness.tools.confirmation import ConfirmationStore


@pytest.fixture
def store() -> ConfirmationStore:
    return ConfirmationStore(ttl=60)


class TestIssuance:
    def test_create_returns_token(self, store: ConfirmationStore) -> None:
        pending = store.create(
            description="Delete foo",
            risk_level="destructive",
            action_name="delete",
            action_params={"path": "foo"},
        )
        assert len(pending.token) > 0
        assert pending.description == "Delete foo"
        assert pending.risk_level == "destructive"

    def test_get_returns_pending(self, store: ConfirmationStore) -> None:
        pending = store.create("desc", "caution", "write", {})
        found = store.get(pending.token)
        assert found is not None
        assert found.token == pending.token

    def test_get_unknown_returns_none(self, store: ConfirmationStore) -> None:
        assert store.get("nonexistent") is None


class TestConfirmation:
    def test_confirm_consumes_token(self, store: ConfirmationStore) -> None:
        pending = store.create("desc", "destructive", "delete", {"path": "x"})
        result = store.confirm(pending.token)
        assert result.token == pending.token
        # Second call should raise
        with pytest.raises(KeyError):
            store.confirm(pending.token)

    def test_confirm_unknown_raises(self, store: ConfirmationStore) -> None:
        with pytest.raises(KeyError):
            store.confirm("bad-token")


class TestCancellation:
    def test_cancel_removes_token(self, store: ConfirmationStore) -> None:
        pending = store.create("desc", "caution", "write", {})
        assert store.cancel(pending.token) is True
        assert store.get(pending.token) is None

    def test_cancel_unknown_returns_false(self, store: ConfirmationStore) -> None:
        assert store.cancel("nonexistent") is False


class TestExpiry:
    def test_expired_token_not_found(self) -> None:
        store = ConfirmationStore(ttl=0)
        pending = store.create("desc", "destructive", "delete", {})
        # Tiny TTL — should expire immediately
        time.sleep(0.01)
        assert store.get(pending.token) is None

    def test_confirm_expired_raises(self) -> None:
        store = ConfirmationStore(ttl=0)
        pending = store.create("desc", "destructive", "delete", {})
        time.sleep(0.01)
        with pytest.raises(KeyError):
            store.confirm(pending.token)
