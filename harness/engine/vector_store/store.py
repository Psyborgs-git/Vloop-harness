"""Vector store backends — sqlite-vec (preferred) and in-memory fallback."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class Document:
    """A chunk of text with metadata."""

    id: str
    text: str
    source: str = ""
    metadata: dict[str, Any] | None = None
    embedding: list[float] | None = None


class VectorStore(ABC):
    """Abstract vector store."""

    @abstractmethod
    async def add(self, documents: list[Document]) -> None:
        """Add documents (with or without precomputed embeddings)."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        """Search for nearest neighbors."""
        ...

    @abstractmethod
    async def delete(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Remove all documents."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total document count."""
        ...


class SqliteVecStore(VectorStore):
    """sqlite-vec backed vector store."""

    def __init__(
        self,
        db_path: Path | str,
        dimensions: int = 768,
        table_name: str = "documents",
    ) -> None:
        self.db_path = Path(db_path)
        self.dimensions = dimensions
        self.table_name = table_name
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        try:
            import sqlite_vec
        except ImportError as exc:
            raise RuntimeError(
                "sqlite-vec not installed. Install with: uv pip install sqlite-vec"
            ) from exc

        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

        self._conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {self.table_name} USING vec0(
                id TEXT PRIMARY KEY,
                embedding FLOAT[{self.dimensions}],
                text TEXT,
                source TEXT,
                metadata TEXT
            )
        """)
        self._conn.commit()

    # ── Public API ────────────────────────────────────────────────────────────

    async def add(self, documents: list[Document]) -> None:
        if self._conn is None:
            raise RuntimeError("DB not initialized")

        rows = []
        for doc in documents:
            emb = doc.embedding
            if emb is None:
                raise ValueError(f"Document {doc.id} missing embedding")
            emb_bytes = np.array(emb, dtype=np.float32).tobytes()
            rows.append((
                doc.id,
                emb_bytes,
                doc.text,
                doc.source,
                json.dumps(doc.metadata or {}),
            ))

        self._conn.executemany(
            f"""
            INSERT OR REPLACE INTO {self.table_name} (id, embedding, text, source, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        if self._conn is None:
            raise RuntimeError("DB not initialized")

        emb_bytes = np.array(query_embedding, dtype=np.float32).tobytes()
        cursor = self._conn.execute(
            f"""
            SELECT id, text, source, metadata, distance
            FROM {self.table_name}
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (emb_bytes, top_k),
        )

        results = []
        for row in cursor.fetchall():
            doc_id, text, source, meta_json, distance = row
            # Apply simple metadata filters post-search if needed
            meta = json.loads(meta_json or "{}")
            if filters and not self._matches_filters(meta, filters):
                continue
            results.append(Document(
                id=doc_id,
                text=text,
                source=source,
                metadata={**meta, "distance": distance},
            ))
        return results

    async def delete(self, doc_id: str) -> bool:
        if self._conn is None:
            return False
        cursor = self._conn.execute(
            f"DELETE FROM {self.table_name} WHERE id = ?", (doc_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    async def clear(self) -> None:
        if self._conn is None:
            return
        self._conn.execute(f"DELETE FROM {self.table_name}")
        self._conn.commit()

    def count(self) -> int:
        if self._conn is None:
            return 0
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        row = cursor.fetchone()
        return row[0] if row else 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _matches_filters(meta: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, value in filters.items():
            if meta.get(key) != value:
                return False
        return True


class InMemoryVecStore(VectorStore):
    """Pure-Python in-memory vector store (no dependencies)."""

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions
        self._docs: dict[str, Document] = {}

    async def add(self, documents: list[Document]) -> None:
        for doc in documents:
            self._docs[doc.id] = doc

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[Document]:
        if not self._docs:
            return []

        q = np.array(query_embedding, dtype=np.float32)
        scores: list[tuple[float, Document]] = []
        for doc in self._docs.values():
            if doc.embedding is None:
                continue
            meta = doc.metadata or {}
            if filters and not all(meta.get(k) == v for k, v in filters.items()):
                continue
            d_vec = np.array(doc.embedding, dtype=np.float32)
            # Cosine similarity
            norm = np.linalg.norm(q) * np.linalg.norm(d_vec)
            sim = float(np.dot(q, d_vec) / norm) if norm > 0 else 0.0
            scores.append((sim, doc))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scores[:top_k]]

    async def delete(self, doc_id: str) -> bool:
        if doc_id in self._docs:
            del self._docs[doc_id]
            return True
        return False

    async def clear(self) -> None:
        self._docs.clear()

    def count(self) -> int:
        return len(self._docs)
