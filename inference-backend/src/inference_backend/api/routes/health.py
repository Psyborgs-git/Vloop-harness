import time

from fastapi import APIRouter

from ...config import (
    LM_PROVIDER,
    OLLAMA_MODEL,
    OPENAI_MODEL,
    ANTHROPIC_MODEL,
    LMSTUDIO_BASE_URL,
)

router = APIRouter()
_start = time.time()

_MODEL_BY_PROVIDER: dict[str, str] = {
    "openai": OPENAI_MODEL,
    "anthropic": ANTHROPIC_MODEL,
    "lmstudio": "local-model",
}


@router.get("/health")
async def health():
    lm_model = _MODEL_BY_PROVIDER.get(LM_PROVIDER, OLLAMA_MODEL)
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _start, 2),
        "lm_provider": LM_PROVIDER,
        "lm_model": lm_model,
    }
