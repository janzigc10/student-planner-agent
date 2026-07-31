import json

import pytest

from app.agent.rag_answer_evaluation import (
    evaluate_answer_item,
    parse_answer_judgment,
    parse_answer_run,
    summarize_answer_rows,
)
from app.agent.rag_evaluation import parse_evaluation_query
from scripts.evaluate_course_rag_answers import evaluate_answer_files


def _query_row(**overrides):
    row = {
        "query_id": "q-full",
        "query": "交叉验证为什么有用？",
        "course_id": "machine_learning",
        "query_type": "paraphrase",
        "answerability": "full",
        "reference_answer": "交叉验证轮换验证集并汇总多次结果。",
        "relevant_source_ids": ["machine_learning/evaluation.md"],
        "relevant_chunk_ids": ["chunk-a"],
        "qrels": [
            {"chunk_id": "chunk-a", "relevance": 2},
            {"chunk_id": "chunk-b", "relevance": 0},
        ],
        "evidence_requirements": [],
        "expected_terms": ["交叉验证", "验证集"],
        "split": "test",
    }
    row.update(overrides)
    return row


def _answer_run_row(**overrides):
    row = {
        "query_id": "q-full",
        "mode": "hybrid_rrf",
        "answer": "交叉验证轮换验证集并汇总多次结果。",
        "refused": False,
        "evidence_chunk_ids": ["chunk-a", "chunk-b"],
        "sentences": [
            {
                "sentence_id": "s-1",
                "text": "交叉验证轮换验证集并汇总多次结果。",
                "citation_chunk_ids": ["chunk-a"],
            }
        ],
        "model": "qwen-test",
        "prompt_version": "answer-v1",
        "temperature": 0,
    }
    row.update(overrides)
    return row


def _judgment_row(**overrides):
    row = {
        "query_id": "q-full",
        "mode": "hybrid_rrf",
        "sentence_judgments": [
            {
                "sentence_id": "s-1",
                "requires_citation": True,
                "support": 2,
            }
        ],
        "nugget_judgments": [
            {"nugget_id": "n-1", "importance": "vital", "coverage": 2},
            {"nugget_id": "n-2", "importance": "okay", "coverage": 1},
        ],
        "completeness": 2,
        "judge_model": "judge-test",
        "rubric_version": "rag-answer-rubric-v1",
        "human_audit_status": "not_reviewed",
    }
    row.update(overrides)
    return row


def test_answer_contract_scores_citations_support_nuggets_and_refusal():
    query = parse_evaluation_query(_query_row())
    run = parse_answer_run(_answer_run_row())
    judgment = parse_answer_judgment(_judgment_row())

    row = evaluate_answer_item(query, run, judgment)

    assert row["refusal_correct"] is True
    assert row["citation_validity"] == 1.0
    assert row["citation_relevance"] == 1.0
    assert row["citation_completeness"] == 1.0
    assert row["sentence_support"] == 1.0
    assert row["fully_supported_claim_rate"] == 1.0
    assert row["nugget_coverage"] == pytest.approx(5 / 6)
    assert row["answer_completeness"] == 1.0


def test_answer_contract_rejects_judgments_for_different_sentences():
    query = parse_evaluation_query(_query_row())
    run = parse_answer_run(_answer_run_row())
    judgment = parse_answer_judgment(
        _judgment_row(
            sentence_judgments=[
                {
                    "sentence_id": "different",
                    "requires_citation": True,
                    "support": 2,
                }
            ]
        )
    )

    with pytest.raises(
        ValueError,
        match="answer_sentence_judgments_incomplete",
    ):
        evaluate_answer_item(query, run, judgment)


def test_answer_summary_keeps_metric_denominators_explicit():
    rows = [
        {
            "mode": "embedding_only",
            "refusal_correct": True,
            "citation_validity": 1.0,
            "citation_relevance": 0.5,
            "citation_completeness": 1.0,
            "sentence_support": 0.5,
            "fully_supported_claim_rate": 0.0,
            "nugget_coverage": 0.5,
            "answer_completeness": 0.5,
        },
        {
            "mode": "embedding_only",
            "refusal_correct": True,
            "citation_validity": None,
            "citation_relevance": None,
            "citation_completeness": None,
            "sentence_support": None,
            "fully_supported_claim_rate": None,
            "nugget_coverage": None,
            "answer_completeness": 1.0,
        },
    ]

    summary = summarize_answer_rows(rows)

    assert summary["by_mode"]["embedding_only"]["query_count"] == 2
    assert summary["by_mode"]["embedding_only"]["citation_validity_n"] == 1
    assert summary["by_mode"]["embedding_only"]["answer_completeness"] == 0.75


def test_answer_file_evaluator_writes_reproducible_artifacts(tmp_path):
    query = parse_evaluation_query(_query_row())
    dataset_path = tmp_path / "queries.jsonl"
    dataset_path.write_text(
        json.dumps(query.to_json(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    runs_path = tmp_path / "answer_runs.jsonl"
    runs_path.write_text(
        json.dumps(_answer_run_row(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    judgments_path = tmp_path / "judgments.jsonl"
    judgments_path.write_text(
        json.dumps(_judgment_row(), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    manifest = evaluate_answer_files(
        dataset_path=dataset_path,
        answer_runs_path=runs_path,
        judgments_path=judgments_path,
        output_dir=output_dir,
    )

    assert manifest["schema_version"] == "course-rag-answer-run-v2"
    assert manifest["query_count"] == 1
    assert (output_dir / "answer_results.jsonl").exists()
    assert (output_dir / "answer_summary.json").exists()
    assert (output_dir / "answer_summary.csv").exists()
    assert (output_dir / "chart_answer_quality.csv").exists()
    assert (output_dir / "answer_run_manifest.json").exists()
