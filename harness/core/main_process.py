"""MainProcess — the single authority that owns and coordinates all subsystems."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.core.base_component import BaseComponent
from harness.core.component_tree import ComponentTree
from harness.core.logger import HarnessLogger
from harness.core.permissions import Permission, PermissionsGuard
from harness.core.process_manager import ProcessManager
from harness.core.state_store import StateStore


class MainProcess:
    """
    Boots once. Lives for the entire process lifetime.

    Owns ComponentTree, ProcessManager, StateStore, PermissionsGuard, HarnessLogger,
    and the new VLoop data/engine subsystems (injected by the app factory).
    """

    def __init__(self, state_db: Path | str = ".harness/state.db") -> None:
        self.logger = HarnessLogger(log_dir=Path(".harness/logs"))
        self.state_store = StateStore(db_path=state_db)
        self.permissions = PermissionsGuard()
        self.component_tree = ComponentTree()
        self.process_manager = ProcessManager(logger=self.logger)

        # Workspace root — captured once at startup (CWD when `harness run` is invoked)
        self.workspace_root: Path = Path(os.getcwd()).resolve()

        # Tool runtime — initialised lazily in boot()
        self._tools: Any | None = None

        # AI engine reference — set by harness.engine bootstrap
        self._ai_engine: Any | None = None

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    async def boot(self) -> None:
        self.logger.info("MainProcess booting…")
        await self.state_store.open()
        self.logger.info("StateStore ready")

        # Initialise tool runtime
        from harness.tools.confirmation import ConfirmationStore
        from harness.tools.filesystem_tool import FilesystemTool
        from harness.tools.policy import PolicyEngine
        from harness.tools.registry import ToolRegistry
        from harness.tools.terminal_tool import TerminalTool

        policy_engine = PolicyEngine(workspace_root=self.workspace_root)
        confirmations = ConfirmationStore()
        tool_registry = ToolRegistry(self)
        tool_registry.policy = policy_engine          # type: ignore[attr-defined]
        tool_registry.confirmations = confirmations    # type: ignore[attr-defined]
        tool_registry.register(TerminalTool(self))
        tool_registry.register(FilesystemTool(self))
        self._tools = tool_registry
        self.logger.info("Tool runtime ready", workspace=str(self.workspace_root))

    async def shutdown(self) -> None:
        self.logger.info("MainProcess shutting down…")
        for comp in list(self.component_tree.list_all()):
            await self.process_manager.stop(comp)
        await self.state_store.persist()
        await self.state_store.close()
        self.logger.info("Shutdown complete")

    # ── Component lifecycle API ───────────────────────────────────────────────

    async def register(
        self,
        component: BaseComponent,
        permissions: set[Permission] | None = None,
    ) -> None:
        self.component_tree.register(component)
        self.permissions.register(
            component.id, permissions or component.default_permissions
        )
        self.logger.register(component.id)
        component._main_process = self
        await self.process_manager.start(component)
        self.logger.info(f"Registered component {component.id}", component=component.id)

    async def unregister(self, component_id: str) -> None:
        comp = self.component_tree.get(component_id)
        if comp is None:
            return
        await self.process_manager.stop(comp)
        self.component_tree.unregister(component_id)
        self.permissions.unregister(component_id)
        self.logger.unregister(component_id)
        await self.state_store.flush(component_id)

    # ── Convenience helpers for components ───────────────────────────────────

    def get_component(self, component_id: str) -> BaseComponent | None:
        return self.component_tree.get(component_id)

    async def broadcast(self, event_name: str, payload: Any = None) -> None:
        await self.component_tree.broadcast(event_name, payload)

    def check_permission(self, component_id: str, permission: Permission) -> None:
        self.permissions.check(component_id, permission)

    # ── Tool runtime accessor ─────────────────────────────────────────────────

    @property
    def tools(self) -> Any:
        if self._tools is None:
            raise RuntimeError("Tool runtime not initialised — call boot() first")
        return self._tools

    # ── AI engine accessor ─────────────────────────────────────────────────────

    @property
    def ai(self) -> Any:
        if self._ai_engine is None:
            raise RuntimeError("AI engine not initialised — call attach_ai_engine() first")
        return self._ai_engine

    def attach_ai_engine(self, engine: Any) -> None:
        self._ai_engine = engine
        self.logger.info("AI engine attached", engine=engine.__class__.__name__)
