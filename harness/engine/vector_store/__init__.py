"""Vector store package — embeddings, storage, and DSPy retrieval."""

from harness.engine.vector_store.embeddings import (
    EmbeddingProvider,
    LocalEmbeddings,
    OpenAIEmbeddings,
)
from harness.engine.vector_store.retriever import VectorRetriever
from harness.engine.vector_store.store import InMemoryVecStore, SqliteVecStore, VectorStore

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddings",
    "LocalEmbeddings",
    "VectorStore",
    "SqliteVecStore",
    "InMemoryVecStore",
    "VectorRetriever",
]
