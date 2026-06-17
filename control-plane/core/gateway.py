import litellm

class TokenLimitExceeded(Exception):
    pass

class LLMGateway:
    """
    Cost/Token Gateway.
    Wraps LiteLLM to track tokens and enforce session limits.
    """
    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self.total_tokens_used = 0

    def generate(self, model: str, messages: list, **kwargs):
        # Enforce limit before call
        if self.total_tokens_used >= self.max_tokens:
            raise TokenLimitExceeded(f"Session limit of {self.max_tokens} tokens exceeded.")

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

        return response
