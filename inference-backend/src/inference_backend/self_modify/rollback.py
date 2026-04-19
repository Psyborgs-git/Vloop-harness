"""Git-based rollback for agent-generated modules."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import git

from ..telemetry.logger import get_logger

logger = get_logger(__name__)

_MODULES_DIR = Path(__file__).parent.parent.parent.parent.parent / "modules"


def _ensure_repo(path: Path) -> git.Repo:
    if not (path / ".git").exists():
        repo = git.Repo.init(path)
        logger.info("Initialised git repo for modules", path=str(path))
    else:
        repo = git.Repo(path)
    return repo


def commit_module(name: str, message: Optional[str] = None) -> str:
    """Stage and commit a module file. Returns the new commit SHA."""
    repo = _ensure_repo(_MODULES_DIR)
    module_file = _MODULES_DIR / f"{name}.py"
    if not module_file.exists():
        raise FileNotFoundError(f"Module not found: {name}")

    repo.index.add([f"{name}.py"])
    msg = message or f"[agent] create module {name}"
    commit = repo.index.commit(msg)
    sha = commit.hexsha
    logger.info("Module committed", name=name, sha=sha)
    return sha


def rollback_module(name: str, version: str) -> None:
    """Restore a module to a given git SHA."""
    repo = _ensure_repo(_MODULES_DIR)
    try:
        blob = repo.commit(version).tree[f"{name}.py"]
        (_MODULES_DIR / f"{name}.py").write_bytes(blob.data_stream.read())
        logger.info("Module rolled back", name=name, version=version)
    except Exception as exc:
        raise ValueError(f"Rollback failed for {name}@{version}: {exc}") from exc


def list_versions(name: str) -> list[dict]:
    """List commit history for a module."""
    repo = _ensure_repo(_MODULES_DIR)
    commits = []
    try:
        for commit in repo.iter_commits(paths=f"{name}.py"):
            commits.append({
                "sha": commit.hexsha,
                "message": commit.message.strip(),
                "authored_at": commit.authored_datetime.isoformat(),
            })
    except Exception:
        pass
    return commits
