import dspy
import json

class CodeGenerationSignature(dspy.Signature):
    """Generate a Python script to achieve the given objective. The code should be fully self-contained."""
    objective = dspy.InputField(desc="The goal the code should accomplish.")
    feedback = dspy.InputField(desc="Feedback or error logs from previous attempts, if any.", default="")
    python_code = dspy.OutputField(desc="The raw Python code string to execute.")

class PolicyGenerationSignature(dspy.Signature):
    """Analyze the given Python code and determine the minimum necessary security permissions."""
    python_code = dspy.InputField(desc="The Python code to analyze.")
    security_policy_json = dspy.OutputField(desc="A valid JSON string with keys: 'network' (bool), 'volume_mount' (bool).")

class CodeGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_code = dspy.Predict(CodeGenerationSignature)

    def forward(self, objective: str, feedback: str = ""):
        return self.generate_code(objective=objective, feedback=feedback)

class PolicyGenerator(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_policy = dspy.Predict(PolicyGenerationSignature)

    def forward(self, python_code: str) -> dict:
        result = self.generate_policy(python_code=python_code)
        try:
            # Attempt to parse the raw JSON from the LLM
            raw_json = result.security_policy_json
            # Strip markdown code blocks if present
            if raw_json.startswith("```json"):
                raw_json = raw_json[7:]
            if raw_json.startswith("```"):
                raw_json = raw_json[3:]
            if raw_json.endswith("```"):
                raw_json = raw_json[:-3]
                
            return json.loads(raw_json.strip())
        except json.JSONDecodeError:
            # Fallback policy if parsing fails (fail closed)
            print("Warning: Failed to parse security policy. Defaulting to strict.")
            return {"network": False, "volume_mount": False}
