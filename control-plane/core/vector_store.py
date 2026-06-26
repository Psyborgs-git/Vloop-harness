"""Pluggable vector stores for embeddings and similarity search.

Supports:
- PostgreSQL pgvector (most scalable)
- DuckDB array + cosine similarity (great for analytics)
- SQLite brute-force (fallback, small datasets only)
- Pinecone (cloud-hosted)

All stores implement the same abstract interface.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("vloop.control_plane.vector_store")


class VectorStore(ABC):
    """Abstract interface for embedding storage and similarity search."""

    @abstractmethod
    def add_embeddings(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> None: ...

    @abstractmethod
    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def delete(self, collection: str, ids: list[str]) -> None: ...

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


def _sanitize_ident(name: str) -> str:
    """Basic sanitization for dynamic table/collection names."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


# ---------------------------------------------------------------------------
# PostgreSQL pgvector
# ---------------------------------------------------------------------------


class PgVectorStore(VectorStore):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._lock = threading.RLock()
        try:
            import psycopg2
            import psycopg2.extras

            self._psycopg2 = psycopg2
            self._extras = psycopg2.extras
        except ImportError as exc:
            raise RuntimeError("psycopg2-binary is required for pgvector") from exc
        self.initialize()

    def _get_conn(self):
        return self._psycopg2.connect(self.database_url)

    def initialize(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
            except Exception:
                LOGGER.warning("pgvector extension unavailable on this server")
            finally:
                conn.close()

    def _ensure_collection(self, conn, collection: str, dim: int) -> None:
        safe = _sanitize_ident(collection)
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS vec_{safe} ("
                f"    id TEXT PRIMARY KEY,"
                f"    embedding vector({dim}),"
                f"    metadata_json TEXT NOT NULL DEFAULT '{{}}'"
                f")"
            )
        conn.commit()

    def add_embeddings(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> None:
        if not vectors:
            return
        dim = len(vectors[0])
        with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_collection(conn, collection, dim)
                safe = _sanitize_ident(collection)
                with conn.cursor() as cur:
                    for id_, vec, meta in zip(ids, vectors, metadata):
                        cur.execute(
                            f"INSERT INTO vec_{safe} (id, embedding, metadata_json) "
                            f"VALUES (%s, %s, %s) "
                            f"ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding, "
                            f"metadata_json = EXCLUDED.metadata_json",
                            (id_, vec, json.dumps(meta)),
                        )
                conn.commit()
            finally:
                conn.close()

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[dict[str, Any]]:
        safe = _sanitize_ident(collection)
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                    cur.execute(
                        f"SELECT id, embedding <=> %s::vector AS distance, metadata_json "
                        f"FROM vec_{safe} ORDER BY distance LIMIT %s",
                        (query_vector, top_k),
                    )
                    rows = cur.fetchall()
                return [
                    {
                        "id": r["id"],
                        "score": float(r["distance"]),
                        "metadata": json.loads(r["metadata_json"]),
                    }
                    for r in rows
                ]
            except Exception:
                LOGGER.exception("pgvector search failed")
                return []
            finally:
                conn.close()

    def delete(self, collection: str, ids: list[str]) -> None:
        safe = _sanitize_ident(collection)
        with self._lock:
            conn = self._get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM vec_{safe} WHERE id = ANY(%s)", (ids,))
                conn.commit()
            finally:
                conn.close()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# DuckDB vector store
# ---------------------------------------------------------------------------


class DuckDBVectorStore(VectorStore):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        try:
            import duckdb

            self._duckdb = duckdb
        except ImportError as exc:
            raise RuntimeError("duckdb is required for DuckDB vector support") from exc
        self.initialize()

    def _get_conn(self):
        return self._duckdb.connect(self.db_path)

    def initialize(self) -> None:
        pass

    def _ensure_collection(self, conn, collection: str) -> None:
        safe = _sanitize_ident(collection)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS vec_{safe} ("
            f"    id TEXT PRIMARY KEY,"
            f"    embedding FLOAT[],"
            f"    metadata_json TEXT NOT NULL DEFAULT '{{}}'"
            f")"
        )

    def add_embeddings(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> None:
        if not vectors:
            return
        with self._lock:
            conn = self._get_conn()
            try:
                self._ensure_collection(conn, collection)
                safe = _sanitize_ident(collection)
                for id_, vec, meta in zip(ids, vectors, metadata):
                    conn.execute(
                        f"INSERT OR REPLACE INTO vec_{safe} (id, embedding, metadata_json) "
                        f"VALUES (?, ?, ?)",
                        (id_, vec, json.dumps(meta)),
                    )
            finally:
                conn.close()

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[dict[str, Any]]:
        safe = _sanitize_ident(collection)
        with self._lock:
            conn = self._get_conn()
            try:
                result = conn.execute(
                    f"""
                    SELECT id, metadata_json,
                           (list_dot_product(embedding, ?::FLOAT[]) /
                            (sqrt(list_dot_product(embedding, embedding)) *
                             sqrt(list_dot_product(?::FLOAT[], ?::FLOAT[])))) AS similarity
                    FROM vec_{safe}
                    ORDER BY similarity DESC
                    LIMIT ?
                """,
                    (query_vector, query_vector, query_vector, top_k),
                )
                rows = result.fetchall()
                return [
                    {
                        "id": row[0],
                        "score": float(row[2] or 0),
                        "metadata": json.loads(row[1]),
                    }
                    for row in rows
                ]
            except Exception:
                LOGGER.exception("DuckDB vector search failed")
                return []
            finally:
                conn.close()

    def delete(self, collection: str, ids: list[str]) -> None:
        safe = _sanitize_ident(collection)
        with self._lock:
            conn = self._get_conn()
            try:
                for id_ in ids:
                    conn.execute(f"DELETE FROM vec_{safe} WHERE id = ?", (id_,))
            finally:
                conn.close()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SQLite brute-force fallback
# ---------------------------------------------------------------------------


class SQLiteVectorStore(VectorStore):
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        import sqlite3

        self._sqlite3 = sqlite3

    def _connect(self):
        conn = self._sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = self._sqlite3.Row
        return conn

    def initialize(self) -> None:
        pass

    def _ensure_collection(self, conn, collection: str) -> None:
        safe = _sanitize_ident(collection)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS vec_{safe} ("
            f"    id TEXT PRIMARY KEY,"
            f"    embedding_json TEXT NOT NULL,"
            f"    metadata_json TEXT NOT NULL DEFAULT '{{}}'"
            f")"
        )
        conn.commit()

    def add_embeddings(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> None:
        if not vectors:
            return
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_collection(conn, collection)
                safe = _sanitize_ident(collection)
                for id_, vec, meta in zip(ids, vectors, metadata):
                    conn.execute(
                        f"INSERT OR REPLACE INTO vec_{safe} (id, embedding_json, metadata_json) "
                        f"VALUES (?, ?, ?)",
                        (id_, json.dumps(vec), json.dumps(meta)),
                    )
                conn.commit()
            finally:
                conn.close()

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[dict[str, Any]]:
        safe = _sanitize_ident(collection)
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_collection(conn, collection)
                rows = conn.execute(
                    f"SELECT id, embedding_json, metadata_json FROM vec_{safe}"
                ).fetchall()

                scored = []
                q_norm = math.sqrt(sum(x * x for x in query_vector))
                if q_norm == 0:
                    return []

                for row in rows:
                    emb = json.loads(row["embedding_json"])
                    if len(emb) != len(query_vector):
                        continue
                    dot = sum(a * b for a, b in zip(query_vector, emb))
                    e_norm = math.sqrt(sum(x * x for x in emb))
                    if e_norm == 0:
                        continue
                    sim = dot / (q_norm * e_norm)
                    scored.append(
                        {
                            "id": row["id"],
                            "score": sim,
                            "metadata": json.loads(row["metadata_json"]),
                        }
                    )

                scored.sort(key=lambda x: x["score"], reverse=True)
                return scored[:top_k]
            except Exception:
                LOGGER.exception("SQLite vector search failed")
                return []
            finally:
                conn.close()

    def delete(self, collection: str, ids: list[str]) -> None:
        safe = _sanitize_ident(collection)
        with self._lock:
            conn = self._connect()
            try:
                for id_ in ids:
                    conn.execute(f"DELETE FROM vec_{safe} WHERE id = ?", (id_,))
                conn.commit()
            finally:
                conn.close()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Pinecone
# ---------------------------------------------------------------------------


class PineconeVectorStore(VectorStore):
    def __init__(
        self, api_key: str, environment: str, index_name: str | None = None
    ) -> None:
        self.api_key = api_key
        self.environment = environment
        self.index_name = index_name or "vloop-default"
        self._lock = threading.RLock()
        try:
            import pinecone

            self._pinecone = pinecone
        except ImportError as exc:
            raise RuntimeError("pinecone-client is required for Pinecone") from exc
        self.initialize()

    def initialize(self) -> None:
        with self._lock:
            self._pinecone.init(api_key=self.api_key, environment=self.environment)

    def _get_index(self):
        return self._pinecone.Index(self.index_name)

    def add_embeddings(
        self,
        collection: str,
        ids: list[str],
        vectors: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> None:
        if not vectors:
            return
        with self._lock:
            index = self._get_index()
            items = [
                (id_, vec, {**meta, "collection": collection})
                for id_, vec, meta in zip(ids, vectors, metadata)
            ]
            index.upsert(vectors=items)

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[dict[str, Any]]:
        with self._lock:
            index = self._get_index()
            result = index.query(
                vector=query_vector,
                top_k=top_k,
                filter={"collection": collection},
                include_metadata=True,
            )
            return [
                {
                    "id": m["id"],
                    "score": m["score"],
                    "metadata": {
                        k: v
                        for k, v in m.get("metadata", {}).items()
                        if k != "collection"
                    },
                }
                for m in result.get("matches", [])
            ]

    def delete(self, collection: str, ids: list[str]) -> None:
        with self._lock:
            index = self._get_index()
            index.delete(ids=ids)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_vector_store(
    vector_db_url: str | None = None,
    runtime_root: Path | None = None,
) -> VectorStore | None:
    vec_url = (vector_db_url or os.environ.get("VLOOP_VECTOR_DB_URL", "") or "").strip()

    if not vec_url or vec_url.lower() == "none":
        LOGGER.info("Vector store disabled (no VLOOP_VECTOR_DB_URL)")
        return None

    if runtime_root is None:
        runtime_root = Path(
            os.environ.get("VLOOP_RUNTIME_ROOT", Path.home() / ".vloop")
        )

    if vec_url.startswith("postgresql://") or vec_url.startswith("postgres://"):
        LOGGER.info("Using pgvector vector store")
        return PgVectorStore(vec_url)

    if vec_url.startswith("duckdb://"):
        path = vec_url[len("duckdb://") :] or str(
            runtime_root / "data" / "vectors.duckdb"
        )
        LOGGER.info("Using DuckDB vector store: %s", path)
        return DuckDBVectorStore(path)

    if vec_url.startswith("pinecone://"):
        api_key = os.environ.get("PINECONE_API_KEY", "")
        environment = os.environ.get("PINECONE_ENVIRONMENT", "us-west1-gcp")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY env var is required for Pinecone")
        LOGGER.info("Using Pinecone vector store")
        return PineconeVectorStore(api_key, environment)

    if vec_url.startswith("sqlite://"):
        path = vec_url[len("sqlite://") :] or str(runtime_root / "data" / "vectors.db")
        LOGGER.info("Using SQLite brute-force vector store: %s", path)
        return SQLiteVectorStore(Path(path))

    raise ValueError(f"Unsupported vector DB URL scheme: {vec_url}")
