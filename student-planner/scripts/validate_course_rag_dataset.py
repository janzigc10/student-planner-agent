from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag_corpus import load_frozen_chunks
from app.agent.rag_evaluation import (
    QUERY_TYPES,
    EvaluationContractError,
    dataset_sha256,
    load_evaluation_queries,
)


def validate_dataset(root: Path, *, profile: str) -> dict:
    corpus_manifest, chunks = load_frozen_chunks(root)
    queries = load_evaluation_queries(root / "golden_queries.jsonl")
    dataset_manifest = json.loads(
        (root / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    errors: list[str] = []
    if dataset_manifest.get("corpus_manifest_sha256") != corpus_manifest.get(
        "manifest_sha256"
    ):
        errors.append("dataset_corpus_manifest_mismatch")
    if dataset_manifest.get("dataset_sha256") != dataset_sha256(queries):
        errors.append("dataset_content_hash_mismatch")

    chunk_ids = {chunk.chunk_id for chunk in chunks}
    source_ids = {chunk.source_id for chunk in chunks}
    for query in queries:
        if query.split not in {"development", "test"}:
            errors.append(f"unfrozen_split:{query.query_id}")
        if not {qrel.chunk_id for qrel in query.qrels}.issubset(chunk_ids):
            errors.append(f"unknown_qrel_chunk:{query.query_id}")
        if not set(query.relevant_source_ids).issubset(source_ids):
            errors.append(f"unknown_relevant_source:{query.query_id}")

    course_counts = Counter(
        str(source.get("metadata", {}).get("course_id") or "")
        for source in corpus_manifest.get("sources", [])
    )
    query_types = Counter(query.query_type for query in queries)
    answerability = Counter(query.answerability for query in queries)
    split_counts = Counter(query.split for query in queries)
    if profile == "full":
        if not 45 <= corpus_manifest["source_count"] <= 60:
            errors.append("full_source_count_out_of_range")
        if not 500 <= corpus_manifest["chunk_count"] <= 850:
            errors.append("full_chunk_count_out_of_range")
        if not 80 <= len(queries) <= 120:
            errors.append("full_query_count_out_of_range")
        if len(course_counts) != 4:
            errors.append("full_course_count_must_be_four")
        if any(not 10 <= count <= 14 for count in course_counts.values()):
            errors.append("full_course_material_count_out_of_range")
        if set(query_types) != QUERY_TYPES:
            errors.append("full_query_type_coverage_incomplete")
        if query_types["out_of_scope"] / len(queries) < 0.1:
            errors.append("full_out_of_scope_below_ten_percent")
    else:
        if corpus_manifest["source_count"] != 10:
            errors.append("pilot_source_count_must_be_ten")
        if not 15 <= len(queries) <= 20:
            errors.append("pilot_query_count_out_of_range")
        if len(course_counts) != 2:
            errors.append("pilot_course_count_must_be_two")
        if not {"full", "partial", "none"}.issubset(answerability):
            errors.append("pilot_answerability_coverage_incomplete")
        if not {"comparison", "multi_concept", "out_of_scope"}.issubset(
            query_types
        ):
            errors.append("pilot_query_type_coverage_incomplete")

    if split_counts["development"] != round(len(queries) * 0.3):
        errors.append("development_split_not_thirty_percent")
    if split_counts["test"] != len(queries) - split_counts["development"]:
        errors.append("test_split_count_invalid")
    if dataset_manifest.get("human_review_status") != "synthetic_unreviewed":
        errors.append("human_review_status_must_remain_explicit")
    if dataset_manifest.get("synthetic") is not True:
        errors.append("dataset_must_be_marked_synthetic")
    if errors:
        raise EvaluationContractError(";".join(errors))
    return {
        "status": "valid",
        "profile": profile,
        "root": str(root.resolve()),
        "source_count": corpus_manifest["source_count"],
        "chunk_count": corpus_manifest["chunk_count"],
        "course_counts": dict(sorted(course_counts.items())),
        "query_count": len(queries),
        "query_types": dict(sorted(query_types.items())),
        "answerability": dict(sorted(answerability.items())),
        "splits": dict(sorted(split_counts.items())),
        "qrel_count": sum(len(query.qrels) for query in queries),
        "corpus_manifest_sha256": corpus_manifest["manifest_sha256"],
        "dataset_sha256": dataset_manifest["dataset_sha256"],
        "human_review_status": dataset_manifest["human_review_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen synthetic course RAG corpus and golden set."
    )
    parser.add_argument(
        "--profile",
        choices=("pilot", "full"),
        required=True,
    )
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate_dataset(args.root, profile=args.profile),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
