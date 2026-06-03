"""Embedding providers — OpenAI API, local sentence-transformers, Ollama."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for *texts*."""
        ...

    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of produced vectors."""
        ...


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI API embeddings (text-embedding-3-small / text-embedding-3-large)."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self._dims = 1536 if "small" in model else 3072

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not configured for embeddings")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]

    def dimensions(self) -> int:
        return self._dims


class OllamaEmbeddings(EmbeddingProvider):
    """Ollama embeddings via /api/embeddings."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in texts:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                vectors.append(data["embedding"])
        return vectors

    def dimensions(self) -> int:
        # Common Ollama embedding dimensions
        return 768


class LocalEmbeddings(EmbeddingProvider):
    """Local sentence-transformers embeddings (CPU/GPU)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: Any | None = None
        self._dims: int | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
                self._dims = self._model.get_sentence_embedding_dimension()
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Install with: uv pip install sentence-transformers"
                ) from exc
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        loop = asyncio.get_running_loop()
        model = self._load()
        # sentence-transformers is sync; offload to thread
        vectors = await loop.run_in_executor(None, model.encode, texts)
        return vectors.tolist() if hasattr(vectors, "tolist") else vectors  # type: ignore[return-value]

    def dimensions(self) -> int:
        if self._dims is None:
            self._load()
        return self._dims or 384
