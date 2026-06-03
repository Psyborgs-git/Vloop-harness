"""REST routes for vector store operations.

Endpoints
─────────
  POST /api/vector-store/documents        — add documents to vector store
  POST /api/vector-store/search           — semantic search
  DELETE /api/vector-store/documents/{id} — delete a document
  DELETE /api/vector-store/clear           — clear all documents
  GET  /api/vector-store/count            — document count
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from harness.engine.vector_store.retriever import ChunkingConfig

router = APIRouter(prefix="/api/vector-store", tags=["vector-store"])


# ── Request models ────────────────────────────────────────────────────────────


class AddDocumentsRequest(BaseModel):
    texts: list[str]
    sources: list[str] | None = None
    metadata: list[dict[str, Any]] | None = None
    chunk_size: int = 512
    chunk_overlap: int = 50


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict[str, Any] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _vector_store(request: Request):
    store = request.app.state.vector_store
    if store is None:
        raise HTTPException(status_code=503, detail="Vector store not configured")
    return store


def _embedder(request: Request):
    embedder = request.app.state.embedder
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedder not configured")
    return embedder


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/documents", status_code=201)
async def add_documents(
    body: AddDocumentsRequest,
    request: Request,
) -> dict[str, Any]:
    """Add documents to the vector store."""
    store = _vector_store(request)
    embedder = _embedder(request)

    from harness.engine.vector_store.store import Document

    # Chunk documents
    config = ChunkingConfig(chunk_size=body.chunk_size, chunk_overlap=body.chunk_overlap)
    all_chunks: list[str] = []
    all_sources: list[str] = []
    all_meta: list[dict[str, Any]] = []

    sources = body.sources or [""] * len(body.texts)
    metas = body.metadata or [{}] * len(body.texts)

    for text, source, meta in zip(body.texts, sources, metas):
        chunks = config.chunk(text)
        for chunk in chunks:
            all_chunks.append(chunk)
            all_sources.append(source)
            all_meta.append(meta)

    # Embed and store
    embeddings = await embedder.embed(all_chunks)
    docs = [
        Document(
            id=f"doc_{i}",
            text=text,
            source=source,
            metadata=meta,
            embedding=emb,
        )
        for i, (text, source, meta, emb) in enumerate(
            zip(all_chunks, all_sources, all_meta, embeddings)
        )
    ]
    await store.add(docs)
    return {"added": len(docs), "chunks": len(all_chunks)}


@router.post("/search")
async def search_vectors(
    body: SearchRequest,
    request: Request,
) -> list[dict[str, Any]]:
    """Semantic search over the vector store."""
    store = _vector_store(request)
    embedder = _embedder(request)

    query_embeddings = await embedder.embed([body.query])
    results = await store.search(
        query_embedding=query_embeddings[0],
        top_k=body.top_k,
        filters=body.filters,
    )
    return [
        {
            "id": doc.id,
            "text": doc.text,
            "source": doc.source,
            "metadata": doc.metadata,
        }
        for doc in results
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request) -> dict[str, Any]:
    store = _vector_store(request)
    deleted = await store.delete(doc_id)
    return {"deleted": deleted, "id": doc_id}


@router.delete("/clear")
async def clear_store(request: Request) -> dict[str, Any]:
    store = _vector_store(request)
    before = store.count()
    await store.clear()
    return {"cleared": True, "previous_count": before}


@router.get("/count")
async def get_count(request: Request) -> dict[str, Any]:
    store = _vector_store(request)
    return {"count": store.count()}
