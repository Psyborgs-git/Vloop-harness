"""Shared persistence helpers — JSON serialization and timestamp generation."""

from __future__ import annotations

import json
import time
from typing import Any


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def to_json(value: Any) -> str:
    """Serialize a value to a JSON string."""
    return json.dumps(value, ensure_ascii=False)


def from_json(value: str | None, default: Any) -> Any:
    """Deserialize a JSON string; return *default* if the value is empty."""
    if not value:
        return default
    return json.loads(value)
