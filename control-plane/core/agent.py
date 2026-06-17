import time
from core.ports import IExecutionManager
from core.dspy_modules import CodeGenerator, PolicyGenerator
from core.gateway import TokenLimitExceeded

class AgentLoop:
    def __init__(self, exec_manager: IExecutionManager):
        self.exec_manager = exec_manager
        self.code_gen = CodeGenerator()
        self.policy_gen = PolicyGenerator()

    def run(self, objective: str, max_iterations: int = 3) -> dict:
        feedback = ""
        
        for iteration in range(max_iterations):
            print(f"\n--- Agent Iteration {iteration + 1}/{max_iterations} ---")
            
            try:
                # 1. Generate Code
                print("Generating code...")
                code_result = self.code_gen(objective=objective, feedback=feedback)
                # Strip backticks if present
                python_code = code_result.python_code.strip()
                if python_code.startswith("```python"):
                    python_code = python_code[9:]
                if python_code.startswith("```"):
                    python_code = python_code[3:]
                if python_code.endswith("```"):
                    python_code = python_code[:-3]
                python_code = python_code.strip()

                # 2. Generate Security Policy
                print("Evaluating security policy...")
                policy = self.policy_gen(python_code=python_code)
                print(f"Policy generated: {policy}")

                # 3. Dispatch to Sandbox
                print("Dispatching to sandbox...")
                # We wrap the python code into a command list for the execution manager
                spec = {
                    "image": "python:3.11-slim",
                    "command": ["python", "-c", python_code]
                }
                
                job_id = self.exec_manager.dispatch_job(spec, policy)
                print(f"Dispatched Job ID: {job_id}")

                # 4. Monitor and Evaluate
                # Wait briefly for execution
                time.sleep(2)
                logs = list(self.exec_manager.stream_logs(job_id))
                full_log = "\n".join(logs)
                
                print("--- Sandbox Output ---")
                print(full_log)
                print("----------------------")

                # Teardown the sandbox immediately after extracting logs
                self.exec_manager.teardown(job_id)

                # Extremely simplified evaluation: If there's an exception, consider it a failure.
                if "Traceback" in full_log or "Error" in full_log:
                    print("Execution failed. Retrying with feedback...")
                    feedback = f"The code resulted in an error:\n{full_log}\nPlease fix the logic."
                else:
                    print("Execution succeeded!")
                    return {"success": True, "output": full_log, "code": python_code}

            except TokenLimitExceeded as e:
                print(f"Agent Loop Terminated: {e}")
                return {"success": False, "error": str(e)}
            except Exception as e:
                print(f"Agent Loop Error: {e}")
                return {"success": False, "error": str(e)}

        print("Max iterations reached without success.")
        return {"success": False, "error": "Max iterations reached."}
