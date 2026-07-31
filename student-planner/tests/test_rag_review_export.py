from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.export_course_rag_review_sample import export_review_sample


CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "rag" / "course_v1"


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_export_review_sample_is_balanced_blind_and_deterministic(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = export_review_sample(CORPUS_DIR, first_dir)
    second = export_review_sample(CORPUS_DIR, second_dir)

    assert first["source_corpus_version"] == "rag-course-v1.1"
    assert first["source_dataset_version"] == "rag-course-golden-v1.1"
    assert first["query_count"] == 20
    assert first["candidate_count"] == 240
    assert set(first["course_counts"].values()) == {5}
    assert first["hidden_answerability_counts"] == {
        "full": 12,
        "none": 4,
        "partial": 4,
    }
    assert set(first["hidden_query_type_counts"]) == {
        "comparison",
        "exact_entity",
        "long_student_query",
        "multi_concept",
        "out_of_scope",
        "paraphrase",
        "summary",
    }

    query_rows = _read_tsv(first_dir / "query_review.tsv")
    qrel_rows = _read_tsv(first_dir / "qrel_review.tsv")
    assert len(query_rows) == 20
    assert len(qrel_rows) == 240
    assert all(not row["review_answerability"] for row in query_rows)
    assert all(not row["review_reference_answer"] for row in query_rows)
    assert all(not row["review_relevance"] for row in qrel_rows)
    assert "answerability" not in query_rows[0]
    assert "reference_answer" not in query_rows[0]
    assert "relevance" not in qrel_rows[0]

    for file_name in ("query_review.tsv", "qrel_review.tsv"):
        assert (first_dir / file_name).read_bytes() == (
            second_dir / file_name
        ).read_bytes()

    first_manifest = json.loads(
        (first_dir / "review_manifest.json").read_text(encoding="utf-8")
    )
    second_manifest = json.loads(
        (second_dir / "review_manifest.json").read_text(encoding="utf-8")
    )
    assert first_manifest == second_manifest
