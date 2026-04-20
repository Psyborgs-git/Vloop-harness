"""Unit tests for the permission system."""

import pytest
from harness.core.permissions import Permission, PermissionSet, PermissionsGuard


def test_permission_set_has():
    ps = PermissionSet({Permission.FILESYSTEM_READ})
    assert ps.has(Permission.FILESYSTEM_READ)
    assert not ps.has(Permission.SHELL_EXEC)


def test_permission_set_check_raises():
    ps = PermissionSet()
    with pytest.raises(PermissionError):
        ps.check(Permission.NETWORK_OUTBOUND)


def test_permission_set_grant_immutable():
    ps = PermissionSet()
    ps2 = ps.grant(Permission.FILESYSTEM_WRITE)
    assert not ps.has(Permission.FILESYSTEM_WRITE)
    assert ps2.has(Permission.FILESYSTEM_WRITE)


def test_permissions_guard_lifecycle():
    guard = PermissionsGuard()
    guard.register("comp_1", {Permission.UI_RESIZE})
    assert guard.has("comp_1", Permission.UI_RESIZE)
    assert not guard.has("comp_1", Permission.SHELL_EXEC)

    guard.grant("comp_1", Permission.SHELL_EXEC)
    assert guard.has("comp_1", Permission.SHELL_EXEC)

    guard.revoke("comp_1", Permission.SHELL_EXEC)
    assert not guard.has("comp_1", Permission.SHELL_EXEC)

    guard.unregister("comp_1")
    assert not guard.has("comp_1", Permission.UI_RESIZE)
