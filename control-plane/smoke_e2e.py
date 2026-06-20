"""End-to-end smoke test for the local kernel + control-plane shell."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
KERNEL_BIN_DIR = REPO_ROOT / "kernel" / "target" / "debug"
VLOOPCTL = KERNEL_BIN_DIR / "vloopctl"
VLOOP_LAUNCHER = KERNEL_BIN_DIR / "vloop-launcher"
TIMEOUT_SECONDS = 60.0
POLL_SECONDS = 0.5
RUN_ID = uuid.uuid4().hex[:8]

_RUNTIME_ROOT_CREATED = (
    "VLOOP_HOME" not in os.environ and "VLOOP_RUNTIME_ROOT" not in os.environ
)
default_runtime_root = Path("/tmp") / f"vloop-smoke-runtime-{RUN_ID}"
RUNTIME_ROOT = Path(
    os.environ.get(
        "VLOOP_HOME",
        os.environ.get("VLOOP_RUNTIME_ROOT", str(default_runtime_root)),
    )
).resolve()
os.environ["VLOOP_HOME"] = str(RUNTIME_ROOT)
os.environ["VLOOP_RUNTIME_ROOT"] = str(RUNTIME_ROOT)
os.environ.setdefault("VLOOP_CP_AUTOSTART", "1")
os.environ.setdefault("VLOOP_CP_HTTP_PORT", "8765")
HTTP_BASE = f"http://127.0.0.1:{os.environ['VLOOP_CP_HTTP_PORT']}"

if python_bin := os.environ.get("VLOOP_CP_PYTHON_BIN"):
    python_path = Path(python_bin).expanduser()
    if not python_path.is_absolute():
        python_path = (Path.cwd() / python_path).resolve()
    if not python_path.is_file():
        raise RuntimeError(f"VLOOP_CP_PYTHON_BIN does not exist: {python_path}")
    deterministic_path = [
        str(python_path.parent),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    os.environ["PATH"] = os.pathsep.join(deterministic_path)


class SmokeFailure(RuntimeError):
    pass


def main() -> int:
    ensure_binary(VLOOPCTL)
    ensure_binary(VLOOP_LAUNCHER)

    print(f"[smoke] runtime root: {RUNTIME_ROOT}")
    print("[smoke] ensuring daemon is stopped before test")
    run_command([str(VLOOPCTL), "stop", "--json"], allow_failure=True)

    try:
        print("[smoke] starting vloopd with managed control-plane autostart")
        run_command([str(VLOOPCTL), "start", "--json"])

        status = wait_for_status_ready()
        print(f"[smoke] kernel health is {status['health']} and CP is registered")

        shell_html = fetch_text(f"{HTTP_BASE}/")
        if "/assets/" not in shell_html or 'id="root"' not in shell_html:
            raise SmokeFailure(
                "control-plane root page did not serve the built frontend bundle"
            )

        health = fetch_json(f"{HTTP_BASE}/health")
        session = fetch_json(f"{HTTP_BASE}/session")
        window = fetch_json(f"{HTTP_BASE}/window")
        events = fetch_json(f"{HTTP_BASE}/events/recent")
        bootstrap = fetch_json(f"{HTTP_BASE}/api/v1/bootstrap")
        provider_catalog = fetch_json(f"{HTTP_BASE}/api/v1/catalog/provider-types")
        templates = fetch_json(f"{HTTP_BASE}/api/v1/agents/templates")

        if health.get("status") != "registered":
            raise SmokeFailure(
                f"expected CP health status 'registered', got {health.get('status')!r}"
            )
        if session.get("session_id") is None:
            raise SmokeFailure(
                "control-plane session endpoint did not expose a session_id"
            )
        if window.get("is_open") is not False:
            raise SmokeFailure(
                "window should stay hidden until an explicit open-ui request"
            )
        if not bootstrap.get("providerCatalog"):
            raise SmokeFailure("bootstrap payload did not expose any provider catalog")
        if not provider_catalog.get("providerCatalog"):
            raise SmokeFailure(
                "provider catalog endpoint did not return any provider types"
            )
        if not templates.get("agentTemplates"):
            raise SmokeFailure("agent template endpoint returned an empty result")

        print("[smoke] creating a mock provider")
        provider = api_request_json(
            "/api/v1/providers",
            method="POST",
            body={
                "name": f"Smoke Mock Provider {RUN_ID}",
                "providerType": "mock",
                "enabled": True,
                "defaultModel": "mock/echo-agent",
                "secretMode": "none",
            },
        ).get("provider")
        if not isinstance(provider, dict) or not provider.get("id"):
            raise SmokeFailure("provider creation did not return a provider entity")

        provider_test = api_request_json(
            f"/api/v1/providers/{provider['id']}/test",
            method="POST",
        )
        if provider_test.get("status") != "ok":
            raise SmokeFailure(f"mock provider test failed: {provider_test}")

        print("[smoke] validating and saving a JSON-output DSPy agent")
        agent_payload = {
            "name": f"Smoke JSON Agent {RUN_ID}",
            "slug": f"smoke-json-agent-{RUN_ID}",
            "description": "Smoke-test agent that returns structured JSON via DSPy.",
            "instructions": "You are a structured smoke-test agent. Read the supplied request and produce a crisp summary plus next actions.",
            "reasoningMode": "chain_of_thought",
            "inputFields": [
                {
                    "name": "request_text",
                    "label": "Request text",
                    "description": "The text to analyze.",
                    "required": True,
                }
            ],
            "outputMode": "json",
            "outputFieldName": "payload",
            "outputSchema": {
                "summary": "string",
                "actions": ["string"],
            },
            "defaultProviderId": provider["id"],
            "temperature": 0.1,
            "maxTokens": 256,
            "enabled": True,
        }
        validation = api_request_json(
            "/api/v1/agents/validate",
            method="POST",
            body=agent_payload,
        )
        if validation.get("valid") is not True:
            raise SmokeFailure(f"agent validation did not pass: {validation}")

        agent = api_request_json(
            "/api/v1/agents",
            method="POST",
            body=agent_payload,
        ).get("agent")
        if not isinstance(agent, dict) or not agent.get("id"):
            raise SmokeFailure("agent creation did not return an agent entity")

        bootstrap = fetch_json(f"{HTTP_BASE}/api/v1/bootstrap")
        if not any(
            item.get("id") == provider["id"] for item in bootstrap.get("providers", [])
        ):
            raise SmokeFailure("bootstrap payload did not include the created provider")
        if not any(
            item.get("id") == agent["id"] for item in bootstrap.get("agents", [])
        ):
            raise SmokeFailure("bootstrap payload did not include the created agent")

        print("[smoke] invoking the agent through the Control Plane")
        invocation = api_request_json(
            f"/api/v1/agents/{agent['id']}/invoke",
            method="POST",
            body={
                "inputs": {
                    "request_text": "Investigate kernel-to-control-plane registration and propose the next actions."
                },
                "overrides": {},
            },
        ).get("invocation")
        if not isinstance(invocation, dict) or not invocation.get("id"):
            raise SmokeFailure("agent invocation did not return an invocation entity")

        terminal_invocation = wait_for_invocation_terminal(invocation["id"])
        if terminal_invocation.get("status") != "succeeded":
            raise SmokeFailure(
                f"invocation did not succeed: {json.dumps(terminal_invocation, indent=2)}"
            )
        if not terminal_invocation.get("reasoningText"):
            raise SmokeFailure("invocation did not expose a reasoning trace")
        output_json = terminal_invocation.get("outputJson")
        if not isinstance(output_json, dict):
            raise SmokeFailure(
                "JSON-output invocation did not produce parsed outputJson"
            )
        if "summary" not in output_json or "actions" not in output_json:
            raise SmokeFailure(
                f"outputJson did not match the expected schema: {output_json}"
            )

        invocation_events = api_request_json(
            f"/api/v1/invocations/{invocation['id']}/events"
        )
        events_list = invocation_events.get("events", [])
        if not isinstance(events_list, list) or len(events_list) < 4:
            raise SmokeFailure(
                "invocation events did not contain the expected timeline"
            )
        event_types = {
            event.get("type") for event in events_list if isinstance(event, dict)
        }
        required_event_types = {
            "queued",
            "started",
            "provider_resolved",
            "validated",
            "completed",
        }
        if not required_event_types.issubset(event_types):
            raise SmokeFailure(
                f"invocation events were missing expected stages: {sorted(required_event_types - event_types)}"
            )

        recent_invocations = api_request_json(
            f"/api/v1/invocations?agentId={agent['id']}"
        )
        if not any(
            item.get("id") == invocation["id"]
            for item in recent_invocations.get("invocations", [])
            if isinstance(item, dict)
        ):
            raise SmokeFailure(
                "agent-filtered invocation list did not include the new run"
            )

        print("[smoke] requesting UI open through the kernel control path")
        run_command([str(VLOOPCTL), "open-ui", "--json"])

        window = wait_for_window_open()
        print("[smoke] pywebview window reported itself open")

        events = fetch_json(f"{HTTP_BASE}/events/recent")
        recent_events = events.get("recent_events", [])
        if not any(
            event.get("event_type") == "control_plane.open_ui_requested"
            for event in recent_events
            if isinstance(event, dict)
        ):
            raise SmokeFailure("kernel event stream did not record the open-ui request")

        print("[smoke] exercising launcher path against the ready system")
        launcher = run_command([str(VLOOP_LAUNCHER)])
        if launcher.returncode != 0:
            raise SmokeFailure(f"launcher exited with {launcher.returncode}")

        print("[smoke] success")
        print(
            json.dumps(
                {
                    "kernel_status": status,
                    "control_plane_health": health,
                    "window": window,
                    "provider": provider,
                    "agent": agent,
                    "invocation": terminal_invocation,
                    "invocation_event_count": len(events_list),
                    "kernel_event_count": events.get("event_count"),
                },
                indent=2,
            )
        )
        return 0
    finally:
        print("[smoke] stopping vloopd")
        run_command([str(VLOOPCTL), "stop", "--json"], allow_failure=True)
        if _RUNTIME_ROOT_CREATED:
            shutil.rmtree(RUNTIME_ROOT, ignore_errors=True)


def wait_for_status_ready() -> dict[str, Any]:
    deadline = time.time() + TIMEOUT_SECONDS
    last_status: dict[str, Any] | None = None

    while time.time() < deadline:
        result = run_command([str(VLOOPCTL), "status", "--json"], allow_failure=True)
        payload = parse_json_output(result.stdout)
        if isinstance(payload, dict):
            last_status = payload
            if (
                payload.get("daemon_reachable") is True
                and payload.get("health") == "ready"
                and payload.get("control_plane", {}).get("registered") is True
            ):
                return payload
        time.sleep(POLL_SECONDS)

    raise SmokeFailure(
        f"timed out waiting for ready kernel status; last status was: {last_status}"
    )


def wait_for_window_open() -> dict[str, Any]:
    deadline = time.time() + TIMEOUT_SECONDS
    last_window: dict[str, Any] | None = None

    while time.time() < deadline:
        payload = fetch_json(f"{HTTP_BASE}/window")
        last_window = payload
        if payload.get("is_open") is True and int(payload.get("open_requests", 0)) >= 1:
            return payload
        time.sleep(POLL_SECONDS)

    raise SmokeFailure(
        f"timed out waiting for the pywebview window to open; last state was: {last_window}"
    )


def wait_for_invocation_terminal(invocation_id: str) -> dict[str, Any]:
    deadline = time.time() + TIMEOUT_SECONDS
    last_invocation: dict[str, Any] | None = None

    while time.time() < deadline:
        payload = api_request_json(f"/api/v1/invocations/{invocation_id}")
        invocation = payload.get("invocation")
        if isinstance(invocation, dict):
            last_invocation = invocation
            if invocation.get("status") in {"succeeded", "failed", "cancelled"}:
                return invocation
        time.sleep(POLL_SECONDS)

    raise SmokeFailure(
        f"timed out waiting for invocation `{invocation_id}` to finish; last state was: {last_invocation}"
    )


def run_command(
    args: list[str], *, allow_failure: bool = False
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    if not allow_failure and result.returncode != 0:
        raise SmokeFailure(
            f"command {args!r} failed with code {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    with urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def api_request_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = Request(
        f"{HTTP_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:  # pragma: no cover - exercised in failures only
        detail = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(
            f"HTTP {exc.code} for {method} {path}: {detail or exc.reason}"
        ) from exc


def parse_json_output(output: str) -> Any:
    for candidate in reversed(
        [chunk.strip() for chunk in output.split("\n\n") if chunk.strip()]
    ):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def ensure_binary(path: Path) -> None:
    if not path.is_file():
        raise SmokeFailure(f"required binary does not exist: {path}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print(f"[smoke] failure: {exc}", file=sys.stderr)
        raise SystemExit(1)
