import importlib.util
from pathlib import Path
from threading import Lock
from typing import Any

from ..telemetry.logger import get_logger

logger = get_logger(__name__)
_PIPELINES_DIR = Path(__file__).parent.parent.parent.parent.parent / "pipelines"


class PipelineRegistry:
    def __init__(self) -> None:
        self._pipelines: dict[str, Any] = {}
        self._lock = Lock()

    def scan(self) -> None:
        if not _PIPELINES_DIR.exists():
            return
        with self._lock:
            for path in _PIPELINES_DIR.glob("*.py"):
                self._load(path)

    def _load(self, path: Path) -> None:
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"pipelines.{name}", path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore[arg-type]
            self._pipelines[name] = mod
            logger.info("Pipeline loaded", name=name)
        except Exception as exc:
            logger.error("Pipeline load failed", name=name, error=str(exc))

    def get(self, name: str) -> Any:
        return self._pipelines.get(name)

    def list(self) -> list[str]:
        return list(self._pipelines.keys())

    def reload(self, name: str) -> None:
        path = _PIPELINES_DIR / f"{name}.py"
        if path.exists():
            with self._lock:
                self._load(path)
