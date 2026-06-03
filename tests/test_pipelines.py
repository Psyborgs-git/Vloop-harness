"""Tests for the DAG-based pipeline framework."""

from __future__ import annotations

import pytest

import dspy

from harness.engine.pipelines.base import (
    Condition,
    NodeType,
    PipelineGraph,
)
from harness.engine.pipelines.executor import PipelineExecutor
from harness.engine.pipelines.templates import (
    RAGPipeline,
    MapReducePipeline,
    ReflectionPipeline,
    SequentialPipeline,
    run_pipeline,
)


class TestPipelineGraph:
    def test_build_and_validate(self) -> None:
        graph = PipelineGraph(name="test")
        inp = graph.add_node(NodeType.INPUT, name="input")
        a = graph.add_node(NodeType.COMPONENT, name="a")
        out = graph.add_node(NodeType.OUTPUT, name="output")
        graph.add_edge(inp, a)
        graph.add_edge(a, out)
        errors = graph.validate()
        assert errors == []

    def test_missing_input_error(self) -> None:
        graph = PipelineGraph(name="bad")
        a = graph.add_node(NodeType.COMPONENT, name="a")
        out = graph.add_node(NodeType.OUTPUT, name="output")
        graph.add_edge(a, out)
        errors = graph.validate()
        assert "missing INPUT node" in " ".join(errors)

    def test_branching(self) -> None:
        graph = PipelineGraph(name="branch")
        inp = graph.add_node(NodeType.INPUT)
        cond = graph.add_node(NodeType.CONDITION, name="cond")
        a = graph.add_node(NodeType.COMPONENT, name="a")
        b = graph.add_node(NodeType.COMPONENT, name="b")
        out = graph.add_node(NodeType.OUTPUT)
        graph.add_edge(inp, cond)
        graph.branch(cond, [(a, Condition("true", lambda ctx: True)), (b, Condition("false", lambda ctx: False))])
        graph.add_edge(a, out)
        graph.add_edge(b, out)
        errors = graph.validate()
        assert errors == []


class TestSequentialPipeline:
    @pytest.mark.asyncio
    async def test_run(self) -> None:
        class Double(dspy.Module):
            def forward(self, x: int) -> dspy.Prediction:
                return dspy.Prediction(result=x * 2)

        pipeline = SequentialPipeline(name="double_pipeline")
        pipeline.add_step("double", {"module": Double(), "inputs": {"x": "$x"}})
        graph = pipeline.build()
        executor = PipelineExecutor(graph)
        ctx = await executor.run({"x": 5})
        assert any("result" in s.outputs and s.outputs["result"] == 10 for s in ctx.step_results if s.success)


class TestRAGPipeline:
    def test_build(self) -> None:
        class FakeRetriever(dspy.Module):
            def forward(self, query: str) -> dspy.Prediction:
                return dspy.Prediction(retrieved_documents="[]")

        class FakeGenerator(dspy.Module):
            def forward(self, question: str, documents: str) -> dspy.Prediction:
                return dspy.Prediction(answer="fake")

        pipeline = RAGPipeline(
            retriever=FakeRetriever(),
            generator=FakeGenerator(),
        )
        graph = pipeline.build()
        assert graph.input_node is not None
        assert graph.output_node is not None


class TestReflectionPipeline:
    def test_build(self) -> None:
        class Stub(dspy.Module):
            def forward(self, **kwargs: object) -> dspy.Prediction:
                return dspy.Prediction(output="stub", critique="ok", revision="ok")

        pipeline = ReflectionPipeline(
            generator=Stub(),
            critic=Stub(),
            reviser=Stub(),
        )
        graph = pipeline.build()
        assert len(graph.nodes()) == 5  # input + generate + critique + revise + output


class TestMapReducePipeline:
    def test_build(self) -> None:
        class Stub(dspy.Module):
            def forward(self, text: str) -> dspy.Prediction:
                return dspy.Prediction(output=text.upper())

        pipeline = MapReducePipeline(
            map_module=Stub(),
        )
        graph = pipeline.build()
        assert graph.input_node is not None

    def test_default_reducer(self) -> None:
        result = MapReducePipeline._default_reducer([{"output": "a"}, {"output": "b"}])
        assert "a" in result
        assert "b" in result
