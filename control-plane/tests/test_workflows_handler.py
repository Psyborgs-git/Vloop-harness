"""Unit tests for the workflow HTTP routes (cp/handlers/workflows.py).

These exercise the route registrations end-to-end through ``cp.handlers.route``
using a fake runtime that records the accessor calls, plus a fake HTTP handler
that captures the JSON response. The Planner / DAG_Executor / template-catalog
wiring itself is covered elsewhere; here we verify the handler contract:

* ``POST /api/v1/workflows`` persists + returns an id only when ``build_dag``
  succeeds, and a rejected definition surfaces as 400 with no id (Req 1.4)
* ``POST /api/v1/workflows/validate`` validates without persisting (Req 1.4, 1.5)
* ``GET  /api/v1/workflows/templates`` lists templates and
  ``POST /api/v1/workflows/templates/{id}`` instantiates one (Req 20.2)
* ``POST /api/v1/workflows/{id}/runs`` starts a run (Req 3.1, 20.1)
* ``GET  /api/v1/workflow-runs/{id}`` observes state + steps + events (Req 4.5)
* ``POST /api/v1/workflow-runs/{id}/cancel`` cancels (Req 4.2)
* ``POST /api/v1/workflow-runs/{id}/retry`` retries (Req 4.4)
"""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import pytest

import cp.handlers  # noqa: F401 — triggers route registration side effects
from cp.handlers import route


class FakeRuntime:
    """Records workflow accessor calls and returns canned values."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.create_error: Exception | None = None
        self.template: dict[str, Any] | None = {"id": "tmpl-1", "name": "Daily report"}
        self.workflow: dict[str, Any] | None = {"id": "wf-1", "name": "Mine"}

    # -- definitions -----------------------------------------------------

    def list_workflows(self):
        self.calls.append(("list_workflows", (), {}))
        return [{"id": "wf-1", "name": "Mine"}]

    def create_workflow(self, body):
        self.calls.append(("create_workflow", (body,), {}))
        if self.create_error is not None:
            raise self.create_error
        return {"id": "wf-new", "name": body.get("name", "untitled")}

    def validate_workflow(self, body):
        self.calls.append(("validate_workflow", (body,), {}))
        return {"valid": True, "problems": []}

    def get_workflow(self, workflow_id):
        self.calls.append(("get_workflow", (workflow_id,), {}))
        return self.workflow

    # -- templates -------------------------------------------------------

    def list_workflow_templates(self):
        self.calls.append(("list_workflow_templates", (), {}))
        return [{"id": "tmpl-1", "name": "Daily report"}]

    def get_workflow_template(self, template_id):
        self.calls.append(("get_workflow_template", (template_id,), {}))
        return self.template

    def instantiate_workflow_template(self, template_id, body):
        self.calls.append(("instantiate_workflow_template", (template_id, body), {}))
        return {"id": "wf-from-tmpl", "templateId": template_id}

    # -- runs ------------------------------------------------------------

    def start_workflow_run(self, workflow_id, body):
        self.calls.append(("start_workflow_run", (workflow_id, body), {}))
        return {"id": "run-1", "state": "pending"}

    def list_workflow_runs(self, workflow_id):
        self.calls.append(("list_workflow_runs", (workflow_id,), {}))
        return [{"id": "run-1", "state": "pending"}]

    def get_workflow_run(self, run_id):
        self.calls.append(("get_workflow_run", (run_id,), {}))
        return {
            "run": {"id": run_id, "state": "running"},
            "steps": [{"step_id": "s1", "state": "completed"}],
            "events": [{"type": "run.created"}],
        }

    def cancel_workflow_run(self, run_id):
        self.calls.append(("cancel_workflow_run", (run_id,), {}))
        return {"id": run_id, "state": "cancelled"}

    def retry_workflow_run(self, run_id):
        self.calls.append(("retry_workflow_run", (run_id,), {}))
        return {"id": run_id, "state": "running"}


class _FakeWFile:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.chunks.append(data)


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler used by write_json."""

    def __init__(self) -> None:
        self.status: HTTPStatus | None = None
        self.headers_sent: dict[str, str] = {}
        self.wfile = _FakeWFile()

    def send_response(self, status: HTTPStatus) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers_sent[key] = value

    def end_headers(self) -> None:
        pass

    @property
    def body(self) -> Any:
        return json.loads(b"".join(self.wfile.chunks).decode("utf-8"))


def _dispatch(method, path, *, query=None, body=None, runtime=None):
    """Route a request and return (handler, runtime). Mirrors http_handler."""
    runtime = runtime if runtime is not None else FakeRuntime()
    handler = FakeHandler()
    route(handler, method, path, query or {}, body or {}, runtime)
    return handler, runtime


# ---------------------------------------------------------------------------
# Create / validate definitions (Requirement 1.4, 1.5)
# ---------------------------------------------------------------------------


def test_post_creates_workflow_and_returns_id():
    handler, runtime = _dispatch(
        "POST", "/api/v1/workflows", body={"name": "Mine", "steps": []}
    )
    assert handler.status == HTTPStatus.CREATED
    assert handler.body == {"workflow": {"id": "wf-new", "name": "Mine"}}
    assert runtime.calls == [("create_workflow", ({"name": "Mine", "steps": []},), {})]


def test_post_rejected_definition_surfaces_error_without_id():
    """A Planner rejection (ValueError) propagates so no id is returned (Req 1.4)."""
    runtime = FakeRuntime()
    runtime.create_error = ValueError("cycle detected involving steps: a, b")
    with pytest.raises(ValueError):
        _dispatch("POST", "/api/v1/workflows", body={"steps": []}, runtime=runtime)
    # create was attempted but no workflow id was produced/returned
    assert runtime.calls == [("create_workflow", ({"steps": []},), {})]


