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
from threading import Lock
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agent.rag_corpus import (
    CHUNK_OVERLAP as COURSE_RAG_CHUNK_OVERLAP,
    CHUNK_SEPARATORS as COURSE_RAG_CHUNK_SEPARATORS,
    CHUNK_SIZE as COURSE_RAG_CHUNK_SIZE,
    frozen_chunk_documents,
    load_course_sources,
    normalize_text,
    stable_chunk_id,
)
from app.agent.rerankers import (
    LocalFeatureReranker,
    Qwen3Reranker,
    RerankerError,
)
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
RAG_CHUNK_SIZE = COURSE_RAG_CHUNK_SIZE
RAG_CHUNK_OVERLAP = COURSE_RAG_CHUNK_OVERLAP
RAG_CONTEXT_EXCERPT_CHARS = 260
RAG_EVIDENCE_CANDIDATE_K = 10
RAG_VECTOR_CANDIDATE_K = 20
RAG_BM25_CANDIDATE_K = 20
RAG_RRF_K = 60
BM25_K1 = 1.5
BM25_B = 0.75
RAG_MIN_EVIDENCE_SCORE = 0.08
RAG_MIN_EVIDENCE_COVERAGE = 0.7
RAG_MIN_EVIDENCE_SEGMENT_COVERAGE = 0.6
RAG_MAX_EVIDENCE_UNMATCHED_RUN = 2
RAG_MIN_EVIDENCE_ANCHOR_COVERAGE = 0.45
CHROMA_COLLECTION_NAME = "student_planner_rag"
RAG_MAX_QUERY_CHARS = 8000
RAG_MAX_QUERY_BYTES = 32000
RAG_RETRIEVAL_MODES = {
    "embedding_only",
    "bm25_only",
    "hybrid_rrf",
    "hybrid_rerank",
}
_RAG_RETRIEVER_CACHE: dict[tuple[Any, ...], "LocalRAGRetriever"] = {}
_RAG_BUILD_LOCK = Lock()
_CHROMA_RUNTIME_PROBE: tuple[bool, str] | None = None
_RAG_QUERY_STOP_FRAGMENTS = {
    "什么时候开始",
    "哪一年开始",
    "何时开始",
    "是什么",
    "什么",
    "怎么",
    "如何",
    "为什么",
    "时候",
    "怎样",
    "解释",
    "说明",
    "总结",
    "梳理",
    "最新",
    "新闻",
    "当前",
    "今天",
    "明天",
    "最近",
}
_RAG_QUERY_STOP_CHARS = set("的是了呢吗吧啊和与在有中对就都而及或")
_RAG_SHORT_ANCHOR_TERMS = {
    "宪法",
    "冷战",
    "北约",
    "华约",
    "五四",
    "民主",
    "法治",
    "鸦片",
    "抗日",
    "国共",
}
_RAG_QUERY_SEGMENT_SEPARATORS = (
    "以及",
    "还有",
    "或者",
    "并且",
    "和",
    "与",
    "及",
    "或",
    "、",
)


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
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def _tokenize(text: str) -> list[str]:
    value = str(text or "")
    if len(value) > RAG_MAX_QUERY_CHARS or len(value.encode("utf-8")) > RAG_MAX_QUERY_BYTES:
        raise ValueError("rag_query_too_long")
    latin_tokens = re.findall(r"[a-z0-9]+", value.lower())
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", value)
    chinese_ngrams: list[str] = []
    if len(chinese_chars) == 1:
        chinese_ngrams.extend(chinese_chars)
    for size in (2, 3, 4):
        chinese_ngrams.extend(
            "".join(chinese_chars[index : index + size])
            for index in range(max(len(chinese_chars) - size + 1, 0))
        )
    return latin_tokens + chinese_ngrams


def _truncate_context_excerpt(text: str, limit: int = RAG_CONTEXT_EXCERPT_CHARS) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _context_excerpt(content: str, query: str, limit: int = RAG_CONTEXT_EXCERPT_CHARS) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?；;])\s*|\n+", str(content or ""))
        if sentence.strip()
    ]
    if not sentences:
        return ""

    query_terms = {token for token in _tokenize(query) if len(token) >= 2}
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        score = sum(1 for token in query_terms if token in sentence)
        if score > 0:
            scored.append((score, index, sentence))

    if not scored:
        return _truncate_context_excerpt(sentences[0], limit)

    _, _, best_sentence = max(scored, key=lambda item: (item[0], -item[1]))
    return _truncate_context_excerpt(best_sentence, limit)


