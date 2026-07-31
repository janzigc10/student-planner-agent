from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag import (
    RAG_BM25_CANDIDATE_K,
    RAG_EVIDENCE_CANDIDATE_K,
    RAG_RETRIEVAL_MODES,
    RAG_RRF_K,
    RAG_VECTOR_CANDIDATE_K,
    clear_rag_cache,
    get_rag_retriever,
)
from app.agent.rag_corpus import load_frozen_chunks
from app.agent.rag_evaluation import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_GATE_GRID,
    PRIMARY_RANKING_METRICS,
    EvaluationContractError,
    apply_frozen_gate,
    bootstrap_metric_intervals,
    calibrate_gate,
    dataset_sha256,
    evaluate_ranked_query,
    load_evaluation_queries,
    paired_bootstrap_comparisons,
    summarize_ranking_rows_by_split,
    write_rows_jsonl,
    write_summary_csv,
)
from app.config import settings


DEFAULT_MODES = (
    "embedding_only",
    "bm25_only",
    "hybrid_rrf",
    "hybrid_rerank",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: Any) -> str:
    rendered = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _git_value(args: list[str], *, default: str = "") -> str:
    completed = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else default


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package_name in ("langchain", "langgraph", "openai", "chromadb"):
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = "not-installed"
    return versions


def _ensure_empty_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise EvaluationContractError(
            f"output_directory_must_be_empty:{output_dir.resolve()}"
        )


def _validate_formal_preflight(
    *,
    output_dir: Path,
    modes: tuple[str, ...],
    allow_reranker_fallback: bool,
) -> None:
    _ensure_empty_output_dir(output_dir)
    if tuple(modes) != DEFAULT_MODES:
        raise EvaluationContractError("formal_run_requires_all_four_modes_in_order")
    if allow_reranker_fallback:
        raise EvaluationContractError("formal_run_forbids_reranker_fallback")
    git_status = _git_value(["status", "--short"], default="git-status-unavailable")
    if git_status:
        raise EvaluationContractError("formal_run_requires_clean_git")
    if settings.rag_embedding_provider != "dashscope":
        raise EvaluationContractError(
            "formal_run_requires_dashscope_embedding_provider"
        )
    if not settings.rag_embedding_api_key:
        raise EvaluationContractError("formal_run_requires_embedding_api_key")
    if settings.rag_reranker_provider != "qwen3":
        raise EvaluationContractError("formal_run_requires_qwen3_reranker")
    if not settings.rag_reranker_api_key:
        raise EvaluationContractError("formal_run_requires_reranker_api_key")
    if not settings.rag_reranker_base_url:
        raise EvaluationContractError("formal_run_requires_reranker_base_url")


def _validate_formal_retriever_runtime(retriever: Any) -> None:
    embedding_info = dict(getattr(retriever, "embedding_info", {}) or {})
    if embedding_info.get("embedding_fallback_reason"):
        raise EvaluationContractError("formal_run_forbids_embedding_fallback")
    if embedding_info.get("embedding_provider") != "dashscope":
        raise EvaluationContractError(
            "formal_run_requires_effective_dashscope_embedding"
        )
    requested_vector_store = str(
        embedding_info.get("vector_store_requested_provider") or ""
    )
    effective_vector_store = str(
        embedding_info.get("vector_store_effective_provider") or ""
    )
    if requested_vector_store != effective_vector_store:
        raise EvaluationContractError("formal_run_forbids_vector_store_fallback")


