import sys

def patch():
    with open('harness/engine/dspy_engine.py', 'r') as f:
        content = f.read()

    react_method = """
    async def run_react_agent(
        self,
        task: str,
        available_tools: str,
        tool_registry: Any,
    ) -> dspy.Prediction:
        \"\"\"Run the ReAct agent to solve a task.\"\"\"
        assert self._react_agent, "Engine not configured — call configure() first"
        return await self.run(
            self._react_agent,
            task=task,
            available_tools=available_tools,
            tool_registry=tool_registry,
        )
"""
    if "async def run_react_agent" not in content:
        content = content.replace(
            "    # ── Direct LM access (escape hatch) ──────────────────────────────────────",
            react_method + "\n    # ── Direct LM access (escape hatch) ──────────────────────────────────────"
        )
        with open('harness/engine/dspy_engine.py', 'w') as f:
            f.write(content)

patch()
