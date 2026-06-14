"""Course-material RAG support for the LangGraph runtime.

The retriever uses LangChain document/splitter abstractions and can call an
OpenAI-compatible embedding endpoint such as Alibaba Cloud Bailian/DashScope.
It keeps a local hash fallback so the project remains testable without network
access or secrets.
"""

from __future__ import annotations

import math
import re
import hashlib
import os
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import BASE_DIR, settings

try:  # pragma: no cover - depends on optional runtime package
    from langchain_core.documents import Document as LangChainDocument
except Exception:  # pragma: no cover
    LangChainDocument = None

try:  # pragma: no cover - depends on optional runtime package
    from langchain_core.embeddings import Embeddings
except Exception:  # pragma: no cover
    Embeddings = object

try:  # pragma: no cover - depends on optional runtime package
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    RecursiveCharacterTextSplitter = None

try:  # pragma: no cover - depends on optional runtime package
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

try:  # pragma: no cover - depends on optional runtime package
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


_OPENAI_COMPATIBLE_PROVIDERS = {"dashscope", "bailian", "aliyun", "openai-compatible"}
_CHROMA_VECTOR_STORE_PROVIDERS = {"chroma", "chromadb"}
RAG_CHUNK_SIZE = 520
RAG_CHUNK_OVERLAP = 150
CHROMA_COLLECTION_NAME = "student_planner_rag"
_RAG_RETRIEVER_CACHE: dict[tuple[Any, ...], "LocalRAGRetriever"] = {}
_CHROMA_RUNTIME_PROBE: tuple[bool, str] | None = None


@dataclass
class LocalDocument:
    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class HashEmbeddings(Embeddings):
    """Small deterministic embedding model for local RAG demos."""

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0 for _ in range(self.dimensions)]
        for token in _tokenize(text):
            vector[hash(token) % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def _tokenize(text: str) -> list[str]:
    latin_tokens = re.findall(r"[a-z0-9]+", text.lower())
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    chinese_ngrams: list[str] = []
    if len(chinese_chars) == 1:
        chinese_ngrams.extend(chinese_chars)
    for size in (2, 3, 4):
        chinese_ngrams.extend(
            "".join(chinese_chars[index : index + size])
            for index in range(max(len(chinese_chars) - size + 1, 0))
        )
    return latin_tokens + chinese_ngrams


class OpenAICompatibleEmbeddings(Embeddings):
    """Embedding adapter for Bailian/DashScope and other OpenAI-compatible APIs."""

    def __init__(self, *, api_key: str, base_url: str, model: str, batch_size: int = 10) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package is not installed")
        self.model = model
        self.base_url = base_url
        self.batch_size = max(1, min(batch_size, 10))
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for offset in range(0, len(texts), self.batch_size):
            batch = list(texts[offset : offset + self.batch_size])
            response = None
            for attempt in range(3):
                try:
                    response = self.client.embeddings.create(model=self.model, input=batch)
                    break
                except Exception:
                    if attempt >= 2:
                        raise
                    time.sleep(1.0 + attempt * 2.0)
            if response is None:  # pragma: no cover - defensive guard
                raise RuntimeError("embedding response missing")
            data = sorted(response.data, key=lambda item: item.index)
            vectors.extend(list(item.embedding) for item in data)
        return vectors


def _local_embedding_info(*, configured_provider: str, reason: str) -> dict[str, str]:
    provider = "local-hash" if configured_provider in {"local", "hash", "local-hash"} else "hash-fallback"
    return {
        "embedding_provider": provider,
        "embedding_model": "local-hash",
        "embedding_configured_provider": configured_provider,
        "embedding_configured_model": settings.rag_embedding_model,
        "embedding_base_url": settings.rag_embedding_base_url,
        "embedding_batch_size": str(settings.rag_embedding_batch_size),
        "embedding_fallback_reason": reason,
    }


def build_embeddings() -> tuple[Embeddings, dict[str, str]]:
    provider = settings.rag_embedding_provider.strip().lower()
    if provider in _OPENAI_COMPATIBLE_PROVIDERS:
        if not settings.rag_embedding_api_key.strip():
            return HashEmbeddings(), _local_embedding_info(
                configured_provider=provider,
                reason="missing_api_key",
            )
        return (
            OpenAICompatibleEmbeddings(
                api_key=settings.rag_embedding_api_key,
                base_url=settings.rag_embedding_base_url,
                model=settings.rag_embedding_model,
                batch_size=settings.rag_embedding_batch_size,
            ),
            {
                "embedding_provider": provider,
                "embedding_model": settings.rag_embedding_model,
                "embedding_configured_provider": provider,
                "embedding_configured_model": settings.rag_embedding_model,
                "embedding_base_url": settings.rag_embedding_base_url,
                "embedding_batch_size": str(settings.rag_embedding_batch_size),
                "embedding_fallback_reason": "",
            },
        )

    return HashEmbeddings(), _local_embedding_info(
        configured_provider=provider or "local",
        reason="local_provider",
    )


def _document(page_content: str, metadata: dict[str, Any]) -> Any:
    if LangChainDocument is not None:
        return LangChainDocument(page_content=page_content, metadata=metadata)
    return LocalDocument(page_content=page_content, metadata=metadata)


def resolve_corpus_dir(corpus_dir: str | Path | None = None) -> Path:
    raw_dir = Path(corpus_dir or settings.rag_corpus_dir)
    if raw_dir.is_absolute():
        return raw_dir
    return BASE_DIR / raw_dir


def _is_corpus_content_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".md", ".txt"} and not path.name.startswith("RAG_")


