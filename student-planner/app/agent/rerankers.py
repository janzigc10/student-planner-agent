"""Reranker interfaces for course-material RAG."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any, Sequence

try:  # pragma: no cover - optional runtime dependency
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


class RerankerError(RuntimeError):
    """Base error for reranker configuration, requests, or response contracts."""


class RerankerUnavailableError(RerankerError):
    """Raised when the requested reranker cannot be called."""


class RerankerResponseError(RerankerError):
    """Raised when a provider returns an invalid ranking response."""


class Reranker(ABC):
    provider: str

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: Sequence[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Return ranked candidate copies with provider score and final rank."""


class LocalFeatureReranker(Reranker):
    """Deterministic compatibility baseline over precomputed retrieval features."""

    provider = "local-feature-rerank"

    def rerank(
        self,
        query: str,
        candidates: Sequence[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        del query
        ranked: list[dict[str, Any]] = []
        for raw_candidate in candidates:
            candidate = deepcopy(raw_candidate)
            rerank_score = (
                0.28 * float(candidate.get("hybrid_norm") or 0.0)
                + 0.20 * float(candidate.get("vector_norm") or 0.0)
                + 0.20 * float(candidate.get("bm25_norm") or 0.0)
                + 0.14 * float(candidate.get("anchor_coverage") or 0.0)
                + 0.10 * float(candidate.get("segment_coverage") or 0.0)
                + 0.08 * float(candidate.get("exact_term_coverage") or 0.0)
            )
            candidate.update(
                {
                    "score": round(rerank_score, 6),
                    "rerank_provider": self.provider,
                    "rerank_score": round(rerank_score, 6),
                }
            )
            ranked.append(candidate)
        ranked.sort(
            key=lambda hit: (
                float(hit.get("rerank_score") or 0.0),
                float(hit.get("hybrid_score") or 0.0),
                float(hit.get("bm25_score") or 0.0),
                float(hit.get("vector_score") or 0.0),
                str((hit.get("metadata") or {}).get("chunk_id") or ""),
            ),
            reverse=True,
        )
        return _with_final_ranks(ranked[: max(0, top_n)])


class Qwen3Reranker(Reranker):
    """Alibaba Cloud qwen3-rerank adapter through its OpenAI-compatible endpoint."""

    provider = "qwen3-rerank"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "qwen3-rerank",
        timeout_seconds: float = 20.0,
        instruct: str = "",
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise RerankerUnavailableError("qwen3_reranker_missing_api_key")
        if not base_url.strip():
            raise RerankerUnavailableError("qwen3_reranker_missing_base_url")
        if client is None:
            if OpenAI is None:
                raise RerankerUnavailableError("openai_package_not_installed")
            client = OpenAI(
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                timeout=timeout_seconds,
            )
        self.client = client
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.instruct = instruct
        self.last_call_info: dict[str, Any] = {}

    def rerank(
        self,
        query: str,
        candidates: Sequence[dict[str, Any]],
        top_n: int,
    ) -> list[dict[str, Any]]:
        if not candidates or top_n <= 0:
            self.last_call_info = {
                "model": self.model,
                "candidate_count": len(candidates),
                "returned_count": 0,
                "usage_total_tokens": 0,
            }
            return []
        documents = [str(candidate.get("content") or "") for candidate in candidates]
        if any(not document.strip() for document in documents):
            raise RerankerResponseError("qwen3_reranker_empty_candidate")

        body: dict[str, Any] = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        }
        if self.instruct.strip():
            body["instruct"] = self.instruct.strip()
        try:
            response = self.client.post("/reranks", body=body, cast_to=object)
        except Exception as exc:
            raise RerankerUnavailableError(
                f"qwen3_reranker_request_failed:{exc.__class__.__name__}"
            ) from exc

        payload = _response_payload(response)
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise RerankerResponseError("qwen3_reranker_results_missing")

        ranked: list[dict[str, Any]] = []
        seen_indexes: set[int] = set()
        for raw_result in raw_results:
            result = _response_payload(raw_result)
            try:
                index = int(result["index"])
                score = float(result["relevance_score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RerankerResponseError("qwen3_reranker_result_invalid") from exc
            if index < 0 or index >= len(candidates) or index in seen_indexes:
                raise RerankerResponseError("qwen3_reranker_index_invalid")
            seen_indexes.add(index)
            candidate = deepcopy(candidates[index])
            candidate.update(
                {
                    "score": round(score, 8),
                    "rerank_provider": self.provider,
                    "rerank_score": round(score, 8),
                    "rerank_input_index": index,
                }
            )
            ranked.append(candidate)

        expected_count = min(top_n, len(candidates))
        if len(ranked) != expected_count:
            raise RerankerResponseError(
                f"qwen3_reranker_result_count:{len(ranked)}:{expected_count}"
            )
        usage = _response_payload(payload.get("usage") or {})
        self.last_call_info = {
            "id": str(payload.get("id") or ""),
            "model": str(payload.get("model") or self.model),
            "candidate_count": len(candidates),
            "returned_count": len(ranked),
            "usage_total_tokens": int(usage.get("total_tokens") or 0),
        }
        return _with_final_ranks(ranked)


def _response_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _with_final_ranks(candidates: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for final_rank, raw_candidate in enumerate(candidates, 1):
        candidate = deepcopy(raw_candidate)
        candidate["final_rank"] = final_rank
        metadata = dict(candidate.get("metadata") or {})
        candidate.setdefault("chunk_id", metadata.get("chunk_id"))
        candidate.setdefault("source", metadata.get("source"))
        ranked.append(candidate)
    return ranked
