from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag import clear_rag_cache, get_rag_retriever
from app.agent.rag_corpus import load_frozen_chunks
from app.agent.rag_evaluation import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    DEFAULT_BOOTSTRAP_SEED,
    PRIMARY_RANKING_METRICS,
    EvaluationContractError,
    apply_frozen_gate,
    bootstrap_metric_intervals,
    dataset_sha256,
    evaluate_ranked_query,
    load_evaluation_queries,
    paired_bootstrap_comparisons,
    summarize_ranking_rows_by_split,
    write_rows_jsonl,
    write_summary_csv,
)
from app.config import settings
from scripts.evaluate_course_rag import (
    DEFAULT_MODES,
    _dependency_versions,
    _ensure_empty_output_dir,
    _git_value,
    _json_hit,
    _sha256_file,
    _validate_formal_preflight,
    _validate_formal_retriever_runtime,
    _write_chart_data,
    _write_group_chart_data,
    _write_paired_comparisons,
)
from scripts.validate_course_rag_challenge import validate_challenge_dataset


def _require_equal(actual: Any, expected: Any, error: str) -> None:
    if actual != expected:
        raise EvaluationContractError(error)


def _validate_challenge_retriever_runtime(
    retriever: Any,
    *,
    gate_bundle: dict[str, Any],
    formal_run: bool,
) -> None:
    if formal_run:
        _validate_formal_retriever_runtime(retriever)
    runtime_embedding = gate_bundle.get("runtime_embedding") or {}
    _require_equal(
        retriever.embedding_info.get("embedding_provider"),
        runtime_embedding.get("provider"),
        "challenge_runtime_embedding_provider_mismatch",
    )
    _require_equal(
        retriever.embedding_info.get("embedding_model"),
        runtime_embedding.get("model"),
        "challenge_runtime_embedding_model_mismatch",
    )
    _require_equal(
        retriever.embedding_info.get("embedding_fallback_reason"),
        runtime_embedding.get("fallback_reason"),
        "challenge_runtime_embedding_fallback_mismatch",
    )
    runtime_vector_store = gate_bundle.get("runtime_vector_store") or {}
    _require_equal(
        retriever.embedding_info.get("vector_store_requested_provider"),
        runtime_vector_store.get("requested_provider"),
        "challenge_runtime_vector_store_request_mismatch",
    )
    _require_equal(
        retriever.embedding_info.get("vector_store_effective_provider"),
        runtime_vector_store.get("effective_provider"),
        "challenge_runtime_vector_store_effective_mismatch",
    )
    _require_equal(
        retriever.embedding_info.get("vector_store_fallback_reason"),
        runtime_vector_store.get("fallback_reason"),
        "challenge_runtime_vector_store_fallback_mismatch",
    )


