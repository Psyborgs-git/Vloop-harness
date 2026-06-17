import time
import json
from core.ports import IExecutionManager
from core.dspy_modules import CodeGenerator, PolicyGenerator
from core.gateway import TokenLimitExceeded
from core.dag import WorkflowManager

class AgentLoop:
    def __init__(self, exec_manager: IExecutionManager, db_path: str):
        self.exec_manager = exec_manager
        self.code_gen = CodeGenerator()
        self.policy_gen = PolicyGenerator()
        self.workflow_manager = WorkflowManager(db_path)

    def compile_goal_to_dag(self, objective: str) -> str:
        """
        Compiles the objective into a DAG and stores it.
        For now, a simple 2-node DAG:
        Node 1: Generate Code & Policy
        Node 2: Execute Sandbox
        """
        nodes = [
            {"name": "codegen", "dependencies": [], "payload": {"objective": objective}},
            {"name": "execution", "dependencies": [], "payload": {}} # Will artificially depend on codegen via dynamic linking below
        ]
        workflow_id = self.workflow_manager.create_workflow(objective, nodes)
        
        # Manually wire dependency (In a real DSPy compiler, this is automated)
        with self.workflow_manager._init_db() if False else __import__("sqlite3").connect(self.workflow_manager.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT node_id, name FROM dag_nodes WHERE workflow_id=?", (workflow_id,))
            rows = c.fetchall()
            id_map = {name: node_id for node_id, name in rows}
            
            # Execution depends on Codegen
            c.execute("UPDATE dag_nodes SET dependencies=? WHERE node_id=?", (json.dumps([id_map["codegen"]]), id_map["execution"]))
            conn.commit()
            
        return workflow_id

    def run(self, objective: str, max_iterations: int = 3) -> dict:
        print(f"Compiling objective into DAG Workflow: {objective}")
        workflow_id = self.compile_goal_to_dag(objective)
        
        feedback = ""
        full_log = ""
        python_code = ""
        
        try:
            while True:
                node = self.workflow_manager.get_next_runnable_node(workflow_id)
                if not node:
                    # Check if workflow is actually done
                    with __import__("sqlite3").connect(self.workflow_manager.db_path) as conn:
                        c = conn.cursor()
                        c.execute("SELECT status FROM dag_nodes WHERE workflow_id=? AND status != 'COMPLETED'", (workflow_id,))
                        pending = c.fetchall()
                        if not pending:
                            self.workflow_manager.mark_workflow_completed(workflow_id)
                            print("Workflow fully executed.")
                            return {"success": True, "output": full_log, "code": python_code}
                        else:
                            print("Workflow Deadlocked (nodes pending but not runnable).")
                            return {"success": False, "error": "DAG Deadlock"}

                node_id = node["node_id"]
                node_name = node["name"]
                payload = json.loads(node["payload"])
                
                print(f"\n--- Executing Node: {node_name} ---")
                self.workflow_manager.update_node_status(node_id, 'RUNNING')
                
                if node_name == "codegen":
                    print("Generating code...")
                    code_result = self.code_gen(objective=payload["objective"], feedback=feedback)
                    
                    python_code = code_result.python_code.strip()
                    if python_code.startswith("```python"):
                        python_code = python_code[9:]
                    if python_code.startswith("```"):
                        python_code = python_code[3:]
                    if python_code.endswith("```"):
                        python_code = python_code[:-3]
                    python_code = python_code.strip()

                    print("Evaluating security policy...")
                    policy = self.policy_gen(python_code=python_code)
                    print(f"Policy generated: {policy}")
                    
                    self.workflow_manager.update_node_status(node_id, 'COMPLETED', {"code": python_code, "policy": policy})
                    
                elif node_name == "execution":
                    # Fetch code from codegen node
                    with __import__("sqlite3").connect(self.workflow_manager.db_path) as conn:
                        c = conn.cursor()
                        c.execute("SELECT payload FROM dag_nodes WHERE workflow_id=? AND name='codegen'", (workflow_id,))
                        codegen_payload = json.loads(c.fetchone()[0])
                        
                    python_code = codegen_payload["code"]
                    policy = codegen_payload["policy"]

                    print("Dispatching to sandbox...")
                    spec = {
                        "image": "python:3.11-slim",
                        "command": ["python", "-c", python_code]
                    }
                    
                    job_id = self.exec_manager.dispatch_job(spec, policy)
                    print(f"Dispatched Job ID: {job_id}")

                    time.sleep(2)
                    logs = list(self.exec_manager.stream_logs(job_id))
                    full_log = "\n".join(logs)
                    
                    print("--- Sandbox Output ---")
                    print(full_log)
                    print("----------------------")

                    self.exec_manager.teardown(job_id)

                    if "Traceback" in full_log or "Error" in full_log:
                        print("Execution failed. (Fail-fast in DAG v1.2)")
                        self.workflow_manager.update_node_status(node_id, 'FAILED', {"logs": full_log})
                        self.workflow_manager.mark_workflow_completed(workflow_id, 'FAILED')
                        return {"success": False, "error": full_log}
                    else:
                        print("Execution succeeded!")
                        self.workflow_manager.update_node_status(node_id, 'COMPLETED', {"logs": full_log})

        except TokenLimitExceeded as e:
            print(f"Agent Loop Terminated: {e}")
            self.workflow_manager.mark_workflow_completed(workflow_id, 'TERMINATED_TOKEN_LIMIT')
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"Agent Loop Error: {e}")
            self.workflow_manager.mark_workflow_completed(workflow_id, 'ERROR')
            return {"success": False, "error": str(e)}
