import pytest
from unittest.mock import AsyncMock, patch
from harness.engine.sandbox_client import SandboxClient
from harness.engine.sandbox_pb2 import SandboxConfig, ProvisionResponse, TeardownResponse

@pytest.mark.asyncio
async def test_sandbox_client_provision():
    client = SandboxClient()
    client.channel = AsyncMock() # Prevent connect() from overwriting stub
    client.stub = AsyncMock()
    
    # Mock the Provision RPC call
    mock_response = ProvisionResponse(success=True)
    client.stub.Provision = AsyncMock(return_value=mock_response)
    
    success = await client.provision(
        session_id="test-session-123",
        sandbox_type=SandboxConfig.Type.LOCAL,
        command="echo",
        args=["hello world"]
    )
    
    assert success is True
    client.stub.Provision.assert_called_once()
    
    # Verify the request payload
    call_args = client.stub.Provision.call_args[0][0]
    assert call_args.session_id == "test-session-123"
    assert call_args.config.type == SandboxConfig.Type.LOCAL
    assert call_args.config.command == "echo"
    assert call_args.config.args == ["hello world"]

@pytest.mark.asyncio
async def test_sandbox_client_teardown():
    client = SandboxClient()
    client.channel = AsyncMock() # Prevent connect() from overwriting stub
    client.stub = AsyncMock()
    
    # Mock the Teardown RPC call
    mock_response = TeardownResponse(success=True)
    client.stub.Teardown = AsyncMock(return_value=mock_response)
    
    success = await client.teardown("test-session-123")
    
    assert success is True
    client.stub.Teardown.assert_called_once()
    
    # Verify the request payload
    call_args = client.stub.Teardown.call_args[0][0]
    assert call_args.session_id == "test-session-123"
