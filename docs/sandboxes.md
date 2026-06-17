# Execution Sandboxes (The Muscle)

VLoop strictly separates cognitive planning (Control Plane) from task execution (Sandboxes). Agent-generated code is **never** executed directly on the host OS. 

Instead, tasks are dispatched through the `IExecutionManager` port.

## 1. Local Docker Adapter (`adapters/docker_exec.py`)

The default execution mode. It utilizes the local machine's Docker daemon via the `docker` Python SDK.

* **Ephemeral:** Creates a container using `python:3.11-slim`, executes the code, streams the logs back to the control plane, and aggressively destroys (`remove=True`, `force=True`) the container upon completion.
* **Hardware Enforcement:** Reads `max_memory_bytes` from the Rust-injected `active.toml` config and applies it as a hard `mem_limit` to the container. If the agent code leaks memory, Docker kills the container, not the host OS.
* **Network Isolation:** Respects the DSPy-generated security policy (`network: false`) to disable container networking if the task doesn't explicitly require it.

## 2. Remote Kubernetes Adapter (`adapters/k8s_exec.py`)

For enterprise or distributed workloads, VLoop can dispatch tasks as Kubernetes Jobs via the `kubernetes` Python SDK.

* **Job Lifecycle:** Generates a dynamic `Job` definition (`vloop-job-<uuid>`), sets resource limits (`512Mi` RAM, `500m` CPU), and deploys it to the `vloop-sandboxes` namespace.
* **Log Tailing:** Discovers the underlying Pod for the Job and streams the logs back to the DSPy evaluator.
* **Background Teardown:** Once evaluated, the Job is deleted via Kubernetes' background propagation policy.