def _json_hit(hit: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(hit.get("metadata") or {})
    return {
        "chunk_id": str(hit.get("chunk_id") or metadata.get("chunk_id") or ""),
        "source_id": str(
            hit.get("source")
            or metadata.get("source_id")
            or metadata.get("source")
            or ""
        ).replace("\\", "/"),
        "course_id": metadata.get("course_id"),
        "chapter_id": metadata.get("chapter_id"),
        "material_type": metadata.get("material_type"),
        "final_rank": hit.get("final_rank"),
        "score": hit.get("score"),
        "vector_rank": hit.get("vector_rank"),
        "vector_score": hit.get("vector_score"),
        "bm25_rank": hit.get("bm25_rank"),
        "bm25_score": hit.get("bm25_score"),
        "rrf_score": hit.get("hybrid_score"),
        "rerank_provider": hit.get("rerank_provider"),
        "rerank_score": hit.get("rerank_score"),
        "query_coverage": hit.get("query_coverage"),
        "segment_coverage": hit.get("segment_coverage"),
        "anchor_coverage": hit.get("anchor_coverage"),
        "unmatched_run": hit.get("unmatched_run"),
        "content": str(hit.get("content") or ""),
    }


def _validate_dataset_against_corpus(
    queries: list[Any],
    *,
    corpus_manifest: dict[str, Any],
    chunks: list[Any],
    dataset_manifest: dict[str, Any],
) -> None:
    if dataset_manifest.get("corpus_manifest_sha256") != corpus_manifest.get(
        "manifest_sha256"
    ):
        raise EvaluationContractError("dataset_corpus_manifest_mismatch")
    if dataset_manifest.get("dataset_sha256") != dataset_sha256(queries):
        raise EvaluationContractError("dataset_content_hash_mismatch")
    dataset_chunk_ids = {chunk.chunk_id for chunk in chunks}
    dataset_source_ids = {chunk.source_id for chunk in chunks}
    for query in queries:
        missing_chunks = {
            qrel.chunk_id
            for qrel in query.qrels
            if qrel.chunk_id not in dataset_chunk_ids
        }
        if missing_chunks:
            raise EvaluationContractError(
                f"qrels_reference_unknown_chunks:{query.query_id}:"
                + ",".join(sorted(missing_chunks))
            )
        missing_sources = set(query.relevant_source_ids) - dataset_source_ids
        if missing_sources:
            raise EvaluationContractError(
                f"query_references_unknown_sources:{query.query_id}:"
                + ",".join(sorted(missing_sources))
            )
        if query.split not in {"development", "test"}:
            raise EvaluationContractError(
                f"query_split_must_be_frozen:{query.query_id}"
            )


def build_frozen_gate_bundle(
    *,
    queries: list[Any],
    gate_results: dict[str, Any],
    corpus_manifest_sha256: str,
    dataset_manifest_sha256: str,
    dataset_content_sha256: str,
    modes: tuple[str, ...],
    formal_run: bool,
    retriever: Any,
) -> dict[str, Any]:
    development_query_ids = sorted(
        query.query_id for query in queries if query.split == "development"
    )
    if not development_query_ids:
        raise EvaluationContractError("gate_bundle_requires_development_queries")
    if set(gate_results) != set(modes):
        raise EvaluationContractError("gate_bundle_modes_mismatch")
    gate_grid = [dict(config) for config in DEFAULT_GATE_GRID]
    return {
        "schema_version": "course-rag-gate-bundle-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "formal_run": formal_run,
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "calibration_split": "development",
        "holdout_used_for_calibration": False,
        "development_query_count": len(development_query_ids),
        "development_query_ids_sha256": _sha256_json(development_query_ids),
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "dataset_sha256": dataset_content_sha256,
        "modes": list(modes),
        "retrieval_contract": {
            "evaluation_top_k": 10,
            "vector_candidate_top_k": RAG_VECTOR_CANDIDATE_K,
            "bm25_candidate_top_k": RAG_BM25_CANDIDATE_K,
            "rrf_k": RAG_RRF_K,
            "reranker_candidate_top_k": RAG_EVIDENCE_CANDIDATE_K * 2,
            "answer_context_top_k": 3,
        },
        "embedding": {
            "provider": settings.rag_embedding_provider,
            "model": settings.rag_embedding_model,
            "dimensions": settings.rag_embedding_dimensions,
            "base_url": settings.rag_embedding_base_url,
            "query_instruct": settings.rag_embedding_query_instruct,
        },
        "vector_store_provider": settings.rag_vector_store_provider,
        "runtime_embedding": {
            "provider": retriever.embedding_info.get("embedding_provider"),
            "model": retriever.embedding_info.get("embedding_model"),
            "fallback_reason": retriever.embedding_info.get(
                "embedding_fallback_reason"
            ),
        },
        "runtime_vector_store": {
            "requested_provider": retriever.embedding_info.get(
                "vector_store_requested_provider"
            ),
            "effective_provider": retriever.embedding_info.get(
                "vector_store_effective_provider"
            ),
            "fallback_reason": retriever.embedding_info.get(
                "vector_store_fallback_reason"
            ),
        },
        "reranker": {
            "provider": settings.rag_reranker_provider,
            "model": settings.rag_reranker_model,
            "base_url": settings.rag_reranker_base_url,
            "instruct": settings.rag_reranker_instruct,
        },
        "gate_parameter_grid_sha256": _sha256_json(gate_grid),
        "gate_configs": {
            mode: dict(gate_results[mode]["development"]["selected_config"])
            for mode in modes
        },
        "calibration": {
            mode: {
                "constraint": gate_results[mode]["development"]["constraint"],
                "constraint_met": gate_results[mode]["development"][
                    "constraint_met"
                ],
                "selected_config_id": gate_results[mode]["development"][
                    "selected_config_id"
                ],
            }
            for mode in modes
        },
    }


def run_evaluation(
    *,
    corpus_dir: Path,
    dataset_path: Path,
    dataset_manifest_path: Path,
    output_dir: Path,
    modes: tuple[str, ...],
    allow_reranker_fallback: bool,
    embedding_cost_per_1k: float,
    reranker_cost_per_1k: float,
    formal_run: bool = False,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    invalid_modes = set(modes) - RAG_RETRIEVAL_MODES
    if invalid_modes:
        raise ValueError(f"unsupported_modes:{','.join(sorted(invalid_modes))}")
    if bootstrap_iterations < 100:
        raise ValueError("bootstrap_iterations_must_be_at_least_100")
    if formal_run:
        _validate_formal_preflight(
            output_dir=output_dir,
            modes=modes,
            allow_reranker_fallback=allow_reranker_fallback,
        )
    else:
        _ensure_empty_output_dir(output_dir)
    corpus_manifest, chunks = load_frozen_chunks(corpus_dir)
    queries = load_evaluation_queries(dataset_path)
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    _validate_dataset_against_corpus(
        queries,
        corpus_manifest=corpus_manifest,
        chunks=chunks,
        dataset_manifest=dataset_manifest,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    clear_rag_cache()
    build_started = time.perf_counter()
    retriever = get_rag_retriever(corpus_dir)
    build_ms = round((time.perf_counter() - build_started) * 1000, 3)
    if formal_run:
        _validate_formal_retriever_runtime(retriever)
    rows_by_mode: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, Any] = {}
    gate_results: dict[str, Any] = {}
    confidence_intervals: dict[str, Any] = {}

    for mode in modes:
        rows: list[dict[str, Any]] = []
        for query in queries:
            started = time.perf_counter()
            hits = retriever.retrieve(
                query.query,
                top_k=10,
                mode=mode,
                allow_reranker_fallback=allow_reranker_fallback,
            )
            if formal_run:
                _validate_formal_retriever_runtime(retriever)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            json_hits = [_json_hit(hit) for hit in hits]
            embedding_tokens = int(
                getattr(retriever.embeddings, "last_call_usage_tokens", 0) or 0
            )
            reranker_tokens = int(
                retriever.last_retrieval_info.get(
                    "reranker_usage_total_tokens",
                    0,
                )
                or 0
            )
            estimated_cost = (
                embedding_tokens / 1000 * embedding_cost_per_1k
                + reranker_tokens / 1000 * reranker_cost_per_1k
            )
            metric_row = evaluate_ranked_query(query, json_hits)
            rows.append(
                {
                    **metric_row,
                    "query": query.query,
                    "split": query.split,
                    "mode": mode,
                    "latency_ms": latency_ms,
                    "embedding_usage_tokens": embedding_tokens,
                    "reranker_usage_tokens": reranker_tokens,
                    "estimated_cost": round(estimated_cost, 10),
                    "reranker_provider": retriever.last_retrieval_info.get(
                        "reranker_provider"
                    ),
                    "reranker_model": retriever.last_retrieval_info.get(
                        "reranker_model"
                    ),
                    "reranker_fallback_reason": retriever.last_retrieval_info.get(
                        "reranker_fallback_reason"
                    ),
                    "hits": json_hits,
                }
            )

        rows_by_mode[mode] = rows
        summaries[mode] = summarize_ranking_rows_by_split(rows)
        development_rows = [row for row in rows if row["split"] == "development"]
        test_rows = [row for row in rows if row["split"] == "test"]
        confidence_intervals[mode] = {
            "test": bootstrap_metric_intervals(
                test_rows,
                metric_names=PRIMARY_RANKING_METRICS,
                iterations=bootstrap_iterations,
                seed=bootstrap_seed,
            )
        }
        calibration = calibrate_gate(development_rows)
        frozen_config = dict(calibration["selected_config"])
        test_gate = apply_frozen_gate(test_rows, frozen_config)
        gate_results[mode] = {
            "development": calibration,
            "test": {
                key: value
                for key, value in test_gate.items()
                if key != "predictions"
            },
            "test_predictions": test_gate["predictions"],
        }
        write_rows_jsonl(output_dir / f"{mode}.jsonl", rows)

    gate_bundle = build_frozen_gate_bundle(
        queries=queries,
        gate_results=gate_results,
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
        dataset_manifest_sha256=_sha256_file(dataset_manifest_path),
        dataset_content_sha256=dataset_manifest["dataset_sha256"],
        modes=modes,
        formal_run=formal_run,
        retriever=retriever,
    )
    gate_bundle_path = output_dir / "frozen_gate_config.json"
    gate_bundle_path.write_text(
        json.dumps(gate_bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    gate_bundle_sha256 = _sha256_file(gate_bundle_path)

    test_rows_by_mode = {
        mode: [row for row in rows if row["split"] == "test"]
        for mode, rows in rows_by_mode.items()
    }
    paired_comparisons = (
        paired_bootstrap_comparisons(
            test_rows_by_mode,
            baseline_mode="embedding_only",
            metric_names=PRIMARY_RANKING_METRICS,
            iterations=bootstrap_iterations,
            seed=bootstrap_seed,
        )
        if "embedding_only" in test_rows_by_mode
        else []
    )
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "ranking": summaries,
                "gate": gate_results,
                "primary_split": "test",
                "test_exposure_status": "internal_test_exposed_by_pilot",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_summary_csv(output_dir / "summary.csv", summaries, split="test")
    (output_dir / "confidence_intervals.json").write_text(
        json.dumps(confidence_intervals, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_paired_comparisons(
        output_dir / "paired_comparisons.csv",
        paired_comparisons,
    )
    _write_chart_data(
        output_dir / "chart_overall.csv",
        summaries,
        gate_results,
        confidence_intervals,
    )
    _write_group_chart_data(
        output_dir / "chart_query_type.csv",
        summaries,
        dimension="query_type",
    )
    _write_group_chart_data(
        output_dir / "chart_answerability.csv",
        summaries,
        dimension="answerability",
    )
    gate_prediction_rows = []
    for mode, gate_result in gate_results.items():
        test_rows = {
            row["query_id"]: row
            for row in rows_by_mode[mode]
            if row["split"] == "test"
        }
        for query_id, prediction in gate_result["test_predictions"].items():
            gate_prediction_rows.append(
                {
                    "mode": mode,
                    "query_id": query_id,
                    "split": "test",
                    "answerability": test_rows[query_id]["answerability"],
                    "expected": (
                        "accept"
                        if test_rows[query_id]["answerability"] == "full"
                        else "reject"
                    ),
                    "prediction": prediction,
                }
            )
    write_rows_jsonl(
        output_dir / "gate_predictions.jsonl",
        gate_prediction_rows,
    )

    output_files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "run_manifest.json"
    )
    run_manifest = {
        "schema_version": "course-rag-run-v2",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "formal_run": formal_run,
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "git_status": _git_value(["status", "--short"]),
        "corpus_dir": str(corpus_dir.resolve()),
        "corpus_manifest_sha256": corpus_manifest["manifest_sha256"],
        "dataset_path": str(dataset_path.resolve()),
        "dataset_manifest_sha256": _sha256_file(dataset_manifest_path),
        "dataset_sha256": dataset_manifest.get("dataset_sha256"),
        "frozen_gate_config_sha256": gate_bundle_sha256,
        "modes": list(modes),
        "top_k": 10,
        "vector_candidate_top_k": RAG_VECTOR_CANDIDATE_K,
        "bm25_candidate_top_k": RAG_BM25_CANDIDATE_K,
        "rrf_k": RAG_RRF_K,
        "answer_context_top_k": 3,
        "allow_reranker_fallback": allow_reranker_fallback,
        "evaluation": {
            "primary_split": "test",
            "development_results_excluded_from_primary_tables": True,
            "test_exposure_status": "internal_test_exposed_by_pilot",
            "evidence_tier": dataset_manifest.get(
                "human_review_status",
                "unknown",
            ),
            "primary_metrics": list(PRIMARY_RANKING_METRICS),
            "bootstrap_iterations": bootstrap_iterations,
            "bootstrap_seed": bootstrap_seed,
            "paired_baseline_mode": "embedding_only",
        },
        "embedding": {
            "provider": settings.rag_embedding_provider,
            "model": settings.rag_embedding_model,
            "base_url": settings.rag_embedding_base_url,
            "dimensions": settings.rag_embedding_dimensions,
            "query_instruct": settings.rag_embedding_query_instruct,
        },
        "runtime_embedding": gate_bundle["runtime_embedding"],
        "vector_store": {
            "configured_provider": settings.rag_vector_store_provider,
            **gate_bundle["runtime_vector_store"],
        },
        "reranker": {
            "provider": settings.rag_reranker_provider,
            "model": settings.rag_reranker_model,
            "base_url": settings.rag_reranker_base_url,
            "instruct": settings.rag_reranker_instruct,
        },
        "cost_rates": {
            "embedding_per_1k_tokens": embedding_cost_per_1k,
            "reranker_per_1k_tokens": reranker_cost_per_1k,
        },
        "retriever_build_ms": build_ms,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": _dependency_versions(),
        },
        "outputs": {
            path.name: {"sha256": _sha256_file(path), "bytes": path.stat().st_size}
            for path in output_files
        },
    }
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return run_manifest


def _write_chart_data(
    path: Path,
    summaries: dict[str, Any],
    gate_results: dict[str, Any],
    confidence_intervals: dict[str, Any],
    *,
    split: str = "test",
) -> None:
    rows = []
    for mode, summary in summaries.items():
        overall = summary[split]["overall"]
        gate = gate_results[mode][split]
        intervals = confidence_intervals[mode][split]
        rows.append(
            {
                "mode": mode,
                "split": split,
                "recall@5": overall.get("recall@5"),
                "recall@5_ci95_low": intervals["recall@5"]["ci95_low"],
                "recall@5_ci95_high": intervals["recall@5"]["ci95_high"],
                "mrr": overall.get("mrr"),
                "mrr_ci95_low": intervals["mrr"]["ci95_low"],
                "mrr_ci95_high": intervals["mrr"]["ci95_high"],
                "ndcg@10": overall.get("ndcg@10"),
                "ndcg@10_ci95_low": intervals["ndcg@10"]["ci95_low"],
                "ndcg@10_ci95_high": intervals["ndcg@10"]["ci95_high"],
                "top1_source_hit": overall.get("top1_source_hit"),
                "complete_evidence_recall@10": overall.get(
                    "complete_evidence_recall@10"
                ),
                "gate_macro_f1": gate.get("macro_f1"),
                "gate_false_accept_rate": gate.get("false_accept_rate"),
                "latency_mean_ms": overall.get("latency_mean_ms"),
                "latency_p95_ms": overall.get("latency_p95_ms"),
                "estimated_cost": overall.get("estimated_cost"),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["mode"])
        writer.writeheader()
        writer.writerows(rows)


def _write_group_chart_data(
    path: Path,
    summaries: dict[str, Any],
    *,
    dimension: str,
    split: str = "test",
) -> None:
    rows: list[dict[str, Any]] = []
    for mode, split_summaries in summaries.items():
        groups = split_summaries[split]["by"].get(dimension, {})
        for value, metrics in groups.items():
            rows.append(
                {
                    "mode": mode,
                    "split": split,
                    dimension: value,
                    "query_count": metrics.get("query_count"),
                    "recall@5": metrics.get("recall@5"),
                    "mrr": metrics.get("mrr"),
                    "ndcg@10": metrics.get("ndcg@10"),
                    "complete_evidence_recall@10": metrics.get(
                        "complete_evidence_recall@10"
                    ),
                    "latency_mean_ms": metrics.get("latency_mean_ms"),
                    "latency_p95_ms": metrics.get("latency_p95_ms"),
                }
            )
    fieldnames = sorted({key for row in rows for key in row}) or [
        "mode",
        "split",
        dimension,
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_paired_comparisons(
    path: Path,
    comparisons: list[dict[str, Any]],
) -> None:
    fieldnames = sorted({key for row in comparisons for key in row}) or [
        "baseline_mode",
        "mode",
        "metric",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparisons)


def write_failure_manifest(
    output_dir: Path,
    *,
    started_at: str,
    corpus_dir: Path,
    dataset_path: Path,
    dataset_manifest_path: Path,
    modes: tuple[str, ...],
    allow_reranker_fallback: bool,
    error: Exception,
    formal_run: bool = False,
) -> dict[str, Any]:
    output_was_nonempty = output_dir.exists() and any(output_dir.iterdir())
    if output_was_nonempty:
        safe_timestamp = (
            started_at.replace(":", "").replace("-", "").replace("+", "_")
        )
        failure_path = output_dir.parent / (
            f"{output_dir.name}.failed_run.{safe_timestamp}.json"
        )
    else:
        failure_path = output_dir / "failed_run.json"
    failure_manifest = {
        "schema_version": "course-rag-run-failure-v2",
        "status": "failed",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "formal_run": formal_run,
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "git_status": _git_value(["status", "--short"]),
        "corpus_dir": str(corpus_dir.resolve()),
        "dataset_path": str(dataset_path.resolve()),
        "dataset_manifest_path": str(dataset_manifest_path.resolve()),
        "requested_output_dir": str(output_dir.resolve()),
        "failure_manifest_path": str(failure_path.resolve()),
        "modes": list(modes),
        "allow_reranker_fallback": allow_reranker_fallback,
        "reranker": {
            "provider": settings.rag_reranker_provider,
            "model": settings.rag_reranker_model,
            "base_url": settings.rag_reranker_base_url,
        },
        "error_type": type(error).__name__,
        "error": str(error),
    }
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        json.dumps(failure_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return failure_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the frozen four-mode course RAG benchmark."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/rag/course_v1"),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/rag/course_v1/golden_queries.jsonl"),
    )
    parser.add_argument(
        "--dataset-manifest",
        type=Path,
        default=Path("data/rag/course_v1/dataset_manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/rag/course_v1"),
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=list(DEFAULT_MODES),
    )
    parser.add_argument(
        "--allow-reranker-fallback",
        action="store_true",
        help="Interactive smoke only. Formal hybrid_rerank runs must not use this.",
    )
    parser.add_argument(
        "--formal",
        action="store_true",
        help=(
            "Enforce clean Git, empty output directory, all four modes, "
            "real online providers, and no fallback."
        ),
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=DEFAULT_BOOTSTRAP_ITERATIONS,
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=DEFAULT_BOOTSTRAP_SEED,
    )
    parser.add_argument("--embedding-cost-per-1k", type=float, default=0.0)
    parser.add_argument("--reranker-cost-per-1k", type=float, default=0.0)
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        manifest = run_evaluation(
            corpus_dir=args.corpus_dir,
            dataset_path=args.dataset,
            dataset_manifest_path=args.dataset_manifest,
            output_dir=args.output_dir,
            modes=tuple(args.modes),
            allow_reranker_fallback=args.allow_reranker_fallback,
            embedding_cost_per_1k=args.embedding_cost_per_1k,
            reranker_cost_per_1k=args.reranker_cost_per_1k,
            formal_run=args.formal,
            bootstrap_iterations=args.bootstrap_iterations,
            bootstrap_seed=args.bootstrap_seed,
        )
    except Exception as error:
        failure_manifest = write_failure_manifest(
            args.output_dir,
            started_at=started_at,
            corpus_dir=args.corpus_dir,
            dataset_path=args.dataset,
            dataset_manifest_path=args.dataset_manifest,
            modes=tuple(args.modes),
            allow_reranker_fallback=args.allow_reranker_fallback,
            error=error,
            formal_run=args.formal,
        )
        print(
            json.dumps(failure_manifest, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
