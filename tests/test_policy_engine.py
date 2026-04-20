"""Tests for the PolicyEngine — allowlist/denylist/blocklist logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.tools.exceptions import PermissionDenied, PolicyBlocked, PermanentlyBlocked
from harness.tools.policy import DirectoryPolicy, PolicyConfig, PolicyEngine


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def engine(workspace: Path) -> PolicyEngine:
    """PolicyEngine with a simple project policy."""
    policy_dir = workspace / ".vloop"
    policy_dir.mkdir()
    config = {
        "permanent_blocklist": [],
        "denylist": ["sudo"],
        "directories": [
            {
                "directory": ".",
                "allowed_commands": ["pytest", "python", "ruff"],
                "max_runtime_seconds": 30,
                "max_output_bytes": 524288,
            },
            {
                "directory": "scripts",
                "allowed_commands": ["bash", "sh"],
            },
        ],
    }
    (policy_dir / "policy.json").write_text(json.dumps(config))
    return PolicyEngine(workspace_root=workspace)


class TestPermanentBlocklist:
    def test_builtin_blocked(self, engine: PolicyEngine, workspace: Path) -> None:
        with pytest.raises(PermanentlyBlocked):
            engine.check_command("mkfs", [], workspace)

    def test_builtin_blocked_regardless_of_allowlist(
        self, engine: PolicyEngine, workspace: Path
    ) -> None:
        """Even if mkfs were in an allowlist, the permanent blocklist wins."""
        with pytest.raises(PermanentlyBlocked):
            engine.check_command("mkfs", [], workspace)

    def test_custom_permanent_block(self, workspace: Path) -> None:
        policy_dir = workspace / ".vloop"
        policy_dir.mkdir(exist_ok=True)
        config = {
            "permanent_blocklist": ["dangerous_cmd"],
            "denylist": [],
            "directories": [
                {"directory": ".", "allowed_commands": ["dangerous_cmd"]}
            ],
        }
        (policy_dir / "policy.json").write_text(json.dumps(config))
        eng = PolicyEngine(workspace_root=workspace)
        with pytest.raises(PermanentlyBlocked):
            eng.check_command("dangerous_cmd", [], workspace)


class TestDenylist:
    def test_denylist_blocked(self, engine: PolicyEngine, workspace: Path) -> None:
        with pytest.raises(PolicyBlocked, match="denylist"):
            engine.check_command("sudo", ["ls"], workspace)

    def test_non_denied_passes_denylist(self, engine: PolicyEngine, workspace: Path) -> None:
        # pytest is allowed in root; should not raise
        engine.check_command("pytest", [], workspace)


class TestAllowlist:
    def test_allowed_in_root(self, engine: PolicyEngine, workspace: Path) -> None:
        result = engine.check_command("pytest", ["-v"], workspace)
        assert result.directory == "."

    def test_not_in_allowlist(self, engine: PolicyEngine, workspace: Path) -> None:
        with pytest.raises(PolicyBlocked, match="allowlist"):
            engine.check_command("cargo", [], workspace)

    def test_allowed_in_subdir(self, engine: PolicyEngine, workspace: Path) -> None:
        scripts_dir = workspace / "scripts"
        scripts_dir.mkdir()
        result = engine.check_command("bash", ["-c", "echo hi"], scripts_dir)
        assert result.directory == "scripts"

    def test_command_not_in_subdir_allowlist(
        self, engine: PolicyEngine, workspace: Path
    ) -> None:
        scripts_dir = workspace / "scripts"
        scripts_dir.mkdir()
        with pytest.raises(PolicyBlocked):
            # pytest allowed in root but not in scripts
            engine.check_command("pytest", [], scripts_dir)

    def test_no_matching_directory_policy(
        self, engine: PolicyEngine, workspace: Path
    ) -> None:
        unknown_dir = workspace / "unknown"
        unknown_dir.mkdir()
        with pytest.raises(PolicyBlocked, match="No allowlist"):
            engine.check_command("pytest", [], unknown_dir)


class TestArgPatterns:
    def test_arg_pattern_match(self, workspace: Path) -> None:
        policy_dir = workspace / ".vloop"
        policy_dir.mkdir()
        config = {
            "permanent_blocklist": [],
            "denylist": [],
            "directories": [
                {
                    "directory": ".",
                    "allowed_commands": ["python"],
                    "allowed_arg_patterns": {"python": [r"-m \w+"]},
                }
            ],
        }
        (policy_dir / "policy.json").write_text(json.dumps(config))
        eng = PolicyEngine(workspace_root=workspace)
        # Should not raise
        eng.check_command("python", ["-m", "pytest"], workspace)

    def test_arg_pattern_no_match(self, workspace: Path) -> None:
        policy_dir = workspace / ".vloop"
        policy_dir.mkdir()
        config = {
            "permanent_blocklist": [],
            "denylist": [],
            "directories": [
                {
                    "directory": ".",
                    "allowed_commands": ["python"],
                    "allowed_arg_patterns": {"python": [r"-m \w+"]},
                }
            ],
        }
        (policy_dir / "policy.json").write_text(json.dumps(config))
        eng = PolicyEngine(workspace_root=workspace)
        with pytest.raises(PolicyBlocked, match="pattern"):
            eng.check_command("python", ["-c", "import os; os.system('ls')"], workspace)


class TestShellInjection:
    def test_backtick_blocked(self, engine: PolicyEngine) -> None:
        with pytest.raises(ValueError, match="disallowed"):
            engine.check_shell_injection("echo `id`")

    def test_dollar_paren_blocked(self, engine: PolicyEngine) -> None:
        with pytest.raises(ValueError):
            engine.check_shell_injection("echo $(id)")

    def test_pipe_blocked(self, engine: PolicyEngine) -> None:
        with pytest.raises(ValueError):
            engine.check_shell_injection("cat file | grep password")

    def test_redirect_blocked(self, engine: PolicyEngine) -> None:
        with pytest.raises(ValueError):
            engine.check_shell_injection("echo hello > /etc/hosts")

    def test_safe_command_passes(self, engine: PolicyEngine) -> None:
        engine.check_shell_injection("pytest -v tests/")


class TestPolicySaveReload:
    def test_save_and_reload(self, workspace: Path) -> None:
        policy_dir = workspace / ".vloop"
        policy_dir.mkdir()
        eng = PolicyEngine(workspace_root=workspace)
        new_cfg = PolicyConfig(
            permanent_blocklist=[],
            denylist=["curl"],
            directories=[
                DirectoryPolicy(directory=".", allowed_commands=["git"])
            ],
        )
        eng.save_project_policy(new_cfg)
        eng.reload()
        # Should allow git
        eng.check_command("git", ["status"], workspace)
        # curl should be denied
        with pytest.raises(PolicyBlocked):
            eng.check_command("curl", [], workspace)
