import dspy
from ..config import (
    LM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LMSTUDIO_BASE_URL,
)
from ..telemetry.logger import get_logger

logger = get_logger(__name__)


def configure_lm() -> None:
    """Configure DSPy LM based on LM_PROVIDER env var."""
    if LM_PROVIDER == "ollama":
        lm = dspy.OllamaLocal(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
        logger.info("LM configured", provider="ollama", model=OLLAMA_MODEL)
    elif LM_PROVIDER == "openai":
        lm = dspy.OpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY)
        logger.info("LM configured", provider="openai", model=OPENAI_MODEL)
    elif LM_PROVIDER == "anthropic":
        lm = dspy.Anthropic(model=ANTHROPIC_MODEL, api_key=ANTHROPIC_API_KEY)
        logger.info("LM configured", provider="anthropic", model=ANTHROPIC_MODEL)
    elif LM_PROVIDER == "lmstudio":
        lm = dspy.OllamaLocal(model="local-model", base_url=LMSTUDIO_BASE_URL)
        logger.info("LM configured", provider="lmstudio", url=LMSTUDIO_BASE_URL)
    else:
        logger.warning("Unknown LM_PROVIDER, falling back to Ollama", provider=LM_PROVIDER)
        lm = dspy.OllamaLocal(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)

    dspy.configure(lm=lm)
