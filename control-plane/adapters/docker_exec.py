import docker
from typing import Dict, Any, Generator
from core.ports import IExecutionManager

class LocalDockerAdapter(IExecutionManager):
    """
    Executes sandboxed tasks using the local Docker daemon.
    Enforces strict memory caps provided by the Rust microkernel.
    """
    def __init__(self, max_memory_bytes: int):
        # We attempt to connect to the local docker socket
        try:
            self.client = docker.from_env()
        except docker.errors.DockerException:
            print("Warning: Could not connect to local Docker daemon.")
            self.client = None
            
        self.max_memory_bytes = max_memory_bytes

    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        if not self.client:
            raise RuntimeError("Docker daemon is not running.")
            
        image = spec.get("image", "python:3.11-slim")
        command = spec.get("command", "")
        
        # Policy enforcement
        network_disabled = not policy.get("network", False)
        
        container = self.client.containers.run(
            image=image,
            command=command,
            detach=True,
            mem_limit=self.max_memory_bytes,
            network_disabled=network_disabled,
            remove=False # Keep it around briefly so we can stream logs
        )
        
        return container.id

    def stream_logs(self, job_id: str) -> Generator[str, None, None]:
        if not self.client:
            return
            
        container = self.client.containers.get(job_id)
        for log_line in container.logs(stream=True, follow=True):
            yield log_line.decode('utf-8').strip()

    def teardown(self, job_id: str) -> None:
        if not self.client:
            return
            
        try:
            container = self.client.containers.get(job_id)
            container.stop(timeout=2)
            container.remove(force=True)
            print(f"Aggressively destroyed container {job_id}")
        except docker.errors.NotFound:
            pass
