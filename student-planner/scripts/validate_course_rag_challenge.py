from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag_corpus import load_frozen_chunks
from app.agent.rag_evaluation import (
    EvaluationContractError,
    load_evaluation_queries,
    validate_challenge_contract,
)

REQUIRED_POOL_MODES = {
    "embedding_only",
    "bm25_only",
    "hybrid_rrf",
    "hybrid_rerank",
}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_frozen_artifacts(
    *,
    challenge_queries,
    challenge_dataset_path: Path,
    challenge_manifest_path: Path,
    challenge_manifest: dict,
) -> dict:
    artifact_hashes = challenge_manifest.get("artifacts")
    if not isinstance(artifact_hashes, dict) or not artifact_hashes:
        raise EvaluationContractError("challenge_artifact_hashes_missing")
    artifact_dir = challenge_manifest_path.parent.resolve()
    for artifact_name, expected_hash in artifact_hashes.items():
        if Path(artifact_name).name != artifact_name:
            raise EvaluationContractError(
                f"challenge_artifact_name_invalid:{artifact_name}"
            )
        artifact_path = artifact_dir / artifact_name
        if not artifact_path.is_file():
            raise EvaluationContractError(
                f"challenge_artifact_missing:{artifact_name}"
            )
        if _sha256_file(artifact_path) != expected_hash:
            raise EvaluationContractError(
                f"challenge_artifact_hash_mismatch:{artifact_name}"
            )

    frozen_config_path = artifact_dir / "frozen_config.json"
    if (
        _sha256_file(frozen_config_path)
        != challenge_manifest.get("frozen_config_sha256")
    ):
        raise EvaluationContractError("challenge_frozen_config_hash_mismatch")
    if (
        _sha256_file(challenge_dataset_path)
        != artifact_hashes.get("challenge_queries.jsonl")
    ):
        raise EvaluationContractError("challenge_dataset_artifact_hash_mismatch")

    pool_path = artifact_dir / "candidate_pool.jsonl"
    pool_rows = [
        json.loads(line)
        for line in pool_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pool_pairs: set[tuple[str, str]] = set()
    modes_by_query: dict[str, set[str]] = {}
    for row in pool_rows:
        pair = (
            str(row.get("query_id") or ""),
            str(row.get("chunk_id") or ""),
        )
        if not all(pair):
            raise EvaluationContractError("challenge_pool_pair_identity_missing")
        if pair in pool_pairs:
            raise EvaluationContractError(
                f"challenge_pool_duplicate_pair:{pair[0]}:{pair[1]}"
            )
        pool_pairs.add(pair)
        origins = row.get("origins")
        if not isinstance(origins, list):
            raise EvaluationContractError(
                f"challenge_pool_origins_invalid:{pair[0]}:{pair[1]}"
            )
        modes_by_query.setdefault(pair[0], set()).update(
            str(origin.get("mode") or "")
            for origin in origins
            if isinstance(origin, dict)
        )
    qrel_pairs = {
        (query.query_id, qrel.chunk_id)
        for query in challenge_queries
        for qrel in query.qrels
    }
    if pool_pairs != qrel_pairs:
        raise EvaluationContractError("challenge_pool_qrel_pairs_mismatch")
    if challenge_manifest.get("pooling", {}).get("candidate_count") != len(
        pool_rows
    ):
        raise EvaluationContractError("challenge_pool_candidate_count_mismatch")
    for query in challenge_queries:
        if not REQUIRED_POOL_MODES.issubset(modes_by_query.get(query.query_id, set())):
            raise EvaluationContractError(
                f"challenge_pool_mode_coverage_incomplete:{query.query_id}"
            )
    return {
        "artifact_count": len(artifact_hashes),
        "candidate_count": len(pool_rows),
        "artifact_hashes_verified": True,
        "pool_qrel_alignment_verified": True,
    }


def validate_challenge_dataset(
    *,
    corpus_dir: Path,
    main_dataset_path: Path,
    challenge_dataset_path: Path,
    challenge_manifest_path: Path,
) -> dict:
    corpus_manifest, chunks = load_frozen_chunks(corpus_dir)
    main_queries = load_evaluation_queries(main_dataset_path)
    challenge_queries = load_evaluation_queries(challenge_dataset_path)
    challenge_manifest = json.loads(
        challenge_manifest_path.read_text(encoding="utf-8")
    )
    result = validate_challenge_contract(
        challenge_queries,
        main_queries=main_queries,
        challenge_manifest=challenge_manifest,
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
        known_chunk_ids={chunk.chunk_id for chunk in chunks},
        known_source_ids={chunk.source_id for chunk in chunks},
    )
    result.update(
        _validate_frozen_artifacts(
            challenge_queries=challenge_queries,
            challenge_dataset_path=challenge_dataset_path,
            challenge_manifest_path=challenge_manifest_path,
            challenge_manifest=challenge_manifest,
        )
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate an untouched course RAG challenge holdout against the "
            "frozen main corpus and dataset."
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
    parser.add_argument("--challenge-dataset", type=Path, required=True)
    parser.add_argument("--challenge-manifest", type=Path, required=True)
    args = parser.parse_args()
    result = validate_challenge_dataset(
        corpus_dir=args.corpus_dir,
        main_dataset_path=args.main_dataset,
        challenge_dataset_path=args.challenge_dataset,
        challenge_manifest_path=args.challenge_manifest,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
