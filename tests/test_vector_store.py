"""Tests for vector store backends and retriever."""

from __future__ import annotations

import pytest

from harness.engine.vector_store.embeddings import LocalEmbeddings, OpenAIEmbeddings, OllamaEmbeddings
from harness.engine.vector_store.store import Document, InMemoryVecStore
from harness.engine.vector_store.retriever import ChunkingConfig, VectorRetriever


class TestInMemoryVecStore:
    @pytest.fixture
    def store(self) -> InMemoryVecStore:
        return InMemoryVecStore(dimensions=3)

    @pytest.mark.asyncio
    async def test_add_and_search(self, store: InMemoryVecStore) -> None:
        docs = [
            Document(id="a", text="hello world", embedding=[1.0, 0.0, 0.0]),
            Document(id="b", text="foo bar", embedding=[0.0, 1.0, 0.0]),
            Document(id="c", text="hello again", embedding=[0.9, 0.1, 0.0]),
        ]
        await store.add(docs)
        results = await store.search(query_embedding=[1.0, 0.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].id in ("a", "c")

    @pytest.mark.asyncio
    async def test_delete(self, store: InMemoryVecStore) -> None:
        await store.add([Document(id="a", text="x", embedding=[1.0, 0.0, 0.0])])
        assert await store.delete("a")
        assert not await store.delete("a")

    @pytest.mark.asyncio
    async def test_clear_and_count(self, store: InMemoryVecStore) -> None:
        await store.add([Document(id="a", text="x", embedding=[1.0, 0.0, 0.0])])
        assert store.count() == 1
        await store.clear()
        assert store.count() == 0


class TestChunkingConfig:
    def test_single_short_text(self) -> None:
        config = ChunkingConfig(chunk_size=100, chunk_overlap=10)
        chunks = config.chunk("hello")
        assert chunks == ["hello"]

    def test_long_text_chunks(self) -> None:
        config = ChunkingConfig(chunk_size=20, chunk_overlap=5)
        text = "a" * 50
        chunks = config.chunk(text)
        assert len(chunks) > 1
        assert all(len(c) <= 20 for c in chunks)


class TestVectorRetriever:
    @pytest.mark.asyncio
    async def test_retrieve(self) -> None:
        store = InMemoryVecStore(dimensions=3)
        docs = [
            Document(id="a", text="DSPy is a framework", embedding=[1.0, 0.0, 0.0]),
            Document(id="b", text="PyTorch is a library", embedding=[0.0, 1.0, 0.0]),
        ]
        await store.add(docs)

        # Create a mock embedder
        class MockEmbedder:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 0.0, 0.0]]

            def dimensions(self) -> int:
                return 3

        retriever = VectorRetriever(store, MockEmbedder(), top_k=1)
        result = retriever(query="What is DSPy?")
        assert "retrieved_documents" in result.toDict()
