import json
from types import SimpleNamespace

import pytest

import scripts.evaluate_course_rag as course_rag_evaluator
from app.agent.rag_evaluation import (
    EvaluationContractError,
    apply_frozen_gate,
    bootstrap_metric_intervals,
    build_challenge_manifest,
    build_dataset_manifest,
    calibrate_gate,
    evaluate_ranked_query,
    paired_bootstrap_comparisons,
    parse_evaluation_query,
    stratified_split,
    summarize_ranking_rows,
    summarize_ranking_rows_by_split,
    validate_challenge_contract,
)
from app.agent.rag_corpus import write_corpus_artifacts
from app.config import settings
from scripts.evaluate_course_rag import (
    _validate_formal_retriever_runtime,
    run_evaluation,
    write_failure_manifest,
)


def _query_row(**overrides):
    row = {
        "query_id": "q-001",
        "query": "交叉验证为什么能降低评估偶然性？",
        "course_id": "machine_learning",
        "query_type": "paraphrase",
        "answerability": "full",
        "reference_answer": "交叉验证轮换验证集并汇总多次结果。",
        "relevant_source_ids": ["machine_learning/evaluation.md"],
        "relevant_chunk_ids": ["chunk-a", "chunk-b"],
        "qrels": [
            {"chunk_id": "chunk-a", "relevance": 2},
            {"chunk_id": "chunk-b", "relevance": 1},
            {"chunk_id": "chunk-c", "relevance": 0},
        ],
        "evidence_requirements": [
            {"requirement_id": "rotation", "any_of_chunk_ids": ["chunk-a"]},
            {"requirement_id": "aggregation", "any_of_chunk_ids": ["chunk-b"]},
        ],
        "expected_terms": ["交叉验证", "验证集"],
    }
    row.update(overrides)
    return row


def test_golden_set_parser_derives_relevant_chunks_from_qrels():
    query = parse_evaluation_query(_query_row())

    assert query.relevant_chunk_ids == ("chunk-a", "chunk-b")
    assert query.evidence_requirements[0].any_of_chunk_ids == ("chunk-a",)


def test_golden_set_parser_rejects_conflicting_duplicate_truth():
    with pytest.raises(
        EvaluationContractError,
        match="relevant_chunk_ids_not_derived_from_qrels",
    ):
        parse_evaluation_query(_query_row(relevant_chunk_ids=["chunk-a"]))

    with pytest.raises(EvaluationContractError, match="none_query_cannot"):
        parse_evaluation_query(
            _query_row(
                answerability="none",
                evidence_requirements=[],
            )
        )


def test_stratified_split_is_deterministic_and_approximately_30_70():
    queries = [
        parse_evaluation_query(
            _query_row(
                query_id=f"q-{index:03d}",
                course_id="machine_learning" if index % 2 else "modern_history",
                query_type="paraphrase" if index % 3 else "exact_entity",
                evidence_requirements=[],
            )
        )
        for index in range(30)
    ]

    first = stratified_split(queries, seed=20260728)
    second = stratified_split(queries, seed=20260728)

    assert first == second
    assert sum(1 for split in first.values() if split == "development") == 9
    assert sum(1 for split in first.values() if split == "test") == 21


def test_ranking_metrics_treat_unjudged_as_non_relevant_and_score_requirements():
    query = parse_evaluation_query(_query_row())
    hits = [
        {
            "chunk_id": "chunk-b",
            "metadata": {"source": "machine_learning/evaluation.md"},
        },
        {"chunk_id": "unjudged", "metadata": {"source": "other.md"}},
        {
            "chunk_id": "chunk-a",
            "metadata": {"source": "machine_learning/evaluation.md"},
        },
    ]

    row = evaluate_ranked_query(query, hits)

    assert row["mrr"] == 1.0
    assert row["recall@3"] == 1.0
    assert row["precision@3"] == pytest.approx(2 / 3)
    assert row["judged@3"] == pytest.approx(2 / 3)
    assert 0.0 < row["ndcg@3"] < 1.0
    assert row["requirement_recall@10"] == 1.0
    assert row["complete_evidence_recall@10"] == 1.0
    assert row["top1_source_hit"] is True


