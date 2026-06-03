"""Built-in pipeline templates — RAG, MapReduce, AgentLoop, Reflection, Sequential."""

from __future__ import annotations

from typing import Any

import dspy

from harness.engine.pipelines.base import (
    Condition,
    NodeType,
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
)
from harness.engine.pipelines.executor import ExecutionContext, PipelineExecutor


class SequentialPipeline:
    """Simple linear pipeline: input → [steps] → output."""

    def __init__(self, name: str = "sequential") -> None:
        self.name = name
        self._steps: list[tuple[str, dict[str, Any]]] = []

    def add_step(self, step_name: str, config: dict[str, Any]) -> "SequentialPipeline":
        self._steps.append((step_name, config))
        return self

    def build(self) -> PipelineGraph:
        graph = PipelineGraph(name=self.name)
        input_id = graph.add_node(NodeType.INPUT, name="input")
        prev = input_id
        for step_name, config in self._steps:
            node_id = graph.add_node(
                NodeType.COMPONENT,
                name=step_name,
                config=config,
            )
            graph.add_edge(prev, node_id)
            prev = node_id
        output_id = graph.add_node(NodeType.OUTPUT, name="output")
        graph.add_edge(prev, output_id)
        return graph


class RAGPipeline:
    """Retrieval-Augmented Generation pipeline.

    Flow: input → retrieve → generate → output
    """

    def __init__(
        self,
        retriever: dspy.Module,
        generator: dspy.Module,
        name: str = "rag",
    ) -> None:
        self.name = name
        self.retriever = retriever
        self.generator = generator

    def build(self) -> PipelineGraph:
        graph = PipelineGraph(name=self.name)
        input_id = graph.add_node(NodeType.INPUT, name="input")

        retrieve_id = graph.add_node(
            NodeType.COMPONENT,
            name="retrieve",
            config={"module": self.retriever, "inputs": {"query": "$query"}},
        )
        generate_id = graph.add_node(
            NodeType.COMPONENT,
            name="generate",
            config={
                "module": self.generator,
                "inputs": {
                    "question": "$query",
                    "documents": "$retrieved_documents",
                },
            },
        )
        output_id = graph.add_node(NodeType.OUTPUT, name="output")

        graph.add_edge(input_id, retrieve_id)
        graph.add_edge(retrieve_id, generate_id, input_map={"documents": "retrieved_documents"})
        graph.add_edge(generate_id, output_id)
        return graph


class MapReducePipeline:
    """Map-Reduce pipeline for processing collections in parallel.

    Flow: input → map (parallel) → reduce → output
    """

    def __init__(
        self,
        map_module: dspy.Module,
        reduce_module: dspy.Module | None = None,
        name: str = "map_reduce",
    ) -> None:
        self.name = name
        self.map_module = map_module
        self.reduce_module = reduce_module

    def build(self) -> PipelineGraph:
        graph = PipelineGraph(name=self.name)
        input_id = graph.add_node(NodeType.INPUT, name="input")

        # Map node uses the sub-graph pattern
        map_graph = PipelineGraph(name="map_sub")
        map_in = map_graph.add_node(NodeType.INPUT, name="map_input")
        map_proc = map_graph.add_node(
            NodeType.COMPONENT,
            name="map_processor",
            config={"module": self.map_module, "inputs": {"text": "$item"}},
        )
        map_out = map_graph.add_node(NodeType.OUTPUT, name="map_output")
        map_graph.add_edge(map_in, map_proc)
        map_graph.add_edge(map_proc, map_out)

        map_id = graph.add_node(
            NodeType.MAP,
            name="map",
            config={
                "sub_graph": map_graph,
                "collection_input": "items",
                "item_key": "item",
            },
        )

        reduce_id = graph.add_node(
            NodeType.REDUCE,
            name="reduce",
            config={
                "collection_input": "map_results",
                "reducer": self._default_reducer,
            },
        )
        output_id = graph.add_node(NodeType.OUTPUT, name="output")

        graph.add_edge(input_id, map_id)
        graph.add_edge(map_id, reduce_id)
        graph.add_edge(reduce_id, output_id)
        return graph

    @staticmethod
    def _default_reducer(items: list[Any]) -> str:
        """Default reducer concatenates outputs."""
        parts = []
        for item in items:
            if isinstance(item, dict):
                parts.append(str(item.get("output", item)))
            else:
                parts.append(str(item))
        return "\n\n".join(parts)