def test_validate_does_not_persist():
    handler, runtime = _dispatch(
        "POST", "/api/v1/workflows/validate", body={"steps": []}
    )
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"valid": True, "problems": []}
    assert runtime.calls == [("validate_workflow", ({"steps": []},), {})]
    # validation never creates/persists a definition
    assert not any(name == "create_workflow" for name, *_ in runtime.calls)


def test_get_lists_workflows():
    handler, runtime = _dispatch("GET", "/api/v1/workflows")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"workflows": [{"id": "wf-1", "name": "Mine"}]}
    assert runtime.calls == [("list_workflows", (), {})]


def test_get_workflow_singleton():
    handler, runtime = _dispatch("GET", "/api/v1/workflows/wf-1")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"workflow": {"id": "wf-1", "name": "Mine"}}
    assert runtime.calls == [("get_workflow", ("wf-1",), {})]


def test_get_unknown_workflow_raises_keyerror():
    runtime = FakeRuntime()
    runtime.workflow = None
    with pytest.raises(KeyError):
        _dispatch("GET", "/api/v1/workflows/nope", runtime=runtime)


# ---------------------------------------------------------------------------
# Templates (Requirement 20.2)
# ---------------------------------------------------------------------------


def test_get_lists_templates():
    handler, runtime = _dispatch("GET", "/api/v1/workflows/templates")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "workflowTemplates": [{"id": "tmpl-1", "name": "Daily report"}]
    }
    assert runtime.calls == [("list_workflow_templates", (), {})]


def test_get_single_template():
    handler, runtime = _dispatch("GET", "/api/v1/workflows/templates/tmpl-1")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "workflowTemplate": {"id": "tmpl-1", "name": "Daily report"}
    }
    assert runtime.calls == [("get_workflow_template", ("tmpl-1",), {})]


def test_get_unknown_template_raises_keyerror():
    runtime = FakeRuntime()
    runtime.template = None
    with pytest.raises(KeyError):
        _dispatch("GET", "/api/v1/workflows/templates/missing", runtime=runtime)


def test_post_instantiates_template():
    handler, runtime = _dispatch(
        "POST", "/api/v1/workflows/templates/tmpl-1", body={"name": "From template"}
    )
    assert handler.status == HTTPStatus.CREATED
    assert handler.body == {"workflow": {"id": "wf-from-tmpl", "templateId": "tmpl-1"}}
    assert runtime.calls == [
        ("instantiate_workflow_template", ("tmpl-1", {"name": "From template"}), {})
    ]


# ---------------------------------------------------------------------------
# Runs: start / list (Requirements 3.1, 20.1)
# ---------------------------------------------------------------------------


def test_post_starts_run():
    handler, runtime = _dispatch(
        "POST", "/api/v1/workflows/wf-1/runs", body={"inputs": {"x": 1}}
    )
    assert handler.status == HTTPStatus.ACCEPTED
    assert handler.body == {"run": {"id": "run-1", "state": "pending"}}
    assert runtime.calls == [
        ("start_workflow_run", ("wf-1", {"inputs": {"x": 1}}), {})
    ]


def test_get_lists_runs_for_workflow():
    handler, runtime = _dispatch("GET", "/api/v1/workflows/wf-1/runs")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"runs": [{"id": "run-1", "state": "pending"}]}
    assert runtime.calls == [("list_workflow_runs", ("wf-1",), {})]


def test_unknown_workflow_action_raises_keyerror():
    runtime = FakeRuntime()
    with pytest.raises(KeyError):
        _dispatch("POST", "/api/v1/workflows/wf-1/bogus", runtime=runtime)


# ---------------------------------------------------------------------------
# Run observation / cancel / retry (Requirements 4.5, 4.2, 4.4)
# ---------------------------------------------------------------------------


def test_get_observes_run():
    handler, runtime = _dispatch("GET", "/api/v1/workflow-runs/run-1")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {
        "run": {"id": "run-1", "state": "running"},
        "steps": [{"step_id": "s1", "state": "completed"}],
        "events": [{"type": "run.created"}],
    }
    assert runtime.calls == [("get_workflow_run", ("run-1",), {})]


def test_post_cancels_run():
    handler, runtime = _dispatch("POST", "/api/v1/workflow-runs/run-1/cancel")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"run": {"id": "run-1", "state": "cancelled"}}
    assert runtime.calls == [("cancel_workflow_run", ("run-1",), {})]


def test_post_retries_run():
    handler, runtime = _dispatch("POST", "/api/v1/workflow-runs/run-1/retry")
    assert handler.status == HTTPStatus.OK
    assert handler.body == {"run": {"id": "run-1", "state": "running"}}
    assert runtime.calls == [("retry_workflow_run", ("run-1",), {})]


def test_unknown_run_action_raises_keyerror():
    runtime = FakeRuntime()
    with pytest.raises(KeyError):
        _dispatch("POST", "/api/v1/workflow-runs/run-1/bogus", runtime=runtime)


def test_observe_rejects_post_method():
    from cp.http_api import MethodNotAllowedError

    runtime = FakeRuntime()
    with pytest.raises(MethodNotAllowedError):
        _dispatch("POST", "/api/v1/workflow-runs/run-1", runtime=runtime)


def test_cancel_rejects_get_method():
    from cp.http_api import MethodNotAllowedError

    runtime = FakeRuntime()
    with pytest.raises(MethodNotAllowedError):
        _dispatch("GET", "/api/v1/workflow-runs/run-1/cancel", runtime=runtime)
