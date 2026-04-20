"""Counter — simplest possible example component."""

from __future__ import annotations

from typing import Any

from harness.core.base_component import BaseComponent
from harness.core.permissions import Permission


class CounterComponent(BaseComponent):
    """Stateful counter. React UI can increment/decrement/reset via events."""

    default_permissions = {Permission.UI_RESIZE}

    async def on_mount(self) -> None:
        await self.update_state({"count": self.props.get("initial", 0)})

    async def on_event(self, name: str, payload: Any) -> None:
        count = self.state.get("count", 0)
        if name == "increment":
            await self.update_state({"count": count + 1})
        elif name == "decrement":
            await self.update_state({"count": count - 1})
        elif name == "reset":
            await self.update_state({"count": self.props.get("initial", 0)})