def load_documents(corpus_dir: str | Path | None = None) -> list[Any]:
    root = resolve_corpus_dir(corpus_dir)
    if not root.exists():
        return []

    documents: list[Any] = []
    for path in sorted(root.rglob("*")):
        if not _is_corpus_content_file(path):
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        documents.append(
            _document(
                content,
                {"source": str(path.relative_to(root)), "file_name": path.name},
            )
        )
    return documents


def split_documents(documents: list[Any]) -> list[Any]:
    if not documents:
        return []
    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAG_CHUNK_SIZE,
            chunk_overlap=RAG_CHUNK_OVERLAP,
        )
        return splitter.split_documents(documents)

    chunks: list[Any] = []
    for document in documents:
        content = str(getattr(document, "page_content", ""))
        metadata = dict(getattr(document, "metadata", {}) or {})
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
        for index, paragraph in enumerate(paragraphs):
            chunks.append(_document(paragraph, {**metadata, "chunk": index}))
    return chunks


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _corpus_signature(corpus_dir: Path) -> tuple[tuple[str, int, int], ...]:
    if not corpus_dir.exists():
        return ()
    entries: list[tuple[str, int, int]] = []
    for path in sorted(corpus_dir.rglob("*")):
        if _is_corpus_content_file(path):
            stat = path.stat()
            entries.append((str(path.relative_to(corpus_dir)), stat.st_size, stat.st_mtime_ns))
    return tuple(entries)


def _embedding_signature() -> tuple[str, str, str, bool, int, str, str]:
    return (
        settings.rag_embedding_provider.strip().lower(),
        settings.rag_embedding_model,
        settings.rag_embedding_base_url,
        bool(settings.rag_embedding_api_key.strip()),
        settings.rag_embedding_batch_size,
        settings.rag_vector_store_provider.strip().lower(),
        settings.rag_vector_store_dir,
    )


