"""Tests for optimization, evaluator, feedback, and self-improvement."""

from __future__ import annotations

import pytest

import dspy

from harness.engine.optimization.evaluator import Evaluator
from harness.engine.optimization.feedback import FeedbackCollector
from harness.engine.optimization.optimizer import DSpyOptimizer, OptimizerConfig
from harness.engine.optimization.self_improve import ImprovementConfig, SelfImprovementLoop


class TestEvaluator:
    @pytest.fixture
    def evaluator(self) -> Evaluator:
        return Evaluator()

    @pytest.mark.asyncio
    async def test_exact_match_metric(self, evaluator: Evaluator) -> None:
        class Stub(dspy.Module):
            def forward(self, question: str) -> dspy.Prediction:
                answers = {"Where is the Eiffel Tower?": "Paris", "2+2?": "4"}
                return dspy.Prediction(answer=answers.get(question, ""))

        dataset = [
            dspy.Example(question="Where is the Eiffel Tower?", answer="Paris").with_inputs("question"),
            dspy.Example(question="2+2?", answer="4").with_inputs("question"),
        ]
        result = await evaluator.evaluate(Stub(), dataset, metric_name="exact_match")
        assert result.score == 1.0
        assert result.passed_examples == 2

    @pytest.mark.asyncio
    async def test_contains_metric(self, evaluator: Evaluator) -> None:
        class Stub(dspy.Module):
            def forward(self, question: str) -> dspy.Prediction:
                return dspy.Prediction(answer="The capital of France is Paris")

        dataset = [
            dspy.Example(question="Capital of France?", answer="Paris").with_inputs("question"),
        ]
        result = await evaluator.evaluate(Stub(), dataset, metric_name="contains")
        assert result.score == 1.0


class TestFeedbackCollector:
    @pytest.fixture
    def collector(self, tmp_path: object) -> FeedbackCollector:
        return FeedbackCollector(storage_dir=str(tmp_path / "feedback"))

    def test_record_and_summary(self, collector: FeedbackCollector) -> None:
        collector.record(
            component_id="comp_1",
            component_name="Test",
            input_data={"q": "hello"},
            output_data={"a": "world"},
            rating=1,
            tags=["good"],
        )
        summary = collector.summary_for_component("comp_1")
        assert summary["count"] == 1
        assert summary["avg_rating"] == 1.0

    def test_to_examples(self, collector: FeedbackCollector) -> None:
        collector.record(
            component_id="comp_1",
            component_name="Test",
            input_data={"q": "hello"},
            output_data={"a": "world"},
            rating=1,
        )
        examples = collector.to_examples("comp_1")
        assert len(examples) == 1


class TestDSpyOptimizer:
    def test_config_defaults(self) -> None:
        cfg = OptimizerConfig()
        assert cfg.teleprompter_type == "BootstrapFewShot"
        assert cfg.metric_threshold == 0.7

    def test_compare_versions(self) -> None:
        class Stub(dspy.Module):
            def forward(self, question: str) -> dspy.Prediction:
                return dspy.Prediction(answer="test")

        opt = DSpyOptimizer()
        testset = [
            dspy.Example(question="q1", answer="test").with_inputs("question"),
        ]

        def metric(ex: dspy.Example, pred: dspy.Prediction, trace: object = None) -> float:
            return 1.0 if ex.answer == pred.answer else 0.0

        result = opt.compare_versions(Stub(), Stub(), testset, metric)
        assert result["baseline_score"] == 1.0
        assert result["optimized_score"] == 1.0


class TestSelfImprovementLoop:
    @pytest.fixture
    def loop(self) -> SelfImprovementLoop:
        return SelfImprovementLoop(config=ImprovementConfig(target_score=1.0, max_iterations=1))

    @pytest.mark.asyncio
    async def test_improve_already_perfect(self, loop: SelfImprovementLoop) -> None:
        class Perfect(dspy.Module):
            def forward(self, question: str) -> dspy.Prediction:
                return dspy.Prediction(answer="Paris")

        dataset = [
            dspy.Example(question="Capital of France?", answer="Paris").with_inputs("question"),
        ]
        result = await loop.improve(Perfect(), "Perfect", trainset=dataset, testset=dataset)
        assert result.baseline_score == 1.0
        assert result.improved is False  # Already at target
