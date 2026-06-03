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
from harness.engine.dynamic_config import DynamicConfig
from harness.engine.memory.conversation import ConversationMemory
from harness.engine.memory.working import WorkingMemory
from harness.engine.model_registry import ModelRegistry
from harness.engine.model_router import ModelRouter
from harness.engine.modules.agent_planner import AgentPlanner
from harness.engine.modules.chat import DashboardChat
from harness.engine.modules.code_gen import CodeGenerator
from harness.engine.modules.component_spec import ComponentSpecGenerator
from harness.engine.modules.qa import QuestionAnswerer
from harness.engine.modules.reasoning import ChainOfThoughtReasoner
from harness.engine.modules.summarise import Summariser
from harness.engine.modules.view_gen import ViewGenerator
from harness.engine.optimization.self_improve import SelfImprovementLoop


class DSPyEngine:
    """
    Central AI engine. Initialise once at boot; share via MainProcess.ai.

    All public methods are async — they offload DSPy (sync) calls to a thread
    pool to avoid blocking the FastAPI event loop.
    """

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self._lm: dspy.LM | None = None

        # Dynamic AI subsystems
        self.model_registry = ModelRegistry()
        self.model_router = ModelRouter(registry=self.model_registry)
        self.dynamic_config = DynamicConfig(registry=self.model_registry)

        # Memory subsystems
        self.conversation_memory = ConversationMemory(summarizer=self)
        self.working_memory = WorkingMemory()

        # Self-improvement
        self.self_improvement = SelfImprovementLoop()

        # Vector store (injected externally after configure)
        self.vector_store: Any | None = None
        self.embedder: Any | None = None

        # Pre-built module instances (lazy-initialised after configure())
        self._reasoner: ChainOfThoughtReasoner | None = None
        self._code_gen: CodeGenerator | None = None
        self._qa: QuestionAnswerer | None = None
        self._summariser: Summariser | None = None
        self._chat: DashboardChat | None = None
        self._view_gen: ViewGenerator | None = None
        self._component_spec: ComponentSpecGenerator | None = None
        self._agent_planner: AgentPlanner | None = None

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def configure(self) -> None:
        """Configure DSPy with the provider specified in EngineConfig."""
        cfg = self.config

        import os
        rust_base_url = os.getenv("RUST_BASE_AI_URL")
        if rust_base_url:
            self._lm = dspy.LM(
                model=f"openai/{cfg.dspy_lm_model}",
                api_key="rust-base-dummy",
                api_base=rust_base_url,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                cache=cfg.cache_enabled,
            )
            dspy.configure(lm=self._lm)

            if cfg.cache_enabled:
                Path(cfg.cache_dir).mkdir(parents=True, exist_ok=True)

            self._reasoner = ChainOfThoughtReasoner()
            self._code_gen = CodeGenerator()
            self._qa = QuestionAnswerer()
            self._summariser = Summariser()
            self._chat = DashboardChat()
            self._view_gen = ViewGenerator()
            self._component_spec = ComponentSpecGenerator()
            self._agent_planner = AgentPlanner()
            return

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
        self._chat = DashboardChat()
        self._view_gen = ViewGenerator()
        self._component_spec = ComponentSpecGenerator()
        self._agent_planner = AgentPlanner()

    def reconfigure(self, new_config: EngineConfig) -> None:
        """Replace the active LM with a new configuration (provider switch)."""
        self.config = new_config
        self.configure()

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

    async def chat(
        self,
        history: str,
        user_message: str,
        available_components: str = "[]",
        available_pipelines: str = "[]",
        available_tools: str = "[]",
    ) -> dspy.Prediction:
        """Multi-turn dashboard chat with DSPy component/pipeline/tool generation."""
        assert self._chat, "Engine not configured — call configure() first"
        return await self.run(
            self._chat,
            history=history,
            user_message=user_message,
            available_components=available_components,
            available_pipelines=available_pipelines,
            available_tools=available_tools,
        )

    async def generate_view(
        self,
        ui_description: str,
        available_components: str = "[]",
        spec: str = "",
    ) -> dspy.Prediction:
        """Generate a React TSX view stub from a natural-language description."""
        assert self._view_gen, "Engine not configured — call configure() first"
        return await self.run(
            self._view_gen,
            ui_description=ui_description,
            available_components=available_components,
            spec=spec,
        )

    async def generate_component_spec(
        self,
        description: str,
        context: str = "",
    ) -> dspy.Prediction:
        """Generate a DSPy component (Signature + Module) from a description."""
        assert self._component_spec, "Engine not configured — call configure() first"
        return await self.run(
            self._component_spec,
            description=description,
            context=context,
        )

    async def plan(
        self,
        goal: str,
        available_components: str = "[]",
        available_pipelines: str = "[]",
        available_tools: str = "[]",
        context: str = "",
    ) -> dspy.Prediction:
        """Generate a structured agent execution plan from a natural-language goal."""
        assert self._agent_planner, "Engine not configured — call configure() first"
        return await self.run(
            self._agent_planner,
            goal=goal,
            available_components=available_components,
            available_pipelines=available_pipelines,
            available_tools=available_tools,
            context=context,
        )

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

    # ── Dynamic AI Engine API ─────────────────────────────────────────────────

    async def route_and_run(
        self,
        module: dspy.Module,
        model_id: str | None = None,
        required_capabilities: list[str] | None = None,
        **kwargs: Any,
    ) -> dspy.Prediction:
        """Run a module using the model router to pick the best provider."""
        from harness.engine.model_registry import ModelCapability

        caps = {ModelCapability(c) for c in (required_capabilities or ["chat"])}
        decision = self.model_router.route(
            model_id=model_id or self.config.dspy_lm_model,
            required_capabilities=list(caps),
            strategy="exact" if model_id else "capability",
            provider_configs=[
                {
                    "provider_type": self.config.dspy_lm_provider,
                    "base_url": getattr(self.config, "ollama_base_url", ""),
                    "api_key": self.config.anthropic_api_key or self.config.openai_api_key,
                }
            ],
        )
        # Temporarily reconfigure for this call
        old_cfg = self.config
        new_cfg = EngineConfig(
            dspy_lm_provider=decision.provider_type,
            dspy_lm_model=decision.model_id,
            anthropic_api_key=decision.api_key if decision.provider_type == "anthropic" else "",
            openai_api_key=decision.api_key if decision.provider_type == "openai" else "",
            ollama_base_url=decision.base_url or self.config.ollama_base_url,
        )
        self.reconfigure(new_cfg)
        try:
            result = await self.run(module, **kwargs)
        finally:
            self.reconfigure(old_cfg)
        return result

    async def run_with_dynamic_config(
        self,
        module: dspy.Module,
        prompt_text: str = "",
        task_type: str = "chat",
        preferred_temperature: float | None = None,
        **kwargs: Any,
    ) -> dspy.Prediction:
        """Run a module with runtime parameter adaptation."""
        self.dynamic_config.resolve(
            model_id=self.config.dspy_lm_model,
            prompt_text=prompt_text,
            preferred_temperature=preferred_temperature,
            task_type=task_type,
        )
        # Override module behavior if supported
        return await self.run(module, **kwargs)

    # ── RAG helpers ───────────────────────────────────────────────────────────

    async def retrieve_and_answer(
        self,
        query: str,
        top_k: int = 5,
    ) -> dspy.Prediction:
        """RAG-style answer using the configured vector store."""
        if self.vector_store is None or self.embedder is None:
            raise RuntimeError("Vector store or embedder not configured")
        from harness.engine.vector_store.retriever import VectorRetriever

        retriever = VectorRetriever(self.vector_store, self.embedder, top_k=top_k)
        docs = retriever(query=query)
        documents = getattr(docs, "retrieved_documents", "[]")
        return await self.answer(question=query, documents=documents)

    # ── Self-improvement helpers ──────────────────────────────────────────────

    async def improve_component(
        self,
        module: dspy.Module,
        module_name: str,
        trainset: list[dspy.Example] | None = None,
    ) -> Any:
        """Run the self-improvement loop on a component."""
        return await self.self_improvement.improve(module, module_name, trainset=trainset)

    async def generate_and_improve(
        self,
        spec: str,
    ) -> Any:
        """Generate a component from spec and immediately improve it."""
        return await self.self_improvement.generate_and_improve(
            spec, generator=self._component_spec
        )

    # ── Memory helpers ────────────────────────────────────────────────────────

    def reset_conversation(self) -> None:
        self.conversation_memory.clear()

    def add_conversation_turn(self, user: str, assistant: str) -> None:
        self.conversation_memory.add_user(user)
        self.conversation_memory.add_assistant(assistant)

    def get_conversation_context(self) -> str:
        return self.conversation_memory.get_context()
