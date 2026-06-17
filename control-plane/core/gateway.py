import litellm
from .cache import SemanticCacheInterceptor

class TokenLimitExceeded(Exception):
    pass

class MockCacheResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage(0)

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockUsage:
    def __init__(self, total_tokens):
        self.total_tokens = total_tokens

class LLMGateway:
    """
    Cost/Token Gateway.
    Wraps LiteLLM to track tokens and enforce session limits.
    """
    def __init__(self, max_tokens: int = 100000, vector_store=None):
        self.max_tokens = max_tokens
        self.total_tokens_used = 0
        self.cache = SemanticCacheInterceptor(vector_store) if vector_store else None

    def generate(self, model: str, messages: list, **kwargs):
        # Enforce limit before call
        if self.total_tokens_used >= self.max_tokens:
            raise TokenLimitExceeded(f"Session limit of {self.max_tokens} tokens exceeded.")

        # Check Semantic Cache
        if self.cache:
            cached_content = self.cache.check_cache(messages, kwargs)
            if cached_content:
                return MockCacheResponse(cached_content)

        # Call LiteLLM
        response = litellm.completion(
            model=model,
            messages=messages,
            **kwargs
        )

        # Update usage
        usage = response.usage
        if usage:
            self.total_tokens_used += usage.total_tokens

        # Enforce limit after call (just in case)
        if self.total_tokens_used >= self.max_tokens:
             print(f"Warning: Reached max tokens ({self.total_tokens_used}/{self.max_tokens}) during this call.")

        # Update Cache
        if self.cache and hasattr(response, 'choices') and len(response.choices) > 0:
            content = response.choices[0].message.content
            self.cache.update_cache(messages, content)

        return response
