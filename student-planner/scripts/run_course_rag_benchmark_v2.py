from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag_evaluation import (
    DEFAULT_BOOTSTRAP_ITERATIONS,
    DEFAULT_BOOTSTRAP_SEED,
)
from scripts.evaluate_course_rag import (
    DEFAULT_MODES,
    _ensure_empty_output_dir,
    _git_value,
    _sha256_file,
    run_evaluation,
)
from scripts.evaluate_course_rag_challenge import run_challenge_evaluation


def run_benchmark_v2(
    *,
    corpus_dir: Path,
    main_dataset_path: Path,
    main_dataset_manifest_path: Path,
    challenge_dataset_path: Path,
    challenge_manifest_path: Path,
    challenge_frozen_config_path: Path,
    output_root: Path,
    allow_reranker_fallback: bool,
    embedding_cost_per_1k: float,
    reranker_cost_per_1k: float,
    formal_run: bool,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    _ensure_empty_output_dir(output_root)
    started_at = datetime.now(timezone.utc).isoformat()
    main_output_dir = output_root / "main"
    challenge_output_dir = output_root / "challenge"
    main_manifest = run_evaluation(
        corpus_dir=corpus_dir,
        dataset_path=main_dataset_path,
        dataset_manifest_path=main_dataset_manifest_path,
        output_dir=main_output_dir,
        modes=DEFAULT_MODES,
        allow_reranker_fallback=allow_reranker_fallback,
        embedding_cost_per_1k=embedding_cost_per_1k,
        reranker_cost_per_1k=reranker_cost_per_1k,
        formal_run=formal_run,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    challenge_manifest = run_challenge_evaluation(
        corpus_dir=corpus_dir,
        main_dataset_path=main_dataset_path,
        main_run_dir=main_output_dir,
        challenge_dataset_path=challenge_dataset_path,
        challenge_manifest_path=challenge_manifest_path,
        challenge_frozen_config_path=challenge_frozen_config_path,
        output_dir=challenge_output_dir,
        modes=DEFAULT_MODES,
        allow_reranker_fallback=allow_reranker_fallback,
        embedding_cost_per_1k=embedding_cost_per_1k,
        reranker_cost_per_1k=reranker_cost_per_1k,
        formal_run=formal_run,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    root_manifest = {
        "schema_version": "course-rag-benchmark-v2-run-v1",
        "status": "completed",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "formal_run": formal_run,
        "git_commit": _git_value(["rev-parse", "HEAD"]),
        "git_status": _git_value(["status", "--short"]),
        "modes": list(DEFAULT_MODES),
        "stages": ["main_development_and_test", "challenge_holdout"],
        "gate_flow": {
            "calibration_source": "main/development",
            "challenge_reuses_frozen_gate": True,
            "challenge_used_for_tuning": False,
        },
        "main": {
            "schema_version": main_manifest["schema_version"],
            "dataset_sha256": main_manifest["dataset_sha256"],
            "run_manifest_sha256": _sha256_file(
                main_output_dir / "run_manifest.json"
            ),
            "frozen_gate_config_sha256": main_manifest[
                "frozen_gate_config_sha256"
            ],
        },
        "challenge": {
            "schema_version": challenge_manifest["schema_version"],
            "dataset_sha256": challenge_manifest["challenge_dataset_sha256"],
            "run_manifest_sha256": _sha256_file(
                challenge_output_dir / "run_manifest.json"
            ),
            "evidence_tier": challenge_manifest["evaluation"]["evidence_tier"],
        },
        "bootstrap_iterations": bootstrap_iterations,
        "bootstrap_seed": bootstrap_seed,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "benchmark_manifest.json").write_text(
        json.dumps(root_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return root_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the one-way Benchmark v2 flow: main development calibration "
            "and internal test, then untouched challenge holdout."
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
    parser.add_argument(
        "--main-dataset-manifest",
        type=Path,
        default=Path("data/rag/course_v1/dataset_manifest.json"),
    )
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
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--formal",
        action="store_true",
        help=(
            "Required by this CLI. Enforces clean Git, real providers, all "
            "four modes, empty outputs, and no fallback."
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
    if not args.formal:
        parser.error(
            "the canonical two-stage CLI requires --formal; offline contract "
            "tests call run_benchmark_v2() with temporary fixtures"
        )
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        manifest = run_benchmark_v2(
            corpus_dir=args.corpus_dir,
            main_dataset_path=args.main_dataset,
            main_dataset_manifest_path=args.main_dataset_manifest,
            challenge_dataset_path=args.challenge_dataset,
            challenge_manifest_path=args.challenge_manifest,
            challenge_frozen_config_path=args.challenge_frozen_config,
            output_root=args.output_root,
            allow_reranker_fallback=False,
            embedding_cost_per_1k=args.embedding_cost_per_1k,
            reranker_cost_per_1k=args.reranker_cost_per_1k,
            formal_run=True,
            bootstrap_iterations=args.bootstrap_iterations,
            bootstrap_seed=args.bootstrap_seed,
        )
    except Exception as error:
        failure_manifest = {
            "schema_version": "course-rag-benchmark-v2-run-failure-v1",
            "status": "failed",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "formal_run": True,
            "git_commit": _git_value(["rev-parse", "HEAD"]),
            "git_status": _git_value(["status", "--short"]),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        failure_path = args.output_root.parent / (
            f"{args.output_root.name}.failed_run.json"
        )
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(
            json.dumps(failure_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
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
