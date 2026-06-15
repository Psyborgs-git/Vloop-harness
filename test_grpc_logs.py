import grpc
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'harness', 'engine'))
from process_pb2_grpc import ProcessManagerServiceStub
from process_pb2 import ListProcessesRequest

def run():
    channel = grpc.insecure_channel('127.0.0.1:9103')
    proc_stub = ProcessManagerServiceStub(channel)
    res = proc_stub.ListProcesses(ListProcessesRequest())
    for p in res.processes:
        if p.name == "Node Frontend":
            print("Found Node Frontend ID:", p.id)
            print("Logs are accessible via Tauri IPC.")

if __name__ == "__main__":
    run()