def _validate_gate_bundle_linkage(
    *,
    corpus_manifest: dict[str, Any],
    main_dataset_path: Path,
    main_run_dir: Path,
    challenge_manifest_path: Path,
    challenge_frozen_config_path: Path,
    modes: tuple[str, ...],
    formal_run: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    main_manifest_path = main_run_dir / "run_manifest.json"
    gate_bundle_path = main_run_dir / "frozen_gate_config.json"
    if not main_manifest_path.is_file():
        raise EvaluationContractError("challenge_requires_main_run_manifest")
    if not gate_bundle_path.is_file():
        raise EvaluationContractError("challenge_requires_frozen_gate_bundle")
    main_manifest = json.loads(main_manifest_path.read_text(encoding="utf-8"))
    gate_bundle = json.loads(gate_bundle_path.read_text(encoding="utf-8"))
    challenge_manifest = json.loads(
        challenge_manifest_path.read_text(encoding="utf-8")
    )
    challenge_frozen_config = json.loads(
        challenge_frozen_config_path.read_text(encoding="utf-8")
    )

    gate_bundle_sha256 = _sha256_file(gate_bundle_path)
    _require_equal(
        main_manifest.get("schema_version"),
        "course-rag-run-v2",
        "challenge_main_run_schema_invalid",
    )
    _require_equal(
        gate_bundle.get("schema_version"),
        "course-rag-gate-bundle-v1",
        "challenge_gate_bundle_schema_invalid",
    )
    _require_equal(
        main_manifest.get("frozen_gate_config_sha256"),
        gate_bundle_sha256,
        "challenge_gate_bundle_hash_mismatch",
    )
    _require_equal(
        main_manifest.get("outputs", {})
        .get("frozen_gate_config.json", {})
        .get("sha256"),
        gate_bundle_sha256,
        "challenge_gate_bundle_output_hash_mismatch",
    )
    _require_equal(
        main_manifest.get("corpus_manifest_sha256"),
        corpus_manifest["manifest_sha256"],
        "challenge_main_run_corpus_mismatch",
    )
    _require_equal(
        gate_bundle.get("corpus_manifest_sha256"),
        corpus_manifest["manifest_sha256"],
        "challenge_gate_bundle_corpus_mismatch",
    )
    main_queries = load_evaluation_queries(main_dataset_path)
    main_dataset_sha256 = dataset_sha256(main_queries)
    _require_equal(
        main_manifest.get("dataset_sha256"),
        main_dataset_sha256,
        "challenge_main_dataset_hash_mismatch",
    )
    _require_equal(
        gate_bundle.get("dataset_sha256"),
        main_dataset_sha256,
        "challenge_gate_bundle_dataset_hash_mismatch",
    )
    _require_equal(
        challenge_manifest.get("main_dataset_sha256"),
        main_dataset_sha256,
        "challenge_manifest_main_dataset_hash_mismatch",
    )
    _require_equal(
        challenge_manifest.get("corpus_manifest_sha256"),
        corpus_manifest["manifest_sha256"],
        "challenge_manifest_corpus_mismatch",
    )
    _require_equal(
        challenge_manifest.get("frozen_config_sha256"),
        _sha256_file(challenge_frozen_config_path),
        "challenge_frozen_config_hash_mismatch",
    )
    _require_equal(
        challenge_manifest.get("used_for_tuning"),
        False,
        "challenge_must_not_be_used_for_tuning",
    )
    _require_equal(
        gate_bundle.get("calibration_split"),
        "development",
        "challenge_gate_bundle_must_use_development",
    )
    _require_equal(
        gate_bundle.get("holdout_used_for_calibration"),
        False,
        "challenge_holdout_must_not_be_used_for_calibration",
    )
    _require_equal(
        tuple(main_manifest.get("modes") or ()),
        modes,
        "challenge_main_run_modes_mismatch",
    )
    _require_equal(
        tuple(gate_bundle.get("modes") or ()),
        modes,
        "challenge_gate_bundle_modes_mismatch",
    )
    _require_equal(
        tuple(challenge_frozen_config.get("retrieval_modes") or ()),
        modes,
        "challenge_frozen_modes_mismatch",
    )
    if set(gate_bundle.get("gate_configs") or {}) != set(modes):
        raise EvaluationContractError("challenge_gate_configs_incomplete")

    frozen_retrieval = challenge_frozen_config
    bundle_retrieval = gate_bundle.get("retrieval_contract") or {}
    retrieval_pairs = (
        ("vector_candidate_top_k", "vector_candidate_top_k"),
        ("bm25_candidate_top_k", "bm25_candidate_top_k"),
        ("rrf_k", "rrf_k"),
        ("evaluation_top_k", "evaluation_top_k"),
        ("answer_context_top_k", "answer_context_top_k"),
    )
    for frozen_key, bundle_key in retrieval_pairs:
        _require_equal(
            frozen_retrieval.get(frozen_key),
            bundle_retrieval.get(bundle_key),
            f"challenge_retrieval_contract_mismatch:{frozen_key}",
        )
    _require_equal(
        frozen_retrieval.get("reranker", {}).get("candidate_top_k"),
        bundle_retrieval.get("reranker_candidate_top_k"),
        "challenge_retrieval_contract_mismatch:reranker_candidate_top_k",
    )
    _require_equal(
        frozen_retrieval.get("evidence_gate", {}).get(
            "parameter_grid_sha256"
        ),
        gate_bundle.get("gate_parameter_grid_sha256"),
        "challenge_gate_parameter_grid_mismatch",
    )

    frozen_embedding = frozen_retrieval.get("embedding") or {}
    bundle_embedding = gate_bundle.get("embedding") or {}
    current_embedding = {
        "provider": settings.rag_embedding_provider,
        "model": settings.rag_embedding_model,
        "dimensions": settings.rag_embedding_dimensions,
        "base_url": settings.rag_embedding_base_url,
        "query_instruct": settings.rag_embedding_query_instruct,
    }
    for key in ("provider", "model", "dimensions"):
        _require_equal(
            frozen_embedding.get(key),
            bundle_embedding.get(key),
            f"challenge_embedding_contract_mismatch:{key}",
        )
    for key, value in current_embedding.items():
        _require_equal(
            bundle_embedding.get(key),
            value,
            f"challenge_current_embedding_mismatch:{key}",
        )
    _require_equal(
        frozen_retrieval.get("vector_store_provider"),
        gate_bundle.get("vector_store_provider"),
        "challenge_vector_store_contract_mismatch",
    )
    _require_equal(
        gate_bundle.get("vector_store_provider"),
        settings.rag_vector_store_provider,
        "challenge_current_vector_store_mismatch",
    )
    frozen_reranker = frozen_retrieval.get("reranker") or {}
    bundle_reranker = gate_bundle.get("reranker") or {}
    current_reranker = {
        "provider": settings.rag_reranker_provider,
        "model": settings.rag_reranker_model,
        "base_url": settings.rag_reranker_base_url,
        "instruct": settings.rag_reranker_instruct,
    }
    for key in ("provider", "model"):
        _require_equal(
            frozen_reranker.get(key),
            bundle_reranker.get(key),
            f"challenge_reranker_contract_mismatch:{key}",
        )
    for key, value in current_reranker.items():
        _require_equal(
            bundle_reranker.get(key),
            value,
            f"challenge_current_reranker_mismatch:{key}",
        )

    if formal_run:
        _require_equal(
            main_manifest.get("formal_run"),
            True,
            "formal_challenge_requires_formal_main_run",
        )
        _require_equal(
            gate_bundle.get("formal_run"),
            True,
            "formal_challenge_requires_formal_gate_bundle",
        )
        _require_equal(
            main_manifest.get("git_status"),
            "",
            "formal_challenge_requires_clean_main_run",
        )
        current_commit = _git_value(["rev-parse", "HEAD"])
        _require_equal(
            main_manifest.get("git_commit"),
            current_commit,
            "formal_challenge_requires_same_git_commit",
        )
        _require_equal(
            challenge_frozen_config.get("formal_reranker_fallback"),
            False,
            "formal_challenge_frozen_config_forbids_fallback",
        )
    return (
        main_manifest,
        gate_bundle,
        challenge_manifest,
        challenge_frozen_config,
    )


def run_challenge_evaluation(
    *,
    corpus_dir: Path,
    main_dataset_path: Path,
    main_run_dir: Path,
    challenge_dataset_path: Path,
    challenge_manifest_path: Path,
    challenge_frozen_config_path: Path,
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
    corpus_manifest, _ = load_frozen_chunks(corpus_dir)
    validation = validate_challenge_dataset(
        corpus_dir=corpus_dir,
        main_dataset_path=main_dataset_path,
        challenge_dataset_path=challenge_dataset_path,
        challenge_manifest_path=challenge_manifest_path,
    )
    (
        main_manifest,
        gate_bundle,
        challenge_manifest,
        _,
    ) = _validate_gate_bundle_linkage(
        corpus_manifest=corpus_manifest,
        main_dataset_path=main_dataset_path,
        main_run_dir=main_run_dir,
        challenge_manifest_path=challenge_manifest_path,
        challenge_frozen_config_path=challenge_frozen_config_path,
        modes=modes,
        formal_run=formal_run,
    )
    queries = load_evaluation_queries(challenge_dataset_path)
    if not queries or any(query.split != "holdout" for query in queries):
        raise EvaluationContractError("challenge_runner_requires_holdout_only")

    output_dir.mkdir(parents=True, exist_ok=True)
    clear_rag_cache()
    build_started = time.perf_counter()
    retriever = get_rag_retriever(corpus_dir)
    build_ms = round((time.perf_counter() - build_started) * 1000, 3)
    _validate_challenge_retriever_runtime(
        retriever,
        gate_bundle=gate_bundle,
        formal_run=formal_run,
    )
    rows_by_mode: dict[str, list[dict[str, Any]]] = {}
    summaries: dict[str, Any] = {}
    gate_results: dict[str, Any] = {}
    confidence_intervals: dict[str, Any] = {}

    for mode in modes:
        rows: list[dict[str, Any]] = []
        for query in queries:
            retrieval_started = time.perf_counter()
            hits = retriever.retrieve(
                query.query,
                top_k=10,
                mode=mode,
                allow_reranker_fallback=allow_reranker_fallback,
            )
            _validate_challenge_retriever_runtime(
                retriever,
                gate_bundle=gate_bundle,
                formal_run=formal_run,
            )
            latency_ms = round(
                (time.perf_counter() - retrieval_started) * 1000,
                3,
            )
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
            rows.append(
                {
                    **evaluate_ranked_query(query, json_hits),
                    "query": query.query,
                    "split": "holdout",
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
        confidence_intervals[mode] = {
            "holdout": bootstrap_metric_intervals(
                rows,
                metric_names=PRIMARY_RANKING_METRICS,
                iterations=bootstrap_iterations,
                seed=bootstrap_seed,
            )
        }
        frozen_gate = dict(gate_bundle["gate_configs"][mode])
        holdout_gate = apply_frozen_gate(rows, frozen_gate)
        gate_results[mode] = {
            "frozen_config": frozen_gate,
            "holdout": {
                key: value
                for key, value in holdout_gate.items()
                if key != "predictions"
            },
            "holdout_predictions": holdout_gate["predictions"],
        }
        write_rows_jsonl(output_dir / f"{mode}.jsonl", rows)

    paired_comparisons = paired_bootstrap_comparisons(
        rows_by_mode,
        baseline_mode="embedding_only",
        metric_names=PRIMARY_RANKING_METRICS,
        iterations=bootstrap_iterations,
        seed=bootstrap_seed,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "ranking": summaries,
                "gate": gate_results,
                "primary_split": "holdout",
                "holdout_used_for_tuning": False,
                "evidence_tier": challenge_manifest["evidence_tier"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_summary_csv(output_dir / "summary.csv", summaries, split="holdout")
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
        split="holdout",
    )
    _write_group_chart_data(
        output_dir / "chart_query_type.csv",
        summaries,
        dimension="query_type",
        split="holdout",
    )
    _write_group_chart_data(
        output_dir / "chart_answerability.csv",
        summaries,
        dimension="answerability",
        split="holdout",
    )
    gate_prediction_rows = []
    row_by_mode_query = {
        mode: {row["query_id"]: row for row in rows}
        for mode, rows in rows_by_mode.items()
    }
    for mode, gate_result in gate_results.items():
        for query_id, prediction in gate_result["holdout_predictions"].items():
            answerability = row_by_mode_query[mode][query_id]["answerability"]
            gate_prediction_rows.append(
                {
                    "mode": mode,
                    "query_id": query_id,
                    "split": "holdout",
                    "answerability": answerability,
                    "expected": (
                        "accept" if answerability == "full" else "reject"
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
        "schema_version": "course-rag-challenge-run-v1",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "formal_run": formal_run,
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "git_status": _git_value(["status", "--short"]),
        "corpus_manifest_sha256": corpus_manifest["manifest_sha256"],
        "main_run_manifest_sha256": _sha256_file(
            main_run_dir / "run_manifest.json"
        ),
        "main_dataset_sha256": main_manifest["dataset_sha256"],
        "frozen_gate_config_sha256": _sha256_file(
            main_run_dir / "frozen_gate_config.json"
        ),
        "challenge_manifest_sha256": _sha256_file(challenge_manifest_path),
        "challenge_dataset_sha256": challenge_manifest["dataset_sha256"],
        "challenge_frozen_config_sha256": _sha256_file(
            challenge_frozen_config_path
        ),
        "modes": list(modes),
        "allow_reranker_fallback": allow_reranker_fallback,
        "evaluation": {
            "primary_split": "holdout",
            "gate_calibration_performed": False,
            "gate_source": "main_dataset_development",
            "holdout_used_for_tuning": False,
            "evidence_tier": challenge_manifest["evidence_tier"],
            "primary_metrics": list(PRIMARY_RANKING_METRICS),
            "bootstrap_iterations": bootstrap_iterations,
            "bootstrap_seed": bootstrap_seed,
            "paired_baseline_mode": "embedding_only",
        },
        "embedding": gate_bundle["embedding"],
        "vector_store_provider": gate_bundle["vector_store_provider"],
        "reranker": gate_bundle["reranker"],
        "retrieval_contract": gate_bundle["retrieval_contract"],
        "cost_rates": {
            "embedding_per_1k_tokens": embedding_cost_per_1k,
            "reranker_per_1k_tokens": reranker_cost_per_1k,
        },
        "retriever_build_ms": build_ms,
        "challenge_validation": validation,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": _dependency_versions(),
        },
        "outputs": {
            path.name: {
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in output_files
        },
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return run_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the challenge holdout with gate configs frozen by a completed "
            "main benchmark run."
        )
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/rag/course_v1"),
    )
    parser.add_argument(
        "--main-dataset",
        type=Path,
        default=Path("data/rag/course_v1/golden_queries.jsonl"),
    )
    parser.add_argument("--main-run-dir", type=Path, required=True)
    parser.add_argument(
        "--challenge-dataset",
        type=Path,
        default=Path(
            "data/rag/course_challenge_v1/challenge_queries.jsonl"
        ),
    )
    parser.add_argument(
        "--challenge-manifest",
        type=Path,
        default=Path("data/rag/course_challenge_v1/challenge_manifest.json"),
    )
    parser.add_argument(
        "--challenge-frozen-config",
        type=Path,
        default=Path("data/rag/course_challenge_v1/frozen_config.json"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument(
        "--allow-diagnostic-holdout",
        action="store_true",
        help=(
            "Explicitly allow a non-formal holdout run. Never use this on the "
            "canonical 28-query challenge before its formal run."
        ),
    )
    parser.add_argument(
        "--allow-reranker-fallback",
        action="store_true",
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
    if not args.formal and not args.allow_diagnostic_holdout:
        parser.error(
            "challenge CLI requires --formal; non-formal use requires the "
            "explicit --allow-diagnostic-holdout acknowledgement"
        )
    try:
        manifest = run_challenge_evaluation(
            corpus_dir=args.corpus_dir,
            main_dataset_path=args.main_dataset,
            main_run_dir=args.main_run_dir,
            challenge_dataset_path=args.challenge_dataset,
            challenge_manifest_path=args.challenge_manifest,
            challenge_frozen_config_path=args.challenge_frozen_config,
            output_dir=args.output_dir,
            modes=DEFAULT_MODES,
            allow_reranker_fallback=args.allow_reranker_fallback,
            embedding_cost_per_1k=args.embedding_cost_per_1k,
            reranker_cost_per_1k=args.reranker_cost_per_1k,
            formal_run=args.formal,
            bootstrap_iterations=args.bootstrap_iterations,
            bootstrap_seed=args.bootstrap_seed,
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema_version": "course-rag-challenge-run-failure-v1",
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
