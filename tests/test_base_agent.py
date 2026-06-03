import pytest
from pathlib import Path
from harness.engine.base_agent import BaseAgent
import tempfile

def test_base_agent_generates_pipeline():
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        agent = BaseAgent(workspace)

        path = agent.generate_pipeline("TestPipe", "Desc", {"foo": "bar"})
        assert Path(path).exists()

        with open(path, "r") as f:
            content = f.read()
            assert "class TestpipePipeline(dspy.Module)" in content
            assert '"foo": "bar"' in content

def test_base_agent_generates_evaluator():
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td)
        agent = BaseAgent(workspace)

        path = agent.generate_evaluator("TestPipe", ["acc"])
        assert Path(path).exists()

        with open(path, "r") as f:
            content = f.read()
            assert "evaluate_metrics(prediction, target)" in content
            assert "acc" in content
