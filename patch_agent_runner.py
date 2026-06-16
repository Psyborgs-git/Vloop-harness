import sys

def patch():
    with open('harness/engine/agent_runner.py', 'r') as f:
        content = f.read()

    new_block = """
        if step_type == "react_agent":
            # Invoke the ReAct Agent loop
            ai = self._mp.ai
            if not ai.is_ready:
                return {"error": "AI engine not ready"}

            task = params.get("task", "")

            # Extract tools catalog as JSON string
            import json
            try:
                catalog = self._mp.tools.catalog()
                available_tools = json.dumps(catalog)
            except Exception:
                available_tools = "[]"

            prediction = await ai.run_react_agent(
                task=task,
                available_tools=available_tools,
                tool_registry=self._mp.tools
            )
            return {"prediction": str(prediction.answer), "history": getattr(prediction, "history", ""), "iterations": getattr(prediction, "iterations", 0)}
"""
    if "step_type == \"react_agent\"" not in content:
        content = content.replace(
            "        if step_type == \"dspy_call\":",
            new_block + "\n        if step_type == \"dspy_call\":"
        )
        with open('harness/engine/agent_runner.py', 'w') as f:
            f.write(content)

patch()
