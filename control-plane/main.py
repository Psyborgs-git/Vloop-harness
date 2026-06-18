import sys
import os
import time
from concurrent import futures
import threading
import uuid

import grpc
import dspy
import webview
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Ensure core and adapters are discoverable
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "generated"))

from core.generated import system_pb2
from core.generated import system_pb2_grpc
from core.config import ConfigManager
from core.gateway import LLMGateway
from core.agent import AgentLoop
from adapters.sqlite_db import SQLiteAdapter
from adapters.dummy_vector import DummyVectorStoreAdapter
from adapters.docker_exec import LocalDockerAdapter
from adapters.k8s_exec import RemoteK8sAdapter
from core.proxy import run_proxy

# Initialize Global Token Gateway
gateway = LLMGateway(max_tokens=50000)

# Configure DSPy to use LiteLLM via our Gateway
lm = dspy.LM('openai/gpt-4o-mini', api_key=os.environ.get("OPENAI_API_KEY", "dummy"))
dspy.settings.configure(lm=lm)

# Global PyWebview Window Reference
main_window = None

class ContextHandler(FileSystemEventHandler):
    def __init__(self, servicer):
        self.servicer = servicer

    def on_created(self, event):
        if not event.is_directory:
            self._ingest(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._ingest(event.src_path)

    def _ingest(self, path):
        # Only ingest text/code files
        ext = os.path.splitext(path)[1]
        if ext in ['.txt', '.md', '.py', '.js', '.rs']:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Use the servicer's ingest method directly
                req = system_pb2.IngestRequest(file_path=path, content=content)
                self.servicer.IngestDocument(req, None)
            except Exception as e:
                print(f"Error reading file {path} for background context: {e}")

class SystemControlServicer(system_pb2_grpc.SystemControlServicer):
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.reinitialize_adapters()

    def reinitialize_adapters(self):
        data_dir = self.config_manager.data_dir
        
        # Ensure directories exist
        os.makedirs(os.path.join(data_dir, "db"), exist_ok=True)
        os.makedirs(os.path.join(data_dir, "vector"), exist_ok=True)
        
        # Boot Adapters
        db_path = os.path.join(data_dir, "db", "vloop.sqlite")
        self.db = SQLiteAdapter(db_path)
        self.db.connect()
        print(f"Relational DB connected at {db_path}")

        vec_path = os.path.join(data_dir, "vector")
        self.vector_store = DummyVectorStoreAdapter(vec_path)
        print(f"Vector Store initialized at {vec_path}")
        
        # Update global gateway with new vector store
        global gateway
        gateway.cache = __import__('core.cache', fromlist=['SemanticCacheInterceptor']).SemanticCacheInterceptor(self.vector_store)
        
        # Determine execution environment (default to local docker)
        use_k8s = self.config_manager.config_data.get("use_k8s", False)
        if use_k8s:
            self.exec_manager = RemoteK8sAdapter()
            print("Execution Sandbox: Kubernetes")
        else:
            mem_limit = self.config_manager.max_memory_bytes
            self.exec_manager = LocalDockerAdapter(max_memory_bytes=mem_limit)
            print(f"Execution Sandbox: Local Docker (Memory Limit: {mem_limit / 1024 / 1024} MB)")

    def HealthCheck(self, request, context):
        return system_pb2.Pong(status="Alive and Ready")

    def Heartbeat(self, request, context):
        return system_pb2.HeartbeatResponse(acknowledged=True)

    def NotifyUserAction(self, request, context):
        global main_window
        action = request.action
        print(f"Received User Action from Rust Tray: {action}")
        
        if action == "quit":
            print("Shutting down CP via safe quit command...")
            if main_window:
                main_window.destroy()
            os._exit(0)
        elif action == "open_home":
            if main_window:
                main_window.load_url("http://localhost:8000/")
                main_window.show()
        elif action == "open_settings":
            if main_window:
                main_window.load_url("http://localhost:8000/settings")
                main_window.show()
                
        return system_pb2.UserActionResponse(success=True)

    def RewindWorkspace(self, request, context):
        workspace_dir = os.path.join(self.config_manager.data_dir, "workspaces", request.workspace_id)
        try:
            import subprocess
            subprocess.run(["git", "reset", "--hard", request.target_commit_hash], cwd=workspace_dir, check=True, capture_output=True)
        except Exception as e:
            return system_pb2.RewindResponse(success=False, message=str(e))
            
        db_path = os.path.join(self.config_manager.data_dir, "db", "workflows.sqlite")
        try:
            from core.dag import WorkflowManager
            wm = WorkflowManager(db_path)
            wm.rewind_workflow(request.workspace_id, request.target_commit_hash)
        except Exception as e:
            print(f"Failed to rewind DAG state: {e}")

        return system_pb2.RewindResponse(success=True, message="Workspace rewound successfully.")

    def IngestDocument(self, request, context):
        try:
            self.vector_store.add_document(
                collection_name="background_rag",
                document_id=str(uuid.uuid4()),
                text=request.content,
                metadata={"file_path": request.file_path, "source": "background_rag"}
            )
            return system_pb2.IngestResponse(success=True, chunks_embedded=1)
        except Exception as e:
            print(f"RAG Ingestion failed: {e}")
            return system_pb2.IngestResponse(success=False, chunks_embedded=0)

    def SwarmTask(self, request, context):
        workspace_dir = os.path.join(self.config_manager.data_dir, "workspaces", request.task.task_id)
        if request.initial_workspace_tarball:
            os.makedirs(workspace_dir, exist_ok=True)
            import tarfile
            import io
            with tarfile.open(fileobj=io.BytesIO(request.initial_workspace_tarball)) as tar:
                tar.extractall(path=workspace_dir)
            
        return self.DispatchTask(request.task, context)

    def ReloadConfig(self, request, context):
        self.config_manager.config_path = request.config_path
        self.config_manager.load_config()
        self.reinitialize_adapters()
        return system_pb2.ReloadResponse(success=True, message="Config reloaded and adapters reinitialized")

    def GetWorkflowState(self, request, context):
        db_path = os.path.join(self.config_manager.data_dir, "db", "workflows.sqlite")
        import sqlite3
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if request.workflow_id:
                    cursor.execute("SELECT * FROM workflows WHERE workflow_id=?", (request.workflow_id,))
                else:
                    cursor.execute("SELECT * FROM workflows ORDER BY rowid DESC LIMIT 1")
                
                wf = cursor.fetchone()
                if not wf:
                    return system_pb2.WorkflowStateResponse()
                
                workflow_id = wf['workflow_id']
                objective = wf['objective']
                status = wf['status']
                
                cursor.execute("SELECT * FROM dag_nodes WHERE workflow_id=?", (workflow_id,))
                nodes = cursor.fetchall()
                
                pb_nodes = []
                for n in nodes:
                    pb_nodes.append(system_pb2.DAGNode(
                        node_id=n['node_id'],
                        name=n['name'],
                        status=n['status'],
                        dependencies=n['dependencies'],
                        payload=n['payload']
                    ))
                
                return system_pb2.WorkflowStateResponse(
                    workflow_id=workflow_id,
                    objective=objective,
                    status=status,
                    nodes=pb_nodes
                )
        except Exception:
            return system_pb2.WorkflowStateResponse()

    def DispatchTask(self, request, context):
        data_dir = self.config_manager.data_dir
        db_path = os.path.join(data_dir, "db", "workflows.sqlite")
        
        agent = AgentLoop(exec_manager=self.exec_manager, db_path=db_path)
        max_iters = request.max_iterations if request.max_iterations > 0 else 3
        
        result = agent.run(objective=request.objective, max_iterations=max_iters)
        
        if result["success"]:
            artifacts_dir = os.path.join(data_dir, "artifacts")
            os.makedirs(artifacts_dir, exist_ok=True)
            artifact_path = os.path.join(artifacts_dir, f"{request.task_id}_output.txt")
            
            with open(artifact_path, "w") as f:
                f.write(result.get("output", ""))
                
            return system_pb2.TaskResponse(
                success=True, 
                message="Task completed successfully.",
                artifact_path=artifact_path
            )
        else:
            return system_pb2.TaskResponse(
                success=False, 
                message=result.get("error", "Unknown error"),
                artifact_path=""
            )

def run_grpc_server(config, servicer):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    system_pb2_grpc.add_SystemControlServicer_to_server(servicer, server)
    
    is_windows = sys.platform == 'win32'
    if not is_windows:
        vloop_home = config.data_dir or os.path.expanduser("~/.vloop")
        rust_dir = os.path.join(vloop_home, "rust")
        os.makedirs(rust_dir, exist_ok=True)
        socket_path = os.path.join(rust_dir, "ipc.sock")
        
        if os.path.exists(socket_path):
            os.remove(socket_path)
            
        bind_address = f"unix://{socket_path}"
        server.add_insecure_port(bind_address)
    else:
        bind_address = "127.0.0.1:50051"
        server.add_insecure_port(bind_address)

    server.start()
    server.wait_for_termination()

def run_fastapi_server():
    app = FastAPI()
    
    # Try to serve the built React app if the dist folder exists
    dist_dir = os.path.join(os.path.dirname(__file__), "..", "src", "dist")
    if os.path.exists(dist_dir):
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")
    else:
        @app.get("/")
        def read_root():
            return {"message": "VLoop UI is building or not available. Please run npm run build in src/"}
            
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

def run_context_daemon(servicer, watch_dir):
    os.makedirs(watch_dir, exist_ok=True)
    event_handler = ContextHandler(servicer)
    observer = Observer()
    observer.schedule(event_handler, path=watch_dir, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except Exception:
        observer.stop()
    observer.join()

def serve():
    global main_window
    
    # 1. Load config dictated by Rust Microkernel
    config = ConfigManager()
    config.load_config()
    
    servicer = SystemControlServicer(config)

    # Start Proxy Server
    threading.Thread(target=run_proxy, args=(gateway,), daemon=True).start()

    # Start gRPC Server
    threading.Thread(target=run_grpc_server, args=(config, servicer), daemon=True).start()
    
    # Start FastAPI UI Server
    threading.Thread(target=run_fastapi_server, daemon=True).start()
    
    # Start Background RAG Context Daemon
    vloop_home = config.data_dir or os.path.expanduser("~/.vloop")
    workspace_dir = os.path.join(vloop_home, "workspace")
    threading.Thread(target=run_context_daemon, args=(servicer, workspace_dir), daemon=True).start()

    # Create PyWebView Window (Main Thread)
    main_window = webview.create_window('VLoop', 'http://localhost:8000', hidden=True, width=1024, height=768)
    webview.start()

if __name__ == '__main__':
    serve()
