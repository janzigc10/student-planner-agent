from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag_corpus import CourseChunk, load_frozen_chunks
from app.agent.rag_evaluation import (
    QUERY_TYPES,
    EvaluationQuery,
    load_evaluation_queries,
)


DEFAULT_SEED = 20260729
DEFAULT_QUERIES_PER_COURSE = 5
DEFAULT_CANDIDATES_PER_QUERY = 12


def _stable_key(*parts: object, seed: int) -> str:
    value = "\n".join(str(part) for part in (seed, *parts))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_take(
    values: Iterable[Any],
    limit: int,
    *,
    seed: int,
    key_prefix: str,
    value_key,
) -> list[Any]:
    ordered = sorted(
        values,
        key=lambda value: _stable_key(
            key_prefix,
            value_key(value),
            seed=seed,
        ),
    )
    return ordered[:limit]


def select_review_queries(
    queries: Sequence[EvaluationQuery],
    *,
    seed: int = DEFAULT_SEED,
    per_course: int = DEFAULT_QUERIES_PER_COURSE,
) -> list[EvaluationQuery]:
    by_course: dict[str, list[EvaluationQuery]] = defaultdict(list)
    for query in queries:
        by_course[query.course_id].append(query)

    selected: list[EvaluationQuery] = []
    for course_id in sorted(by_course):
        course_queries = by_course[course_id]
        course_selected: list[EvaluationQuery] = []
        for answerability in ("none", "partial"):
            candidates = [
                query
                for query in course_queries
                if query.answerability == answerability
            ]
            if candidates:
                course_selected.extend(
                    _stable_take(
                        candidates,
                        1,
                        seed=seed,
                        key_prefix=f"{course_id}:{answerability}",
                        value_key=lambda query: query.query_id,
                    )
                )

        selected_ids = {query.query_id for query in course_selected}
        remaining = [
            query
            for query in course_queries
            if query.query_id not in selected_ids
        ]
        remaining = _stable_take(
            remaining,
            len(remaining),
            seed=seed,
            key_prefix=f"{course_id}:remaining",
            value_key=lambda query: query.query_id,
        )

        used_types = {query.query_type for query in course_selected}
        for query in remaining:
            if len(course_selected) >= per_course:
                break
            if query.query_type not in used_types:
                course_selected.append(query)
                used_types.add(query.query_type)
        if len(course_selected) < per_course:
            selected_ids = {query.query_id for query in course_selected}
            course_selected.extend(
                query
                for query in remaining
                if query.query_id not in selected_ids
            )
            course_selected = course_selected[:per_course]

        if len(course_selected) != per_course:
            raise ValueError(
                f"course_review_sample_too_small:{course_id}:"
                f"{len(course_selected)}<{per_course}"
            )
        selected.extend(course_selected)

    selected_by_id = {query.query_id: query for query in selected}
    type_counts = Counter(query.query_type for query in selected_by_id.values())
    for missing_type in sorted(QUERY_TYPES - set(type_counts)):
        candidates = _stable_take(
            (
                query
                for query in queries
                if query.query_type == missing_type
                and query.query_id not in selected_by_id
            ),
            len(queries),
            seed=seed,
            key_prefix=f"missing-type:{missing_type}",
            value_key=lambda query: query.query_id,
        )
        replacement_made = False
        for candidate in candidates:
            replaceable = _stable_take(
                (
                    query
                    for query in selected_by_id.values()
                    if query.course_id == candidate.course_id
                    and query.answerability == candidate.answerability
                    and type_counts[query.query_type] > 1
                ),
                len(selected_by_id),
                seed=seed,
                key_prefix=f"replace-for:{missing_type}",
                value_key=lambda query: query.query_id,
            )
            if not replaceable:
                continue
            replaced = replaceable[0]
            del selected_by_id[replaced.query_id]
            selected_by_id[candidate.query_id] = candidate
            type_counts[replaced.query_type] -= 1
            type_counts[candidate.query_type] += 1
            replacement_made = True
            break
        if not replacement_made:
            raise ValueError(f"review_query_type_not_covered:{missing_type}")

    return sorted(
        selected_by_id.values(),
        key=lambda query: (query.course_id, query.query_id),
    )


def select_blind_candidates(
    query: EvaluationQuery,
    chunks_by_id: dict[str, CourseChunk],
    *,
    seed: int = DEFAULT_SEED,
    limit: int = DEFAULT_CANDIDATES_PER_QUERY,
) -> list[CourseChunk]:
    qrels_by_grade: dict[int, list[str]] = defaultdict(list)
    for qrel in query.qrels:
        qrels_by_grade[qrel.relevance].append(qrel.chunk_id)

    selected_ids: list[str] = []
    for grade, grade_limit in ((2, 2), (1, 5)):
        selected_ids.extend(
            _stable_take(
                qrels_by_grade.get(grade, []),
                grade_limit,
                seed=seed,
                key_prefix=f"{query.query_id}:grade-{grade}",
                value_key=lambda chunk_id: chunk_id,
            )
        )
    remaining_limit = max(0, limit - len(selected_ids))
    selected_ids.extend(
        _stable_take(
            qrels_by_grade.get(0, []),
            remaining_limit,
            seed=seed,
            key_prefix=f"{query.query_id}:grade-0",
            value_key=lambda chunk_id: chunk_id,
        )
    )

    if len(selected_ids) < limit:
        already_selected = set(selected_ids)
        remaining_ids = [
            qrel.chunk_id
            for qrel in query.qrels
            if qrel.chunk_id not in already_selected
        ]
        selected_ids.extend(
            _stable_take(
                remaining_ids,
                limit - len(selected_ids),
                seed=seed,
                key_prefix=f"{query.query_id}:fill",
                value_key=lambda chunk_id: chunk_id,
            )
        )

    missing_ids = [
        chunk_id for chunk_id in selected_ids if chunk_id not in chunks_by_id
    ]
    if missing_ids:
        raise ValueError(
            f"review_candidate_chunk_missing:{query.query_id}:{missing_ids[0]}"
        )

    return [
        chunks_by_id[chunk_id]
        for chunk_id in sorted(
            selected_ids,
            key=lambda chunk_id: _stable_key(
                query.query_id,
                "blind-order",
                chunk_id,
                seed=seed,
            ),
        )
    ]


