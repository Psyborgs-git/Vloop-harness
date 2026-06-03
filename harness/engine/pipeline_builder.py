"""PipelineBuilder — assembles and executes chains of DSPy modules and tool steps.

A *pipeline* is an ordered list of steps.  Each step has a ``"type"`` key:

Component step (backward-compat default when ``"type"`` absent)::

    {
        "type": "component",
        "component_id": "comp_abc",
        "config": {"input_map": {}}
    }

Tool step::

    {
        "type": "tool",
        "tool_name": "terminal",
        "config": {
            "command": "pytest {test_path}",
            "cwd_relative": ".",
            "timeout": 60,
            "input_map": {"test_path": "file_path"}
        }
    }

The output of every step is merged into a running ``result`` dict so later
steps can reference fields by name regardless of which step produced them.
"""

from __future__ import annotations

import asyncio
import functools
import re
from typing import TYPE_CHECKING, Any

import dspy

if TYPE_CHECKING:
    from harness.data.models import PipelineDef
    from harness.engine.component_registry import DSPyComponentRegistry
    from harness.tools.registry import ToolRegistry


class PipelineRunError(RuntimeError):
    """Raised when a pipeline step fails."""


class PipelinePausedForConfirmation(Exception):
    """Raised when a tool step requires human confirmation before proceeding.

    Attributes
    ----------
    token : str
        Confirmation token the client must echo back.
    description : str
        Human-readable description of the pending action.
    risk_level : str
        "caution" | "destructive"
    step_index : int
        Which step in the pipeline triggered the pause.
    """

    def __init__(
        self,
        token: str,
        description: str,
        risk_level: str,
        step_index: int,
    ) -> None:
        super().__init__(description)
        self.token = token
        self.description = description
        self.risk_level = risk_level
        self.step_index = step_index


def _apply_input_map(
    input_map: dict[str, Any],
    accumulated: dict[str, Any],
) -> dict[str, Any]:
    """Resolve input_map entries against the accumulated result dict."""
    resolved: dict[str, Any] = {}
    for target_field, source in input_map.items():
        if isinstance(source, str) and source in accumulated:
            resolved[target_field] = accumulated[source]
        else:
            resolved[target_field] = source  # literal
    return resolved


def _interpolate_params(params: dict[str, Any], accumulated: dict[str, Any]) -> dict[str, Any]:
    """String-interpolate ``{field}`` placeholders in string param values."""
    out: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str):
            def _replace(m: re.Match[str]) -> str:
                return str(accumulated.get(m.group(1), m.group(0)))
            out[k] = re.sub(r"\{(\w+)\}", _replace, v)
        else:
            out[k] = v
    return out


