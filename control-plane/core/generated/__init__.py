"""Helpers for generating and loading Python gRPC stubs for VLoop."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


def generated_dir() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def kernel_proto_path() -> Path:
    return repo_root() / "proto" / "kernel.proto"


def ensure_generated_stubs() -> None:
    output_dir = generated_dir()
    proto_path = kernel_proto_path()
    _ensure_import_path(output_dir)

    pb2_path = output_dir / "kernel_pb2.py"
    grpc_path = output_dir / "kernel_pb2_grpc.py"

    if (
        pb2_path.exists()
        and grpc_path.exists()
        and pb2_path.stat().st_mtime >= proto_path.stat().st_mtime
        and grpc_path.stat().st_mtime >= proto_path.stat().st_mtime
    ):
        return

    try:
        protoc = importlib.import_module("grpc_tools.protoc")
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(
            "grpcio-tools is required to generate Python kernel stubs. "
            "Install control-plane dependencies first."
        ) from exc

    result = protoc.main(
        [
            "grpc_tools.protoc",
            f"-I{proto_path.parent}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            str(proto_path),
        ]
    )
    if result != 0:
        raise RuntimeError(f"failed to generate Python gRPC stubs from {proto_path}")

    importlib.invalidate_caches()


def load_kernel_modules() -> tuple[ModuleType, ModuleType]:
    ensure_generated_stubs()

    try:
        kernel_pb2 = _import_or_reload("kernel_pb2")
        kernel_pb2_grpc = _import_or_reload("kernel_pb2_grpc")
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
        missing = exc.name or "required package"
        raise RuntimeError(
            f"missing Python dependency `{missing}` while loading kernel gRPC stubs. "
            "Install control-plane dependencies first."
        ) from exc

    return kernel_pb2, kernel_pb2_grpc


def _ensure_import_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def _import_or_reload(module_name: str) -> ModuleType:
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)
