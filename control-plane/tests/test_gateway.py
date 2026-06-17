import pytest
from core.gateway import LLMGateway, TokenLimitExceeded

class MockUsage:
    def __init__(self, total_tokens):
        self.total_tokens = total_tokens

class MockResponse:
    def __init__(self, total_tokens):
        self.usage = MockUsage(total_tokens)

def test_gateway_enforces_limit(mocker):
    # Mock litellm.completion
    mocker.patch('litellm.completion', return_value=MockResponse(5000))
    
    # 10k limit
    gateway = LLMGateway(max_tokens=10000)
    
    # First call uses 5k tokens
    gateway.generate(model="test", messages=[])
    assert gateway.total_tokens_used == 5000
    
    # Second call uses 5k tokens (total 10k)
    gateway.generate(model="test", messages=[])
    assert gateway.total_tokens_used == 10000
    
    # Third call should hit limit
    with pytest.raises(TokenLimitExceeded):
        gateway.generate(model="test", messages=[])
