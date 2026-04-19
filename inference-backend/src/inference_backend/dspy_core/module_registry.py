import importlib
import importlib.util
import sys
from pathlib import Path
from threading import Lock
from typing import Any

from ..telemetry.logger import get_logger

logger = get_logger(__name__)
_MODULES_DIR = Path(__file__).parent.parent.parent.parent.parent / "modules"


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, Any] = {}
        self._lock = Lock()

    def scan(self) -> None:
        modules_dir = _MODULES_DIR
        if not modules_dir.exists():
            return
        with self._lock:
            for path in modules_dir.glob("*.py"):
                self._load(path)

    def _load(self, path: Path) -> None:
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"modules.{name}", path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore[arg-type]
            self._modules[name] = mod
            logger.info("Module loaded", name=name)
        except Exception as exc:
            logger.error("Module load failed", name=name, error=str(exc))

    def get(self, name: str) -> Any:
        return self._modules.get(name)

    def list(self) -> list[str]:
        return list(self._modules.keys())

    def reload(self, name: str) -> None:
        modules_dir = _MODULES_DIR
        path = modules_dir / f"{name}.py"
        if path.exists():
            with self._lock:
                self._load(path)
