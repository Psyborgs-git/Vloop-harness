"""ComponentTree — registry for all live components."""

from __future__ import annotations

from typing import Any

from harness.core.base_component import BaseComponent


class ComponentTree:
    """Flat registry: component_id → BaseComponent instance."""

    def __init__(self) -> None:
        self._components: dict[str, BaseComponent] = {}
        self.root: BaseComponent | None = None

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def register(self, component: BaseComponent) -> None:
        self._components[component.id] = component

    def unregister(self, component_id: str) -> BaseComponent | None:
        return self._components.pop(component_id, None)

    def get(self, component_id: str) -> BaseComponent | None:
        return self._components.get(component_id)

    def get_or_raise(self, component_id: str) -> BaseComponent:
        comp = self._components.get(component_id)
        if comp is None:
            raise KeyError(f"Component not found: {component_id}")
        return comp

    def list_all(self) -> list[BaseComponent]:
        return list(self._components.values())

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast(self, event_name: str, payload: Any = None) -> None:
        """Send an event to every registered component."""
        for comp in list(self._components.values()):
            try:
                await comp.on_event(event_name, payload)
            except Exception:
                pass

    def __len__(self) -> int:
        return len(self._components)

    def __contains__(self, component_id: str) -> bool:
        return component_id in self._components
