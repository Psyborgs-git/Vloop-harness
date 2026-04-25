"""Secret redaction utility.

``redact_secrets`` recursively walks a nested data structure (dict, list, or
scalar) and replaces string values whose keys match common secret-like patterns
with the sentinel ``"[REDACTED]"``.  String values larger than 8 KiB are also
truncated to prevent oversized payloads reaching logs or traces.
"""

from __future__ import annotations

import re
from typing import Any

_8KiB = 8 * 1024

# Keys whose values should always be redacted (case-insensitive substring match)
_SECRET_PATTERN = re.compile(
    r"(api_key|password|token|secret|credential|auth|bearer|authorization)",
    re.IGNORECASE,
)


def redact_secrets(data: Any) -> Any:
    """Recursively redact sensitive values and truncate oversized strings.

    Parameters
    ----------
    data:
        Any JSON-serialisable value (dict, list, str, int, float, bool, None).

    Returns
    -------
    The same structure with secret values replaced by ``"[REDACTED]"`` and
    strings longer than 8 KiB truncated.
    """
    if isinstance(data, dict):
        return {k: _redact_value(k, v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, str):
        return _truncate(data)
    return data


def _redact_value(key: str, value: Any) -> Any:
    """Return ``"[REDACTED]"`` if *key* matches a secret pattern, else recurse."""
    if isinstance(key, str) and _SECRET_PATTERN.search(key):
        return "[REDACTED]"
    return redact_secrets(value)


def _truncate(value: str) -> str:
    if len(value) > _8KiB:
        return value[:_8KiB] + "…[truncated]"
    return value
