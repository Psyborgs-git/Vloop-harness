"""BaseComponent — abstract base class every harness component inherits."""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC
from typing import TYPE_CHECKING, Any

from harness.core.permissions import Permission, PermissionSet

if TYPE_CHECKING:
    from harness.core.main_process import MainProcess


class BaseComponent(ABC):
    """
    Pure Python. No UI code.

    Subclass this, override lifecycle hooks, and optionally declare
    ``default_permissions`` as a class-level set.
    """

    default_permissions: set[Permission] = set()

    def __init__(
        self,
        props: dict[str, Any] | None = None,
        component_id: str | None = None,
    ) -> None:
        self.id: str = component_id or f"comp_{uuid.uuid4().hex[:8]}"
        self.props: dict[str, Any] = props or {}
        self.state: dict[str, Any] = {}
        self.children: list[BaseComponent] = []
        self.permissions: PermissionSet = PermissionSet(self.default_permissions)
        self._main_process: MainProcess | None = None
        self._event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._ws_subscribers: set[Any] = set()

    # ── Lifecycle hooks (override in subclass) ────────────────────────────────

    async def on_mount(self) -> None:
        """Called when the view opens and the component starts."""

    async def on_unmount(self) -> None:
        """Called when the view is closed (hard). Release resources here."""

    async def on_hide(self) -> None:
        """Called when the view is minimised. Process stays alive."""

    async def on_show(self) -> None:
        """Called when the view is restored from minimised."""

    async def on_update(self, new_props: dict[str, Any]) -> None:
        """Called when the parent pushes updated props."""
        self.props = {**self.props, **new_props}

    async def on_event(self, name: str, payload: Any) -> None:
        """Called when the paired React UI emits an event."""

    # ── State management ──────────────────────────────────────────────────────

    async def update_state(self, patch: dict[str, Any]) -> None:
        """Merge patch into state and push update to all connected React clients."""
        self.state = {**self.state, **patch}
        await self._broadcast_ws("state_update", self.state)

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "props": self.props,
            "permissions": [p.value for p in self.permissions.all_granted()],
        }

    # ── Event emission ────────────────────────────────────────────────────────

    async def emit(self, name: str, payload: Any = None) -> None:
        """Push a named event to all connected React clients via WebSocket."""
        await self._broadcast_ws(name, payload)

    # ── Internal WebSocket management ─────────────────────────────────────────

    def _add_ws(self, ws: Any) -> None:
        self._ws_subscribers.add(ws)

    def _remove_ws(self, ws: Any) -> None:
        self._ws_subscribers.discard(ws)

    async def _broadcast_ws(self, event_type: str, data: Any) -> None:
        import json

        message = json.dumps({"type": event_type, "data": data})
        dead: set[Any] = set()
        for ws in list(self._ws_subscribers):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._ws_subscribers.discard(ws)

    # ── Tool access ───────────────────────────────────────────────────────────

    async def run_tool(self, tool_name: str, **params: Any) -> Any:
        """Execute a registered tool with this component's permissions and policy context.

        The component must hold the permission required by the tool; attempting
        ``run_tool`` without it raises ``PermissionError``.
        """
        if self._main_process is None:
            raise RuntimeError("Component is not registered with a MainProcess.")
        return await self._main_process.tools.execute(
            tool_name=tool_name,
            component_id=self.id,
            session_id=None,
            params=params,
        )

    # ── Resource cleanup ──────────────────────────────────────────────────────

    async def cleanup(self) -> None:
        """Release threads, connections, and file handles."""
        self._ws_subscribers.clear()

    # ── Repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"