def test_ranking_summary_reports_groups_latency_and_cost():
    rows = [
        {
            **evaluate_ranked_query(
                parse_evaluation_query(
                    _query_row(
                        query_id=f"q-{index}",
                        evidence_requirements=[],
                    )
                ),
                [{"chunk_id": "chunk-a", "metadata": {"source": "machine_learning/evaluation.md"}}],
            ),
            "latency_ms": 10 + index * 10,
            "estimated_cost": 0.001,
        }
        for index in range(3)
    ]

    summary = summarize_ranking_rows(rows)

    assert summary["overall"]["query_count"] == 3
    assert summary["overall"]["latency_mean_ms"] == 20.0
    assert summary["overall"]["latency_p95_ms"] == 30.0
    assert summary["overall"]["estimated_cost"] == 0.003
    assert summary["by"]["course_id"]["machine_learning"]["query_count"] == 3


def test_v2_summary_separates_development_and_test():
    query = parse_evaluation_query(_query_row(evidence_requirements=[]))
    metric_row = evaluate_ranked_query(
        query,
        [
            {
                "chunk_id": "chunk-a",
                "metadata": {"source": "machine_learning/evaluation.md"},
            }
        ],
    )
    rows = [
        {**metric_row, "query_id": "dev", "split": "development"},
        {**metric_row, "query_id": "test", "split": "test"},
    ]

    summary = summarize_ranking_rows_by_split(rows)

    assert summary["development"]["overall"]["query_count"] == 1
    assert summary["test"]["overall"]["query_count"] == 1


def test_v2_bootstrap_intervals_are_deterministic():
    rows = [
        {"query_id": f"q-{index}", "recall@5": value}
        for index, value in enumerate((0.0, 0.5, 1.0, 1.0))
    ]

    first = bootstrap_metric_intervals(
        rows,
        metric_names=("recall@5",),
        iterations=200,
        seed=17,
    )
    second = bootstrap_metric_intervals(
        rows,
        metric_names=("recall@5",),
        iterations=200,
        seed=17,
    )

    assert first == second
    assert first["recall@5"]["mean"] == 0.625
    assert first["recall@5"]["ci95_low"] <= 0.625
    assert first["recall@5"]["ci95_high"] >= 0.625


def test_v2_paired_bootstrap_aligns_query_ids_and_reports_direction():
    rows_by_mode = {
        "embedding_only": [
            {"query_id": "q-1", "mrr": 0.0},
            {"query_id": "q-2", "mrr": 0.5},
            {"query_id": "q-3", "mrr": 0.5},
        ],
        "hybrid_rrf": [
            {"query_id": "q-1", "mrr": 1.0},
            {"query_id": "q-2", "mrr": 1.0},
            {"query_id": "q-3", "mrr": 1.0},
        ],
    }

    comparisons = paired_bootstrap_comparisons(
        rows_by_mode,
        metric_names=("mrr",),
        iterations=200,
        seed=19,
    )

    assert comparisons[0]["mean_difference"] == pytest.approx(2 / 3, abs=1e-6)
    assert comparisons[0]["direction"] == "improvement"


def test_gate_calibration_enforces_false_accept_constraint_then_freezes_config():
    rows = [
        {
            "query_id": "full",
            "answerability": "full",
            "hits": [
                {
                    "score": 0.9,
                    "query_coverage": 0.9,
                    "anchor_coverage": 0.9,
                    "segment_coverage": 0.9,
                    "unmatched_run": 0,
                }
            ],
        },
        {
            "query_id": "partial",
            "answerability": "partial",
            "hits": [
                {
                    "score": 0.8,
                    "query_coverage": 0.2,
                    "anchor_coverage": 0.2,
                    "segment_coverage": 0.2,
                    "unmatched_run": 3,
                }
            ],
        },
        {
            "query_id": "none",
            "answerability": "none",
            "hits": [
                {
                    "score": 0.7,
                    "query_coverage": 0.1,
                    "anchor_coverage": 0.0,
                    "segment_coverage": 0.1,
                    "unmatched_run": 5,
                }
            ],
        },
    ]
    grid = [
        {
            "config_id": "loose",
            "score_quantile": 0.0,
            "min_query_coverage": 0.0,
            "min_anchor_coverage": 0.0,
            "min_segment_coverage": 0.0,
            "max_unmatched_run": 999,
        },
        {
            "config_id": "strict",
            "score_quantile": 0.0,
            "min_query_coverage": 0.8,
            "min_anchor_coverage": 0.8,
            "min_segment_coverage": 0.8,
            "max_unmatched_run": 1,
        },
    ]

    calibration = calibrate_gate(rows, parameter_grid=grid)
    frozen = calibration["selected_config"]
    applied = apply_frozen_gate(rows, frozen)

    assert calibration["constraint_met"] is True
    assert calibration["selected_config_id"] == "strict"
    assert applied["false_accept_rate"] == 0.0
    assert applied["full_answer_recall"] == 1.0


