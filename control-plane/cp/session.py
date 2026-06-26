"""Session snapshot and metadata helpers."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class SessionSnapshot:
    status: str
    kernel_endpoint: str
    http_base_url: str | None
    shell_url: str | None
    session_id: str | None
    granted_scopes: list[str]
    last_registered_at_unix_ms: int | None
    last_heartbeat_at_unix_ms: int | None
    last_error: str | None
    active_config: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_unix_ms() -> int:
    """Return current time as Unix timestamp in milliseconds."""
    return int(time.time() * 1000)


def make_metadata(
    *,
    config: Any,
    include_bootstrap: bool = False,
    include_session: bool = False,
    session_id: str | None = None,
) -> list[tuple[str, str]]:
    """Build gRPC metadata with request ID and optional session/bootstrap tokens."""
    metadata = [("x-vloop-request-id", str(uuid.uuid4()))]
    if include_bootstrap and config.bootstrap_token:
        metadata.append(("x-vloop-bootstrap-token", config.bootstrap_token))
    if include_session and session_id:
        metadata.append(("x-vloop-session-id", session_id))
    return metadata
