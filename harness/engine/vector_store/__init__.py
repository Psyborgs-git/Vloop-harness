"""Vector store package — embeddings, storage, and DSPy retrieval."""

from harness.engine.vector_store.embeddings import EmbeddingProvider, OpenAIEmbeddings, LocalEmbeddings
from harness.engine.vector_store.store import VectorStore, SqliteVecStore, InMemoryVecStore
from harness.engine.vector_store.retriever import VectorRetriever

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddings",
    "LocalEmbeddings",
    "VectorStore",
    "SqliteVecStore",
    "InMemoryVecStore",
    "VectorRetriever",
]
