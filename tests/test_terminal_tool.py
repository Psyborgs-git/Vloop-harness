"""Tests for TerminalTool — policy enforcement, timeout, output truncation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.tools.confirmation import ConfirmationStore
from harness.tools.policy import DirectoryPolicy, PolicyConfig, PolicyEngine
from harness.tools.registry import ToolRegistry
from harness.tools.terminal_tool import TerminalTool


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


def _write_policy(workspace: Path, allowed_commands: list[str]) -> None:
    policy_dir = workspace / ".vloop"
    policy_dir.mkdir(exist_ok=True)
    config = {
        "permanent_blocklist": [],
        "denylist": [],
        "directories": [
            {
                "directory": ".",
                "allowed_commands": allowed_commands,
                "max_runtime_seconds": 10,
                "max_output_bytes": 1024,
            }
        ],
    }
    (policy_dir / "policy.json").write_text(json.dumps(config))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def tool(workspace: Path) -> TerminalTool:
    _write_policy(workspace, ["python", "echo", sys.executable.split("/")[-1]])
    return TerminalTool(_make_mp(workspace))


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_python_echo(self, workspace: Path) -> None:
        _write_policy(workspace, [sys.executable.split("/")[-1]])
        tool = TerminalTool(_make_mp(workspace))
        result = await tool.execute(
            None, None,
            {"command": f"{sys.executable} -c \"print('hello')\"", "cwd_relative": "."},
        )
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_exit_code_captured(self, workspace: Path) -> None:
        _write_policy(workspace, [sys.executable.split("/")[-1]])
        tool = TerminalTool(_make_mp(workspace))
        result = await tool.execute(
            None, None,
            {"command": f"{sys.executable} -c 'import sys\nsys.exit(42)'", "cwd_relative": "."},
        )
        assert not result.success
        assert result.exit_code == 42


class TestPolicyBlocking:
    @pytest.mark.asyncio
    async def test_not_in_allowlist(self, tool: TerminalTool) -> None:
        result = await tool.execute(
            None, None, {"command": "cargo build", "cwd_relative": "."}
        )
        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_permanent_blocklist(self, workspace: Path) -> None:
        _write_policy(workspace, ["mkfs"])
        tool = TerminalTool(_make_mp(workspace))
        result = await tool.execute(
            None, None, {"command": "mkfs /dev/sda", "cwd_relative": "."}
        )
        assert not result.success
        assert "permanently blocked" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_shell_injection_rejected(self, tool: TerminalTool) -> None:
        result = await tool.execute(
            None, None, {"command": "echo $(id)", "cwd_relative": "."}
        )
        assert not result.success
        assert "disallowed" in (result.error or "").lower()


class TestWorkspaceBoundary:
    @pytest.mark.asyncio
    async def test_cwd_outside_workspace(self, tool: TerminalTool) -> None:
        result = await tool.execute(
            None, None,
            {"command": f"{sys.executable} -c \"print('x')\"", "cwd_relative": "../../.."},
        )
        assert not result.success
        assert "outside" in (result.error or "").lower()


class TestOutputTruncation:
    @pytest.mark.asyncio
    async def test_output_truncated(self, workspace: Path) -> None:
        policy_dir = workspace / ".vloop"
        policy_dir.mkdir(exist_ok=True)
        config = {
            "permanent_blocklist": [],
            "denylist": [],
            "directories": [
                {
                    "directory": ".",
                    "allowed_commands": [sys.executable.split("/")[-1]],
                    "max_runtime_seconds": 10,
                    "max_output_bytes": 10,  # very small
                }
            ],
        }
        (policy_dir / "policy.json").write_text(json.dumps(config))
        tool = TerminalTool(_make_mp(workspace))
        # Write a script file to avoid the -c semicolon parsing issue
        script = workspace / "_big_output.py"
        script.write_text("print('a' * 1000)\n")
        result = await tool.execute(
            None, None,
            {"command": f"{sys.executable} _big_output.py", "cwd_relative": "."},
        )
        # Output should be truncated to 10 bytes
        assert len(result.output) <= 50  # some slack for decode artefacts
        assert result.metadata.get("truncated") is True


class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_kills_process(self, workspace: Path) -> None:
        policy_dir = workspace / ".vloop"
        policy_dir.mkdir(exist_ok=True)
        config = {
            "permanent_blocklist": [],
            "denylist": [],
            "directories": [
                {
                    "directory": ".",
                    "allowed_commands": [sys.executable.split("/")[-1]],
                    "max_runtime_seconds": 60,
                    "max_output_bytes": 1024,
                }
            ],
        }
        (policy_dir / "policy.json").write_text(json.dumps(config))
        tool = TerminalTool(_make_mp(workspace))
        # Write a sleep script to avoid the inline -c semicolon issue
        script = workspace / "_sleep.py"
        script.write_text("import time\ntime.sleep(60)\n")
        result = await tool.execute(
            None, None,
            {
                "command": f"{sys.executable} _sleep.py",
                "cwd_relative": ".",
                "timeout": 1,
            },
        )
        assert not result.success
        assert "timed out" in (result.error or "").lower()
