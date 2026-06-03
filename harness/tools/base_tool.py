"""AbstractTool — base class every tool implementation inherits."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from harness.core.permissions import Permission

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess


# ── Result type ───────────────────────────────────────────────────────────────


@dataclass
class ToolResult:
    """Uniform return value for every tool call."""

    success: bool
    output: str = ""
    error: str | None = None
    exit_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, redact_secrets: bool = True) -> dict[str, Any]:
        """Convert to dictionary with optional secret redaction.

        Args:
            redact_secrets: If True, redact potential secrets from output and error.

        Returns:
            Dictionary representation of the result.
        """
        if redact_secrets:
            from harness.core.secret_redaction import redact_any

            return {
                "success": self.success,
                "output": redact_any(self.output),
                "error": redact_any(self.error),
                "exit_code": self.exit_code,
                "metadata": redact_any(self.metadata),
            }
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "metadata": self.metadata,
        }


# ── AbstractTool ──────────────────────────────────────────────────────────────


class AbstractTool(ABC):
    """Every tool must subclass this and implement ``execute``."""

    #: Unique snake_case identifier (e.g. "terminal", "filesystem")
    name: str

    #: Human-readable description exposed to the UI and AI context
    description: str

    #: Permission the caller must hold to use this tool
    required_permission: Permission

    #: Risk classification — gates the confirmation protocol
    risk_level: Literal["safe", "caution", "destructive"] = "safe"

    def __init__(self, main_process: MainProcess) -> None:
        self._mp = main_process

    # ── Permission gate ───────────────────────────────────────────────────────

    def _check_permission(self, component_id: str | None) -> None:
        """Raise PermissionDenied if *component_id* lacks the required permission.

        When *component_id* is None (direct UI access) we use the well-known
        ``"root"`` context which is always granted all tool permissions.
        """
        from harness.tools.exceptions import PermissionDenied

        cid = component_id or "root"
        if cid == "root":
            return  # root context (direct UI) always permitted
        if not self._mp.permissions.has(cid, self.required_permission):
            raise PermissionDenied(
                f"Component {cid!r} does not have permission "
                f"{self.required_permission.value!r} required for tool "
                f"{self.name!r}."
            )

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    async def execute(
        self,
        component_id: str | None,
        session_id: str | None,
        params: dict[str, Any],
    ) -> ToolResult:
        """Execute the tool with *params*.

        Implementations must:
          1. Call ``self._check_permission(component_id)`` first.
          2. Validate *params*.
          3. Perform the operation.
          4. Return a ``ToolResult``.
        """

    # ── Metadata ──────────────────────────────────────────────────────────────

    def catalog_entry(self) -> dict[str, Any]:
        """Return a JSON-serialisable description for the tool catalog."""
        return {
            "name": self.name,
            "description": self.description,
            "required_permission": self.required_permission.value,
            "risk_level": self.risk_level,
        }