def _write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)


def export_review_sample(
    corpus_dir: Path,
    output_dir: Path,
    *,
    seed: int = DEFAULT_SEED,
    per_course: int = DEFAULT_QUERIES_PER_COURSE,
    candidates_per_query: int = DEFAULT_CANDIDATES_PER_QUERY,
) -> dict[str, Any]:
    corpus_manifest, chunks = load_frozen_chunks(corpus_dir)
    dataset_manifest = json.loads(
        (corpus_dir / "dataset_manifest.json").read_text(encoding="utf-8")
    )
    queries = load_evaluation_queries(corpus_dir / "golden_queries.jsonl")
    review_queries = select_review_queries(
        queries,
        seed=seed,
        per_course=per_course,
    )
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}

    output_dir.mkdir(parents=True, exist_ok=True)
    query_rows: list[dict[str, Any]] = []
    qrel_rows: list[dict[str, Any]] = []
    for review_index, query in enumerate(review_queries, start=1):
        review_id = f"R{review_index:02d}"
        query_rows.append(
            {
                "review_id": review_id,
                "query_id": query.query_id,
                "course_id": query.course_id,
                "query_type": query.query_type,
                "query_text": query.query,
                "reviewer_id": "",
                "review_date": "",
                "review_answerability": "",
                "review_reference_answer": "",
                "review_expected_terms": "",
                "review_notes": "",
            }
        )
        candidates = select_blind_candidates(
            query,
            chunks_by_id,
            seed=seed,
            limit=candidates_per_query,
        )
        for candidate_index, chunk in enumerate(candidates, start=1):
            metadata = chunk.metadata
            qrel_rows.append(
                {
                    "review_id": review_id,
                    "candidate_id": f"{review_id}-C{candidate_index:02d}",
                    "query_id": query.query_id,
                    "query_text": query.query,
                    "chunk_id": chunk.chunk_id,
                    "course_name": str(metadata.get("course_name") or ""),
                    "source_id": chunk.source_id,
                    "title": str(metadata.get("title") or ""),
                    "chunk_text": chunk.text.replace("\r", "").replace("\n", "\\n"),
                    "review_relevance": "",
                    "review_notes": "",
                }
            )

    query_path = output_dir / "query_review.tsv"
    qrel_path = output_dir / "qrel_review.tsv"
    _write_tsv(query_path, list(query_rows[0]), query_rows)
    _write_tsv(qrel_path, list(qrel_rows[0]), qrel_rows)

    course_counts = Counter(query.course_id for query in review_queries)
    answerability_counts = Counter(
        query.answerability for query in review_queries
    )
    query_type_counts = Counter(query.query_type for query in review_queries)
    manifest = {
        "schema_version": "course-rag-blind-review-v1",
        "source_corpus_version": corpus_manifest["corpus_version"],
        "source_corpus_manifest_sha256": corpus_manifest["manifest_sha256"],
        "source_dataset_version": dataset_manifest["dataset_version"],
        "source_dataset_sha256": dataset_manifest["dataset_sha256"],
        "review_seed": seed,
        "query_count": len(review_queries),
        "candidate_count": len(qrel_rows),
        "queries_per_course": per_course,
        "candidates_per_query": candidates_per_query,
        "course_counts": dict(sorted(course_counts.items())),
        "hidden_answerability_counts": dict(
            sorted(answerability_counts.items())
        ),
        "hidden_query_type_counts": dict(sorted(query_type_counts.items())),
        "selection_policy": (
            "Per course: one none and one partial query when available, then "
            "fill with distinct query types. Per query: up to two grade-2, "
            "five grade-1, then grade-0 pooled candidates; final order is "
            "deterministically shuffled. Existing labels are omitted."
        ),
        "labels_excluded_from_review_files": [
            "answerability",
            "reference_answer",
            "expected_terms",
            "qrels.relevance",
            "relevant_source_ids",
            "split",
        ],
        "files": {
            "query_review": query_path.name,
            "qrel_review": qrel_path.name,
        },
        "review_status": "optional_archive_not_planned",
    }
    manifest_path = output_dir / "review_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": str(output_dir.resolve()),
        **manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a deterministic blind-review sample for course RAG."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/rag/course_v1"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/rag/review/course_v1_1"),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--queries-per-course",
        type=int,
        default=DEFAULT_QUERIES_PER_COURSE,
    )
    parser.add_argument(
        "--candidates-per-query",
        type=int,
        default=DEFAULT_CANDIDATES_PER_QUERY,
    )
    args = parser.parse_args()
    result = export_review_sample(
        args.corpus_dir,
        args.output_dir,
        seed=args.seed,
        per_course=args.queries_per_course,
        candidates_per_query=args.candidates_per_query,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
