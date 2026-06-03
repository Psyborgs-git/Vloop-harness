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
        import os
        ai_url = os.environ.get("RUST_BASE_AI_URL", "")
        if ai_url:
            self._rust_url = ai_url.rsplit("/v1", 1)[0]
        else:
            self._rust_url = None

    def register(self, component_id: str, initial: set[Permission] | None = None) -> None:
        self._sets[component_id] = PermissionSet(initial)
        if self._rust_url and initial:
            import httpx
            import threading
            def reg():
                with httpx.Client() as client:
                    for p in initial:
                        try:
                            client.post(
                                f"{self._rust_url}/harness/permissions/grant",
                                json={"component_id": component_id, "permission": p.value}
                            )
                        except Exception:
                            pass
            threading.Thread(target=reg, daemon=True).start()

    def unregister(self, component_id: str) -> None:
        self._sets.pop(component_id, None)

    def check(self, component_id: str, permission: Permission) -> None:
        if not self.has(component_id, permission):
            raise PermissionError(f"Permission denied: {permission.value}")

    def has(self, component_id: str, permission: Permission) -> bool:
        if self._rust_url:
            import httpx
            with httpx.Client() as client:
                try:
                    res = client.post(
                        f"{self._rust_url}/harness/permissions/check",
                        json={"component_id": component_id, "permission": permission.value},
                        timeout=5.0
                    )
                    if res.status_code == 200:
                        return res.json().get("has_permission", False)
                except Exception:
                    pass
        pset = self._sets.get(component_id)
        return pset is not None and pset.has(permission)

    def grant(self, component_id: str, permission: Permission) -> None:
        if self._rust_url:
            import httpx
            with httpx.Client() as client:
                try:
                    client.post(
                        f"{self._rust_url}/harness/permissions/grant",
                        json={"component_id": component_id, "permission": permission.value},
                        timeout=5.0
                    )
                except Exception:
                    pass
        pset = self._sets.get(component_id)
        if pset is None:
            self._sets[component_id] = PermissionSet()
            pset = self._sets[component_id]
        self._sets[component_id] = pset.grant(permission)

    def revoke(self, component_id: str, permission: Permission) -> None:
        if self._rust_url:
            import httpx
            with httpx.Client() as client:
                try:
                    client.post(
                        f"{self._rust_url}/harness/permissions/revoke",
                        json={"component_id": component_id, "permission": permission.value},
                        timeout=5.0
                    )
                except Exception:
                    pass
        pset = self._sets.get(component_id)
        if pset is None:
            raise KeyError(f"Unknown component: {component_id}")
        self._sets[component_id] = pset.revoke(permission)

    def get_set(self, component_id: str) -> PermissionSet:
        return self._sets.get(component_id, PermissionSet())
