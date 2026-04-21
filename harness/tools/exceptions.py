"""Custom exceptions for the tool runtime layer."""

from __future__ import annotations


class ToolError(Exception):
    """Base class for all tool runtime errors."""


class PermissionDenied(ToolError):
    """Raised when the caller lacks a required permission."""


class PermanentlyBlocked(ToolError):
    """Raised when a command matches the permanent blocklist."""


class PolicyBlocked(ToolError):
    """Raised when a command is blocked by the denylist or not in the allowlist."""


class ConfirmationRequired(ToolError):
    """Raised when a destructive action requires human confirmation.

    Attributes
    ----------
    token:
        Short-lived confirmation token the client must echo back.
    description:
        Human-readable description of the action that will be executed.
    risk_level:
        "caution" or "destructive".
    """

    def __init__(self, token: str, description: str, risk_level: str) -> None:
        super().__init__(description)
        self.token = token
        self.description = description
        self.risk_level = risk_level


class WorkspaceEscape(ToolError):
    """Raised when a path resolves outside the workspace root."""


class TimeoutExceeded(ToolError):
    """Raised when a terminal command exceeds its allowed runtime."""
