import subprocess
import time
import sys
import os
import grpc
import urllib.request
import json

# Ensure proto stubs can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.generated import system_pb2, system_pb2_grpc

def run_e2e():
    print("🚀 Starting VLoop End-to-End Integration Tests...")
    
    try:
        # Determine Socket Path
        vloop_home = os.path.expanduser("~/.vloop")
        socket_path = os.path.join(vloop_home, "rust", "ipc.sock")
        
        if sys.platform == 'win32':
            channel_str = '127.0.0.1:50051'
        else:
            channel_str = f'unix://{socket_path}'
            
        print(f"\n[2] Connecting to gRPC Control Plane at {channel_str}...")
        channel = grpc.insecure_channel(channel_str)
        stub = system_pb2_grpc.SystemControlStub(channel)
        
        # --- TEST A: HealthCheck (v1.1 UDS) ---
        print("\n[Test A] Sending HealthCheck via UDS...")
        resp = stub.HealthCheck(system_pb2.Ping())
        print(f"✅ HealthCheck Response: {resp.status}")
        assert "Alive" in resp.status, "HealthCheck failed"
        
        # --- TEST B: Background RAG Ingestion (v1.3) ---
        print("\n[Test B] Sending Document for Vector Ingestion...")
        resp = stub.IngestDocument(system_pb2.IngestRequest(
            file_path="/test/mock_document.txt",
            content="This is a test of the background RAG context daemon."
        ))
        print(f"✅ Ingestion Response: success={resp.success}, chunks={resp.chunks_embedded}")
        assert resp.success is True, "Ingestion failed"
        
        # --- TEST C: Time-Travel Git Rewind (v1.3) ---
        print("\n[Test C] Testing DAG Time-Travel Git Reset...")
        test_ws = os.path.join(vloop_home, "workspaces", "e2e_test_ws")
        os.makedirs(test_ws, exist_ok=True)
        subprocess.run(["git", "init"], cwd=test_ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=test_ws, check=True, capture_output=True)
        
        resp = stub.RewindWorkspace(system_pb2.RewindRequest(
            workspace_id="e2e_test_ws",
            target_commit_hash="HEAD"
        ))
        print(f"✅ Rewind Response: success={resp.success}, msg={resp.message}")
        assert resp.success is True, "Time-Travel rewind failed"
        
        # --- TEST D: Local LLM Proxy Trap (v1.2) ---
        print("\n[Test D] Pinging Local LiteLLM Proxy Trap on port 4000...")
        req = urllib.request.Request(
            "http://127.0.0.1:4000/v1/chat/completions", 
            method="POST", 
            data=json.dumps({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as response:
                print(f"✅ Proxy Trap responded with 200 OK: {response.read()[:50]}...")
        except urllib.error.HTTPError as e:
            # We expect a 500 or Auth Error since there is no real OpenAI key configured in this shell
            print(f"✅ Proxy Trap responded with HTTP {e.code} (Expected if no API key is provided).")
        except urllib.error.URLError as e:
            print(f"❌ Proxy Trap connection failed: {e}")
            assert False, "Proxy trap is not running"

        print("\n🎉 ALL E2E TESTS PASSED SUCCESSFULLY! 🎉")

    finally:
        pass

if __name__ == "__main__":
    run_e2e()