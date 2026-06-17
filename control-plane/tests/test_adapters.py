import pytest
from core.ports import IExecutionManager
from adapters.docker_exec import LocalDockerAdapter
from adapters.k8s_exec import RemoteK8sAdapter

def test_docker_adapter_implements_interface():
    assert issubclass(LocalDockerAdapter, IExecutionManager)

def test_k8s_adapter_implements_interface():
    assert issubclass(RemoteK8sAdapter, IExecutionManager)

def test_docker_adapter_runtime_gvisor_fallback(mocker):
    mock_docker_client = mocker.MagicMock()
    mock_docker_client.info.return_value = {"Runtimes": {"runc": {}, "runc-custom": {}}} # runsc not available
    mocker.patch('docker.from_env', return_value=mock_docker_client)
    
    adapter = LocalDockerAdapter(max_memory_bytes=1024)
    assert adapter.has_runsc is False
    
    # Dispatching a job should not use runsc as runtime if not explicitly forced or not available
    adapter.dispatch_job({"image": "alpine"}, {"network": False})
    mock_docker_client.containers.run.assert_called_once()
    kwargs = mock_docker_client.containers.run.call_args[1]
    assert kwargs.get("runtime") is None

    # Reset mock and simulate runsc available
    mock_docker_client.containers.run.reset_mock()
    mock_docker_client.info.return_value = {"Runtimes": {"runc": {}, "runsc": {}}}
    
    adapter2 = LocalDockerAdapter(max_memory_bytes=1024)
    assert adapter2.has_runsc is True
    
    adapter2.dispatch_job({"image": "alpine"}, {"network": False})
    kwargs = mock_docker_client.containers.run.call_args[1]
    assert kwargs.get("runtime") == "runsc"

def test_docker_adapter_get_job_ports(mocker):
    mock_docker_client = mocker.MagicMock()
    mock_container = mocker.MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Ports": {
                "8501/tcp": [{"HostIp": "0.0.0.0", "HostPort": "32768"}]
            }
        }
    }
    mock_docker_client.containers.get.return_value = mock_container
    mocker.patch('docker.from_env', return_value=mock_docker_client)
    
    adapter = LocalDockerAdapter(max_memory_bytes=1024)
    ports = adapter.get_job_ports("fake-job-id")
    
    mock_docker_client.containers.get.assert_called_with("fake-job-id")
    mock_container.reload.assert_called_once()
    assert ports == {"8501/tcp": [{"HostIp": "0.0.0.0", "HostPort": "32768"}]}

def test_docker_adapter_dispatch_job_with_ports_and_volumes(mocker):
    mock_docker_client = mocker.MagicMock()
    mocker.patch('docker.from_env', return_value=mock_docker_client)
    
    adapter = LocalDockerAdapter(max_memory_bytes=1024)
    spec = {
        "image": "python:3.11-slim",
        "command": "python main.py",
        "volumes": {"/host/path": {"bind": "/app", "mode": "rw"}},
        "ports": {"8501/tcp": None}
    }
    
    adapter.dispatch_job(spec, {"network": True})
    mock_docker_client.containers.run.assert_called_once_with(
        image="python:3.11-slim",
        command="python main.py",
        volumes={"/host/path": {"bind": "/app", "mode": "rw"}},
        working_dir=None,
        environment=None,
        ports={"8501/tcp": None},
        extra_hosts={"host.docker.internal": "host-gateway"},
        detach=True,
        mem_limit=1024,
        network_disabled=False,
        runtime=None,
        remove=False
    )

def test_k8s_adapter_dispatch_without_config(mocker):
    from kubernetes.config.config_exception import ConfigException
    mocker.patch('kubernetes.config.load_kube_config', side_effect=ConfigException)
    
    adapter = RemoteK8sAdapter()
    assert adapter.batch_v1 is None
    
    with pytest.raises(RuntimeError, match="Kubernetes is not configured."):
        adapter.dispatch_job({"image": "alpine"}, {"network": False})