def _vector_store_dir() -> Path:
    raw_dir = Path(settings.rag_vector_store_dir)
    if raw_dir.is_absolute():
        return raw_dir
    return BASE_DIR / raw_dir


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _chroma_runtime_available() -> tuple[bool, str]:
    """Probe Chroma in a subprocess so native crashes cannot kill the app."""

    global _CHROMA_RUNTIME_PROBE
    if _CHROMA_RUNTIME_PROBE is not None:
        return _CHROMA_RUNTIME_PROBE
    if chromadb is None:
        _CHROMA_RUNTIME_PROBE = (False, "chromadb_import_failed")
        return _CHROMA_RUNTIME_PROBE

    probe_dir = _vector_store_dir().parent / f".chroma_probe_{uuid.uuid4().hex}"
    probe_dir.parent.mkdir(parents=True, exist_ok=True)
    probe_code = "\n".join(
        [
            "import chromadb",
            "from pathlib import Path",
            f"probe_dir = Path({str(probe_dir)!r})",
            "client = chromadb.PersistentClient(path=str(probe_dir))",
            "collection = client.get_or_create_collection('student_planner_probe')",
            "vector = [1.0, 0.0, 0.0, 0.0]",
            "collection.upsert(",
            "    ids=['probe'],",
            "    documents=['probe document'],",
            "    embeddings=[vector],",
            "    metadatas=[{'corpus_key': 'probe'}],",
            ")",
            "collection.query(",
            "    query_embeddings=[vector],",
            "    n_results=1,",
            "    where={'corpus_key': 'probe'},",
            "    include=['documents', 'metadatas', 'distances'],",
            ")",
        ]
    )
    env = {
        **os.environ,
        "ANONYMIZED_TELEMETRY": "False",
        "CHROMA_TELEMETRY": "False",
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe_code],
            cwd=str(BASE_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _CHROMA_RUNTIME_PROBE = (False, "chroma_probe_timeout")
    except Exception as exc:  # pragma: no cover - defensive environment guard
        _CHROMA_RUNTIME_PROBE = (False, f"chroma_probe_error:{exc.__class__.__name__}")
    else:
        if completed.returncode == 0:
            _CHROMA_RUNTIME_PROBE = (True, "")
        else:
            _CHROMA_RUNTIME_PROBE = (
                False,
                f"chroma_probe_failed:returncode={completed.returncode}",
            )
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    return _CHROMA_RUNTIME_PROBE


class SQLiteVectorStore:
    """Persistent local vector cache for corpus chunk embeddings."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_vectors (
                    id TEXT PRIMARY KEY,
                    vector_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def get_many(self, ids: Sequence[str]) -> dict[str, list[float]]:
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id, vector_json FROM rag_vectors WHERE id IN ({placeholders})",
                list(ids),
            ).fetchall()
        vectors: dict[str, list[float]] = {}
        for row_id, vector_json in rows:
            values = json.loads(vector_json)
            vectors[str(row_id)] = [float(value) for value in values]
        return vectors

    def set_many(self, items: Sequence[tuple[str, list[float]]]) -> None:
        if not items:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO rag_vectors(id, vector_json, updated_at)
                VALUES(?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    vector_json=excluded.vector_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                [(item_id, json.dumps(vector),) for item_id, vector in items],
            )
            connection.commit()


class ChromaVectorStore:
    """Persistent Chroma vector database for RAG chunk storage and retrieval."""

    def __init__(self, persist_dir: Path) -> None:
        if chromadb is None:
            raise RuntimeError("chromadb package is not installed")
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def get_existing_ids(self, ids: Sequence[str], *, corpus_key: str) -> set[str]:
        if not ids:
            return set()
        result = self.collection.get(ids=list(ids), include=["metadatas"])
        metadatas = result.get("metadatas", [])
        return {
            str(item_id)
            for item_id, metadata in zip(result.get("ids", []), metadatas, strict=False)
            if dict(metadata or {}).get("corpus_key") == corpus_key
        }

    def upsert_many(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str],
        embeddings: Sequence[list[float]],
        metadatas: Sequence[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        self.collection.upsert(
            ids=list(ids),
            documents=list(documents),
            embeddings=list(embeddings),
            metadatas=[_chroma_metadata(metadata) for metadata in metadatas],
        )

    def query(self, *, query_vector: list[float], top_k: int, corpus_key: str) -> list[dict[str, Any]]:
        result = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where={"corpus_key": corpus_key},
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[dict[str, Any]] = []
        for content, metadata, distance in zip(documents, metadatas, distances, strict=False):
            if not str(content).strip():
                continue
            hits.append(
                {
                    "score": round(1.0 - float(distance), 4),
                    "content": str(content).strip(),
                    "metadata": dict(metadata or {}),
                }
            )
        return hits


def _chroma_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    clean: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


def clear_rag_cache() -> None:
    _RAG_RETRIEVER_CACHE.clear()


def get_rag_retriever(corpus_dir: str | Path | None = None) -> "LocalRAGRetriever":
    resolved_dir = resolve_corpus_dir(corpus_dir)
    cache_key = (
        str(resolved_dir),
        _corpus_signature(resolved_dir),
        _embedding_signature(),
        RAG_CHUNK_SIZE,
        RAG_CHUNK_OVERLAP,
    )
    cached = _RAG_RETRIEVER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    _RAG_RETRIEVER_CACHE.clear()
    retriever = LocalRAGRetriever(resolved_dir)
    _RAG_RETRIEVER_CACHE[cache_key] = retriever
    return retriever


class LocalRAGRetriever:
    """Load, chunk, vectorize, and retrieve local course documents."""

    def __init__(self, corpus_dir: str | Path | None = None, embeddings: Embeddings | None = None) -> None:
        self.corpus_dir = resolve_corpus_dir(corpus_dir)
        self.vector_store_requested_provider = settings.rag_vector_store_provider.strip().lower() or "memory"
        self.vector_store_effective_provider = self.vector_store_requested_provider
        self.vector_store_fallback_reason = ""
        self.vector_store: ChromaVectorStore | SQLiteVectorStore | None = self._build_vector_store()
        self.vector_store_hits = 0
        self.vector_store_misses = 0
        if embeddings is None:
            self.embeddings, self.embedding_info = build_embeddings()
        else:
            self.embeddings = embeddings
            self.embedding_info = {
                "embedding_provider": embeddings.__class__.__name__,
                "embedding_model": "",
                "embedding_configured_provider": "custom",
                "embedding_configured_model": "",
                "embedding_base_url": "",
                "embedding_batch_size": "",
                "embedding_fallback_reason": "",
            }
        self.documents = split_documents(load_documents(self.corpus_dir))
        self.corpus_key = self._build_corpus_key()
        self.vectors = self._embed_documents()
        self._update_vector_store_info()

    def _build_vector_store(self) -> ChromaVectorStore | SQLiteVectorStore | None:
        provider = self.vector_store_requested_provider
        if provider in _CHROMA_VECTOR_STORE_PROVIDERS:
            available, reason = _chroma_runtime_available()
            if not available:
                self.vector_store_effective_provider = "sqlite"
                self.vector_store_fallback_reason = reason
                return SQLiteVectorStore(_vector_store_dir() / "rag_vectors.sqlite3")
            self.vector_store_effective_provider = "chroma"
            return ChromaVectorStore(_vector_store_dir())
        if provider not in {"sqlite", "local-sqlite", "persistent-sqlite"}:
            self.vector_store_effective_provider = "memory"
            return None
        self.vector_store_effective_provider = "sqlite"
        return SQLiteVectorStore(_vector_store_dir() / "rag_vectors.sqlite3")

    def _update_vector_store_info(self) -> None:
        path = ""
        if isinstance(self.vector_store, ChromaVectorStore):
            path = str(self.vector_store.persist_dir)
        elif isinstance(self.vector_store, SQLiteVectorStore):
            path = str(self.vector_store.db_path)
        self.embedding_info.update(
            {
                "vector_store_provider": self.vector_store_effective_provider,
                "vector_store_requested_provider": self.vector_store_requested_provider,
                "vector_store_effective_provider": self.vector_store_effective_provider,
                "vector_store_fallback_reason": self.vector_store_fallback_reason,
                "vector_store_path": path,
                "vector_store_hits": str(self.vector_store_hits),
                "vector_store_misses": str(self.vector_store_misses),
            }
        )

    def _build_corpus_key(self) -> str:
        raw = {
            "corpus_dir": str(self.corpus_dir),
            "corpus_signature": _corpus_signature(self.corpus_dir),
            "embedding_provider": self.embedding_info.get("embedding_provider", ""),
            "embedding_model": self.embedding_info.get("embedding_model", ""),
            "embedding_base_url": self.embedding_info.get("embedding_base_url", ""),
            "chunk_size": RAG_CHUNK_SIZE,
            "chunk_overlap": RAG_CHUNK_OVERLAP,
        }
        return hashlib.sha256(_stable_json(raw).encode("utf-8")).hexdigest()

    def _document_texts(self) -> list[str]:
        return [str(getattr(document, "page_content", "")) for document in self.documents]

    def _embed_documents(self) -> list[list[float]]:
        texts = self._document_texts()
        if not texts:
            return []
        if isinstance(self.vector_store, ChromaVectorStore):
            try:
                self._upsert_chroma_documents(texts)
                return []
            except Exception as exc:
                if not str(exc).startswith("embedding_request_failed:"):
                    raise
                self._fallback_to_hash(str(exc))
                self._upsert_chroma_documents(texts)
                return []
        if self.vector_store is not None:
            try:
                return self._embed_documents_with_vector_store(texts)
            except Exception as exc:
                if not str(exc).startswith("embedding_request_failed:"):
                    raise
                self._fallback_to_hash(str(exc))
                return self._embed_documents_with_vector_store(texts)
        try:
            return self.embeddings.embed_documents(texts)
        except Exception as exc:
            self._fallback_to_hash(f"embedding_request_failed:{exc.__class__.__name__}")
            return self.embeddings.embed_documents(texts)

    def _document_vector_ids(self) -> list[str]:
        embedding_key = {
            "provider": self.embedding_info.get("embedding_provider", ""),
            "model": self.embedding_info.get("embedding_model", ""),
            "base_url": self.embedding_info.get("embedding_base_url", ""),
            "chunk_size": RAG_CHUNK_SIZE,
            "chunk_overlap": RAG_CHUNK_OVERLAP,
            "corpus_dir": str(self.corpus_dir),
        }
        ids: list[str] = []
        for index, document in enumerate(self.documents):
            content = str(getattr(document, "page_content", ""))
            metadata = dict(getattr(document, "metadata", {}) or {})
            raw = {
                **embedding_key,
                "index": index,
                "source": metadata.get("source", ""),
                "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            ids.append(hashlib.sha256(_stable_json(raw).encode("utf-8")).hexdigest())
        return ids

    def _embed_documents_with_vector_store(self, texts: list[str]) -> list[list[float]]:
        if self.vector_store is None:
            return self.embeddings.embed_documents(texts)
        vector_ids = self._document_vector_ids()
        cached = self.vector_store.get_many(vector_ids)
        self.vector_store_hits = sum(1 for vector_id in vector_ids if vector_id in cached)
        missing_indexes = [
            index for index, vector_id in enumerate(vector_ids) if vector_id not in cached
        ]
        self.vector_store_misses = len(missing_indexes)
        if missing_indexes:
            try:
                missing_vectors = self.embeddings.embed_documents([texts[index] for index in missing_indexes])
            except Exception as exc:
                raise RuntimeError(f"embedding_request_failed:{exc.__class__.__name__}") from exc
            self.vector_store.set_many(
                [
                    (vector_ids[index], vector)
                    for index, vector in zip(missing_indexes, missing_vectors, strict=True)
                ]
            )
            for index, vector in zip(missing_indexes, missing_vectors, strict=True):
                cached[vector_ids[index]] = vector
        return [cached[vector_id] for vector_id in vector_ids]

    def _document_metadatas(self, vector_ids: Sequence[str]) -> list[dict[str, Any]]:
        metadatas: list[dict[str, Any]] = []
        for index, (document, vector_id) in enumerate(zip(self.documents, vector_ids, strict=True)):
            metadata = dict(getattr(document, "metadata", {}) or {})
            metadata.update(
                {
                    "corpus_key": self.corpus_key,
                    "vector_id": vector_id,
                    "chunk_index": index,
                    "chunk_size": RAG_CHUNK_SIZE,
                    "chunk_overlap": RAG_CHUNK_OVERLAP,
                }
            )
            metadatas.append(metadata)
        return metadatas

    def _upsert_chroma_documents(self, texts: list[str]) -> None:
        if not isinstance(self.vector_store, ChromaVectorStore):
            return
        vector_ids = self._document_vector_ids()
        existing_ids = self.vector_store.get_existing_ids(vector_ids, corpus_key=self.corpus_key)
        self.vector_store_hits = sum(1 for vector_id in vector_ids if vector_id in existing_ids)
        missing_indexes = [
            index for index, vector_id in enumerate(vector_ids) if vector_id not in existing_ids
        ]
        self.vector_store_misses = len(missing_indexes)
        if not missing_indexes:
            return
        try:
            missing_vectors = self.embeddings.embed_documents([texts[index] for index in missing_indexes])
        except Exception as exc:
            raise RuntimeError(f"embedding_request_failed:{exc.__class__.__name__}") from exc
        all_metadatas = self._document_metadatas(vector_ids)
        self.vector_store.upsert_many(
            ids=[vector_ids[index] for index in missing_indexes],
            documents=[texts[index] for index in missing_indexes],
            embeddings=missing_vectors,
            metadatas=[all_metadatas[index] for index in missing_indexes],
        )

    def _fallback_to_hash(self, reason: str) -> None:
        if isinstance(self.embeddings, HashEmbeddings):
            raise RuntimeError(reason)
        configured_provider = self.embedding_info.get("embedding_configured_provider", "custom")
        self.embeddings = HashEmbeddings()
        self.embedding_info = _local_embedding_info(
            configured_provider=configured_provider,
            reason=reason,
        )
        if hasattr(self, "documents"):
            self.corpus_key = self._build_corpus_key()
        self._update_vector_store_info()

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not query.strip() or not self.documents:
            return []
        try:
            query_vector = self.embeddings.embed_query(query)
        except Exception as exc:
            self._fallback_to_hash(f"query_embedding_failed:{exc.__class__.__name__}")
            self.vectors = self._embed_documents()
            query_vector = self.embeddings.embed_query(query)
        return self.retrieve_by_vector(query_vector, top_k=top_k)

    def retrieve_by_vector(self, query_vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        if isinstance(self.vector_store, ChromaVectorStore):
            return self.vector_store.query(
                query_vector=query_vector,
                top_k=top_k,
                corpus_key=self.corpus_key,
            )
        if not self.vectors:
            return []
        scored = [
            (_cosine(query_vector, vector), document)
            for document, vector in zip(self.documents, self.vectors, strict=False)
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        hits: list[dict[str, Any]] = []
        for score, document in scored[:top_k]:
            content = str(getattr(document, "page_content", "")).strip()
            if not content:
                continue
            hits.append(
                {
                    "score": round(float(score), 4),
                    "content": content,
                    "metadata": dict(getattr(document, "metadata", {}) or {}),
                }
            )
        return hits


def build_rag_context(query: str, *, corpus_dir: str | Path | None = None, top_k: int = 3) -> dict[str, Any]:
    retriever = get_rag_retriever(corpus_dir)
    hits = retriever.retrieve(query, top_k=top_k)
    context = "\n\n".join(
        f"[{index}] 来源：{hit['metadata'].get('source', 'local')}；内容：{hit['content']}"
        for index, hit in enumerate(hits, 1)
    )
    return {
        "query": query,
        "corpus_dir": str(retriever.corpus_dir),
        "document_count": len(retriever.documents),
        "hits": hits,
        "context": context,
        "chunk_size": RAG_CHUNK_SIZE,
        "chunk_overlap": RAG_CHUNK_OVERLAP,
        "uses_langchain_documents": LangChainDocument is not None,
        "uses_langchain_splitter": RecursiveCharacterTextSplitter is not None,
        **retriever.embedding_info,
    }
