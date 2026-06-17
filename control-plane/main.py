import sys
import os
import time
from concurrent import futures
import threading

import grpc
import dspy
import litellm

# Ensure core and adapters are discoverable
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
        print("Received Ping from Microkernel")
        return system_pb2.Pong(status="Alive and Ready")

    def Heartbeat(self, request, context):
        # Respond to heartbeat from Rust supervisor
        return system_pb2.HeartbeatResponse(acknowledged=True)

    def RewindWorkspace(self, request, context):
        workspace_dir = os.path.join(self.config_manager.data_dir, "workspaces", request.workspace_id)
        print(f"Time-Travel Rewind Requested for workspace {request.workspace_id} to commit {request.target_commit_hash}")
        
        # 1. Execute Git Reset
        try:
            import subprocess
            subprocess.run(["git", "reset", "--hard", request.target_commit_hash], cwd=workspace_dir, check=True, capture_output=True)
            print("Git reset successful.")
        except Exception as e:
            print(f"Failed to execute git reset: {e}")
            return system_pb2.RewindResponse(success=False, message=str(e))
            
        # 2. Delete downstream DAG nodes (simulated here as we need the workflow_id, but assuming 1:1 mapping for MVP)
        # Note: In a full implementation, you'd map workspace_id to workflow_id and target_commit to target_node_id
        db_path = os.path.join(self.config_manager.data_dir, "db", "workflows.sqlite")
        try:
            from core.dag import WorkflowManager
            wm = WorkflowManager(db_path)
            # Find workflow and node matching the commit (mocked for scaffolding)
            # wm.rewind_workflow(workflow_id, target_node_id)
            pass
        except Exception as e:
            pass

        return system_pb2.RewindResponse(success=True, message="Workspace rewound successfully.")

    def IngestDocument(self, request, context):
        print(f"Background RAG: Ingesting document {request.file_path} ({len(request.content)} bytes)")
        try:
            # A real implementation would chunk the document and embed it via LiteLLM/OpenAI
            # For the MVP, we add the raw text to our dummy vector store
            self.vector_store.add_document(
                content=request.content,
                metadata={"file_path": request.file_path, "source": "background_rag"}
            )
            return system_pb2.IngestResponse(success=True, chunks_embedded=1)
        except Exception as e:
            print(f"RAG Ingestion failed: {e}")
            return system_pb2.IngestResponse(success=False, chunks_embedded=0)

    def SwarmTask(self, request, context):
        print(f"P2P Swarm: Received task from remote node {request.remote_node_id}")
        
        # If there's a tarball, unpack it to the workspace
        workspace_dir = os.path.join(self.config_manager.data_dir, "workspaces", request.task.task_id)
        if request.initial_workspace_tarball:
            os.makedirs(workspace_dir, exist_ok=True)
            import tarfile
            import io
            with tarfile.open(fileobj=io.BytesIO(request.initial_workspace_tarball)) as tar:
                tar.extractall(path=workspace_dir)
            print(f"Extracted remote workspace payload to {workspace_dir}")
            
        # Dispatch the task normally via the existing logic
        return self.DispatchTask(request.task, context)

    def ReloadConfig(self, request, context):
        print(f"Reloading config from {request.config_path}")
        self.config_manager.config_path = request.config_path
        self.config_manager.load_config()
        self.reinitialize_adapters()
        return system_pb2.ReloadResponse(success=True, message="Config reloaded and adapters reinitialized")

    def DispatchTask(self, request, context):
        print(f"Received Task Dispatch: {request.objective}")
        
        # Determine database path for workflow state
        data_dir = self.config_manager.data_dir
        db_path = os.path.join(data_dir, "db", "workflows.sqlite")
        
        agent = AgentLoop(exec_manager=self.exec_manager, db_path=db_path)
        
        # Determine iteration cap
        max_iters = request.max_iterations if request.max_iterations > 0 else 3
        
        # Run the agent
        result = agent.run(objective=request.objective, max_iterations=max_iters)
        
        # Return response
        if result["success"]:
            # Write artifact out
            artifacts_dir = os.path.join(self.config_manager.data_dir, "artifacts")
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

def serve():
    # 1. Load config dictated by Rust Microkernel
    config = ConfigManager()
    config.load_config()

    # Start Proxy Server in background thread
    proxy_thread = threading.Thread(target=run_proxy, args=(gateway,), daemon=True)
    proxy_thread.start()

    # 2. Boot gRPC Server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    system_pb2_grpc.add_SystemControlServicer_to_server(
        SystemControlServicer(config), server
    )
    
    # 3. Bind and start (UDS with TCP Fallback for Windows)
    is_windows = sys.platform == 'win32'
    
    if not is_windows:
        vloop_home = config.data_dir
        if not vloop_home:
            vloop_home = os.path.expanduser("~/.vloop")
        
        rust_dir = os.path.join(vloop_home, "rust")
        os.makedirs(rust_dir, exist_ok=True)
        socket_path = os.path.join(rust_dir, "ipc.sock")
        
        if os.path.exists(socket_path):
            os.remove(socket_path)
            
        bind_address = f"unix://{socket_path}"
        server.add_insecure_port(bind_address)
        print(f"VLoop Python Control Plane listening on UDS: {bind_address}")
    else:
        bind_address = "127.0.0.1:50051"
        server.add_insecure_port(bind_address)
        print(f"VLoop Python Control Plane listening on TCP: {bind_address}")

    server.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Shutting down Control Plane...")
        server.stop(0)

if __name__ == '__main__':
    serve()