def test_dataset_manifest_records_frozen_split_and_hash():
    queries = [
        parse_evaluation_query(
            _query_row(
                query_id="q-dev",
                split="development",
                evidence_requirements=[],
            )
        ),
        parse_evaluation_query(
            _query_row(
                query_id="q-test",
                split="test",
                evidence_requirements=[],
            )
        ),
    ]

    manifest = build_dataset_manifest(
        queries,
        dataset_version="rag-course-golden-v1",
        corpus_manifest_sha256="corpus-hash",
    )

    assert manifest["query_count"] == 2
    assert manifest["development_count"] == 1
    assert manifest["test_count"] == 1
    assert len(manifest["dataset_sha256"]) == 64


def test_v2_challenge_contract_requires_untouched_balanced_holdout():
    main_queries = [
        parse_evaluation_query(
            _query_row(
                query_id="main-1",
                query="主集问题",
                split="test",
                evidence_requirements=[],
            )
        )
    ]
    courses = (
        "machine_learning",
        "modern_chinese_history",
        "political_theory",
        "world_modern_history",
    )
    query_types = (
        "paraphrase",
        "multi_concept",
        "long_student_query",
        "out_of_scope",
        "comparison",
        "summary",
    )
    challenge_queries = []
    for index in range(24):
        answerability = "full"
        relevance = 2
        relevant_sources = ["source-a"]
        reference_answer = "参考答案"
        if index % 6 == 4:
            answerability = "partial"
            relevance = 1
        elif index % 6 == 5:
            answerability = "none"
            relevance = 0
            relevant_sources = []
            reference_answer = ""
        challenge_queries.append(
            parse_evaluation_query(
                _query_row(
                    query_id=f"challenge-{index:02d}",
                    query=f"从未用于调参的挑战问题 {index}",
                    course_id=courses[index % len(courses)],
                    query_type=query_types[index % len(query_types)],
                    answerability=answerability,
                    reference_answer=reference_answer,
                    relevant_source_ids=relevant_sources,
                    relevant_chunk_ids=["chunk-a"] if relevance else [],
                    qrels=[{"chunk_id": "chunk-a", "relevance": relevance}],
                    evidence_requirements=[],
                    split="holdout",
                )
            )
        )
    manifest = build_challenge_manifest(
        challenge_queries,
        dataset_version="rag-course-challenge-v1",
        corpus_manifest_sha256="corpus-hash",
        evidence_tier="llm_assisted_unreviewed",
        frozen_config_sha256="a" * 64,
    )

    result = validate_challenge_contract(
        challenge_queries,
        main_queries=main_queries,
        challenge_manifest=manifest,
        corpus_manifest_sha256="corpus-hash",
        known_chunk_ids={"chunk-a"},
        known_source_ids={"source-a"},
    )

    assert result["query_count"] == 24
    assert result["answerability"]["partial"] == 4
    assert result["answerability"]["none"] == 4
    assert result["evidence_tier"] == "llm_assisted_unreviewed"


