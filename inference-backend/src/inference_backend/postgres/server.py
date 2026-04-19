"""Optional local Postgres process management."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..telemetry.logger import get_logger

logger = get_logger(__name__)


def find_pg_ctl() -> str | None:
    return shutil.which("pg_ctl") or shutil.which("pg_ctlcluster")


def start_postgres(data_dir: str, port: int = 5432) -> bool:
    pg_ctl = find_pg_ctl()
    if pg_ctl is None:
        logger.warning("pg_ctl not found — try Docker Postgres instead")
        return False
    try:
        result = subprocess.run(
            [pg_ctl, "start", "-D", data_dir, "-o", f"-p {port}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Postgres started", data_dir=data_dir, port=port)
            return True
        logger.error("pg_ctl start failed", stderr=result.stderr)
        return False
    except Exception as exc:
        logger.error("pg_ctl start exception", error=str(exc))
        return False


def stop_postgres(data_dir: str) -> bool:
    pg_ctl = find_pg_ctl()
    if pg_ctl is None:
        return False
    try:
        result = subprocess.run(
            [pg_ctl, "stop", "-D", data_dir, "-m", "fast"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False