def _salient_query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for raw_token in _tokenize(query):
        token = raw_token.strip().lower()
        if len(token) < 2:
            continue
        if token in _RAG_QUERY_STOP_FRAGMENTS:
            continue
        if any(fragment in token for fragment in _RAG_QUERY_STOP_FRAGMENTS):
            continue
        if len(token) <= 2 and any(char in _RAG_QUERY_STOP_CHARS for char in token):
            continue
        terms.add(token)
    return terms


def _matched_evidence_terms(query: str, content: str) -> list[str]:
    content_text = str(content or "").lower()
    return sorted(term for term in _salient_query_terms(query) if term in content_text)


def _anchor_query_terms(query: str) -> set[str]:
    strong_terms = {
        term
        for term in _salient_query_terms(query)
        if _has_strong_evidence_term([term])
    }
    return {
        term
        for term in strong_terms
        if not any(term != other and term in other for other in strong_terms)
    }


def _contentful_query_chars(query: str) -> set[str]:
    compact = str(query or "").lower()
    for fragment in sorted(_RAG_QUERY_STOP_FRAGMENTS, key=len, reverse=True):
        compact = compact.replace(fragment, "")
    ignored_chars = _RAG_QUERY_STOP_CHARS | set("里我你请帮")
    return {
        char
        for char in compact
        if char.isalnum() and char not in ignored_chars
    }


def _evidence_query_coverage(query: str, content: str) -> float:
    required_chars = _contentful_query_chars(query)
    if not required_chars:
        return 0.0
    content_text = str(content or "").lower()
    matched_chars = {char for char in required_chars if char in content_text}
    return len(matched_chars) / len(required_chars)


def _query_segment_char_sets(query: str) -> list[set[str]]:
    compact = str(query or "").lower()
    for fragment in sorted(_RAG_QUERY_STOP_FRAGMENTS, key=len, reverse=True):
        compact = compact.replace(fragment, " ")
    for separator in _RAG_QUERY_SEGMENT_SEPARATORS:
        compact = compact.replace(separator, " ")

    ignored_chars = _RAG_QUERY_STOP_CHARS | set("里我你请帮")
    normalized = "".join(
        char if char.isalnum() and char not in ignored_chars else " "
        for char in compact
    )
    return [
        set(segment)
        for segment in normalized.split()
        if len(set(segment)) >= 2
    ]


def _evidence_segment_coverage(query: str, content: str) -> float:
    segment_char_sets = _query_segment_char_sets(query)
    if not segment_char_sets:
        return 0.0
    content_text = str(content or "").lower()
    segment_coverages = [
        len({char for char in segment_chars if char in content_text}) / len(segment_chars)
        for segment_chars in segment_char_sets
    ]
    return min(segment_coverages)


def _longest_unmatched_query_run(query: str, content: str) -> int:
    compact = str(query or "").lower()
    for fragment in sorted(_RAG_QUERY_STOP_FRAGMENTS, key=len, reverse=True):
        compact = compact.replace(fragment, " ")

    ignored_chars = _RAG_QUERY_STOP_CHARS | set("里我你请帮")
    content_text = str(content or "").lower()
    current_run = 0
    longest_run = 0
    for char in compact:
        if not char.isalnum() or char in ignored_chars:
            current_run = 0
            continue
        if char in content_text:
            current_run = 0
            continue
        current_run += 1
        longest_run = max(longest_run, current_run)
    return longest_run


def _evidence_anchor_coverage(query: str, content: str) -> float:
    anchors = _anchor_query_terms(query)
    if not anchors:
        return 0.0
    content_text = str(content or "").lower()
    matched_anchors = {term for term in anchors if term in content_text}
    return len(matched_anchors) / len(anchors)


def _has_strong_evidence_term(terms: Sequence[str]) -> bool:
    return any(
        len(term) >= 3
        or term in _RAG_SHORT_ANCHOR_TERMS
        or (term.isascii() and any(char.isalpha() for char in term) and len(term) >= 4)
        for term in terms
    )


