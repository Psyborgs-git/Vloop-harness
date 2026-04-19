"""Optional Docker sandbox for running agent-generated code in isolation."""
from __future__ import annotations

import json
import os
from typing import Any


def run_in_docker(code: str, inputs: dict[str, Any], image: str = "python:3.11-slim") -> dict:
    """
    Run Python code inside a Docker container.
    Requires SANDBOX_MODE=docker and Docker installed.
    """
    try:
        import docker  # type: ignore[import]
    except ImportError:
        return {"error": "docker package not installed. pip install inference-backend[docker]"}

    client = docker.from_env()
    script = f"""
import json, sys
inputs = {json.dumps(inputs)}
{code}
"""
    try:
        result = client.containers.run(
            image,
            command=["python", "-c", script],
            remove=True,
            mem_limit="256m",
            cpu_period=100000,
            cpu_quota=50000,
            network_disabled=True,
            stderr=True,
            stdout=True,
        )
        return {"output": result.decode("utf-8", errors="replace")}
    except Exception as exc:
        return {"error": str(exc)}
