"""Property-based test for sandbox grant/toolset scoping.

# Feature: orchestration-engine-completion, Property 39: Sandboxes receive only the run's configured toolset and grants

Property 39 states that *for any* Workflow_Run configuration, a Sandbox is
granted exactly the toolset and secret grants configured for that run and
nothing more (Requirement 16.4).

This test drives :meth:`core.code_executor.CodeExecutor.execute` over randomly
generated ``toolsets`` lists and ``secret_grants`` (:class:`GrantContext`)
lists, captures the policy actually dispatched to the (faked) Kernel-managed
Sandbox execution manager, and asserts:

* the dispatched policy's ``toolsets`` equals *exactly* the configured toolsets
  (same elements, same order) and nothing more;
* the dispatched policy's ``secret_grants`` equals *exactly* the configured
  grants serialized as ``grant_id`` + ``session_ref`` reference dicts and
  nothing more — no extra toolset or grant appears; and
* no raw secret value appears anywhere in the policy. ``GrantContext`` carries
  only opaque references, so the raw secret value associated with each grant
  (deliberately kept out of the ``GrantContext``) must never surface in the
  policy handed to the sandbox.

**Validates: Requirements 16.4**
"""

from __future__ import annotations

import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.code_executor import CodeExecutor, ScriptRequest
from core.orchestration_types import GrantContext, RunScope


class _RecordingExecutionManager:
    """A minimal sandbox execution manager that records the dispatched policy.

    Replays a single terminal exit line so ``execute`` completes normally; the
    test only inspects the ``policy`` captured at ``dispatch_job`` time.
    """

    def __init__(self) -> None:
        self.dispatched_policy: dict | None = None

    def dispatch_job(self, spec, policy) -> str:
        self.dispatched_policy = policy
        return "job-1"

    def stream_logs(self, job_id):
        yield {"stream": "exit", "line": "0"}

    def teardown(self, job_id) -> None:  # pragma: no cover - not exercised here
        pass


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Identifier-like tokens for toolset names and grant references. Kept short and
# printable so they exercise realistic configuration values.
_tokens = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=12,
)

# Toolsets are an ordered list (duplicates allowed) — the executor must pass
# them through verbatim, preserving order and multiplicity.
_toolsets = st.lists(_tokens, max_size=8)


@st.composite
def _grants_with_secrets(draw: st.DrawFn) -> tuple[list[GrantContext], list[str]]:
    """Generate random grants plus a distinct raw secret value per grant.

    The raw secret values are intentionally NOT placed inside the
    ``GrantContext`` (which only references a grant by id/session). They are
    returned alongside so the test can assert none of them leak into the policy.
    """
    count = draw(st.integers(min_value=0, max_value=8))
    grants: list[GrantContext] = []
    secrets: list[str] = []
    for i in range(count):
        grant_id = draw(_tokens)
        session_ref = draw(_tokens)
        # A unique, recognizable raw secret bound to this grant out-of-band.
        raw_secret = f"RAW_SECRET_{i}_{draw(_tokens)}"
        grants.append(GrantContext(grant_id=grant_id, session_ref=session_ref))
        secrets.append(raw_secret)
    return grants, secrets


# ---------------------------------------------------------------------------
# Property 39: Sandboxes receive only the run's configured toolset and grants
# ---------------------------------------------------------------------------


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    toolsets=_toolsets,
    grants_and_secrets=_grants_with_secrets(),
)
def test_sandbox_receives_only_configured_toolset_and_grants(
    toolsets: list[str],
    grants_and_secrets: tuple[list[GrantContext], list[str]],
) -> None:
    """The dispatched sandbox policy carries exactly the run's configured
    toolsets and grant references and nothing more, and never a raw secret."""
    grants, raw_secrets = grants_and_secrets

    manager = _RecordingExecutionManager()
    executor = CodeExecutor(manager)
    run_scope = RunScope(run_id="run-123", definition_id="def-456")

    executor.execute(
        ScriptRequest(command=["./run"]),
        run_scope,
        toolsets=toolsets,
        secret_grants=grants,
    )

    policy = manager.dispatched_policy
    assert policy is not None

    # Toolsets: exactly the configured list, same elements and order, no more.
    assert policy["toolsets"] == list(toolsets)

    # Secret grants: exactly the configured grants, each as a grant_id +
    # session_ref reference dict — nothing extra, nothing missing.
    expected_grants = [
        {"grant_id": g.grant_id, "session_ref": g.session_ref} for g in grants
    ]
    assert policy["secret_grants"] == expected_grants

    # Each serialized grant exposes ONLY the two reference keys — no field that
    # could smuggle a raw secret value.
    for serialized in policy["secret_grants"]:
        assert set(serialized.keys()) == {"grant_id", "session_ref"}

    # No raw secret value bound to any grant appears anywhere in the policy.
    policy_blob = json.dumps(policy, sort_keys=True)
    for raw_secret in raw_secrets:
        assert raw_secret not in policy_blob
