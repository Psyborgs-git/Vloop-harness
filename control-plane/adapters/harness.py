import os
import uuid
import subprocess
from typing import Dict, Any
from .docker_exec import LocalDockerAdapter

class AiderAdapter(LocalDockerAdapter):
    """
    Specialized execution sandbox for Aider (or similar coding harnesses).
    It mounts a workspace volume and injects the local LiteLLM proxy configuration.
    """
    def __init__(self, max_memory_bytes: int, host_proxy_url: str = "http://host.docker.internal:4000/v1"):
        super().__init__(max_memory_bytes)
        self.host_proxy_url = host_proxy_url

    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        if not self.client:
            raise RuntimeError("Docker daemon is not running.")
            
        task_id = str(uuid.uuid4())
        workspace_dir = spec.get("workspace_dir", f"/tmp/vloop-workspaces/{task_id}")
        
        # Provision workspace on host and init git
        os.makedirs(workspace_dir, exist_ok=True)
        try:
            subprocess.run(["git", "init"], cwd=workspace_dir, check=True, capture_output=True)
        except Exception as e:
            print(f"Warning: Failed to init git in {workspace_dir}: {e}")
            
        # Aider specific command
        prompt = spec.get("prompt", "Write a python hello world script.")
        command = f"aider --message '{prompt}' --yes --no-auto-commits"
        
        container = self.client.containers.run(
            image="paige/aider:latest", # Assuming a standard sider docker image exists, or built locally
            command=command,
            detach=True,
            mem_limit=self.max_memory_bytes,
            volumes={
                workspace_dir: {'bind': '/app', 'mode': 'rw'}
            },
            environment={
                "OPENAI_API_BASE": self.host_proxy_url,
                "OPENAI_API_KEY": "dummy-key-vloop" # The proxy doesn't care about this key, it uses the gateway's real key
            },
            working_dir="/app",
            network_disabled=not policy.get("network", True), # Harnesses typically need network
            runtime="runsc" if policy.get("use_gvisor", False) else None,
            remove=False 
        )
        
        self.active_jobs[container.id] = container
        return container.id