def test_unified_runner_writes_raw_summary_csv_chart_and_manifest(
    tmp_path,
    monkeypatch,
):
    corpus_dir = tmp_path / "corpus"
    source_path = corpus_dir / "machine_learning" / "evaluation" / "outline.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "---\n"
        "course_id: machine_learning\n"
        "chapter_id: evaluation\n"
        "material_type: review_outline\n"
        "synthetic: true\n"
        "corpus_version: rag-course-v1\n"
        "---\n"
        "# 模型评估\n\n监督学习使用带标签样本。交叉验证轮换验证集并汇总多次结果，"
        "可以降低单次划分的偶然性。测试集只能用于最终评估。",
        encoding="utf-8",
    )
    _, _, corpus_manifest = write_corpus_artifacts(corpus_dir)
    chunks = [
        json.loads(line)
        for line in (corpus_dir / "chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    relevant_chunk_id = chunks[0]["chunk_id"]
    source_id = chunks[0]["source_id"]
    query_rows = [
        _query_row(
            query_id="dev-full",
            split="development",
            relevant_source_ids=[source_id],
            relevant_chunk_ids=[relevant_chunk_id],
            qrels=[{"chunk_id": relevant_chunk_id, "relevance": 2}],
            evidence_requirements=[],
        ),
        _query_row(
            query_id="dev-none",
            query="量子退相干如何纠错？",
            query_type="out_of_scope",
            answerability="none",
            reference_answer="",
            split="development",
            relevant_source_ids=[],
            relevant_chunk_ids=[],
            qrels=[{"chunk_id": relevant_chunk_id, "relevance": 0}],
            evidence_requirements=[],
        ),
        _query_row(
            query_id="test-full",
            split="test",
            relevant_source_ids=[source_id],
            relevant_chunk_ids=[relevant_chunk_id],
            qrels=[{"chunk_id": relevant_chunk_id, "relevance": 2}],
            evidence_requirements=[],
        ),
        _query_row(
            query_id="test-none",
            query="火星殖民需要什么推进器？",
            query_type="out_of_scope",
            answerability="none",
            reference_answer="",
            split="test",
            relevant_source_ids=[],
            relevant_chunk_ids=[],
            qrels=[{"chunk_id": relevant_chunk_id, "relevance": 0}],
            evidence_requirements=[],
        ),
    ]
    queries = [parse_evaluation_query(row) for row in query_rows]
    dataset_path = corpus_dir / "golden_queries.jsonl"
    dataset_path.write_text(
        "".join(
            json.dumps(query.to_json(), ensure_ascii=False) + "\n"
            for query in queries
        ),
        encoding="utf-8",
    )
    dataset_manifest = build_dataset_manifest(
        queries,
        dataset_version="test-dataset",
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
    )
    dataset_manifest_path = corpus_dir / "dataset_manifest.json"
    dataset_manifest_path.write_text(
        json.dumps(dataset_manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    monkeypatch.setattr(settings, "rag_embedding_provider", "local")
    monkeypatch.setattr(settings, "rag_embedding_api_key", "")
    monkeypatch.setattr(settings, "rag_vector_store_provider", "memory")
    monkeypatch.setattr(settings, "rag_reranker_api_key", "")
    monkeypatch.setattr(settings, "rag_reranker_base_url", "")

    run_manifest = run_evaluation(
        corpus_dir=corpus_dir,
        dataset_path=dataset_path,
        dataset_manifest_path=dataset_manifest_path,
        output_dir=output_dir,
        modes=(
            "embedding_only",
            "bm25_only",
            "hybrid_rrf",
            "hybrid_rerank",
        ),
        allow_reranker_fallback=True,
        embedding_cost_per_1k=0.0,
        reranker_cost_per_1k=0.0,
    )

    assert run_manifest["modes"] == [
        "embedding_only",
        "bm25_only",
        "hybrid_rrf",
        "hybrid_rerank",
    ]
    assert (output_dir / "summary.json").exists()
    assert (output_dir / "summary.csv").exists()
    assert (output_dir / "confidence_intervals.json").exists()
    assert (output_dir / "paired_comparisons.csv").exists()
    assert (output_dir / "chart_overall.csv").exists()
    assert (output_dir / "chart_query_type.csv").exists()
    assert (output_dir / "chart_answerability.csv").exists()
    assert (output_dir / "gate_predictions.jsonl").exists()
    assert (output_dir / "frozen_gate_config.json").exists()
    assert (output_dir / "run_manifest.json").exists()
    assert run_manifest["schema_version"] == "course-rag-run-v2"
    assert len(run_manifest["frozen_gate_config_sha256"]) == 64
    assert run_manifest["outputs"]["frozen_gate_config.json"]["sha256"] == (
        run_manifest["frozen_gate_config_sha256"]
    )
    assert run_manifest["evaluation"]["primary_split"] == "test"
    gate_bundle = json.loads(
        (output_dir / "frozen_gate_config.json").read_text(encoding="utf-8")
    )
    assert gate_bundle["calibration_split"] == "development"
    assert gate_bundle["holdout_used_for_calibration"] is False
    assert set(gate_bundle["gate_configs"]) == set(run_manifest["modes"])
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["primary_split"] == "test"
    assert summary["ranking"]["embedding_only"]["development"]["overall"][
        "query_count"
    ] == 2
    assert summary["ranking"]["embedding_only"]["test"]["overall"][
        "query_count"
    ] == 2
    assert all(
        (output_dir / f"{mode}.jsonl").exists()
        for mode in run_manifest["modes"]
    )


def test_v2_runner_rejects_reused_output_directory(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "old.json").write_text("{}", encoding="utf-8")

    with pytest.raises(
        EvaluationContractError,
        match="output_directory_must_be_empty",
    ):
        run_evaluation(
            corpus_dir=tmp_path / "corpus",
            dataset_path=tmp_path / "queries.jsonl",
            dataset_manifest_path=tmp_path / "dataset_manifest.json",
            output_dir=output_dir,
            modes=("embedding_only",),
            allow_reranker_fallback=True,
            embedding_cost_per_1k=0.0,
            reranker_cost_per_1k=0.0,
        )


def test_v2_formal_preflight_rejects_dirty_git_before_online_work(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        course_rag_evaluator,
        "_git_value",
        lambda args, default="": " M tracked.py"
        if args == ["status", "--short"]
        else default,
    )

    with pytest.raises(
        EvaluationContractError,
        match="formal_run_requires_clean_git",
    ):
        run_evaluation(
            corpus_dir=tmp_path / "corpus",
            dataset_path=tmp_path / "queries.jsonl",
            dataset_manifest_path=tmp_path / "dataset_manifest.json",
            output_dir=tmp_path / "output",
            modes=(
                "embedding_only",
                "bm25_only",
                "hybrid_rrf",
                "hybrid_rerank",
            ),
            allow_reranker_fallback=False,
            embedding_cost_per_1k=0.0,
            reranker_cost_per_1k=0.0,
            formal_run=True,
        )


def test_v2_formal_runtime_rejects_embedding_and_vector_store_fallbacks():
    with pytest.raises(
        EvaluationContractError,
        match="formal_run_forbids_embedding_fallback",
    ):
        _validate_formal_retriever_runtime(
            SimpleNamespace(
                embedding_info={
                    "embedding_provider": "hash-fallback",
                    "embedding_fallback_reason": "request_failed",
                    "vector_store_requested_provider": "chroma",
                    "vector_store_effective_provider": "chroma",
                }
            )
        )

    with pytest.raises(
        EvaluationContractError,
        match="formal_run_forbids_vector_store_fallback",
    ):
        _validate_formal_retriever_runtime(
            SimpleNamespace(
                embedding_info={
                    "embedding_provider": "dashscope",
                    "embedding_fallback_reason": "",
                    "vector_store_requested_provider": "chroma",
                    "vector_store_effective_provider": "sqlite",
                }
            )
        )


def test_failure_manifest_records_formal_reranker_error(tmp_path):
    output_dir = tmp_path / "failed"

    manifest = write_failure_manifest(
        output_dir,
        started_at="2026-07-28T00:00:00+00:00",
        corpus_dir=tmp_path / "corpus",
        dataset_path=tmp_path / "queries.jsonl",
        dataset_manifest_path=tmp_path / "dataset_manifest.json",
        modes=("hybrid_rerank",),
        allow_reranker_fallback=False,
        error=RuntimeError("qwen3_reranker_missing_api_key"),
    )

    assert manifest["status"] == "failed"
    assert manifest["allow_reranker_fallback"] is False
    assert manifest["error"] == "qwen3_reranker_missing_api_key"
    assert json.loads(
        (output_dir / "failed_run.json").read_text(encoding="utf-8")
    )["error_type"] == "RuntimeError"
