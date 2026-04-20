"""Dashboard — aggregates state from sibling components and provides AI-powered summaries."""

from __future__ import annotations

import asyncio
from typing import Any

from harness.core.base_component import BaseComponent
from harness.core.permissions import Permission


class DashboardComponent(BaseComponent):
    """
    Aggregator component.

    Listens to broadcast events from siblings, accumulates metrics,
    and (when the AI engine is available) generates an AI-authored summary
    of the current system state.
    """

    default_permissions = {
        Permission.IPC_RECEIVE,
        Permission.AI_INFERENCE,
        Permission.STATE_PERSIST,
    }

    async def on_mount(self) -> None:
        await self.update_state(
            {
                "metrics": {},
                "summary": "",
                "ai_ready": False,
            }
        )
        # Check if the AI engine is attached
        mp = self._main_process
        if mp is not None:
            try:
                _ = mp.ai
                await self.update_state({"ai_ready": True})
            except RuntimeError:
                pass

    async def on_event(self, name: str, payload: Any) -> None:
        if name == "metric_update":
            metrics = dict(self.state.get("metrics", {}))
            if isinstance(payload, dict):
                metrics.update(payload)
            await self.update_state({"metrics": metrics})

        elif name == "request_summary":
            await self._generate_summary()

    async def _generate_summary(self) -> None:
        mp = self._main_process
        if mp is None:
            return
        try:
            engine = mp.ai
        except RuntimeError:
            await self.update_state({"summary": "AI engine not available."})
            return

        metrics_text = str(self.state.get("metrics", {}))
        result = await engine.reason(
            question="Provide a one-paragraph dashboard summary of these system metrics.",
            context=f"Current metrics: {metrics_text}",
        )
        await self.update_state({"summary": result.answer})
