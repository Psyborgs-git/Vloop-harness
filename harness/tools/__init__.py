"""harness.tools — Tool runtime layer for safe terminal and filesystem access."""

from __future__ import annotations

from harness.tools.base_tool import AbstractTool, ToolResult
from harness.tools.confirmation import ConfirmationStore
from harness.tools.exceptions import (
    ConfirmationRequired,
    PermissionDenied,
    PolicyBlocked,
    PermanentlyBlocked,
    TimeoutExceeded,
    ToolError,
    WorkspaceEscape,
)
from harness.tools.filesystem_tool import FilesystemTool
from harness.tools.policy import PolicyEngine
from harness.tools.registry import ToolRegistry
from harness.tools.terminal_tool import TerminalTool

__all__ = [
    "AbstractTool",
    "ToolResult",
    "ConfirmationStore",
    "ConfirmationRequired",
    "PermissionDenied",
    "PolicyBlocked",
    "PermanentlyBlocked",
    "TimeoutExceeded",
    "ToolError",
    "WorkspaceEscape",
    "FilesystemTool",
    "PolicyEngine",
    "ToolRegistry",
    "TerminalTool",
]
