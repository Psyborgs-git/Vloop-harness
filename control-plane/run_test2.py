import main
import threading
import time
import os
import sys
import grpc
from core.generated import system_pb2, system_pb2_grpc

t = threading.Thread(target=main.serve, daemon=True)
t.start()
time.sleep(2)

socket_path = os.path.expanduser("~/.vloop/rust/ipc.sock")
channel_str = f'unix://{socket_path}'
print(f"Connecting to {channel_str}")
channel = grpc.insecure_channel(channel_str)
stub = system_pb2_grpc.SystemControlStub(channel)

resp = stub.HealthCheck(system_pb2.Ping())
print("HealthCheck:", resp.status)
