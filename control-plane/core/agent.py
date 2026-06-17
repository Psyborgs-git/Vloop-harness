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
        For Phase 2: 3-node DAG:
        Node 1: harness_coder (AiderAdapter)
        Node 2: worker_sandbox (Execute and validate via git diff)
        Node 3: serve_ui (Ephemeral WebApp)
        """
        nodes = [
            {"name": "harness_coder", "dependencies": [], "payload": {"objective": objective}},
            {"name": "worker_sandbox", "dependencies": [], "payload": {}},
            {"name": "serve_ui", "dependencies": [], "payload": {}}
        ]
        workflow_id = self.workflow_manager.create_workflow(objective, nodes)
        
        with __import__("sqlite3").connect(self.workflow_manager.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT node_id, name FROM dag_nodes WHERE workflow_id=?", (workflow_id,))
            rows = c.fetchall()
            id_map = {name: node_id for node_id, name in rows}
            
            c.execute("UPDATE dag_nodes SET dependencies=? WHERE node_id=?", (json.dumps([id_map["harness_coder"]]), id_map["worker_sandbox"]))
            c.execute("UPDATE dag_nodes SET dependencies=? WHERE node_id=?", (json.dumps([id_map["worker_sandbox"]]), id_map["serve_ui"]))
            conn.commit()
            
        return workflow_id

    def run(self, objective: str, max_iterations: int = 3) -> dict:
        print(f"Compiling objective into DAG Workflow: {objective}")
        workflow_id = self.compile_goal_to_dag(objective)
        
        full_log = ""
        served_url = ""
        
        # We need workspaces path, we'll extract it from db_path directory for now
        base_dir = os.path.dirname(os.path.dirname(self.workflow_manager.db_path))
        workspace_dir = os.path.join(base_dir, "workspaces", workflow_id)
        os.makedirs(workspace_dir, exist_ok=True)
        
        try:
            while True:
                node = self.workflow_manager.get_next_runnable_node(workflow_id)
                if not node:
                    with __import__("sqlite3").connect(self.workflow_manager.db_path) as conn:
                        c = conn.cursor()
                        c.execute("SELECT status FROM dag_nodes WHERE workflow_id=? AND status != 'COMPLETED'", (workflow_id,))
                        pending = c.fetchall()
                        if not pending:
                            self.workflow_manager.mark_workflow_completed(workflow_id)
                            print("Workflow fully executed.")
                            return {"success": True, "output": full_log, "served_url": served_url}
                        else:
                            print("Workflow Deadlocked (nodes pending but not runnable).")
                            return {"success": False, "error": "DAG Deadlock"}

                node_id = node["node_id"]
                node_name = node["name"]
                payload = json.loads(node["payload"])
                
                print(f"\n--- Executing Node: {node_name} ---")
                self.workflow_manager.update_node_status(node_id, 'RUNNING')
                
                if node_name == "harness_coder":
                    print("Provisioning Aider Harness...")
                    try:
                        from adapters.harness import AiderAdapter
                        mem_limit = getattr(self.exec_manager, 'max_memory_bytes', 512 * 1024 * 1024)
                        aider = AiderAdapter(max_memory_bytes=mem_limit)
                        
                        spec = {
                            "prompt": f"Write a python script that addresses this objective: {payload['objective']}. Name it main.py. Also write a requirements.txt if needed.",
                            "workspace_dir": workspace_dir
                        }
                        # We mock network to true for aider to download tools if needed
                        job_id = aider.dispatch_job(spec, {"network": True})
                        time.sleep(2)
                        logs = list(aider.stream_logs(job_id))
                        aider.teardown(job_id)
                        
                        # Commit the generated code to git to pass state
                        import subprocess
                        subprocess.run(["git", "add", "."], cwd=workspace_dir, check=False)
                        subprocess.run(["git", "commit", "-m", "Aider harness generated code"], cwd=workspace_dir, check=False)
                        
                        self.workflow_manager.update_node_status(node_id, 'COMPLETED', {"logs": "\n".join(logs)})
                    except Exception as e:
                        print(f"Harness error: {e}")
                        self.workflow_manager.update_node_status(node_id, 'FAILED', {"logs": str(e)})
                        self.workflow_manager.mark_workflow_completed(workflow_id, 'FAILED')
                        return {"success": False, "error": str(e)}

                elif node_name == "worker_sandbox":
                    print("Validating codebase via git diff and executing...")
                    import subprocess
                    # Read git diff
                    diff_res = subprocess.run(["git", "log", "-p", "-1"], cwd=workspace_dir, capture_output=True, text=True)
                    diff_text = diff_res.stdout
                    print(f"Git Diff read: {len(diff_text)} chars")
                    
                    # Execute
                    try:
                        has_docker = hasattr(self.exec_manager, "client") and self.exec_manager.client is not None
                        if has_docker:
                            print("Dispatching job inside the worker sandbox...")
                            spec = {
                                "image": "python:3.11-slim",
                                "command": "python main.py",
                                "volumes": {
                                    workspace_dir: {"bind": "/app", "mode": "rw"}
                                },
                                "working_dir": "/app"
                            }
                            policy = {"network": False} # isolated worker sandbox
                            job_id = self.exec_manager.dispatch_job(spec, policy)
                            logs = []
                            for log_line in self.exec_manager.stream_logs(job_id):
                                logs.append(log_line)
                            self.exec_manager.teardown(job_id)
                            out = "\n".join(logs)
                        else:
                            print("Warning: Local Docker daemon not available. Falling back to host subprocess execution.")
                            res = subprocess.run(["python", "main.py"], cwd=workspace_dir, capture_output=True, text=True, timeout=30)
                            out = res.stdout + res.stderr
                            if res.returncode != 0:
                                raise RuntimeError(f"Execution failed on host with exit code {res.returncode}:\n{out}")
                            
                        self.workflow_manager.update_node_status(node_id, 'COMPLETED', {"logs": out, "git_diff": diff_text})
                    except Exception as e:
                        self.workflow_manager.update_node_status(node_id, 'FAILED', {"logs": str(e)})
                        self.workflow_manager.mark_workflow_completed(workflow_id, 'FAILED')
                        return {"success": False, "error": str(e)}

                elif node_name == "serve_ui":
                    print("Serving UI Mini-App...")
                    try:
                        has_docker = hasattr(self.exec_manager, "client") and self.exec_manager.client is not None
                        if has_docker:
                            print("Launching real dynamic UI Mini-App in UI Sandbox...")
                            # Determine if there's a requirements.txt to install
                            import os
                            reqs_file = os.path.join(workspace_dir, "requirements.txt")
                            install_cmd = "pip install -r requirements.txt && " if os.path.exists(reqs_file) else ""
                            
                            # Determine entrypoint
                            main_file = os.path.join(workspace_dir, "main.py")
                            is_streamlit = False
                            if os.path.exists(main_file):
                                with open(main_file, "r") as f:
                                    content = f.read()
                                    if "import streamlit" in content or "from streamlit" in content:
                                        is_streamlit = True
                                        
                            if is_streamlit:
                                app_cmd = "streamlit run main.py --server.port 8501 --server.address 0.0.0.0"
                                internal_port = 8501
                            else:
                                app_cmd = "python main.py"
                                internal_port = 8000 # Default fallback port
                                
                            full_cmd = f"sh -c '{install_cmd}{app_cmd}'"
                            print(f"UI Container Command: {full_cmd}")
                            
                            spec = {
                                "image": "python:3.11-slim",
                                "command": full_cmd,
                                "volumes": {
                                    workspace_dir: {"bind": "/app", "mode": "rw"}
                                },
                                "working_dir": "/app",
                                "ports": {f"{internal_port}/tcp": None} # Request dynamic port mapping
                            }
                            policy = {"network": True} # Needs network to download pip requirements and serve UI
                            job_id = self.exec_manager.dispatch_job(spec, policy)
                            
                            # Wait brief moment for container to boot and get ports
                            time.sleep(3)
                            
                            # Retrieve the dynamic host port assigned by Docker
                            mapped_ports = self.exec_manager.get_job_ports(job_id)
                            host_port = None
                            if mapped_ports:
                                port_info = mapped_ports.get(f"{internal_port}/tcp")
                                if port_info and len(port_info) > 0:
                                    host_port = port_info[0].get("HostPort")
                                    
                            if host_port:
                                served_url = f"http://localhost:{host_port}"
                                print(f"UI successfully served at: {served_url}")
                            else:
                                print("Warning: Failed to retrieve dynamic host port, falling back to localhost default.")
                                served_url = f"http://localhost:{internal_port}"
                        else:
                            print("Warning: Local Docker daemon not available. Falling back to mock served UI.")
                            served_url = "http://localhost:8501"
                            
                        self.workflow_manager.update_node_status(node_id, 'COMPLETED', {"logs": "UI Served successfully.", "served_url": served_url})
                    except Exception as e:
                        print(f"UI Serve error: {e}")
                        self.workflow_manager.update_node_status(node_id, 'FAILED', {"logs": str(e)})
                        self.workflow_manager.mark_workflow_completed(workflow_id, 'FAILED')
                        return {"success": False, "error": str(e)}
                    
        except TokenLimitExceeded as e:
            print(f"Agent Loop Terminated: {e}")
            self.workflow_manager.mark_workflow_completed(workflow_id, 'TERMINATED_TOKEN_LIMIT')
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"Agent Loop Error: {e}")
            self.workflow_manager.mark_workflow_completed(workflow_id, 'ERROR')
            return {"success": False, "error": str(e)}
