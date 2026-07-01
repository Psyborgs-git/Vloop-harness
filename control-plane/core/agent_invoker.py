"""Agent invocation execution — DSPy runner, event hooks, and output parsing."""

from __future__ import annotations

import ast
import importlib
import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable

from core.helpers import now_iso, to_json
from core.orchestration_types import ModelRequest, RoutingPolicy, RunScope

if TYPE_CHECKING:
    from core.inference_gateway import InferenceGateway
    from core.provider_service import ProviderService

    from core.database import DatabaseBackend


def execute_invocation(
    invocation_id: str,
    agent: dict[str, Any],
    provider: dict[str, Any],
    inputs: dict[str, Any],
    overrides: dict[str, Any],
    *,
    providers: ProviderService,
    state: DatabaseBackend,
    append_event: AppendEventFn,
    gateway: "InferenceGateway | None" = None,
) -> None:
    """Run a DSPy agent invocation in a background thread.

    Updates the invocation row through each stage and posts events.

    When an :class:`~core.inference_gateway.InferenceGateway` is supplied, the
    model call is routed through :meth:`InferenceGateway.call` so the gateway's
    policy layer (routing, budgets, rate limits, prompt cache, retries, and
    fallback) wraps the real DSPy/``build_lm`` execution (Req 6.1). The
    per-invocation DSPy execution is passed to the gateway as the provider call,
    so no orphaned direct provider call remains. When no gateway is supplied the
    invocation runs the DSPy program directly, preserving the original behavior.
    Invocation and usage recording is unchanged in both paths (Req 5.4).
    """
    trace_id = str(uuid.uuid4())
    started_at = now_iso()
    started_at_ms = int(time.time() * 1000)
    resolved_model = str(
        overrides.get("model")
        or agent.get("modelOverride")
        or provider.get("defaultModel")
        or ""
    ).strip()
    temperature_source = (
        overrides["temperature"]
        if overrides.get("temperature") is not None
        else agent["temperature"]
    )
    token_source = (
        overrides["maxTokens"]
        if overrides.get("maxTokens") is not None
        else agent["maxTokens"]
    )
    resolved_temperature = float(temperature_source)
    resolved_max_tokens = int(token_source)
    resolved_config = {
        "providerId": provider["id"],
        "model": resolved_model,
        "temperature": resolved_temperature,
        "maxTokens": resolved_max_tokens,
        "reasoningMode": agent["reasoningMode"],
        "outputMode": agent["outputMode"],
    }

    state.execute(
        "UPDATE invocations SET status = ?, started_at = ?, resolved_model = ?, resolved_config_json = ? WHERE id = ?",
        (
            "running",
            started_at,
            resolved_model,
            to_json(resolved_config),
            invocation_id,
        ),
    )
    append_event(
        invocation_id,
        "started",
        "Invocation started",
        resolved_config,
        trace_id=trace_id,
    )

    request_text = _build_request_text(agent, inputs)

    def _run_model_call(
        resolved_provider_id: str,
    ) -> tuple[str, dict[str, Any] | None, str | None, dict[str, Any] | None]:
        """Build the LM and run the DSPy program for ``resolved_provider_id``.

        This is the real provider invocation. It is shared by both the direct
        path and the gateway-routed path so the model call is identical whether
        or not a gateway wraps it with policy.
        """
        lm = providers.build_lm(
            resolved_provider_id,
            model_override=resolved_model,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
        )
        append_event(
            invocation_id,
            "provider_resolved",
            "Provider and model resolved",
            {"providerName": provider["name"], "model": resolved_model},
            started_at_ms=started_at_ms,
            trace_id=trace_id,
        )

        append_event(
            invocation_id,
            "validated",
            "Structured request compiled for DSPy",
            {"inputCount": len(inputs)},
            started_at_ms=started_at_ms,
            trace_id=trace_id,
        )

        lm_call_started_ms = int(time.time() * 1000)
        append_event(
            invocation_id,
            "lm_call_started",
            "DSPy LM call started",
            {},
            started_at_ms=started_at_ms,
            trace_id=trace_id,
        )

        result = _run_dspy_program(agent, lm, request_text)

        lm_call_finished_ms = int(time.time() * 1000)
        append_event(
            invocation_id,
            "lm_call_finished",
            "DSPy LM call finished",
            {"lmCallDurationMs": lm_call_finished_ms - lm_call_started_ms},
            started_at_ms=started_at_ms,
            trace_id=trace_id,
        )
        return result

    try:
        if gateway is not None:
            output_text, output_json, reasoning_text, usage = _invoke_via_gateway(
                gateway,
                provider_id=provider["id"],
                agent_id=str(agent["id"]),
                resolved_model=resolved_model,
                request_text=request_text,
                run_model_call=_run_model_call,
            )
        else:
            output_text, output_json, reasoning_text, usage = _run_model_call(
                provider["id"]
            )

        if usage:
            state.execute(
                "INSERT OR REPLACE INTO usage_logs (invocation_id, phase, prompt_tokens, completion_tokens, total_tokens, model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    invocation_id,
                    "lm_call",
                    int(usage.get("prompt_tokens") or 0),
                    int(usage.get("completion_tokens") or 0),
                    int(usage.get("total_tokens") or 0),
                    usage.get("model"),
                    now_iso(),
                ),
            )

        finished_at = now_iso()
        state.execute(
            "UPDATE invocations SET status = ?, output_text = ?, output_json = ?, reasoning_text = ?, usage_json = ?, finished_at = ?, error_code = NULL, error_message = NULL WHERE id = ?",
            (
                "succeeded",
                output_text,
                to_json(output_json) if output_json is not None else None,
                reasoning_text,
                to_json(usage) if usage is not None else None,
                finished_at,
                invocation_id,
            ),
        )
        append_event(
            invocation_id,
            "completed",
            "Agent invocation completed",
            {"hasReasoning": bool(reasoning_text)},
            started_at_ms=started_at_ms,
            trace_id=trace_id,
        )
    except Exception as exc:
        finished_at = now_iso()
        state.execute(
            "UPDATE invocations SET status = ?, error_code = ?, error_message = ?, finished_at = ? WHERE id = ?",
            (
                "failed",
                exc.__class__.__name__,
                str(exc),
                finished_at,
                invocation_id,
            ),
        )
        append_event(
            invocation_id,
            "failed",
            "Agent invocation failed",
            {"error": str(exc), "errorCode": exc.__class__.__name__},
            started_at_ms=started_at_ms,
            trace_id=trace_id,
        )


