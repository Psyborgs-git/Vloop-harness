import pytest
from core.ports import IExecutionManager
from adapters.docker_exec import LocalDockerAdapter
from adapters.k8s_exec import RemoteK8sAdapter

def test_docker_adapter_implements_interface():
    assert issubclass(LocalDockerAdapter, IExecutionManager)

def test_k8s_adapter_implements_interface():
    assert issubclass(RemoteK8sAdapter, IExecutionManager)

def test_docker_adapter_dispatch_without_daemon(mocker):
    # Mock docker.from_env to raise an exception
    import docker
    mocker.patch('docker.from_env', side_effect=docker.errors.DockerException)
    
    adapter = LocalDockerAdapter(max_memory_bytes=1024)
    assert adapter.client is None
    
    with pytest.raises(RuntimeError, match="Docker daemon is not running."):
        adapter.dispatch_job({"image": "alpine"}, {"network": False})

def test_k8s_adapter_dispatch_without_config(mocker):
    from kubernetes.config.config_exception import ConfigException
    mocker.patch('kubernetes.config.load_kube_config', side_effect=ConfigException)
    
    adapter = RemoteK8sAdapter()
    assert adapter.batch_v1 is None
    
    with pytest.raises(RuntimeError, match="Kubernetes is not configured."):
        adapter.dispatch_job({"image": "alpine"}, {"network": False})
