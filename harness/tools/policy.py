"""PolicyEngine — three-tier security policy for tool execution.

Tiers (evaluated in order, highest priority first):
  1. Permanent blocklist — unconditionally blocked; cannot be overridden.
  2. Denylist — blocked by default; removable only at the global policy level.
  3. Per-directory allowlist — commands allowed for a specific directory path.

Policy files
────────────
  Project-local:  <workspace_root>/.vloop/policy.json
  Global:         ~/.vloop/policy.json

The project-local file takes precedence for allowlist and denylist entries;
the global permanent blocklist is always merged in and cannot be weakened.

Schema for policy.json
──────────────────────
{
  "permanent_blocklist": ["rm -rf /", "mkfs", "dd if=/dev/"],
  "denylist": ["sudo", "su", "passwd"],
  "directories": [
    {
      "directory": ".",
      "allowed_commands": ["python", "pytest", "ruff"],
      "allowed_arg_patterns": {
        "python": ["-m \\w+", "-c .+"]
      },
      "max_runtime_seconds": 60,
      "max_output_bytes": 524288
    }
  ]
}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Default hard limits ───────────────────────────────────────────────────────

DEFAULT_MAX_RUNTIME_SECONDS = 30
DEFAULT_MAX_OUTPUT_BYTES = 512 * 1024  # 512 KiB

# Commands that are always blocked regardless of any policy configuration.
_BUILTIN_PERMANENT_BLOCKLIST: list[str] = [
    "mkfs",
    "fdisk",
    "parted",
    "shred",
    "wipefs",
]

# Shell injection patterns — detected in any command string and hard-rejected.
_SHELL_INJECTION_RE = re.compile(
    r"""
    \$\(          |   # $( ... )
    `             |   # backtick subshell
    \$\{[^}]*\}   |   # ${...} variable expansion
    \beval\b      |   # eval
    \|\s*eval\b   |   # pipe to eval
    &&|\|\|       |   # shell boolean chaining
    ;\s*\w        |   # command chaining with ;
    >>\s*\S       |   # append redirect
    >\s*\S        |   # output redirect
    <\s*\(        |   # process substitution
    \|\s*\w           # pipes
    """,
    re.VERBOSE,
)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class DirectoryPolicy:
    """Per-directory allowlist entry."""

    directory: str  # relative to workspace_root
    allowed_commands: list[str] = field(default_factory=list)
    allowed_arg_patterns: dict[str, list[str]] = field(default_factory=dict)
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DirectoryPolicy:
        return cls(
            directory=data.get("directory", "."),
            allowed_commands=data.get("allowed_commands", []),
            allowed_arg_patterns=data.get("allowed_arg_patterns", {}),
            max_runtime_seconds=data.get("max_runtime_seconds", DEFAULT_MAX_RUNTIME_SECONDS),
            max_output_bytes=data.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "directory": self.directory,
            "allowed_commands": self.allowed_commands,
            "allowed_arg_patterns": self.allowed_arg_patterns,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_output_bytes": self.max_output_bytes,
        }


@dataclass
class PolicyConfig:
    """Complete policy configuration."""

    permanent_blocklist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)
    directories: list[DirectoryPolicy] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyConfig:
        return cls(
            permanent_blocklist=data.get("permanent_blocklist", []),
            denylist=data.get("denylist", []),
            directories=[
                DirectoryPolicy.from_dict(d) for d in data.get("directories", [])
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "permanent_blocklist": self.permanent_blocklist,
            "denylist": self.denylist,
            "directories": [d.to_dict() for d in self.directories],
        }

    @classmethod
    def default(cls) -> PolicyConfig:
        return cls(
            permanent_blocklist=list(_BUILTIN_PERMANENT_BLOCKLIST),
            denylist=["sudo", "su", "passwd", "chown", "chmod"],
            directories=[],
        )


# ── PolicyEngine ──────────────────────────────────────────────────────────────


class PolicyEngine:
    """Loads, merges, and evaluates the three-tier security policy.

    Usage::

        engine = PolicyEngine(workspace_root=Path("/my/project"))
        engine.check_command("pytest", argv=["-v", "tests/"], cwd_abs=Path("/my/project"))
    """

    def __init__(
        self,
        workspace_root: Path,
        policy_path_override: Path | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self._project_policy_path = policy_path_override or (
            self.workspace_root / ".vloop" / "policy.json"
        )
        self._global_policy_path = Path.home() / ".vloop" / "policy.json"
        self._effective: PolicyConfig = self._load()

    # ── Load / reload ─────────────────────────────────────────────────────────

    def _load_file(self, path: Path) -> PolicyConfig:
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return PolicyConfig.from_dict(data)
            except Exception:
                pass
        return PolicyConfig()

    def _load(self) -> PolicyConfig:
        global_cfg = self._load_file(self._global_policy_path)
        project_cfg = self._load_file(self._project_policy_path)

        # Merge: permanent blocklist is a union of all sources + builtins
        permanent = set(_BUILTIN_PERMANENT_BLOCKLIST)
        permanent.update(global_cfg.permanent_blocklist)
        permanent.update(project_cfg.permanent_blocklist)

        # Denylist: project takes precedence over global (project can remove entries)
        denylist = project_cfg.denylist if project_cfg.denylist else global_cfg.denylist
        if not denylist:
            denylist = ["sudo", "su", "passwd", "chown", "chmod"]

        # Directories: project entries override global entries for same path
        global_dirs = {d.directory: d for d in global_cfg.directories}
        for d in project_cfg.directories:
            global_dirs[d.directory] = d

        return PolicyConfig(
            permanent_blocklist=sorted(permanent),
            denylist=denylist,
            directories=list(global_dirs.values()),
        )

    def reload(self) -> None:
        """Reload policy from disk (e.g. after the user edits policy.json)."""
        self._effective = self._load()

    def save_project_policy(self, config: PolicyConfig) -> None:
        """Persist an updated project-local policy to disk."""
        self._project_policy_path.parent.mkdir(parents=True, exist_ok=True)
        # The permanent blocklist in the project file must not remove builtins —
        # strip them from the persisted file to avoid confusion.
        safe_perm = [
            cmd for cmd in config.permanent_blocklist
            if cmd not in _BUILTIN_PERMANENT_BLOCKLIST
        ]
        data = {
            "permanent_blocklist": safe_perm,
            "denylist": config.denylist,
            "directories": [d.to_dict() for d in config.directories],
        }
        with self._project_policy_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        self.reload()

    # ── Effective policy accessor ─────────────────────────────────────────────

    @property
    def effective(self) -> PolicyConfig:
        return self._effective

    # ── Validation helpers ────────────────────────────────────────────────────

    def _command_matches(self, pattern: str, command: str) -> bool:
        """True if *command* starts with or equals *pattern* (normalised)."""
        pattern = pattern.strip().split()[0]  # compare binary names only
        return command.strip().split()[0] == pattern

    def check_shell_injection(self, raw_command: str) -> None:
        """Raise ValueError if *raw_command* contains shell injection patterns."""
        if _SHELL_INJECTION_RE.search(raw_command):
            raise ValueError(
                f"Command contains disallowed shell characters: {raw_command!r}"
            )

    def check_command(
        self,
        binary: str,
        argv: list[str],
        cwd_abs: Path,
    ) -> DirectoryPolicy:
        """Validate *binary* + *argv* against the policy for *cwd_abs*.

        Returns the matching ``DirectoryPolicy`` (so callers know the limits).

        Raises
        ------
        PermanentlyBlocked
            If the command matches the permanent blocklist.
        PolicyBlocked
            If the command is in the denylist, or if no allowlist entry permits it.
        """
        from harness.tools.exceptions import PermanentlyBlocked, PolicyBlocked

        binary_name = Path(binary).name  # strip path prefix

        # 1. Permanent blocklist (builtins + configured)
        for blocked in self._effective.permanent_blocklist:
            if self._command_matches(blocked, binary_name):
                raise PermanentlyBlocked(
                    f"Command {binary_name!r} is permanently blocked."
                )

        # 2. Denylist
        for denied in self._effective.denylist:
            if self._command_matches(denied, binary_name):
                raise PolicyBlocked(
                    f"Command {binary_name!r} is in the denylist."
                )

        # 3. Per-directory allowlist
        # Find the most-specific matching directory policy (exact or parent match)
        rel_cwd = self._relative_cwd(cwd_abs)
        matched_policy: DirectoryPolicy | None = None

        for dir_policy in self._effective.directories:
            policy_dir = Path(dir_policy.directory)
            # An entry matches if the CWD is exactly the policy directory
            # or is a subdirectory of it. The most-specific (longest) match wins.
            if rel_cwd == policy_dir or (
                policy_dir != Path(".") and self._path_is_under(rel_cwd, policy_dir)
            ) or (
                policy_dir == Path(".") and rel_cwd == Path(".")
            ):
                if matched_policy is None or len(str(policy_dir)) > len(
                    str(Path(matched_policy.directory))
                ):
                    matched_policy = dir_policy

        if matched_policy is None:
            raise PolicyBlocked(
                f"No allowlist entry permits {binary_name!r} in directory "
                f"{rel_cwd!r}. Add a directory entry in .vloop/policy.json."
            )

        if binary_name not in matched_policy.allowed_commands:
            raise PolicyBlocked(
                f"Command {binary_name!r} is not in the allowlist for "
                f"directory {matched_policy.directory!r}."
            )

        # 4. Argument pattern validation (optional)
        arg_patterns = matched_policy.allowed_arg_patterns.get(binary_name, [])
        if arg_patterns:
            arg_string = " ".join(argv)
            if not any(re.search(pat, arg_string) for pat in arg_patterns):
                raise PolicyBlocked(
                    f"Arguments {argv!r} for {binary_name!r} do not match any "
                    f"allowed pattern: {arg_patterns!r}"
                )

        return matched_policy

    def _relative_cwd(self, cwd_abs: Path) -> Path:
        """Return CWD relative to workspace_root, defaulting to '.' if at root."""
        try:
            rel = cwd_abs.relative_to(self.workspace_root)
            return rel if str(rel) != "" else Path(".")
        except ValueError:
            return Path(".")

    @staticmethod
    def _path_is_under(path: Path, parent: Path) -> bool:
        """Return True if *path* is a subdirectory of *parent* (not equal)."""
        try:
            path.relative_to(parent)
            return path != parent
        except ValueError:
            return False
