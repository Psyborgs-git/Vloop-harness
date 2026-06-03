"""PipelineExecutor — async DAG executor with parallel step execution."""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass, field
from typing import Any

import dspy

from harness.engine.pipelines.base import (
    Condition,
    NodeType,
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
)


@dataclass
class StepResult:
    """Result of executing a single pipeline step."""

    node_id: str
    node_name: str
    success: bool
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "success": self.success,
            "outputs": self.outputs,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ExecutionContext:
    """Mutable execution state passed through the pipeline."""

    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    step_results: list[StepResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.outputs.get(key, self.inputs.get(key, default))

    def set(self, key: str, value: Any) -> None:
        self.outputs[key] = value


class PipelineExecutor:
    """Executes a PipelineGraph asynchronously with support for parallel branches."""

    def __init__(self, graph: PipelineGraph) -> None:
        self.graph = graph

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(
        self,
        initial_inputs: dict[str, Any],
        tool_registry: Any | None = None,
    ) -> ExecutionContext:
        """Execute the pipeline from INPUT to OUTPUT."""
        ctx = ExecutionContext(inputs=initial_inputs)
        visited: set[str] = set()
        queue: asyncio.Queue[str] = asyncio.Queue()

        input_node = self.graph.input_node
        if input_node is None:
            raise RuntimeError("Pipeline has no INPUT node")

        # Seed with input node
        await queue.put(input_node)

        while not queue.empty():
            node_id = await queue.get()
            if node_id in visited:
                continue
            visited.add(node_id)

            node = self.graph.get_node(node_id)
            if node is None:
                continue

            # Wait for all incoming edges to be visited (simple topo-like ordering)
            incoming = self.graph.incoming_edges(node_id)
            if any(e.source not in visited for e in incoming):
                # Re-queue for later
                await queue.put(node_id)
                continue

            result = await self._execute_node(node, ctx, tool_registry)
            ctx.step_results.append(result)

            if not result.success:
                # Stop on first failure unless configured otherwise
                break

            # Merge outputs into context
            for k, v in result.outputs.items():
                ctx.set(k, v)

            # Schedule outgoing edges
            outgoing = self.graph.outgoing_edges(node_id)
            for edge in outgoing:
                if edge.condition and not edge.condition.evaluate(ctx.outputs):
                    continue
                await queue.put(edge.target)

        return ctx

    # ── Node execution ──────────────────────────────────────────────────────

    async def _execute_node(
        self,
        node: PipelineNode,
        ctx: ExecutionContext,
        tool_registry: Any | None,
    ) -> StepResult:
        import time

        t0 = time.time()
        try:
            if node.type == NodeType.INPUT:
                outputs = dict(ctx.inputs)
            elif node.type == NodeType.COMPONENT:
                outputs = await self._run_component(node, ctx)
            elif node.type == NodeType.TOOL:
                outputs = await self._run_tool(node, ctx, tool_registry)
            elif node.type == NodeType.CONDITION:
                outputs = await self._run_condition(node, ctx)
            elif node.type == NodeType.LOOP:
                outputs = await self._run_loop(node, ctx, tool_registry)
            elif node.type == NodeType.MAP:
                outputs = await self._run_map(node, ctx, tool_registry)
            elif node.type == NodeType.REDUCE:
                outputs = await self._run_reduce(node, ctx)
            elif node.type == NodeType.OUTPUT:
                outputs = dict(ctx.outputs)
            else:
                outputs = {}

            duration_ms = int((time.time() - t0) * 1000)
            return StepResult(
                node_id=node.id,
                node_name=node.name,
                success=True,
                outputs=outputs,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            return StepResult(
                node_id=node.id,
                node_name=node.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
            )

    async def _run_component(self, node: PipelineNode, ctx: ExecutionContext) -> dict[str, Any]:
        module = node.config.get("module")
        if module is None:
            raise RuntimeError(f"Node {node.id} missing 'module' config")

        # Build inputs from context + input_map
        raw_inputs = node.config.get("inputs", {})
        inputs = self._resolve_inputs(raw_inputs, ctx)

        if isinstance(module, dspy.Module):
            loop = asyncio.get_running_loop()
            fn = functools.partial(module, **inputs)
            output = await loop.run_in_executor(None, fn)
        elif callable(module):
            loop = asyncio.get_running_loop()
            fn = functools.partial(module, **inputs)
            output = await loop.run_in_executor(None, fn)
        else:
            raise RuntimeError(f"Node {node.id} module is not callable")

        # Normalize output
        if hasattr(output, "toDict"):
            return output.toDict()
        if hasattr(output, "__dict__"):
            return {k: v for k, v in output.__dict__.items() if not k.startswith("_")}
        if isinstance(output, dict):
            return output
        return {"output": output}

    async def _run_tool(
        self,
        node: PipelineNode,
        ctx: ExecutionContext,
        tool_registry: Any | None,
    ) -> dict[str, Any]:
        if tool_registry is None:
            raise RuntimeError(f"Node {node.id} requires tool_registry but none provided")
        tool_name = node.config.get("tool_name")
        params = self._resolve_inputs(node.config.get("params", {}), ctx)
        result = await tool_registry.execute(
            tool_name=tool_name,
            component_id=None,
            session_id=None,
            params=params,
        )
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if isinstance(result, dict):
            return result
        return {"result": str(result)}

    async def _run_condition(self, node: PipelineNode, ctx: ExecutionContext) -> dict[str, Any]:
        condition = node.config.get("condition")
        if isinstance(condition, Condition):
            value = condition.evaluate(ctx.outputs)
        elif callable(condition):
            value = condition(ctx.outputs)
        else:
            raise RuntimeError(f"Node {node.id} missing valid condition")
        return {"condition_result": value}

    async def _run_loop(
        self,
        node: PipelineNode,
        ctx: ExecutionContext,
        tool_registry: Any | None,
    ) -> dict[str, Any]:
        collection = ctx.get(node.config.get("collection_input", "items"), [])
        item_key = node.config.get("item_key", "item")
        sub_graph: PipelineGraph | None = node.config.get("sub_graph")
        if sub_graph is None:
            raise RuntimeError(f"Node {node.id} LOOP missing 'sub_graph'")

        results = []
        for item in collection:
            sub_inputs = dict(ctx.inputs)
            sub_inputs[item_key] = item
            sub_inputs.update(ctx.outputs)
            sub_executor = PipelineExecutor(sub_graph)
            sub_ctx = await sub_executor.run(sub_inputs, tool_registry)
            results.append(sub_ctx.outputs)

        return {"loop_results": results}

    async def _run_map(
        self,
        node: PipelineNode,
        ctx: ExecutionContext,
        tool_registry: Any | None,
    ) -> dict[str, Any]:
        collection = ctx.get(node.config.get("collection_input", "items"), [])
        item_key = node.config.get("item_key", "item")
        sub_graph: PipelineGraph | None = node.config.get("sub_graph")
        if sub_graph is None:
            raise RuntimeError(f"Node {node.id} MAP missing 'sub_graph'")

        async def _run_one(item: Any) -> dict[str, Any]:
            sub_inputs = dict(ctx.inputs)
            sub_inputs[item_key] = item
            sub_inputs.update(ctx.outputs)
            sub_executor = PipelineExecutor(sub_graph)
            sub_ctx = await sub_executor.run(sub_inputs, tool_registry)
            return sub_ctx.outputs

        tasks = [_run_one(item) for item in collection]
        results = await asyncio.gather(*tasks)
        return {"map_results": results}

    async def _run_reduce(self, node: PipelineNode, ctx: ExecutionContext) -> dict[str, Any]:
        reducer = node.config.get("reducer")
        items = ctx.get(node.config.get("collection_input", "items"), [])
        if callable(reducer):
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, reducer, items)
            return {"reduced": result}
        return {"reduced": items}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_inputs(raw: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        """Resolve input references like {field} or ctx lookups."""
        resolved: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, str) and v.startswith("$"):
                resolved[k] = ctx.get(v[1:], v)
            else:
                resolved[k] = v
        return resolved