def _invoke_via_gateway(
    gateway: "InferenceGateway",
    *,
    provider_id: str,
    agent_id: str,
    resolved_model: str,
    request_text: str,
    run_model_call: Callable[
        [str], tuple[str, dict[str, Any] | None, str | None, dict[str, Any] | None]
    ],
) -> tuple[str, dict[str, Any] | None, str | None, dict[str, Any] | None]:
    """Route an agent model call through :meth:`InferenceGateway.call`.

    Wraps the per-invocation DSPy execution (``run_model_call``) in a
    :data:`~core.inference_gateway.ProviderCall` and hands it to the gateway so
    routing, budgets, rate limits, prompt cache, retries, and fallback apply
    around the real provider call (Req 6.1). The DSPy program's structured
    outputs are carried back on :attr:`ModelResponse.raw` so invocation and
    usage recording in :func:`execute_invocation` is unchanged (Req 5.4).

    Ad-hoc agent invocations have no Workflow_Run, so a synthetic
    :class:`RunScope` (no budget) and a single-provider routing policy are used;
    the gateway therefore routes to the agent's configured provider while still
    applying its policy pipeline.
    """
    # Import here to avoid a module-level import cycle and to keep the direct
    # (no-gateway) path free of the gateway's import cost.
    from core.inference_gateway import ModelResponse

    def _provider_call(
        routed_provider_id: str,
        _request: ModelRequest,
        _scope: RunScope,
        **_kwargs: Any,
    ) -> ModelResponse:
        output_text, output_json, reasoning_text, usage = run_model_call(
            routed_provider_id
        )
        token_usage = int(usage.get("total_tokens") or 0) if usage else None
        return ModelResponse(
            text=output_text,
            provider_id=routed_provider_id,
            model=resolved_model,
            token_usage=token_usage,
            raw=(output_text, output_json, reasoning_text, usage),
        )

    request = ModelRequest(
        messages=[{"role": "user", "content": request_text}],
        model_hint=resolved_model or None,
    )
    scope = RunScope(run_id=invocation_scope_id(provider_id, agent_id), definition_id=agent_id)
    policy = RoutingPolicy(
        preference="cost", fallback_order=[provider_id], max_retries=0
    )

    response = gateway.call(
        request, scope, policy=policy, provider_call=_provider_call
    )
    return response.raw


def invocation_scope_id(provider_id: str, agent_id: str) -> str:
    """Build a stable RunScope id for an ad-hoc (non-workflow) agent invocation."""
    return f"agent:{agent_id}:{provider_id}"


