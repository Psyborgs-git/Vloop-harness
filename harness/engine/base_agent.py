import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class BaseAgent:
    """
    Base Agent responsible for dynamic pipeline generation.
    Writes physical files to the pipelines directory.
    """
    def __init__(self, workspace_root: Path):
        self.pipelines_dir = workspace_root / ".vloop" / "pipelines"
        self.pipelines_dir.mkdir(parents=True, exist_ok=True)

    def generate_pipeline(self, name: str, description: str, dspy_config: dict):
        pipeline_path = self.pipelines_dir / f"{name}.py"

        # Simple template for a generated pipeline
        content = f'''"""
Auto-generated pipeline: {name}
Description: {description}
"""
import dspy

class {name.capitalize()}Pipeline(dspy.Module):
    def __init__(self):
        super().__init__()
        # Config: {json.dumps(dspy_config)}

    def forward(self, *args, **kwargs):
        pass
'''
        with open(pipeline_path, 'w') as f:
            f.write(content)

        logger.info(f"Generated pipeline {name} at {pipeline_path}")
        return str(pipeline_path)

    def generate_evaluator(self, name: str, metrics: list):
        eval_path = self.pipelines_dir / f"{name}_eval.py"
        content = f'''"""
Auto-generated evaluator for: {name}
Metrics: {metrics}
"""
def evaluate_metrics(prediction, target):
    # Base evaluation logic based on metrics
    return 1.0
'''
        with open(eval_path, 'w') as f:
            f.write(content)

        logger.info(f"Generated evaluator for {name} at {eval_path}")
        return str(eval_path)
