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
        self.has_runsc = False
        if self.client:
            try:
                info = self.client.info()
                runtimes = info.get("Runtimes", {})
                self.has_runsc = "runsc" in runtimes
                if self.has_runsc:
                    print("gVisor (runsc) runtime detected and enabled for sandboxes.")
            except Exception as e:
                print(f"Warning: Failed to retrieve Docker daemon info: {e}")

    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        if not self.client:
            raise RuntimeError("Docker daemon is not running.")
            
        image = spec.get("image", "python:3.11-slim")
        command = spec.get("command", "")
        volumes = spec.get("volumes", None)
        working_dir = spec.get("working_dir", None)
        environment = spec.get("environment", None)
        ports = spec.get("ports", None)
        
        # Policy enforcement
        network_disabled = not policy.get("network", False)
        
        # Enforce gVisor MicroVM isolation if available or explicitly requested
        runtime = None
        if self.has_runsc or policy.get("use_gvisor", False):
            runtime = "runsc"
        else:
            print("Warning: gVisor (runsc) is not installed/configured in Docker. Running sandbox container without gVisor kernel isolation.")
        
        container = self.client.containers.run(
            image=image,
            command=command,
            volumes=volumes,
            working_dir=working_dir,
            environment=environment,
            ports=ports,
            extra_hosts={"host.docker.internal": "host-gateway"},
            detach=True,
            mem_limit=self.max_memory_bytes,
            network_disabled=network_disabled,
            runtime=runtime,
            remove=False # Keep it around briefly so we can stream logs
        )
        
        return container.id

    def get_job_ports(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieves mapped host ports for a running container.
        Returns a dictionary mapping internal ports to host ports.
        """
        if not self.client:
            return {}
        try:
            container = self.client.containers.get(job_id)
            # Reload to ensure we have the latest attributes (like network ports assigned after booting)
            container.reload()
            return container.attrs.get("NetworkSettings", {}).get("Ports", {})
        except Exception as e:
            print(f"Warning: Failed to get ports for job {job_id}: {e}")
            return {}

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
