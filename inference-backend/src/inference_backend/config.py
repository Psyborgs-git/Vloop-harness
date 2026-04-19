import os
from typing import Literal

LM_PROVIDER: str = os.getenv("LM_PROVIDER", "ollama")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
LMSTUDIO_BASE_URL: str = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234")
HARNESS_CORE_URL: str = os.getenv("HARNESS_CORE_URL", "http://localhost:47200")
SANDBOX_MODE: str = os.getenv("SANDBOX_MODE", "process")
DB_ENGINE: str = os.getenv("DB_ENGINE", "sqlite")
PORT: int = int(os.getenv("PORT", "47201"))
