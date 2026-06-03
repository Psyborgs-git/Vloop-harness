"""VectorRetriever — DSPy-compatible retriever module for RAG pipelines."""

from __future__ import annotations

from typing import Any

import dspy

from harness.engine.vector_store.embeddings import EmbeddingProvider
from harness.engine.vector_store.store import Document, VectorStore


class VectorRetrieverSignature(dspy.Signature):
    """Retrieve relevant documents for a query."""

    query: str = dspy.InputField(desc="The user's question or search query")
    retrieved_documents: str = dspy.OutputField(
        desc="JSON array of retrieved documents [{id, text, source, score}]"
    )


class VectorRetriever(dspy.Module):
    """DSPy module that retrieves documents from a vector store.

    Usage in a RAG pipeline::

        retriever = VectorRetriever(store, embedder)
        docs = retriever(query="What is DSPy?")
        # docs.retrieved_documents is a JSON string of results
    """

    def __init__(
        self,
        store: VectorStore,
        embedder: EmbeddingProvider,
        top_k: int = 5,
    ) -> None:
        super().__init__()
        self.store = store
        self.embedder = embedder
        self.top_k = top_k

    def forward(self, query: str) -> dspy.Prediction:
        import json
        import asyncio
        import concurrent.futures

        def _run_async() -> Any:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self._retrieve(query))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # If there's already a running loop, offload to a thread
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                docs = pool.submit(_run_async).result()
        except RuntimeError:
            docs = _run_async()

        results = [
            {
                "id": doc.id,
                "text": doc.text,
                "source": doc.source,
                "metadata": doc.metadata,
            }
            for doc in docs
        ]
        return dspy.Prediction(
            query=query,
            retrieved_documents=json.dumps(results, ensure_ascii=False),
        )

    async def _retrieve(self, query: str) -> list[Document]:
        embeddings = await self.embedder.embed([query])
        return await self.store.search(
            query_embedding=embeddings[0],
            top_k=self.top_k,
        )

    def add_documents(self, texts: list[str], sources: list[str] | None = None) -> None:
        """Convenience: embed and store raw text strings."""
        import asyncio

        sources = sources or [""] * len(texts)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._add_documents(texts, sources))
        finally:
            loop.close()

    async def _add_documents(self, texts: list[str], sources: list[str]) -> None:
        embeddings = await self.embedder.embed(texts)
        docs = [
            Document(
                id=f"doc_{i}_{hash(text) % 1000000000:09d}",
                text=text,
                source=source,
                embedding=emb,
            )
            for i, (text, source, emb) in enumerate(zip(texts, sources, embeddings))
        ]
        await self.store.add(docs)


class ChunkingConfig:
    """Config for document chunking."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= self.chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.chunk_overlap
        return chunks
