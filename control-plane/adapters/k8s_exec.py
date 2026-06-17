import uuid
from typing import Dict, Any, Generator
from kubernetes import client, config
from core.ports import IExecutionManager

class RemoteK8sAdapter(IExecutionManager):
    """
    Executes sandboxed tasks by dispatching Kubernetes Jobs to a remote cluster.
    """
    def __init__(self, namespace: str = "vloop-sandboxes"):
        self.namespace = namespace
        try:
            config.load_kube_config()
            self.batch_v1 = client.BatchV1Api()
            self.core_v1 = client.CoreV1Api()
        except config.config_exception.ConfigException:
            print("Warning: Could not load local kubeconfig. K8s adapter offline.")
            self.batch_v1 = None

    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        if not self.batch_v1:
            raise RuntimeError("Kubernetes is not configured.")

        job_id = f"vloop-job-{uuid.uuid4().hex[:8]}"
        image = spec.get("image", "python:3.11-slim")
        command = spec.get("command", ["echo", "Hello K8s"])

        container = client.V1Container(
            name=job_id,
            image=image,
            command=command,
            resources=client.V1ResourceRequirements(
                limits={"memory": "512Mi", "cpu": "500m"}
            )
        )

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": "vloop-sandbox", "job": job_id}),
            spec=client.V1PodSpec(restart_policy="Never", containers=[container]),
        )

        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_id),
            spec=client.V1JobSpec(template=template, backoff_limit=0),
        )

        self.batch_v1.create_namespaced_job(body=job, namespace=self.namespace)
        return job_id

    def stream_logs(self, job_id: str) -> Generator[str, None, None]:
        if not self.batch_v1:
            return

        # Find the pod associated with the job
        pods = self.core_v1.list_namespaced_pod(
            namespace=self.namespace,
            label_selector=f"job={job_id}"
        )
        
        if not pods.items:
            return
            
        pod_name = pods.items[0].metadata.name
        
        # This is a naive tail, in reality you'd want watch=True
        # which requires kubernetes.watch.Watch
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
            )
            for line in logs.split('\n'):
                if line:
                    yield line
        except client.exceptions.ApiException:
            pass

    def teardown(self, job_id: str) -> None:
        if not self.batch_v1:
            return
            
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_id,
                namespace=self.namespace,
                propagation_policy="Background"
            )
            print(f"Teardown initiated for K8s Job {job_id}")
        except client.exceptions.ApiException:
            pass