class VLoopPipeline(dspy.Module):
    """A runtime chain of DSPy modules (and tool steps) built from a ``PipelineDef``."""

    def __init__(
        self,
        modules: list[dspy.Module | None],
        step_configs: list[dict[str, Any]],
        step_ids: list[str],
        step_types: list[str],
        tool_names: list[str | None],
        tool_registry: ToolRegistry | None,
    ) -> None:
        self.modules = modules
        self.step_configs = step_configs
        self.step_ids = step_ids
        self.step_types = step_types
        self.tool_names = tool_names
        self.tool_registry = tool_registry

    def forward(self, **kwargs: Any) -> dspy.Prediction:
        """Execute all *component* steps synchronously.

        Tool steps cannot be executed from ``forward()`` because they are async.
        Use ``run_async`` instead for pipelines that contain tool steps.
        """
        if any(t == "tool" for t in self.step_types):
            raise RuntimeError(
                "Pipeline contains tool steps; use build_and_run() "
                "(async) instead of calling the pipeline directly."
            )
        return self._run_component_steps(**kwargs)

    def _run_component_steps(self, **kwargs: Any) -> dspy.Prediction:
        result: dict[str, Any] = dict(kwargs)
        step_results: list[dict[str, Any]] = []

        for module, config, step_id in zip(self.modules, self.step_configs, self.step_ids, strict=False):
            input_map: dict[str, Any] = config.get("input_map", {})
            inputs = _apply_input_map(input_map, result)
            # Pass through accumulated fields not already mapped
            for key, val in result.items():
                if key not in inputs:
                    inputs[key] = val

            try:
                output = module(**inputs)  # type: ignore[operator]
                output_dict: dict[str, Any] = {}
                if hasattr(output, "toDict"):
                    output_dict = output.toDict()
                elif hasattr(output, "__dict__"):
                    output_dict = {
                        k: v for k, v in output.__dict__.items() if not k.startswith("_")
                    }
                result = {**result, **output_dict}
                step_results.append({"step_id": step_id, "outputs": output_dict})
            except Exception as exc:
                step_results.append({"step_id": step_id, "error": str(exc)})
                raise PipelineRunError(f"Pipeline step {step_id!r} failed: {exc}") from exc

        return dspy.Prediction(step_results=step_results, **result)

    async def run_async(self, **kwargs: Any) -> dspy.Prediction:
        """Execute the pipeline asynchronously, supporting both component and tool steps."""
        from harness.tools.exceptions import ConfirmationRequired

        result: dict[str, Any] = dict(kwargs)
        step_results: list[dict[str, Any]] = []

        for idx, (module, config, step_id, step_type, tool_name) in enumerate(
            zip(
                self.modules,
                self.step_configs,
                self.step_ids,
                self.step_types,
                self.tool_names, strict=False,
            )
        ):
            input_map: dict[str, Any] = config.get("input_map", {})
            inputs = _apply_input_map(input_map, result)
            for key, val in result.items():
                if key not in inputs:
                    inputs[key] = val

            if step_type == "tool":
                # Build tool params from config (minus input_map) + resolved inputs
                tool_params = {k: v for k, v in config.items() if k != "input_map"}
                tool_params = _interpolate_params(tool_params, result)
                tool_params.update(inputs)

                if self.tool_registry is None:
                    raise PipelineRunError(
                        f"Tool step {step_id!r} requires a ToolRegistry but none was provided."
                    )
                try:
                    tool_result = await self.tool_registry.execute(
                        tool_name=tool_name or "",
                        component_id=None,
                        session_id=None,
                        params=tool_params,
                    )
                except ConfirmationRequired as exc:
                    raise PipelinePausedForConfirmation(
                        token=exc.token,
                        description=exc.description,
                        risk_level=exc.risk_level,
                        step_index=idx,
                    ) from exc
                except Exception as exc:
                    step_results.append({"step_id": step_id, "error": str(exc)})
                    raise PipelineRunError(
                        f"Tool step {step_id!r} failed: {exc}"
                    ) from exc

                output_dict = tool_result.to_dict()
                result = {**result, **output_dict}
                step_results.append({"step_id": step_id, "outputs": output_dict})

            else:
                # Component step — run in thread pool
                loop = asyncio.get_running_loop()
                fn = functools.partial(module, **inputs)  # type: ignore[operator]
                try:
                    output = await loop.run_in_executor(None, fn)
                    output_dict = {}
                    if hasattr(output, "toDict"):
                        output_dict = output.toDict()
                    elif hasattr(output, "__dict__"):
                        output_dict = {
                            k: v for k, v in output.__dict__.items() if not k.startswith("_")
                        }
                    result = {**result, **output_dict}
                    step_results.append({"step_id": step_id, "outputs": output_dict})
                except Exception as exc:
                    step_results.append({"step_id": step_id, "error": str(exc)})
                    raise PipelineRunError(
                        f"Pipeline step {step_id!r} failed: {exc}"
                    ) from exc

        return dspy.Prediction(step_results=step_results, **result)


class PipelineBuilder:
    """Builds executable ``VLoopPipeline`` instances from ``PipelineDef`` objects."""

    def __init__(
        self,
        registry: DSPyComponentRegistry,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.tool_registry = tool_registry

    def build(self, pipeline_def: PipelineDef) -> VLoopPipeline:
        """Compile and assemble all pipeline steps."""
        modules: list[dspy.Module | None] = []
        step_configs: list[dict[str, Any]] = []
        step_ids: list[str] = []
        step_types: list[str] = []
        tool_names: list[str | None] = []

        for step in pipeline_def.steps:
            step_type = step.get("type", "component")

            if step_type == "tool":
                tool_name = step.get("tool_name", "")
                config = step.get("config", {})
                modules.append(None)
                step_configs.append(config)
                step_ids.append(tool_name or f"tool_{len(step_ids)}")
                step_types.append("tool")
                tool_names.append(tool_name)

            else:
                # component step (default)
                component_id: str = step.get("component_id", step.get("component_id", ""))
                config = step.get("config", {})
                module = self.registry.instantiate(component_id)
                if module is None:
                    raise ValueError(
                        f"Component {component_id!r} is not loaded in the registry. "
                        "Load or compile it before building the pipeline."
                    )
                modules.append(module)
                step_configs.append(config)
                step_ids.append(component_id)
                step_types.append("component")
                tool_names.append(None)

        return VLoopPipeline(
            modules, step_configs, step_ids, step_types, tool_names, self.tool_registry
        )

    async def build_and_run(
        self, pipeline_def: PipelineDef, inputs: dict[str, Any]
    ) -> dspy.Prediction:
        """Build the pipeline and execute it asynchronously."""
        pipeline = self.build(pipeline_def)
        return await pipeline.run_async(**inputs)
