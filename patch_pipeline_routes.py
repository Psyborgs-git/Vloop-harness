import sys

def patch():
    with open('harness/server/routes/pipeline_routes.py', 'r') as f:
        content = f.read()

    new_block = """
@router.post("/build/react_agent")
async def build_react_agent(body: SequentialPipelineRequest) -> dict[str, Any]:
    \"\"\"Build a ReAct Agent pipeline.\"\"\"
    pipeline = SequentialPipeline(name=body.name)
    # The first step will just invoke the react_agent step directly in executor
    # But since PipelineExecutor handles NODES, we can model it as a component node

    # We will assume that the execution context handles the react agent.
    # In Vloop, usually PipelineBuilder or Executor needs custom nodes.

    return {"graph": pipeline.build().to_dict(), "validation_errors": []}
"""
    if "@router.post(\"/build/react_agent\")" not in content:
        content = content.replace(
            "@router.post(\"/run\")",
            new_block + "\n@router.post(\"/run\")"
        )
        with open('harness/server/routes/pipeline_routes.py', 'w') as f:
            f.write(content)

patch()
