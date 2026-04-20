"""Tests for FilesystemTool — boundary enforcement, operations, symlink traversal."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from harness.tools.confirmation import ConfirmationStore
from harness.tools.exceptions import ConfirmationRequired, WorkspaceEscape
from harness.tools.filesystem_tool import FilesystemTool
from harness.tools.policy import PolicyEngine
from harness.tools.registry import ToolRegistry


def _make_mp(workspace: Path) -> MagicMock:
    mp = MagicMock()
    mp.workspace_root = workspace
    policy = PolicyEngine(workspace_root=workspace)
    conf = ConfirmationStore()
    registry = MagicMock()
    registry.policy = policy
    registry.confirmations = conf
    mp.tools = registry
    mp.permissions.has.return_value = True
    return mp


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def fs_tool(workspace: Path) -> FilesystemTool:
    return FilesystemTool(_make_mp(workspace))


class TestList:
    @pytest.mark.asyncio
    async def test_list_root(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "a.txt").write_text("hi")
        (workspace / "subdir").mkdir()
        result = await fs_tool.execute(None, None, {"operation": "list", "path": "."})
        assert result.success
        names = [e["name"] for e in result.metadata["entries"]]
        assert "a.txt" in names
        assert "subdir" in names

    @pytest.mark.asyncio
    async def test_list_nonexistent(self, fs_tool: FilesystemTool) -> None:
        result = await fs_tool.execute(None, None, {"operation": "list", "path": "nope"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_list_escapes_workspace(self, fs_tool: FilesystemTool) -> None:
        result = await fs_tool.execute(None, None, {"operation": "list", "path": "../.."})
        assert not result.success
        assert "outside" in (result.error or "").lower()


class TestRead:
    @pytest.mark.asyncio
    async def test_read_text(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "hello.txt").write_text("hello world")
        result = await fs_tool.execute(None, None, {"operation": "read", "path": "hello.txt"})
        assert result.success
        assert result.output == "hello world"

    @pytest.mark.asyncio
    async def test_read_binary(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "data.bin").write_bytes(b"\x00\x01\x02")
        result = await fs_tool.execute(None, None, {"operation": "read", "path": "data.bin"})
        assert result.success
        assert result.metadata["encoding"] == "base64"

    @pytest.mark.asyncio
    async def test_read_escape(self, fs_tool: FilesystemTool) -> None:
        result = await fs_tool.execute(None, None, {"operation": "read", "path": "../../etc/passwd"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_read_symlink_outside_workspace(
        self, tmp_path: Path
    ) -> None:
        # Create workspace as a subdirectory so tmp_path itself is outside
        ws = tmp_path / "workspace"
        ws.mkdir()
        secret = tmp_path / "secret.txt"  # outside workspace
        secret.write_text("secret")
        link = ws / "link.txt"
        link.symlink_to(secret)
        tool = FilesystemTool(_make_mp(ws))
        # The symlink resolves outside the workspace
        result = await tool.execute(None, None, {"operation": "read", "path": "link.txt"})
        assert not result.success


class TestStat:
    @pytest.mark.asyncio
    async def test_stat_file(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "f.txt").write_text("x")
        result = await fs_tool.execute(None, None, {"operation": "stat", "path": "f.txt"})
        assert result.success
        assert result.metadata["type"] == "file"
        assert result.metadata["size"] == 1


class TestWrite:
    @pytest.mark.asyncio
    async def test_write_new_file(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        result = await fs_tool.execute(
            None, None, {"operation": "write", "path": "new.txt", "content": "data"}
        )
        assert result.success
        assert (workspace / "new.txt").read_text() == "data"

    @pytest.mark.asyncio
    async def test_overwrite_raises_confirmation(
        self, workspace: Path, fs_tool: FilesystemTool
    ) -> None:
        (workspace / "existing.txt").write_text("old")
        with pytest.raises(ConfirmationRequired) as exc_info:
            await fs_tool.execute(
                None, None, {"operation": "write", "path": "existing.txt", "content": "new"}
            )
        assert exc_info.value.risk_level == "caution"

    @pytest.mark.asyncio
    async def test_overwrite_with_token(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "existing.txt").write_text("old")
        # Get the confirmation token first
        try:
            await fs_tool.execute(
                None, None, {"operation": "write", "path": "existing.txt", "content": "new"}
            )
        except ConfirmationRequired as exc:
            token = exc.token
        # Now confirm
        result = await fs_tool.execute(
            None,
            None,
            {"operation": "write", "path": "existing.txt", "content": "new", "_confirmation_token": token},
        )
        assert result.success
        assert (workspace / "existing.txt").read_text() == "new"


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_always_needs_confirmation(
        self, workspace: Path, fs_tool: FilesystemTool
    ) -> None:
        (workspace / "del.txt").write_text("x")
        with pytest.raises(ConfirmationRequired) as exc_info:
            await fs_tool.execute(None, None, {"operation": "delete", "path": "del.txt"})
        assert exc_info.value.risk_level == "destructive"

    @pytest.mark.asyncio
    async def test_delete_with_token(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "del.txt").write_text("x")
        try:
            await fs_tool.execute(None, None, {"operation": "delete", "path": "del.txt"})
        except ConfirmationRequired as exc:
            token = exc.token
        result = await fs_tool.execute(
            None, None, {"operation": "delete", "path": "del.txt", "_confirmation_token": token}
        )
        assert result.success
        assert not (workspace / "del.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_escape(self, fs_tool: FilesystemTool) -> None:
        result = await fs_tool.execute(
            None, None, {"operation": "delete", "path": "../outside", "_confirmation_token": "x"}
        )
        assert not result.success
        assert "outside" in (result.error or "").lower()


class TestMove:
    @pytest.mark.asyncio
    async def test_move_needs_confirmation(
        self, workspace: Path, fs_tool: FilesystemTool
    ) -> None:
        (workspace / "src.txt").write_text("x")
        with pytest.raises(ConfirmationRequired):
            await fs_tool.execute(
                None, None, {"operation": "move", "src": "src.txt", "dest": "dst.txt"}
            )

    @pytest.mark.asyncio
    async def test_move_with_token(self, workspace: Path, fs_tool: FilesystemTool) -> None:
        (workspace / "src.txt").write_text("x")
        try:
            await fs_tool.execute(
                None, None, {"operation": "move", "src": "src.txt", "dest": "dst.txt"}
            )
        except ConfirmationRequired as exc:
            token = exc.token
        result = await fs_tool.execute(
            None,
            None,
            {"operation": "move", "src": "src.txt", "dest": "dst.txt", "_confirmation_token": token},
        )
        assert result.success
        assert (workspace / "dst.txt").exists()
        assert not (workspace / "src.txt").exists()