def _evidence_score(hit: dict[str, Any]) -> float:
    try:
        return float(hit.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_evidence_hit(query: str, hit: dict[str, Any]) -> bool:
    content = str(hit.get("content") or "")
    matched_terms = _matched_evidence_terms(query, content)
    if not matched_terms:
        return False
    if _evidence_score(hit) < RAG_MIN_EVIDENCE_SCORE:
        return False
    if _evidence_query_coverage(query, content) < RAG_MIN_EVIDENCE_COVERAGE:
        return False
    if _evidence_segment_coverage(query, content) < RAG_MIN_EVIDENCE_SEGMENT_COVERAGE:
        return False
    if _longest_unmatched_query_run(query, content) > RAG_MAX_EVIDENCE_UNMATCHED_RUN:
        return False
    return _has_strong_evidence_term(matched_terms) or len(matched_terms) >= 2


def _document_identity(content: str, metadata: dict[str, Any]) -> str:
    chunk_id = metadata.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    vector_id = metadata.get("vector_id")
    if vector_id:
        return str(vector_id)
    source = str(metadata.get("source") or "")
    chunk_index = metadata.get("chunk_index")
    if chunk_index is not None:
        return f"{source}:{chunk_index}"
    digest = hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()
    return f"{source}:{digest}"


def _normalize_score(value: float, *, lower: float = 0.0, upper: float = 1.0) -> float:
    if upper <= lower:
        return 0.0
    normalized = (value - lower) / (upper - lower)
    return max(0.0, min(1.0, normalized))


class OpenAICompatibleEmbeddings(Embeddings):
    """Embedding adapter for Bailian/DashScope and other OpenAI-compatible APIs."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        batch_size: int = 10,
        dimensions: int | None = None,
    ) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package is not installed")
        self.model = model
        self.base_url = base_url
        self.batch_size = max(1, min(batch_size, 10))
        self.dimensions = dimensions
        self.last_call_usage_tokens = 0
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        usage_tokens = 0
        for offset in range(0, len(texts), self.batch_size):
            batch = list(texts[offset : offset + self.batch_size])
            response = None
            for attempt in range(3):
                try:
                    request: dict[str, Any] = {"model": self.model, "input": batch}
                    if self.dimensions:
                        request["dimensions"] = self.dimensions
                    response = self.client.embeddings.create(**request)
                    break
                except Exception:
                    if attempt >= 2:
                        raise
                    time.sleep(1.0 + attempt * 2.0)
            if response is None:  # pragma: no cover - defensive guard
                raise RuntimeError("embedding response missing")
            usage = getattr(response, "usage", None)
            usage_tokens += int(getattr(usage, "total_tokens", 0) or 0)
            data = sorted(response.data, key=lambda item: item.index)
            vectors.extend(list(item.embedding) for item in data)
        self.last_call_usage_tokens = usage_tokens
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
        "embedding_dimensions": str(settings.rag_embedding_dimensions),
        "embedding_query_instruct": settings.rag_embedding_query_instruct,
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
                dimensions=settings.rag_embedding_dimensions,
            ),
            {
                "embedding_provider": provider,
                "embedding_model": settings.rag_embedding_model,
                "embedding_configured_provider": provider,
                "embedding_configured_model": settings.rag_embedding_model,
                "embedding_base_url": settings.rag_embedding_base_url,
                "embedding_batch_size": str(settings.rag_embedding_batch_size),
                "embedding_dimensions": str(settings.rag_embedding_dimensions),
                "embedding_query_instruct": settings.rag_embedding_query_instruct,
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
    return [
        _document(source.body, dict(source.metadata))
        for source in load_course_sources(root, strict_metadata=False)
    ]


def split_documents(documents: list[Any]) -> list[Any]:
    if not documents:
        return []
    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=RAG_CHUNK_SIZE,
            chunk_overlap=RAG_CHUNK_OVERLAP,
            length_function=len,
            keep_separator=True,
            separators=list(COURSE_RAG_CHUNK_SEPARATORS),
            is_separator_regex=False,
            strip_whitespace=True,
        )
        chunks: list[Any] = []
        for document in documents:
            content = str(getattr(document, "page_content", ""))
            metadata = dict(getattr(document, "metadata", {}) or {})
            source = str(metadata.get("source_id") or metadata.get("source") or "")
            for chunk_index, raw_chunk in enumerate(splitter.split_text(content)):
                text = normalize_text(raw_chunk)
                if not text:
                    continue
                chunk_id = stable_chunk_id(source, chunk_index, text)
                chunks.append(
                    _document(
                        text,
                        {
                            **metadata,
                            "source": source,
                            "source_id": source,
                            "chunk_id": chunk_id,
                            "chunk_index": chunk_index,
                        },
                    )
                )
        return chunks

    chunks: list[Any] = []
    for document in documents:
        content = str(getattr(document, "page_content", ""))
        metadata = dict(getattr(document, "metadata", {}) or {})
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
        for index, paragraph in enumerate(paragraphs):
            source = str(metadata.get("source_id") or metadata.get("source") or "")
            text = normalize_text(paragraph)
            chunks.append(
                _document(
                    text,
                    {
                        **metadata,
                        "source": source,
                        "source_id": source,
                        "chunk_id": stable_chunk_id(source, index, text),
                        "chunk_index": index,
                    },
                )
            )
    return chunks


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _corpus_signature(corpus_dir: Path) -> tuple[tuple[str, str], ...]:
    if not corpus_dir.exists():
        return ()
    entries: list[tuple[str, str]] = []
    for path in sorted(corpus_dir.rglob("*")):
        if _is_corpus_content_file(path):
            content = path.read_bytes()
            entries.append(
                (
                    str(path.relative_to(corpus_dir)),
                    hashlib.sha256(content).hexdigest(),
                )
            )
    return tuple(entries)


def _embedding_signature() -> tuple[str, str, str, bool, int, int, str, str, str]:
    return (
        settings.rag_embedding_provider.strip().lower(),
        settings.rag_embedding_model,
        settings.rag_embedding_base_url,
        bool(settings.rag_embedding_api_key.strip()),
        settings.rag_embedding_batch_size,
        settings.rag_embedding_dimensions,
        settings.rag_embedding_query_instruct,
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
    with _RAG_BUILD_LOCK:
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
        self.last_retrieval_info: dict[str, Any] = {}
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
                "embedding_dimensions": "",
                "embedding_query_instruct": "",
                "embedding_fallback_reason": "",
            }
        self.documents = [
            _document(row["page_content"], dict(row["metadata"]))
            for row in frozen_chunk_documents(self.corpus_dir)
        ]
        self._document_tokens = [_tokenize(text) for text in self._document_texts()]
        self._bm25_doc_freqs = self._build_bm25_doc_freqs()
        self._bm25_avg_doc_len = (
            sum(len(tokens) for tokens in self._document_tokens) / len(self._document_tokens)
            if self._document_tokens
            else 0.0
        )
        self.corpus_key = self._build_corpus_key()
        self.vectors = self._embed_documents()
        self._update_vector_store_info()

    def _build_bm25_doc_freqs(self) -> dict[str, int]:
        doc_freqs: dict[str, int] = {}
        for tokens in self._document_tokens:
            for token in set(tokens):
                doc_freqs[token] = doc_freqs.get(token, 0) + 1
        return doc_freqs

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
            "corpus_signature": _corpus_signature(self.corpus_dir),
            "embedding_provider": self.embedding_info.get("embedding_provider", ""),
            "embedding_model": self.embedding_info.get("embedding_model", ""),
            "embedding_base_url": self.embedding_info.get("embedding_base_url", ""),
            "embedding_dimensions": self.embedding_info.get("embedding_dimensions", ""),
            "embedding_query_instruct": self.embedding_info.get(
                "embedding_query_instruct",
                "",
            ),
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
            "dimensions": self.embedding_info.get("embedding_dimensions", ""),
            "query_instruct": self.embedding_info.get("embedding_query_instruct", ""),
            "chunk_size": RAG_CHUNK_SIZE,
            "chunk_overlap": RAG_CHUNK_OVERLAP,
        }
        ids: list[str] = []
        for index, document in enumerate(self.documents):
            content = str(getattr(document, "page_content", ""))
            metadata = dict(getattr(document, "metadata", {}) or {})
            chunk_index = int(metadata.get("chunk_index", index))
            chunk_id = str(
                metadata.get("chunk_id")
                or stable_chunk_id(
                    str(metadata.get("source") or ""),
                    chunk_index,
                    content,
                )
            )
            raw = {
                **embedding_key,
                "chunk_id": chunk_id,
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
            metadata.setdefault("chunk_index", index)
            metadata.setdefault(
                "chunk_id",
                stable_chunk_id(
                    str(metadata.get("source") or ""),
                    int(metadata["chunk_index"]),
                    str(getattr(document, "page_content", "")),
                ),
            )
            metadata.update(
                {
                    "corpus_key": self.corpus_key,
                    "vector_id": vector_id,
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

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        *,
        mode: str | None = None,
        allow_reranker_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        if not query.strip() or not self.documents:
            self.last_retrieval_info = {
                "retrieval_mode": mode or settings.rag_retrieval_mode,
                "reranker_provider": "none",
                "reranker_fallback_reason": "",
            }
            return []
        retrieval_mode = (mode or settings.rag_retrieval_mode).strip().lower()
        if retrieval_mode not in RAG_RETRIEVAL_MODES:
            raise ValueError(f"unsupported_rag_retrieval_mode:{retrieval_mode}")
        vector_top_k = max(top_k, RAG_VECTOR_CANDIDATE_K)
        bm25_top_k = max(top_k, RAG_BM25_CANDIDATE_K)
        vector_hits: list[dict[str, Any]] = []
        bm25_hits: list[dict[str, Any]] = []
        if retrieval_mode in {"embedding_only", "hybrid_rrf", "hybrid_rerank"}:
            try:
                query_vector = self.embeddings.embed_query(query)
            except Exception as exc:
                self._fallback_to_hash(f"query_embedding_failed:{exc.__class__.__name__}")
                self.vectors = self._embed_documents()
                query_vector = self.embeddings.embed_query(query)
            vector_hits = self.retrieve_by_vector(query_vector, top_k=vector_top_k)
        if retrieval_mode in {"bm25_only", "hybrid_rrf", "hybrid_rerank"}:
            bm25_hits = self.retrieve_by_bm25(query, top_k=bm25_top_k)

        self.last_retrieval_info = {
            "retrieval_mode": retrieval_mode,
            "reranker_provider": "none",
            "reranker_fallback_reason": "",
            "reranker_model": "",
            "reranker_usage_total_tokens": 0,
        }
        if retrieval_mode == "embedding_only":
            return self._rank_single_source(query, vector_hits, top_k=top_k)
        if retrieval_mode == "bm25_only":
            return self._rank_single_source(query, bm25_hits, top_k=top_k)

        rrf_candidates = self._rrf_fuse(
            vector_hits=vector_hits,
            bm25_hits=bm25_hits,
        )
        if retrieval_mode == "hybrid_rrf":
            return self._rank_rrf(query, rrf_candidates, top_k=top_k)
        return self._rerank_hybrid_candidates(
            query,
            rrf_candidates=rrf_candidates[:RAG_EVIDENCE_CANDIDATE_K * 2],
            top_k=top_k,
            allow_fallback=allow_reranker_fallback,
        )

    def retrieve_by_vector(self, query_vector: list[float], top_k: int = 3) -> list[dict[str, Any]]:
        if isinstance(self.vector_store, ChromaVectorStore):
            hits = self.vector_store.query(
                query_vector=query_vector,
                top_k=top_k,
                corpus_key=self.corpus_key,
            )
            for rank, hit in enumerate(hits, 1):
                hit["vector_rank"] = rank
                hit["vector_score"] = float(hit.get("score") or 0.0)
                hit["retrieval_sources"] = ["vector"]
            return hits
        if not self.vectors:
            return []
        scored = [
            (_cosine(query_vector, vector), index, document)
            for index, (document, vector) in enumerate(zip(self.documents, self.vectors, strict=False))
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        hits: list[dict[str, Any]] = []
        for rank, (score, index, document) in enumerate(scored[:top_k], 1):
            content = str(getattr(document, "page_content", "")).strip()
            if not content:
                continue
            metadata = dict(getattr(document, "metadata", {}) or {})
            metadata.setdefault("chunk_index", index)
            hits.append(
                {
                    "score": round(float(score), 4),
                    "vector_score": round(float(score), 4),
                    "vector_rank": rank,
                    "retrieval_sources": ["vector"],
                    "content": content,
                    "metadata": metadata,
                }
            )
        return hits

    def retrieve_by_bm25(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        if not query_tokens or not self._document_tokens:
            return []
        scored: list[tuple[float, int, Any]] = []
        for index, (document, doc_tokens) in enumerate(zip(self.documents, self._document_tokens, strict=False)):
            score = self._bm25_score(query_tokens, doc_tokens)
            if score <= 0:
                continue
            scored.append((score, index, document))
        scored.sort(key=lambda item: item[0], reverse=True)

        hits: list[dict[str, Any]] = []
        for rank, (score, index, document) in enumerate(scored[:top_k], 1):
            content = str(getattr(document, "page_content", "")).strip()
            if not content:
                continue
            metadata = dict(getattr(document, "metadata", {}) or {})
            metadata.setdefault("chunk_index", index)
            hits.append(
                {
                    "score": round(float(score), 4),
                    "bm25_score": round(float(score), 4),
                    "bm25_rank": rank,
                    "retrieval_sources": ["bm25"],
                    "content": content,
                    "metadata": metadata,
                }
            )
        return hits

    def _bm25_score(self, query_tokens: Sequence[str], doc_tokens: Sequence[str]) -> float:
        if not doc_tokens or not self._bm25_avg_doc_len:
            return 0.0
        doc_len = len(doc_tokens)
        term_counts: dict[str, int] = {}
        for token in doc_tokens:
            term_counts[token] = term_counts.get(token, 0) + 1
        score = 0.0
        total_docs = len(self._document_tokens)
        for token in set(query_tokens):
            freq = term_counts.get(token, 0)
            if freq <= 0:
                continue
            doc_freq = self._bm25_doc_freqs.get(token, 0)
            idf = math.log(1.0 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denominator = freq + BM25_K1 * (1.0 - BM25_B + BM25_B * doc_len / self._bm25_avg_doc_len)
            score += idf * (freq * (BM25_K1 + 1.0)) / denominator
        return score

    def _rank_single_source(
        self,
        query: str,
        hits: Sequence[dict[str, Any]],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for final_rank, raw_hit in enumerate(hits[:top_k], 1):
            hit = dict(raw_hit)
            metadata = dict(hit.get("metadata") or {})
            content = str(hit.get("content") or "")
            hit.update(
                {
                    "chunk_id": metadata.get("chunk_id"),
                    "source": metadata.get("source"),
                    "final_rank": final_rank,
                    "rerank_provider": "none",
                    "query_coverage": round(
                        _evidence_query_coverage(query, content),
                        4,
                    ),
                    "segment_coverage": round(
                        _evidence_segment_coverage(query, content),
                        4,
                    ),
                    "anchor_coverage": round(
                        _evidence_anchor_coverage(query, content),
                        4,
                    ),
                    "unmatched_run": _longest_unmatched_query_run(query, content),
                }
            )
            ranked.append(hit)
        return ranked

    def _rrf_fuse(
        self,
        *,
        vector_hits: list[dict[str, Any]],
        bm25_hits: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}

        def add_hit(hit: dict[str, Any], *, source: str, rank: int) -> None:
            content = str(hit.get("content") or "")
            metadata = dict(hit.get("metadata") or {})
            identity = _document_identity(content, metadata)
            candidate = candidates.setdefault(
                identity,
                {
                    "content": content,
                    "metadata": metadata,
                    "retrieval_sources": [],
                    "vector_score": 0.0,
                    "bm25_score": 0.0,
                    "vector_rank": None,
                    "bm25_rank": None,
                    "hybrid_score": 0.0,
                },
            )
            if source not in candidate["retrieval_sources"]:
                candidate["retrieval_sources"].append(source)
            candidate["hybrid_score"] += 1.0 / (RAG_RRF_K + rank)
            if source == "vector":
                candidate["vector_rank"] = rank
                candidate["vector_score"] = float(hit.get("vector_score", hit.get("score") or 0.0) or 0.0)
            if source == "bm25":
                candidate["bm25_rank"] = rank
                candidate["bm25_score"] = float(hit.get("bm25_score", hit.get("score") or 0.0) or 0.0)

        for rank, hit in enumerate(vector_hits, 1):
            add_hit(hit, source="vector", rank=rank)
        for rank, hit in enumerate(bm25_hits, 1):
            add_hit(hit, source="bm25", rank=rank)

        fused = list(candidates.values())
        fused.sort(
            key=lambda hit: (
                float(hit.get("hybrid_score") or 0.0),
                float(hit.get("bm25_score") or 0.0),
                float(hit.get("vector_score") or 0.0),
                str((hit.get("metadata") or {}).get("chunk_id") or ""),
            ),
            reverse=True,
        )
        return fused

    def _rank_rrf(
        self,
        query: str,
        candidates: Sequence[dict[str, Any]],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for final_rank, raw_hit in enumerate(candidates[:top_k], 1):
            hit = dict(raw_hit)
            metadata = dict(hit.get("metadata") or {})
            content = str(hit.get("content") or "")
            hybrid_score = float(hit.get("hybrid_score") or 0.0)
            hit.update(
                {
                    "score": round(hybrid_score, 8),
                    "hybrid_score": round(hybrid_score, 8),
                    "chunk_id": metadata.get("chunk_id"),
                    "source": metadata.get("source"),
                    "final_rank": final_rank,
                    "rerank_provider": "none",
                    "query_coverage": round(
                        _evidence_query_coverage(query, content),
                        4,
                    ),
                    "segment_coverage": round(
                        _evidence_segment_coverage(query, content),
                        4,
                    ),
                    "anchor_coverage": round(
                        _evidence_anchor_coverage(query, content),
                        4,
                    ),
                    "unmatched_run": _longest_unmatched_query_run(query, content),
                }
            )
            ranked.append(hit)
        return ranked

    def _feature_candidates(
        self,
        query: str,
        candidates: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        max_hybrid_score = max(
            float(hit.get("hybrid_score") or 0.0) for hit in candidates
        ) or 1.0
        max_bm25_score = max(
            float(hit.get("bm25_score") or 0.0) for hit in candidates
        ) or 1.0
        enriched: list[dict[str, Any]] = []
        for raw_hit in candidates:
            hit = dict(raw_hit)
            vector_norm = _normalize_score(float(hit["vector_score"]), lower=-1.0, upper=1.0)
            bm25_norm = _normalize_score(float(hit["bm25_score"]), upper=max_bm25_score)
            hybrid_norm = _normalize_score(float(hit["hybrid_score"]), upper=max_hybrid_score)
            content = str(hit.get("content") or "")
            anchor_coverage = _evidence_anchor_coverage(query, content)
            segment_coverage = _evidence_segment_coverage(query, content)
            query_coverage = _evidence_query_coverage(query, content)
            unmatched_run = _longest_unmatched_query_run(query, content)
            matched_terms = _matched_evidence_terms(query, content)
            exact_term_coverage = min(1.0, len(matched_terms) / max(1, len(_salient_query_terms(query))))
            hit.update(
                {
                    "hybrid_score": round(float(hit["hybrid_score"]), 6),
                    "vector_score": round(float(hit["vector_score"]), 4),
                    "bm25_score": round(float(hit["bm25_score"]), 4),
                    "vector_norm": round(vector_norm, 6),
                    "bm25_norm": round(bm25_norm, 6),
                    "hybrid_norm": round(hybrid_norm, 6),
                    "anchor_coverage": round(anchor_coverage, 4),
                    "segment_coverage": round(segment_coverage, 4),
                    "query_coverage": round(query_coverage, 4),
                    "unmatched_run": unmatched_run,
                    "exact_term_coverage": round(exact_term_coverage, 4),
                    "matched_terms": matched_terms,
                }
            )
            enriched.append(hit)
        return enriched

    def _rerank_hybrid_candidates(
        self,
        query: str,
        *,
        rrf_candidates: Sequence[dict[str, Any]],
        top_k: int,
        allow_fallback: bool,
    ) -> list[dict[str, Any]]:
        enriched = self._feature_candidates(query, rrf_candidates)
        fallback_reason = ""
        try:
            reranker = Qwen3Reranker(
                api_key=settings.rag_reranker_api_key,
                base_url=settings.rag_reranker_base_url,
                model=settings.rag_reranker_model,
                timeout_seconds=settings.rag_reranker_timeout_seconds,
                instruct=settings.rag_reranker_instruct,
            )
            ranked = reranker.rerank(query, enriched, top_k)
            self.last_retrieval_info.update(
                {
                    "reranker_provider": reranker.provider,
                    "reranker_model": reranker.last_call_info.get(
                        "model",
                        settings.rag_reranker_model,
                    ),
                    "reranker_usage_total_tokens": reranker.last_call_info.get(
                        "usage_total_tokens",
                        0,
                    ),
                }
            )
            return ranked
        except RerankerError as exc:
            fallback_reason = str(exc)
            if not allow_fallback:
                raise

        reranker = LocalFeatureReranker()
        ranked = reranker.rerank(query, enriched, top_k)
        self.last_retrieval_info.update(
            {
                "reranker_provider": reranker.provider,
                "reranker_model": "",
                "reranker_fallback_reason": fallback_reason,
                "reranker_usage_total_tokens": 0,
            }
        )
        return ranked

    def _hybrid_rerank(
        self,
        query: str,
        *,
        vector_hits: list[dict[str, Any]],
        bm25_hits: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Compatibility helper for the previous local feature rerank tests."""

        candidates = self._rrf_fuse(
            vector_hits=vector_hits,
            bm25_hits=bm25_hits,
        )
        return LocalFeatureReranker().rerank(
            query,
            self._feature_candidates(query, candidates),
            top_k,
        )


def build_rag_context(
    query: str,
    *,
    corpus_dir: str | Path | None = None,
    top_k: int = 3,
    retrieval_mode: str | None = None,
    allow_reranker_fallback: bool = True,
) -> dict[str, Any]:
    if len(str(query or "")) > RAG_MAX_QUERY_CHARS or len(str(query or "").encode("utf-8")) > RAG_MAX_QUERY_BYTES:
        raise ValueError("rag_query_too_long")
    retriever = get_rag_retriever(corpus_dir)
    candidate_top_k = max(top_k, RAG_EVIDENCE_CANDIDATE_K)
    candidate_hits = retriever.retrieve(
        query,
        top_k=candidate_top_k,
        mode=retrieval_mode,
        allow_reranker_fallback=allow_reranker_fallback,
    )
    hits = candidate_hits[:top_k]
    evidence_hits = [hit for hit in candidate_hits if _is_evidence_hit(query, hit)]
    context_hits = evidence_hits[:top_k]
    evidence_terms = sorted(
        {
            term
            for hit in evidence_hits
            for term in _matched_evidence_terms(query, str(hit.get("content") or ""))
        }
    )
    evidence_top_score = max((_evidence_score(hit) for hit in candidate_hits), default=0.0)
    evidence_best_score = max((_evidence_score(hit) for hit in evidence_hits), default=0.0)
    evidence_top_coverage = max(
        (_evidence_query_coverage(query, str(hit.get("content") or "")) for hit in candidate_hits),
        default=0.0,
    )
    evidence_best_coverage = max(
        (_evidence_query_coverage(query, str(hit.get("content") or "")) for hit in evidence_hits),
        default=0.0,
    )
    evidence_top_segment_coverage = max(
        (_evidence_segment_coverage(query, str(hit.get("content") or "")) for hit in candidate_hits),
        default=0.0,
    )
    evidence_best_segment_coverage = max(
        (_evidence_segment_coverage(query, str(hit.get("content") or "")) for hit in evidence_hits),
        default=0.0,
    )
    evidence_top_unmatched_run = max(
        (_longest_unmatched_query_run(query, str(hit.get("content") or "")) for hit in candidate_hits),
        default=0,
    )
    evidence_best_unmatched_run = max(
        (_longest_unmatched_query_run(query, str(hit.get("content") or "")) for hit in evidence_hits),
        default=0,
    )
    evidence_top_anchor_coverage = max(
        (_evidence_anchor_coverage(query, str(hit.get("content") or "")) for hit in candidate_hits),
        default=0.0,
    )
    evidence_best_anchor_coverage = max(
        (_evidence_anchor_coverage(query, str(hit.get("content") or "")) for hit in evidence_hits),
        default=0.0,
    )
    evidence_sufficient = bool(evidence_hits)
    if evidence_sufficient:
        evidence_reason = "sufficient"
    elif candidate_hits:
        evidence_reason = "no_relevant_local_evidence"
    else:
        evidence_reason = "no_local_evidence"
    context = "\n\n".join(
        f"[{index}] 来源：{hit['metadata'].get('source', 'local')}；内容：{_context_excerpt(hit['content'], query)}"
        for index, hit in enumerate(context_hits, 1)
    )
    return {
        "query": query,
        "corpus_dir": str(retriever.corpus_dir),
        "document_count": len(retriever.documents),
        "retrieval_mode": retriever.last_retrieval_info.get(
            "retrieval_mode",
            retrieval_mode or settings.rag_retrieval_mode,
        ),
        "reranker_provider": retriever.last_retrieval_info.get(
            "reranker_provider",
            "none",
        ),
        "reranker_model": retriever.last_retrieval_info.get("reranker_model", ""),
        "reranker_fallback_reason": retriever.last_retrieval_info.get(
            "reranker_fallback_reason",
            "",
        ),
        "reranker_usage_total_tokens": retriever.last_retrieval_info.get(
            "reranker_usage_total_tokens",
            0,
        ),
        "requested_top_k": top_k,
        "candidate_top_k": candidate_top_k,
        "vector_candidate_top_k": max(candidate_top_k, RAG_VECTOR_CANDIDATE_K),
        "bm25_candidate_top_k": max(candidate_top_k, RAG_BM25_CANDIDATE_K),
        "rrf_k": RAG_RRF_K,
        "hits": hits,
        "candidate_hits": candidate_hits,
        "evidence_hits": evidence_hits,
        "evidence_context_count": len(context_hits),
        "evidence_sufficient": evidence_sufficient,
        "evidence_count": len(evidence_hits),
        "evidence_reason": evidence_reason,
        "evidence_top_score": round(evidence_top_score, 4),
        "evidence_best_score": round(evidence_best_score, 4),
        "evidence_top_coverage": round(evidence_top_coverage, 4),
        "evidence_best_coverage": round(evidence_best_coverage, 4),
        "evidence_top_segment_coverage": round(evidence_top_segment_coverage, 4),
        "evidence_best_segment_coverage": round(evidence_best_segment_coverage, 4),
        "evidence_top_unmatched_run": evidence_top_unmatched_run,
        "evidence_best_unmatched_run": evidence_best_unmatched_run,
        "evidence_top_anchor_coverage": round(evidence_top_anchor_coverage, 4),
        "evidence_best_anchor_coverage": round(evidence_best_anchor_coverage, 4),
        "evidence_terms": evidence_terms,
        "evidence_min_score": RAG_MIN_EVIDENCE_SCORE,
        "evidence_min_coverage": RAG_MIN_EVIDENCE_COVERAGE,
        "evidence_min_segment_coverage": RAG_MIN_EVIDENCE_SEGMENT_COVERAGE,
        "evidence_max_unmatched_run": RAG_MAX_EVIDENCE_UNMATCHED_RUN,
        "evidence_min_anchor_coverage": RAG_MIN_EVIDENCE_ANCHOR_COVERAGE,
        "context": context,
        "chunk_size": RAG_CHUNK_SIZE,
        "chunk_overlap": RAG_CHUNK_OVERLAP,
        "uses_langchain_documents": LangChainDocument is not None,
        "uses_langchain_splitter": RecursiveCharacterTextSplitter is not None,
        **retriever.embedding_info,
    }
