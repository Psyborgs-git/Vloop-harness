"""Component permission system. Components declare permissions; MainProcess enforces them."""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    NETWORK_OUTBOUND = "network.outbound"
    NETWORK_INBOUND = "network.inbound"
    SHELL_EXEC = "shell.exec"
    IPC_BROADCAST = "ipc.broadcast"
    IPC_RECEIVE = "ipc.receive"
    STATE_PERSIST = "state.persist"
    UI_RESIZE = "ui.resize"
    UI_SPAWN = "ui.spawn"
    AI_INFERENCE = "ai.inference"


class PermissionSet:
    """Immutable per-component permission set. Components cannot self-escalate."""

    def __init__(self, granted: set[Permission] | None = None) -> None:
        self._granted: frozenset[Permission] = frozenset(granted or set())

    # ── Querying ──────────────────────────────────────────────────────────────

    def has(self, permission: Permission) -> bool:
        return permission in self._granted

    def check(self, permission: Permission) -> None:
        if not self.has(permission):
            raise PermissionError(f"Permission denied: {permission.value}")

    def all_granted(self) -> frozenset[Permission]:
        return self._granted

    # ── Mutation (only MainProcess/PermissionsGuard may call these) ───────────

    def grant(self, permission: Permission) -> "PermissionSet":
        return PermissionSet(self._granted | {permission})

    def revoke(self, permission: Permission) -> "PermissionSet":
        return PermissionSet(self._granted - {permission})

    def __repr__(self) -> str:
        names = ", ".join(p.value for p in sorted(self._granted, key=lambda p: p.value))
        return f"PermissionSet({{{names}}})"


class PermissionsGuard:
    """Central authority. Owns all component permission sets."""

    def __init__(self) -> None:
        self._sets: dict[str, PermissionSet] = {}

    def register(self, component_id: str, initial: set[Permission] | None = None) -> None:
        self._sets[component_id] = PermissionSet(initial)

    def unregister(self, component_id: str) -> None:
        self._sets.pop(component_id, None)

    def check(self, component_id: str, permission: Permission) -> None:
        pset = self._sets.get(component_id)
        if pset is None:
            raise PermissionError(f"Unknown component: {component_id}")
        pset.check(permission)

    def has(self, component_id: str, permission: Permission) -> bool:
        pset = self._sets.get(component_id)
        return pset is not None and pset.has(permission)

    def grant(self, component_id: str, permission: Permission) -> None:
        pset = self._sets.get(component_id)
        if pset is None:
            raise KeyError(f"Unknown component: {component_id}")
        self._sets[component_id] = pset.grant(permission)

    def revoke(self, component_id: str, permission: Permission) -> None:
        pset = self._sets.get(component_id)
        if pset is None:
            raise KeyError(f"Unknown component: {component_id}")
        self._sets[component_id] = pset.revoke(permission)

    def get_set(self, component_id: str) -> PermissionSet:
        return self._sets.get(component_id, PermissionSet())
