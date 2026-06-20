"""Kernel event routing for the Python control plane."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Deque

from cp.window import WindowManager

LOGGER = logging.getLogger("vloop.control_plane.events")


@dataclass(slots=True)
class KernelEventRecord:
    event_id: str
    event_type: str
    resource_type: str
    resource_id: str
    status: str
    message: str
    timestamp_unix_ms: int
    attributes: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KernelEventRouter:
    def __init__(self, window_manager: WindowManager, *, max_events: int = 200) -> None:
        self._window_manager = window_manager
        self._recent_events: Deque[KernelEventRecord] = deque(maxlen=max_events)

    def handle_proto_event(self, event: Any) -> KernelEventRecord:
        record = KernelEventRecord(
            event_id=str(getattr(event, "event_id", "")),
            event_type=str(getattr(event, "event_type", "")),
            resource_type=str(getattr(event, "resource_type", "")),
            resource_id=str(getattr(event, "resource_id", "")),
            status=str(getattr(event, "status", "")),
            message=str(getattr(event, "message", "")),
            timestamp_unix_ms=int(getattr(event, "timestamp_unix_ms", 0)),
            attributes=dict(getattr(event, "attributes", {})),
        )
        self._recent_events.append(record)

        LOGGER.info(
            "kernel event: %s %s %s - %s",
            record.status,
            record.event_type,
            record.resource_id,
            record.message,
        )

        if record.event_type == "control_plane.open_ui_requested":
            reason = (
                record.attributes.get("reason")
                or record.message
                or "kernel open-ui request"
            )
            self._window_manager.open_main_window(reason)

        return record

    def snapshot(self) -> dict[str, Any]:
        return {
            "event_count": len(self._recent_events),
            "recent_events": [event.to_dict() for event in self._recent_events],
        }


def start_event_router(
    window_manager: WindowManager, *, max_events: int = 200
) -> KernelEventRouter:
    return KernelEventRouter(window_manager, max_events=max_events)
