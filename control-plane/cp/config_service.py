"""Typed CP config service backed by kernel-injected and local runtime config."""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(slots=True)
class KernelActiveConfig:
    ipc_endpoint: str
    boot_id: str
    runtime_root: str
    available_runtimes: list[str] = field(default_factory=list)
    features: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_proto(cls, payload: object | None) -> "KernelActiveConfig | None":
        if payload is None:
            return None
        return cls(
            ipc_endpoint=getattr(payload, "ipc_endpoint", ""),
            boot_id=getattr(payload, "boot_id", ""),
            runtime_root=getattr(payload, "runtime_root", ""),
            available_runtimes=list(getattr(payload, "available_runtimes", [])),
            features=dict(getattr(payload, "features", {})),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ControlPlaneConfig:
    kernel_endpoint: str
    bootstrap_token: str | None
    runtime_root: Path
    repo_root: Path
    version: str
    announced_capabilities: list[str] = field(
        default_factory=lambda: [
            "kernel.status",
            "kernel.events",
            "kernel.open_ui",
        ]
    )
    serve_http: bool = True
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    heartbeat_interval_seconds: float = 10.0
    reconnect_backoff_seconds: float = 2.0
    connect_timeout_seconds: float = 10.0
    rpc_timeout_seconds: float = 10.0
    event_buffer_size: int = 200
    open_window_on_boot: bool = False
    window_title: str = "VLoop"
    window_width: int = 1320
    window_height: int = 860
    window_hidden_until_open: bool = True
    window_debug: bool = False

    def registration_metadata(self) -> dict[str, str]:
        return {
            "component": "python-control-plane",
            "http_enabled": str(self.serve_http).lower(),
            "repo_root": str(self.repo_root),
            "runtime_root": str(self.runtime_root),
            "window_backend": "pywebview",
        }

    def http_base_url(self) -> str:
        return f"http://{self.http_host}:{self.http_port}"

    def shell_url(self) -> str:
        return f"{self.http_base_url()}/"


def load_active_config() -> ControlPlaneConfig:
    repo_root = _repo_root()
    runtime_root = Path(
        os.environ.get("VLOOP_RUNTIME_ROOT", Path.home() / ".vloop")
    ).expanduser()
    kernel_endpoint = os.environ.get(
        "VLOOP_KERNEL_ENDPOINT",
        f"unix://{runtime_root / 'run' / 'vloopd.sock'}",
    )

    return ControlPlaneConfig(
        kernel_endpoint=kernel_endpoint,
        bootstrap_token=os.environ.get("VLOOP_KERNEL_BOOTSTRAP_TOKEN"),
        runtime_root=runtime_root,
        repo_root=repo_root,
        version=_control_plane_version(repo_root),
        serve_http=_env_flag("VLOOP_CP_HTTP", default=True),
        http_host=os.environ.get("VLOOP_CP_HTTP_HOST", "127.0.0.1"),
        http_port=int(os.environ.get("VLOOP_CP_HTTP_PORT", "8765")),
        heartbeat_interval_seconds=float(
            os.environ.get("VLOOP_CP_HEARTBEAT_SECONDS", "10")
        ),
        reconnect_backoff_seconds=float(
            os.environ.get("VLOOP_CP_RECONNECT_SECONDS", "2")
        ),
        connect_timeout_seconds=float(
            os.environ.get("VLOOP_CP_CONNECT_TIMEOUT_SECONDS", "10")
        ),
        rpc_timeout_seconds=float(os.environ.get("VLOOP_CP_RPC_TIMEOUT_SECONDS", "10")),
        event_buffer_size=int(os.environ.get("VLOOP_CP_EVENT_BUFFER_SIZE", "200")),
        open_window_on_boot=_env_flag("VLOOP_CP_OPEN_WINDOW_ON_BOOT", default=False),
        window_title=os.environ.get("VLOOP_CP_WINDOW_TITLE", "VLoop"),
        window_width=int(os.environ.get("VLOOP_CP_WINDOW_WIDTH", "1320")),
        window_height=int(os.environ.get("VLOOP_CP_WINDOW_HEIGHT", "860")),
        window_hidden_until_open=_env_flag("VLOOP_CP_WINDOW_HIDDEN", default=True),
        window_debug=_env_flag("VLOOP_CP_WINDOW_DEBUG", default=False),
    )


def _repo_root() -> Path:
    explicit = os.environ.get("VLOOP_REPO_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _control_plane_version(repo_root: Path) -> str:
    pyproject_path = repo_root / "control-plane" / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        payload = tomllib.load(handle)
    return str(payload.get("project", {}).get("version", "0.0.0"))


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
