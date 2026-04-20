"""PipelineBuilder — assembles and executes chains of DSPy modules.

A *pipeline* is an ordered list of steps.  Each step specifies:
  • ``component_id``  — which DSPy module to run
  • ``input_map``     — mapping from this step's input field names to either
                        a previous step's output field name (string) or a
                        literal value (any JSON-serialisable type)

The output of every step is merged into a running ``result`` dict so later
steps can reference fields by name regardless of which step produced them.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any

import dspy

if TYPE_CHECKING:
    from harness.data.models import PipelineDef
    from harness.engine.component_registry import DSPyComponentRegistry


class PipelineRunError(RuntimeError):
    """Raised when a pipeline step fails."""


class VLoopPipeline(dspy.Module):
    """A runtime chain of DSPy modules built from a ``PipelineDef``."""

    def __init__(
        self,
        modules: list[dspy.Module],
        step_configs: list[dict[str, Any]],
        step_ids: list[str],
    ) -> None:
        self.modules = modules
        self.step_configs = step_configs
        self.step_ids = step_ids

    def forward(self, **kwargs: Any) -> dspy.Prediction:
        """Execute all steps sequentially, passing accumulated outputs forward."""
        result: dict[str, Any] = dict(kwargs)
        step_results: list[dict[str, Any]] = []

        for module, config, step_id in zip(self.modules, self.step_configs, self.step_ids):
            input_map: dict[str, Any] = config.get("input_map", {})
            inputs: dict[str, Any] = {}

            # Apply explicit field mappings first
            for target_field, source in input_map.items():
                if isinstance(source, str) and source in result:
                    inputs[target_field] = result[source]
                else:
                    inputs[target_field] = source  # literal

            # Pass through any accumulated fields not already mapped
            for key, val in result.items():
                if key not in inputs:
                    inputs[key] = val

            try:
                output = module(**inputs)
                output_dict: dict[str, Any] = {}
                if hasattr(output, "toDict"):
                    output_dict = output.toDict()
                elif hasattr(output, "__dict__"):
                    output_dict = {
                        k: v
                        for k, v in output.__dict__.items()
                        if not k.startswith("_")
                    }
                result = {**result, **output_dict}
                step_results.append({"step_id": step_id, "outputs": output_dict})
            except Exception as exc:
                error_entry = {"step_id": step_id, "error": str(exc)}
                step_results.append(error_entry)
                raise PipelineRunError(
                    f"Pipeline step {step_id!r} failed: {exc}"
                ) from exc

        return dspy.Prediction(step_results=step_results, **result)


class PipelineBuilder:
    """Builds executable ``VLoopPipeline`` instances from ``PipelineDef`` objects."""

    def __init__(self, registry: "DSPyComponentRegistry") -> None:
        self.registry = registry

    def build(self, pipeline_def: "PipelineDef") -> VLoopPipeline:
        """Compile and assemble all pipeline steps.

        Raises ``ValueError`` if any component is not loaded in the registry.
        """
        modules: list[dspy.Module] = []
        step_configs: list[dict[str, Any]] = []
        step_ids: list[str] = []

        for step in pipeline_def.steps:
            component_id: str = step["component_id"]
            config: dict[str, Any] = step.get("config", {})

            module = self.registry.instantiate(component_id)
            if module is None:
                raise ValueError(
                    f"Component {component_id!r} is not loaded in the registry. "
                    "Load or compile it before building the pipeline."
                )
            modules.append(module)
            step_configs.append(config)
            step_ids.append(component_id)

        return VLoopPipeline(modules, step_configs, step_ids)

    async def build_and_run(
        self, pipeline_def: "PipelineDef", inputs: dict[str, Any]
    ) -> dspy.Prediction:
        """Build the pipeline and execute it asynchronously."""
        pipeline = self.build(pipeline_def)
        loop = asyncio.get_running_loop()
        fn = functools.partial(pipeline, **inputs)
        return await loop.run_in_executor(None, fn)
