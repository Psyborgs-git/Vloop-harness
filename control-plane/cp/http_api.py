"""Frontend-facing HTTP shell for the control-plane runtime (shim).

All functionality has been split into focused sub-modules.
This module re-exports the public API for backward compatibility.
"""

from cp.http_handler import handler_factory
from cp.http_server import HttpShellServer


class MethodNotAllowedError(RuntimeError):
    def __init__(self, method: str, allowed: set[str]) -> None:
        self.method = method
        self.allowed = allowed
        allowed_text = ", ".join(sorted(allowed))
        super().__init__(
            f"method {method} is not supported; allowed methods: {allowed_text}"
        )


__all__ = ["HttpShellServer", "MethodNotAllowedError", "handler_factory"]