class AgentLoopPipeline:
    """Agent loop with reflection and continuation.

    Flow: input → think → act → observe → (continue|stop) → output
    """

    def __init__(
        self,
        think_module: dspy.Module,
        act_module: dspy.Module,
        observe_module: dspy.Module,
        should_continue: Condition | None = None,
        max_iterations: int = 5,
        name: str = "agent_loop",
    ) -> None:
        self.name = name
        self.think_module = think_module
        self.act_module = act_module
        self.observe_module = observe_module
        self.should_continue = should_continue or Condition(
            "should_continue",
            lambda ctx: ctx.get("should_continue", False) and ctx.get("iteration", 0) < max_iterations,
        )
        self.max_iterations = max_iterations

    def build(self) -> PipelineGraph:
        graph = PipelineGraph(name=self.name)
        input_id = graph.add_node(NodeType.INPUT, name="input")

        think_id = graph.add_node(
            NodeType.COMPONENT,
            name="think",
            config={"module": self.think_module, "inputs": {"goal": "$goal", "context": "$context"}},
        )
        act_id = graph.add_node(
            NodeType.COMPONENT,
            name="act",
            config={"module": self.act_module, "inputs": {"plan": "$plan"}},
        )
        observe_id = graph.add_node(
            NodeType.COMPONENT,
            name="observe",
            config={"module": self.observe_module, "inputs": {"action_result": "$action_result"}},
        )
        continue_check = graph.add_node(
            NodeType.CONDITION,
            name="continue_check",
            config={"condition": self.should_continue},
        )
        output_id = graph.add_node(NodeType.OUTPUT, name="output")

        graph.add_edge(input_id, think_id)
        graph.add_edge(think_id, act_id)
        graph.add_edge(act_id, observe_id)
        graph.add_edge(observe_id, continue_check)
        # Loop back to think if condition is true
        graph.add_edge(continue_check, think_id, condition=self.should_continue)
        # Exit to output if condition is false
        graph.add_edge(
            continue_check,
            output_id,
            condition=Condition("should_stop", lambda ctx: not self.should_continue.evaluate(ctx)),
        )
        return graph


class ReflectionPipeline:
    """Reflection pipeline: generate → critique → revise → output.

    Flow: input → generate → critique → revise → output
    """

    def __init__(
        self,
        generator: dspy.Module,
        critic: dspy.Module,
        reviser: dspy.Module,
        name: str = "reflection",
    ) -> None:
        self.name = name
        self.generator = generator
        self.critic = critic
        self.reviser = reviser

    def build(self) -> PipelineGraph:
        graph = PipelineGraph(name=self.name)
        input_id = graph.add_node(NodeType.INPUT, name="input")

        generate_id = graph.add_node(
            NodeType.COMPONENT,
            name="generate",
            config={
                "module": self.generator,
                "inputs": {"prompt": "$prompt", "context": "$context"},
            },
        )
        critique_id = graph.add_node(
            NodeType.COMPONENT,
            name="critique",
            config={
                "module": self.critic,
                "inputs": {"draft": "$output", "criteria": "$criteria"},
            },
        )
        revise_id = graph.add_node(
            NodeType.COMPONENT,
            name="revise",
            config={
                "module": self.reviser,
                "inputs": {"draft": "$output", "critique": "$critique"},
            },
        )
        output_id = graph.add_node(NodeType.OUTPUT, name="output")

        graph.add_edge(input_id, generate_id)
        graph.add_edge(generate_id, critique_id, input_map={"draft": "output"})
        graph.add_edge(critique_id, revise_id, input_map={"critique": "critique"})
        graph.add_edge(revise_id, output_id)
        return graph


# ── Utility: build and run in one call ──────────────────────────────────────

async def run_pipeline(
    graph: PipelineGraph,
    inputs: dict[str, Any],
    tool_registry: Any | None = None,
) -> ExecutionContext:
    """Convenience: validate, build executor, and run."""
    errors = graph.validate()
    if errors:
        raise ValueError(f"Pipeline validation failed: {errors}")
    executor = PipelineExecutor(graph)
    return await executor.run(inputs, tool_registry)
