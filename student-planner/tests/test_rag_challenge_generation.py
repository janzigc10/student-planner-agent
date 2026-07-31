from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.agent.rag_evaluation import EvaluationContractError, load_evaluation_queries
from scripts.generate_course_rag_challenge import (
    CHALLENGE_SPECS,
    generate_challenge,
)
from scripts.validate_course_rag_challenge import validate_challenge_dataset


PROJECT_DIR = Path(__file__).resolve().parents[1]
CORPUS_DIR = PROJECT_DIR / "data" / "rag" / "course_v1"
MAIN_DATASET = CORPUS_DIR / "golden_queries.jsonl"


def test_challenge_specs_freeze_balanced_unseen_query_shape():
    assert len(CHALLENGE_SPECS) == 28
    assert len({spec.query_id for spec in CHALLENGE_SPECS}) == 28
    assert len({spec.query.casefold() for spec in CHALLENGE_SPECS}) == 28
    assert {
        spec.query_type for spec in CHALLENGE_SPECS
    } == {
        "exact_entity",
        "paraphrase",
        "comparison",
        "multi_concept",
        "summary",
        "long_student_query",
        "out_of_scope",
    }
    course_counts: dict[str, int] = {}
    answerability_counts = {"full": 0, "partial": 0, "none": 0}
    for spec in CHALLENGE_SPECS:
        course_counts[spec.course_id] = course_counts.get(spec.course_id, 0) + 1
        answerability_counts[spec.answerability] += 1
    assert sorted(course_counts.values()) == [7, 7, 7, 7]
    assert answerability_counts == {"full": 20, "partial": 4, "none": 4}


def test_challenge_generator_writes_valid_pool_and_blind_review_pack(tmp_path):
    output_dir = tmp_path / "challenge"

    result = generate_challenge(
        corpus_dir=CORPUS_DIR,
        main_dataset_path=MAIN_DATASET,
        output_dir=output_dir,
    )

    assert result["status"] == "valid"
    assert result["query_count"] == 28
    assert result["evidence_tier"] == "llm_assisted_unreviewed"
    assert result["human_review_status"] == "not_reviewed"
    assert result["candidate_count"] == result["qrel_count"]

    manifest = json.loads(
        (output_dir / "challenge_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["used_for_tuning"] is False
    assert manifest["pooling"]["modes"] == [
        "embedding_only",
        "bm25_only",
        "hybrid_rrf",
        "hybrid_rerank",
    ]
    assert manifest["pooling"]["embedding_for_pool_construction"] == "local_hash"
    assert manifest["pooling"]["hybrid_rerank_for_pool_construction"] == (
        "local_feature_fallback"
    )

    pool_rows = [
        json.loads(line)
        for line in (output_dir / "candidate_pool.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for query_id in {spec.query_id for spec in CHALLENGE_SPECS}:
        query_rows = [row for row in pool_rows if row["query_id"] == query_id]
        observed_modes = {
            origin["mode"]
            for row in query_rows
            for origin in row["origins"]
        }
        assert {
            "embedding_only",
            "bm25_only",
            "hybrid_rrf",
            "hybrid_rerank",
        }.issubset(observed_modes)

    with (output_dir / "blind_qrel_review.tsv").open(
        encoding="utf-8",
        newline="",
    ) as handle:
        blind_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(blind_rows) == result["candidate_count"]
    assert set(blind_rows[0]) == {
        "review_id",
        "review_query_id",
        "query",
        "candidate_text",
        "relevance_0_1_2",
        "review_notes",
    }
    assert all(row["relevance_0_1_2"] == "" for row in blind_rows)

    validation = validate_challenge_dataset(
        corpus_dir=CORPUS_DIR,
        main_dataset_path=MAIN_DATASET,
        challenge_dataset_path=output_dir / "challenge_queries.jsonl",
        challenge_manifest_path=output_dir / "challenge_manifest.json",
    )
    assert validation["status"] == "valid"
    assert validation["artifact_hashes_verified"] is True
    assert validation["pool_qrel_alignment_verified"] is True
    challenge_queries = load_evaluation_queries(
        output_dir / "challenge_queries.jsonl"
    )
    main_queries = load_evaluation_queries(MAIN_DATASET)
    assert {
        query.query.casefold() for query in challenge_queries
    }.isdisjoint({query.query.casefold() for query in main_queries})

    frozen_config_path = output_dir / "frozen_config.json"
    frozen_config_path.write_text(
        frozen_config_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationContractError,
        match="challenge_artifact_hash_mismatch:frozen_config.json",
    ):
        validate_challenge_dataset(
            corpus_dir=CORPUS_DIR,
            main_dataset_path=MAIN_DATASET,
            challenge_dataset_path=output_dir / "challenge_queries.jsonl",
            challenge_manifest_path=output_dir / "challenge_manifest.json",
        )
