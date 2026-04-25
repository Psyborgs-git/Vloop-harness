from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from harness.core.base_component import BaseComponent
from harness.core.process_manager import ProcessManager


class DummyComponent(BaseComponent):
    def __init__(self, component_id: str = "svc") -> None:
        super().__init__(component_id=component_id)
        self.mounted = 0
        self.unmounted = 0
        self.cleaned = 0

    async def on_mount(self) -> None:
        self.mounted += 1

    async def on_unmount(self) -> None:
        self.unmounted += 1

    async def cleanup(self) -> None:
        self.cleaned += 1
        await super().cleanup()


@pytest.mark.asyncio
async def test_start_stop_status_and_restart_transitions() -> None:
    logger = MagicMock()
    manager = ProcessManager(logger)
    comp = DummyComponent("svc-a")

    assert manager.is_running("svc-a") is False

    await manager.start(comp)
    assert manager.is_running("svc-a") is True
    assert comp.mounted == 1

    # idempotent start while already running
    await manager.start(comp)
    assert comp.mounted == 1

    await manager.restart(comp)
    assert manager.is_running("svc-a") is True
    assert comp.unmounted == 1
    assert comp.cleaned == 1
    assert comp.mounted == 2

    await manager.stop(comp)
    assert manager.is_running("svc-a") is False
    assert comp.unmounted == 2
    assert comp.cleaned == 2


@pytest.mark.asyncio
async def test_stop_cleans_up_even_if_unmount_fails() -> None:
    logger = MagicMock()
    manager = ProcessManager(logger)

    class BrokenUnmount(DummyComponent):
        async def on_unmount(self) -> None:  # type: ignore[override]
            self.unmounted += 1
            raise RuntimeError("boom")

    comp = BrokenUnmount("svc-b")
    await manager.start(comp)

    await manager.stop(comp)

    assert comp.unmounted == 1
    assert comp.cleaned == 1
    assert manager.is_running("svc-b") is False


@pytest.mark.asyncio
async def test_health_check_watchdog_logs_crashed_task() -> None:
    logger = MagicMock()
    manager = ProcessManager(logger)

    async def crash() -> None:
        raise RuntimeError("task crashed")

    task = asyncio.create_task(crash())
    await asyncio.sleep(0)
    manager._tasks["svc-c"] = task

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(manager.watchdog(interval=0.01), timeout=0.03)

    assert logger.error.call_count >= 1
    assert "crashed" in logger.error.call_args[0][0]


@pytest.mark.asyncio
async def test_stop_cancels_background_task_and_cleans_up() -> None:
    logger = MagicMock()
    manager = ProcessManager(logger)
    comp = DummyComponent("svc-d")

    await manager.start(comp)

    async def long_running() -> None:
        await asyncio.sleep(100)

    manager._tasks[comp.id] = asyncio.create_task(long_running())
    await manager.stop(comp)

    assert manager.is_running(comp.id) is False
    assert comp.cleaned == 1
    assert comp.unmounted == 1
