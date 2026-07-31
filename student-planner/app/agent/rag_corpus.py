"""Frozen course-corpus normalization, chunking, and artifact contracts."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:  # pragma: no cover - optional import is exercised in integration tests
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    RecursiveCharacterTextSplitter = None


CORPUS_SCHEMA_VERSION = "course-rag-corpus-v1"
NORMALIZER_VERSION = "course-rag-normalize-v1"
CHUNKER_VERSION = "course-rag-chunker-v1"
CHUNK_ID_VERSION = "course-rag-chunk-v1"
DEFAULT_CORPUS_VERSION = "rag-course-v1"
CHUNK_SIZE = 520
CHUNK_OVERLAP = 150
CHUNK_SEPARATORS = ("\n\n", "\n", "。", "！", "？", "；", "，", " ", "")
REQUIRED_METADATA = (
    "course_id",
    "chapter_id",
    "material_type",
    "synthetic",
    "corpus_version",
)
ARTIFACT_NAMES = {"corpus_manifest.json", "chunks.jsonl"}


@dataclass(frozen=True)
class CourseSource:
    source_id: str
    body: str
    metadata: dict[str, Any]
    source_sha256: str


@dataclass(frozen=True)
class CourseChunk:
    chunk_id: str
    source_id: str
    chunk_index: int
    text: str
    text_sha256: str
    metadata: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "chunk_index": self.chunk_index,
            "text": self.text,
            "text_sha256": self.text_sha256,
            "metadata": self.metadata,
        }


class CorpusContractError(ValueError):
    """Raised when source files or frozen artifacts violate the corpus contract."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    """Apply course-rag-normalize-v1 to source or chunk text."""

    normalized = str(value or "")
    if normalized.startswith("\ufeff"):
        normalized = normalized[1:]
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return normalized.strip()


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the deliberately small scalar-only YAML subset used by the corpus."""

    normalized = normalize_text(text)
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, normalized
    closing_index = next(
        (index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise CorpusContractError("front_matter_missing_closing_delimiter")

    metadata: dict[str, Any] = {}
    for line_number, line in enumerate(lines[1:closing_index], 2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise CorpusContractError(f"front_matter_invalid_line:{line_number}")
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise CorpusContractError(f"front_matter_empty_key:{line_number}")
        if key in metadata:
            raise CorpusContractError(f"front_matter_duplicate_key:{key}")
        metadata[key] = _parse_scalar(raw_value)
    body = normalize_text("\n".join(lines[closing_index + 1 :]))
    return metadata, body


def _is_source_file(path: Path) -> bool:
    return (
        path.is_file()
        and path.suffix.lower() in {".md", ".txt"}
        and path.name not in ARTIFACT_NAMES
        and not path.name.startswith("RAG_")
    )


def source_id_for(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CorpusContractError(f"source_outside_corpus:{path}") from exc
    return relative.as_posix()


def load_course_sources(
    root: str | Path,
    *,
    strict_metadata: bool = False,
) -> list[CourseSource]:
    corpus_root = Path(root)
    if not corpus_root.exists():
        return []

    sources: list[CourseSource] = []
    for path in sorted(
        (candidate for candidate in corpus_root.rglob("*") if _is_source_file(candidate)),
        key=lambda candidate: source_id_for(candidate, corpus_root),
    ):
        raw = path.read_text(encoding="utf-8")
        metadata, body = parse_front_matter(raw)
        if not body:
            continue
        source_id = source_id_for(path, corpus_root)
        if strict_metadata:
            missing = [key for key in REQUIRED_METADATA if key not in metadata]
            if missing:
                raise CorpusContractError(
                    f"missing_metadata:{source_id}:{','.join(missing)}"
                )
            if metadata.get("synthetic") is not True:
                raise CorpusContractError(f"synthetic_flag_required:{source_id}")
        metadata = {
            **metadata,
            "source": source_id,
            "source_id": source_id,
            "file_name": path.name,
        }
        sources.append(
            CourseSource(
                source_id=source_id,
                body=body,
                metadata=metadata,
                source_sha256=sha256_text(body),
            )
        )
    return sources


def _build_splitter() -> Any:
    if RecursiveCharacterTextSplitter is None:
        raise RuntimeError("langchain-text-splitters is required for course-rag-chunker-v1")
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        keep_separator=True,
        separators=list(CHUNK_SEPARATORS),
        is_separator_regex=False,
        strip_whitespace=True,
    )


def stable_chunk_id(source_id: str, chunk_index: int, text: str) -> str:
    normalized_chunk = normalize_text(text)
    text_hash = sha256_text(normalized_chunk)
    raw = f"{CHUNK_ID_VERSION}\n{source_id}\n{chunk_index}\n{text_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def chunk_course_sources(sources: Iterable[CourseSource]) -> list[CourseChunk]:
    splitter = _build_splitter()
    chunks: list[CourseChunk] = []
    for source in sorted(sources, key=lambda item: item.source_id):
        raw_chunks = splitter.split_text(source.body)
        for chunk_index, raw_chunk in enumerate(raw_chunks):
            text = normalize_text(raw_chunk)
            if not text:
                continue
            text_hash = sha256_text(text)
            chunk_id = stable_chunk_id(source.source_id, chunk_index, text)
            metadata = {
                **source.metadata,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "normalizer_version": NORMALIZER_VERSION,
                "chunker_version": CHUNKER_VERSION,
            }
            chunks.append(
                CourseChunk(
                    chunk_id=chunk_id,
                    source_id=source.source_id,
                    chunk_index=chunk_index,
                    text=text,
                    text_sha256=text_hash,
                    metadata=metadata,
                )
            )
    return chunks


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_corpus_manifest(
    sources: list[CourseSource],
    chunks: list[CourseChunk],
) -> dict[str, Any]:
    corpus_versions = {
        str(source.metadata.get("corpus_version") or DEFAULT_CORPUS_VERSION)
        for source in sources
    }
    if len(corpus_versions) > 1:
        raise CorpusContractError(
            f"mixed_corpus_versions:{','.join(sorted(corpus_versions))}"
        )
    corpus_version = next(iter(corpus_versions), DEFAULT_CORPUS_VERSION)
    source_rows = [
        {
            "source_id": source.source_id,
            "source_sha256": source.source_sha256,
            "metadata": {
                key: value
                for key, value in source.metadata.items()
                if key not in {"source", "source_id", "file_name"}
            },
        }
        for source in sources
    ]
    chunk_set_sha256 = sha256_text("\n".join(chunk.chunk_id for chunk in chunks))
    manifest_core = {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "corpus_version": corpus_version,
        "normalizer": {
            "version": NORMALIZER_VERSION,
            "unicode": "NFC",
            "newlines": "LF",
            "strip_trailing_whitespace": True,
            "front_matter_in_chunks": False,
        },
        "chunker": {
            "version": CHUNKER_VERSION,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "length_function": "len",
            "keep_separator": True,
            "separators": list(CHUNK_SEPARATORS),
        },
        "source_count": len(sources),
        "chunk_count": len(chunks),
        "chunk_set_sha256": chunk_set_sha256,
        "sources": source_rows,
    }
    return {
        **manifest_core,
        "manifest_sha256": sha256_text(_stable_json(manifest_core)),
    }


def build_corpus_artifacts(
    root: str | Path,
    *,
    strict_metadata: bool = True,
) -> tuple[dict[str, Any], list[CourseChunk]]:
    sources = load_course_sources(root, strict_metadata=strict_metadata)
    chunks = chunk_course_sources(sources)
    return build_corpus_manifest(sources, chunks), chunks


def write_corpus_artifacts(
    root: str | Path,
    *,
    strict_metadata: bool = True,
) -> tuple[Path, Path, dict[str, Any]]:
    corpus_root = Path(root)
    manifest, chunks = build_corpus_artifacts(
        corpus_root,
        strict_metadata=strict_metadata,
    )
    manifest_path = corpus_root / "corpus_manifest.json"
    chunks_path = corpus_root / "chunks.jsonl"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    chunks_path.write_text(
        "".join(
            json.dumps(chunk.to_json(), ensure_ascii=False, sort_keys=True) + "\n"
            for chunk in chunks
        ),
        encoding="utf-8",
    )
    return manifest_path, chunks_path, manifest


def load_frozen_chunks(
    root: str | Path,
    *,
    verify_sources: bool = True,
) -> tuple[dict[str, Any], list[CourseChunk]]:
    corpus_root = Path(root)
    manifest_path = corpus_root / "corpus_manifest.json"
    chunks_path = corpus_root / "chunks.jsonl"
    if not manifest_path.exists() or not chunks_path.exists():
        raise CorpusContractError("frozen_corpus_artifacts_missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_manifest_hash = manifest.get("manifest_sha256")
    manifest_core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if raw_manifest_hash != sha256_text(_stable_json(manifest_core)):
        raise CorpusContractError("manifest_hash_mismatch")

    chunks: list[CourseChunk] = []
    for line_number, line in enumerate(chunks_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        text = normalize_text(str(row["text"]))
        chunk = CourseChunk(
            chunk_id=str(row["chunk_id"]),
            source_id=str(row["source_id"]),
            chunk_index=int(row["chunk_index"]),
            text=text,
            text_sha256=str(row["text_sha256"]),
            metadata=dict(row.get("metadata") or {}),
        )
        if chunk.text_sha256 != sha256_text(text):
            raise CorpusContractError(f"chunk_text_hash_mismatch:{line_number}")
        expected_id = stable_chunk_id(chunk.source_id, chunk.chunk_index, text)
        if chunk.chunk_id != expected_id:
            raise CorpusContractError(f"chunk_id_mismatch:{line_number}")
        chunks.append(chunk)

    if int(manifest.get("chunk_count", -1)) != len(chunks):
        raise CorpusContractError("manifest_chunk_count_mismatch")
    if manifest.get("chunk_set_sha256") != sha256_text(
        "\n".join(chunk.chunk_id for chunk in chunks)
    ):
        raise CorpusContractError("chunk_set_hash_mismatch")

    if verify_sources:
        current_sources = load_course_sources(corpus_root, strict_metadata=True)
        current_rows = {
            source.source_id: source.source_sha256 for source in current_sources
        }
        manifest_rows = {
            str(row["source_id"]): str(row["source_sha256"])
            for row in manifest.get("sources", [])
        }
        if current_rows != manifest_rows:
            raise CorpusContractError("corpus_sources_changed_rebuild_required")

    return manifest, chunks


def frozen_chunk_documents(root: str | Path) -> list[dict[str, Any]]:
    """Return runtime-neutral document dictionaries from frozen or ad-hoc sources."""

    corpus_root = Path(root)
    try:
        _, chunks = load_frozen_chunks(corpus_root)
    except CorpusContractError as exc:
        if str(exc) != "frozen_corpus_artifacts_missing":
            raise
        sources = load_course_sources(corpus_root, strict_metadata=False)
        chunks = chunk_course_sources(sources)
    return [
        {
            "page_content": chunk.text,
            "metadata": {
                **chunk.metadata,
                "source": chunk.source_id,
                "source_id": chunk.source_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
            },
        }
        for chunk in chunks
    ]
