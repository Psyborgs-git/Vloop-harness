import sys
import os
import time
from concurrent import futures

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

    def ReloadConfig(self, request, context):
        print(f"Reloading config from {request.config_path}")
        self.config_manager.config_path = request.config_path
        self.config_manager.load_config()
        self.reinitialize_adapters()
        return system_pb2.ReloadResponse(success=True, message="Config reloaded and adapters reinitialized")

    def DispatchTask(self, request, context):
        print(f"Received Task Dispatch: {request.objective}")
        agent = AgentLoop(exec_manager=self.exec_manager)
        
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

    # 2. Boot gRPC Server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    system_pb2_grpc.add_SystemControlServicer_to_server(
        SystemControlServicer(config), server
    )
    
    # 3. Bind and start
    port = 50051
    server.add_insecure_port(f'[::]:{port}')
    print(f"Python Control Plane (gRPC) booting on port {port}...")
    server.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Shutting down Control Plane...")
        server.stop(0)

if __name__ == '__main__':
    serve()
