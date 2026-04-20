"""ProcessManager — mounts, stops, and watchdogs components."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness.core.base_component import BaseComponent
    from harness.core.logger import HarnessLogger


class ProcessManager:
    """Manages the lifecycle of every BaseComponent instance."""

    def __init__(self, logger: HarnessLogger) -> None:
        self._log = logger
        self._running: dict[str, BaseComponent] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, component: BaseComponent) -> None:
        if component.id in self._running:
            self._log.info(f"Component {component.id} already running — skipping start")
            return

        self._log.info(f"Starting component {component.id}", component=component.id)
        self._running[component.id] = component
        try:
            await component.on_mount()
        except Exception as exc:
            self._log.error(
                f"on_mount failed for {component.id}: {exc}", component=component.id
            )
            raise

    async def stop(self, component: BaseComponent) -> None:
        cid = component.id
        if cid not in self._running:
            return

        self._log.info(f"Stopping component {cid}", component=cid)
        task = self._tasks.pop(cid, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        try:
            await component.on_unmount()
        except Exception as exc:
            self._log.error(f"on_unmount error for {cid}: {exc}", component=cid)
        finally:
            await component.cleanup()
            self._running.pop(cid, None)

    async def restart(self, component: BaseComponent) -> None:
        await component.emit("reloading", {})
        await self.stop(component)
        await self.start(component)

    # ── Hot reload from file ──────────────────────────────────────────────────

    async def hot_reload(self, component: BaseComponent, source_file: Path) -> BaseComponent:
        """
        Reimport the component class from source_file, recreate the instance
        preserving id and props, then restart it.
        """
        old_state = component.state.copy()
        old_props = component.props.copy()
        old_id = component.id

        await self.stop(component)

        spec = importlib.util.spec_from_file_location(source_file.stem, source_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec from {source_file}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[arg-type]

        cls = getattr(mod, component.__class__.__name__)
        new_comp: BaseComponent = cls(props=old_props, component_id=old_id)
        new_comp.state = old_state
        await self.start(new_comp)
        return new_comp

    # ── Watchdog ──────────────────────────────────────────────────────────────

    async def watchdog(self, interval: float = 5.0) -> None:
        """Periodically checks for crashed components and logs warnings."""
        while True:
            await asyncio.sleep(interval)
            for cid, task in list(self._tasks.items()):
                if task.done() and not task.cancelled():
                    exc = task.exception()
                    if exc:
                        self._log.error(
                            f"Component task {cid} crashed: {exc}", component=cid
                        )

    # ── Queries ───────────────────────────────────────────────────────────────

    def list_running(self) -> list[BaseComponent]:
        return list(self._running.values())

    def is_running(self, component_id: str) -> bool:
        return component_id in self._running