def _run_dspy_program(
    agent: dict[str, Any], lm: Any, request_text: str
) -> tuple[str, dict[str, Any] | None, str | None, dict[str, Any] | None]:
    """Execute a DSPy module against the given LM and return structured output."""
    dspy = importlib.import_module("dspy")
    output_field_name = str(agent.get("outputFieldName") or "response")
    signature = f"request -> {output_field_name}"
    module = (
        dspy.ChainOfThought(signature)
        if agent["reasoningMode"] == "chain_of_thought"
        else dspy.Predict(signature)
    )
    module.set_lm(lm)
    result = module(request=request_text)

    field_value = getattr(result, output_field_name, "")
    reasoning_text = str(getattr(result, "reasoning", "")).strip() or None
    output_json: dict[str, Any] | None = None
    if agent["outputMode"] == "json":
        if isinstance(field_value, dict):
            output_json = field_value
            response_text = json.dumps(output_json, ensure_ascii=False)
        else:
            response_text = str(field_value).strip()
            output_json = _parse_json_output(response_text)
            response_text = json.dumps(output_json, ensure_ascii=False)
    else:
        response_text = str(field_value).strip()

    usage: dict[str, Any] | None = None
    history = getattr(lm, "history", None)
    if history:
        latest = history[-1]
        if isinstance(latest, dict):
            raw_usage = latest.get("usage") or {}
            usage = {
                "prompt_tokens": raw_usage.get(
                    "prompt_tokens", raw_usage.get("input_tokens", 0)
                ),
                "completion_tokens": raw_usage.get(
                    "completion_tokens", raw_usage.get("output_tokens", 0)
                ),
                "total_tokens": raw_usage.get("total_tokens", 0),
                "model": latest.get("model") or raw_usage.get("model"),
            }
            if usage.get("model") is None:
                usage["model"] = getattr(lm, "model", None) or getattr(
                    lm, "model_name", None
                )
            if latest.get("prompt"):
                usage["_raw_prompt"] = latest["prompt"]
            if latest.get("response"):
                usage["_raw_response"] = latest["response"]

    return response_text, output_json, reasoning_text, usage


def _parse_json_output(response_text: str) -> dict[str, Any]:
    """Attempt to parse a model response as JSON, with markdown-fence cleaning."""
    candidate = response_text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(candidate)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(
                "agent was configured for JSON output, but the model response was not valid JSON"
            ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON-output agents must return an object at the top level")
    return parsed


def _build_request_text(agent: dict[str, Any], inputs: dict[str, Any]) -> str:
    """Assemble a structured prompt from agent instructions and input fields."""
    sections = [agent["instructions"].strip(), "", "Structured inputs:"]
    for field in agent["inputFields"]:
        label = field["label"]
        value = str(inputs.get(field["name"], "")).strip()
        sections.append(f"- {label} ({field['name']}): {value or '(not provided)'}")
        if field.get("description"):
            sections.append(f"  Guidance: {field['description']}")

    sections.extend(
        [
            "",
            f"Return the final answer in the `{agent['outputFieldName']}` field.",
        ]
    )

    if agent["outputMode"] == "json" and agent.get("outputSchema"):
        sections.extend(
            [
                "",
                "Return valid JSON only. Do not wrap it in markdown fences.",
                "JSON shape guidance:",
                json.dumps(agent["outputSchema"], ensure_ascii=False, indent=2),
            ]
        )

    return "\n".join(sections).strip()


# Type alias for the event-append callback
AppendEventFn = Any


def append_event(
    state: DatabaseBackend,
    invocation_id: str,
    event_type: str,
    message: str,
    payload: dict[str, Any],
    *,
    started_at_ms: int | None = None,
    trace_id: str | None = None,
) -> None:
    """Persist an invocation lifecycle event."""
    now_ms = int(time.time() * 1000)
    existing = state.fetch_one(
        "SELECT COALESCE(MAX(seq), 0) AS seq FROM invocation_events WHERE invocation_id = ?",
        (invocation_id,),
    )
    next_seq = int(existing["seq"]) + 1 if existing else 1
    elapsed_ms = None
    if started_at_ms is not None:
        elapsed_ms = now_ms - started_at_ms
    if trace_id:
        payload = {**payload, "traceId": trace_id}
    state.execute(
        "INSERT INTO invocation_events (invocation_id, seq, type, message, payload_json, elapsed_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            invocation_id,
            next_seq,
            event_type,
            message,
            to_json(payload),
            elapsed_ms,
            now_iso(),
        ),
    )
