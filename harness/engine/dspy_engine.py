"""
DSPyEngine — the central AI brain of the Vloop Harness.

Responsibilities:
  - Configure and own the DSPy language model
  - Expose typed async wrappers around DSPy modules
  - Provide a component-friendly run() interface for arbitrary DSPy modules
  - Handle caching, retries, and error normalisation

Components interact with the engine via MainProcess.ai:

    result = await main_process.ai.reason("What should I display?", context=state_json)
    result = await main_process.ai.run(MyModule(), question="…")
"""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from typing import Any

import dspy

from harness.engine.config import EngineConfig
from harness.engine.modules.code_gen import CodeGenerator
from harness.engine.modules.qa import QuestionAnswerer
from harness.engine.modules.reasoning import ChainOfThoughtReasoner
from harness.engine.modules.summarise import Summariser


class DSPyEngine:
    """
    Central AI engine. Initialise once at boot; share via MainProcess.ai.

    All public methods are async — they offload DSPy (sync) calls to a thread
    pool to avoid blocking the FastAPI event loop.
    """

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self._lm: dspy.LM | None = None

        # Pre-built module instances (lazy-initialised after configure())
        self._reasoner: ChainOfThoughtReasoner | None = None
        self._code_gen: CodeGenerator | None = None
        self._qa: QuestionAnswerer | None = None
        self._summariser: Summariser | None = None

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def configure(self) -> None:
        """Configure DSPy with the provider specified in EngineConfig."""
        cfg = self.config
        provider = cfg.dspy_lm_provider.lower()

        if provider == "anthropic":
            if not cfg.anthropic_api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is required when DSPY_LM_PROVIDER=anthropic"
                )
            self._lm = dspy.LM(
                model=f"anthropic/{cfg.dspy_lm_model}",
                api_key=cfg.anthropic_api_key,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                cache=cfg.cache_enabled,
            )

        elif provider == "openai":
            if not cfg.openai_api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is required when DSPY_LM_PROVIDER=openai"
                )
            self._lm = dspy.LM(
                model=f"openai/{cfg.dspy_lm_model}",
                api_key=cfg.openai_api_key,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                cache=cfg.cache_enabled,
            )

        elif provider == "ollama":
            self._lm = dspy.LM(
                model=f"ollama/{cfg.dspy_lm_model}",
                api_base=cfg.ollama_base_url,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                cache=cfg.cache_enabled,
            )

        else:
            raise ValueError(f"Unknown provider: {provider!r}")

        dspy.configure(lm=self._lm)

        if cfg.cache_enabled:
            Path(cfg.cache_dir).mkdir(parents=True, exist_ok=True)

        # Eager-init modules so they're ready immediately
        self._reasoner = ChainOfThoughtReasoner()
        self._code_gen = CodeGenerator()
        self._qa = QuestionAnswerer()
        self._summariser = Summariser()

    # ── Async execution wrapper ───────────────────────────────────────────────

    async def run(self, module: dspy.Module, **kwargs: Any) -> dspy.Prediction:
        """
        Execute any DSPy module asynchronously.

        Runs module(**kwargs) in the default thread-pool to avoid blocking
        the asyncio event loop.
        """
        loop = asyncio.get_running_loop()
        fn = functools.partial(module, **kwargs)
        return await loop.run_in_executor(None, fn)

    # ── High-level helpers ────────────────────────────────────────────────────

    async def reason(self, question: str, context: str = "") -> dspy.Prediction:
        """Chain-of-thought reasoning over a question."""
        assert self._reasoner, "Engine not configured — call configure() first"
        return await self.run(self._reasoner, question=question, context=context)

    async def generate_code(
        self, language: str, specification: str, context: str = ""
    ) -> dspy.Prediction:
        """Generate code from a natural-language spec."""
        assert self._code_gen, "Engine not configured — call configure() first"
        return await self.run(
            self._code_gen,
            language=language,
            specification=specification,
            context=context,
        )

    async def answer(self, question: str, documents: str = "") -> dspy.Prediction:
        """Answer a question given supporting documents."""
        assert self._qa, "Engine not configured — call configure() first"
        return await self.run(self._qa, documents=documents, question=question)

    async def summarise(self, text: str, max_words: int = 100) -> dspy.Prediction:
        """Summarise long-form text."""
        assert self._summariser, "Engine not configured — call configure() first"
        return await self.run(self._summariser, text=text, max_words=max_words)

    # ── Direct LM access (escape hatch) ──────────────────────────────────────

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Raw LM completion. Returns the first choice as a string."""
        if self._lm is None:
            raise RuntimeError("Engine not configured")
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, functools.partial(self._lm, prompt, **kwargs))
        if isinstance(response, list):
            return response[0] if response else ""
        return str(response)

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self._lm is not None

    def __repr__(self) -> str:
        status = "ready" if self.is_ready else "unconfigured"
        return f"<DSPyEngine provider={self.config.dspy_lm_provider!r} model={self.config.dspy_lm_model!r} {status}>"
