import grpc
import sys
import os

# Add generated Python protobufs to path
sys.path.append(os.path.join(os.getcwd(), 'harness', 'engine'))

from environment_pb2_grpc import EnvironmentManagerServiceStub
from environment_pb2 import ListEnvironmentsRequest, CreateEnvironmentRequest, EnvironmentConfig
from process_pb2_grpc import ProcessManagerServiceStub
from process_pb2 import CreateProcessRequest, ProcessConfig, ListProcessesRequest, StartProcessRequest

def run():
    port = 0
    # Search common dynamic ports configured by harness
    for p in range(9100, 9110):
        try:
            channel = grpc.insecure_channel(f'127.0.0.1:{p}')
            env_stub = EnvironmentManagerServiceStub(channel)
            # Short timeout to fail fast
            envs = env_stub.ListEnvironments(ListEnvironmentsRequest(), timeout=1)
            print(f"Connected to gRPC on 127.0.0.1:{p}")
            port = p
            break
        except Exception as e:
            continue
            
    if port == 0:
        print("Could not connect to any gRPC port.")
        return

    proc_stub = ProcessManagerServiceStub(channel)

    print("\n--- Listing Environments ---")
    envs = env_stub.ListEnvironments(ListEnvironmentsRequest())
    for e in envs.environments:
        print(f"Env: {e.name} (Type: {e.config.type})")
    
    default_env_id = None
    if len(envs.environments) > 0:
        default_env_id = envs.environments[0].id

    print("\n--- Creating Environment ---")
    new_env = env_stub.CreateEnvironment(CreateEnvironmentRequest(
        name="Test Docker Env",
        description="A test docker environment",
        config=EnvironmentConfig(type=1, image="alpine:latest") # 1 = DOCKER
    ))
    print(f"Created Env: {new_env.name} ({new_env.id})")

    print("\n--- Creating Process (Fallback to Default) ---")
    proc1 = proc_stub.CreateProcess(CreateProcessRequest(
        name="Test Process 1",
        description="Echo locally",
        config=ProcessConfig(command="echo", args=["local test"])
    ))
    print(f"Created Proc: {proc1.name} ({proc1.id}) - Env: {proc1.config.environment_id}")

    print("\n--- Creating Process (Explicit Env) ---")
    proc2 = proc_stub.CreateProcess(CreateProcessRequest(
        name="Test Process 2",
        description="Echo in Docker",
        config=ProcessConfig(command="echo", args=["docker test"], environment_id=new_env.id)
    ))
    print(f"Created Proc: {proc2.name} ({proc2.id}) - Env: {proc2.config.environment_id}")

    print("\n--- Starting Processes ---")
    print("Starting Proc 1...")
    proc_stub.StartProcess(StartProcessRequest(id=proc1.id))
    print("Starting Proc 2...")
    proc_stub.StartProcess(StartProcessRequest(id=proc2.id))
    print("Started successfully.")

if __name__ == "__main__":
    run()
