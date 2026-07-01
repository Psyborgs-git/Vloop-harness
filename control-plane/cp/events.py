"""Kernel event routing for the Python control plane."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Deque

from core.event_router import EventRouter, WorkflowEvent
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
    def __init__(
        self,
        window_manager: WindowManager,
        *,
        max_events: int = 200,
        event_router: EventRouter | None = None,
    ) -> None:
        self._window_manager = window_manager
        self._recent_events: Deque[KernelEventRecord] = deque(maxlen=max_events)
        # Optional bridge to the orchestration Event_Router. When set, Kernel
        # events that can be attributed to a Workflow_Run are normalized into
        # user-facing workflow events, and internal orchestration events can be
        # emitted through ``handle_orchestration_event`` (Requirements 4.1, 21.5).
        self._event_router = event_router

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

        # Bridge run-attributable Kernel events into the workflow event stream.
        # Events with no run association are left as Kernel-only records.
        if self._event_router is not None:
            try:
                self._event_router.normalize_kernel_event(record)
            except Exception:  # noqa: BLE001 - event bridging must not drop the kernel record
                LOGGER.exception("failed to normalize kernel event into workflow event")

        return record

    def handle_orchestration_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        *,
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> WorkflowEvent | None:
        """Accept an internal orchestration event and route it for normalization.

        Delegates to the orchestration :class:`~core.event_router.EventRouter`,
        which attributes the event to ``run_id`` (Requirement 21.5), redacts
        secret values (Requirement 21.4), and persists it to ``workflow_events``.
        Returns ``None`` when no Event_Router is configured.
        """
        if self._event_router is None:
            return None
        return self._event_router.emit(
            run_id,
            event_type,
            message,
            step_id=step_id,
            payload=payload,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "event_count": len(self._recent_events),
            "recent_events": [event.to_dict() for event in self._recent_events],
        }


def start_event_router(
    window_manager: WindowManager,
    *,
    max_events: int = 200,
    event_router: EventRouter | None = None,
) -> KernelEventRouter:
    return KernelEventRouter(
        window_manager,
        max_events=max_events,
        event_router=event_router,
    )
