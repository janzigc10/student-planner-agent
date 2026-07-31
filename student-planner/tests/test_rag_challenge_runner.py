from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.agent.rag import (
    RAG_BM25_CANDIDATE_K,
    RAG_EVIDENCE_CANDIDATE_K,
    RAG_RRF_K,
    RAG_VECTOR_CANDIDATE_K,
)
from app.agent.rag_corpus import load_frozen_chunks, write_corpus_artifacts
from app.agent.rag_evaluation import (
    DEFAULT_GATE_GRID,
    EvaluationContractError,
    build_challenge_manifest,
    build_dataset_manifest,
    dataset_sha256,
    parse_evaluation_query,
)
from app.config import settings
from scripts.evaluate_course_rag import DEFAULT_MODES, _sha256_json
from scripts.evaluate_course_rag_challenge import (
    _validate_gate_bundle_linkage,
    run_challenge_evaluation,
)
from scripts.run_course_rag_benchmark_v2 import run_benchmark_v2


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _query_row(
    *,
    query_id: str,
    query: str,
    course_id: str,
    query_type: str,
    answerability: str,
    chunk_id: str,
    source_id: str,
    split: str,
) -> dict:
    relevance = 0 if answerability == "none" else (
        1 if answerability == "partial" else 2
    )
    return {
        "query_id": query_id,
        "query": query,
        "course_id": course_id,
        "query_type": query_type,
        "answerability": answerability,
        "reference_answer": "" if answerability == "none" else "监督学习使用带标签样本。",
        "relevant_source_ids": [] if answerability == "none" else [source_id],
        "relevant_chunk_ids": [] if relevance == 0 else [chunk_id],
        "qrels": [{"chunk_id": chunk_id, "relevance": relevance}],
        "evidence_requirements": [],
        "expected_terms": [] if answerability == "none" else ["监督学习"],
        "split": split,
    }


def _build_two_stage_fixture(tmp_path: Path) -> dict[str, Path]:
    corpus_dir = tmp_path / "corpus"
    source_path = corpus_dir / "machine_learning" / "supervised" / "outline.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "---\n"
        "course_id: machine_learning\n"
        "course_name: 机器学习基础\n"
        "chapter_id: supervised\n"
        "material_type: review_outline\n"
        "synthetic: true\n"
        "corpus_version: test-v1\n"
        "title: 监督学习\n"
        "---\n\n"
        "# 监督学习\n\n监督学习使用带标签样本学习输入与输出的映射，"
        "训练集用于拟合模型，测试集只用于最终评估。",
        encoding="utf-8",
    )
    _, _, corpus_manifest = write_corpus_artifacts(corpus_dir)
    _, chunks = load_frozen_chunks(corpus_dir)
    chunk_id = chunks[0].chunk_id
    source_id = chunks[0].source_id

    main_rows = [
        _query_row(
            query_id="main-dev-full",
            query="监督学习为什么需要标签？",
            course_id="machine_learning",
            query_type="paraphrase",
            answerability="full",
            chunk_id=chunk_id,
            source_id=source_id,
            split="development",
        ),
        _query_row(
            query_id="main-dev-none",
            query="明天的实时天气是什么？",
            course_id="machine_learning",
            query_type="out_of_scope",
            answerability="none",
            chunk_id=chunk_id,
            source_id=source_id,
            split="development",
        ),
        _query_row(
            query_id="main-test-full",
            query="概括监督学习的输入信息。",
            course_id="machine_learning",
            query_type="summary",
            answerability="full",
            chunk_id=chunk_id,
            source_id=source_id,
            split="test",
        ),
        _query_row(
            query_id="main-test-none",
            query="预测下期开奖。",
            course_id="machine_learning",
            query_type="out_of_scope",
            answerability="none",
            chunk_id=chunk_id,
            source_id=source_id,
            split="test",
        ),
    ]
    main_queries = [parse_evaluation_query(row) for row in main_rows]
    main_dataset_path = corpus_dir / "golden_queries.jsonl"
    _write_jsonl(main_dataset_path, (query.to_json() for query in main_queries))
    main_dataset_manifest = build_dataset_manifest(
        main_queries,
        dataset_version="test-main-v1",
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
    )
    main_dataset_manifest["human_review_status"] = "synthetic_unreviewed"
    main_manifest_path = corpus_dir / "dataset_manifest.json"
    _write_json(main_manifest_path, main_dataset_manifest)

    challenge_dir = tmp_path / "challenge_data"
    challenge_dir.mkdir()
    courses = (
        "machine_learning",
        "modern_chinese_history",
        "world_modern_history",
        "political_theory",
    )
    query_types = (
        "paraphrase",
        "multi_concept",
        "long_student_query",
        "out_of_scope",
        "comparison",
        "summary",
    )
    challenge_rows = []
    for index in range(24):
        answerability = "full"
        if index % 6 == 4:
            answerability = "partial"
        elif index % 6 == 5:
            answerability = "none"
        challenge_rows.append(
            _query_row(
                query_id=f"holdout-{index:02d}",
                query=f"未见挑战问题 {index}",
                course_id=courses[index % len(courses)],
                query_type=query_types[index % len(query_types)],
                answerability=answerability,
                chunk_id=chunk_id,
                source_id=source_id,
                split="holdout",
            )
        )
    challenge_queries = [
        parse_evaluation_query(row) for row in challenge_rows
    ]
    challenge_dataset_path = challenge_dir / "challenge_queries.jsonl"
    _write_jsonl(
        challenge_dataset_path,
        (query.to_json() for query in challenge_queries),
    )

    frozen_config = {
        "schema_version": "course-rag-frozen-config-v1",
        "corpus_manifest_sha256": corpus_manifest["manifest_sha256"],
        "retrieval_modes": list(DEFAULT_MODES),
        "embedding": {
            "provider": settings.rag_embedding_provider,
            "model": settings.rag_embedding_model,
            "dimensions": settings.rag_embedding_dimensions,
        },
        "vector_store_provider": settings.rag_vector_store_provider,
        "vector_candidate_top_k": RAG_VECTOR_CANDIDATE_K,
        "bm25_candidate_top_k": RAG_BM25_CANDIDATE_K,
        "rrf_k": RAG_RRF_K,
        "reranker": {
            "provider": settings.rag_reranker_provider,
            "model": settings.rag_reranker_model,
            "candidate_top_k": RAG_EVIDENCE_CANDIDATE_K * 2,
        },
        "evaluation_top_k": 10,
        "answer_context_top_k": 3,
        "formal_reranker_fallback": False,
        "evidence_gate": {
            "parameter_grid_sha256": _sha256_json(
                [dict(config) for config in DEFAULT_GATE_GRID]
            )
        },
    }
    frozen_config_path = challenge_dir / "frozen_config.json"
    _write_json(frozen_config_path, frozen_config)

    pool_rows = [
        {
            "query_id": query.query_id,
            "chunk_id": chunk_id,
            "source_id": source_id,
            "course_id": "machine_learning",
            "chapter_id": "supervised",
            "text": chunks[0].text,
            "origins": [
                {"mode": mode, "rank": 1, "score": 1.0}
                for mode in DEFAULT_MODES
            ],
        }
        for query in challenge_queries
    ]
    pool_path = challenge_dir / "candidate_pool.jsonl"
    _write_jsonl(pool_path, pool_rows)
    challenge_manifest = build_challenge_manifest(
        challenge_queries,
        dataset_version="test-challenge-v1",
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
        evidence_tier="llm_assisted_unreviewed",
        frozen_config_sha256=_sha256_file(frozen_config_path),
    )
    challenge_manifest.update(
        {
            "main_dataset_sha256": dataset_sha256(main_queries),
            "human_review_status": "not_reviewed",
            "pooling": {"candidate_count": len(pool_rows)},
            "artifacts": {
                "frozen_config.json": _sha256_file(frozen_config_path),
                "challenge_queries.jsonl": _sha256_file(
                    challenge_dataset_path
                ),
                "candidate_pool.jsonl": _sha256_file(pool_path),
            },
        }
    )
    challenge_manifest_path = challenge_dir / "challenge_manifest.json"
    _write_json(challenge_manifest_path, challenge_manifest)
    return {
        "corpus_dir": corpus_dir,
        "main_dataset": main_dataset_path,
        "main_manifest": main_manifest_path,
        "challenge_dataset": challenge_dataset_path,
        "challenge_manifest": challenge_manifest_path,
        "challenge_frozen_config": frozen_config_path,
    }


def test_two_stage_runner_reuses_development_gate_without_holdout_calibration(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "rag_embedding_provider", "local")
    monkeypatch.setattr(settings, "rag_embedding_api_key", "")
    monkeypatch.setattr(settings, "rag_vector_store_provider", "memory")
    monkeypatch.setattr(settings, "rag_reranker_api_key", "")
    monkeypatch.setattr(settings, "rag_reranker_base_url", "")
    paths = _build_two_stage_fixture(tmp_path)
    output_root = tmp_path / "run"

    root_manifest = run_benchmark_v2(
        corpus_dir=paths["corpus_dir"],
        main_dataset_path=paths["main_dataset"],
        main_dataset_manifest_path=paths["main_manifest"],
        challenge_dataset_path=paths["challenge_dataset"],
        challenge_manifest_path=paths["challenge_manifest"],
        challenge_frozen_config_path=paths["challenge_frozen_config"],
        output_root=output_root,
        allow_reranker_fallback=True,
        embedding_cost_per_1k=0.0,
        reranker_cost_per_1k=0.0,
        formal_run=False,
        bootstrap_iterations=100,
        bootstrap_seed=23,
    )

    assert root_manifest["schema_version"] == "course-rag-benchmark-v2-run-v1"
    assert root_manifest["gate_flow"] == {
        "calibration_source": "main/development",
        "challenge_reuses_frozen_gate": True,
        "challenge_used_for_tuning": False,
    }
    gate_bundle = json.loads(
        (output_root / "main" / "frozen_gate_config.json").read_text(
            encoding="utf-8"
        )
    )
    challenge_summary = json.loads(
        (output_root / "challenge" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    challenge_run = json.loads(
        (output_root / "challenge" / "run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert gate_bundle["calibration_split"] == "development"
    assert gate_bundle["holdout_used_for_calibration"] is False
    assert challenge_summary["primary_split"] == "holdout"
    assert challenge_summary["holdout_used_for_tuning"] is False
    assert challenge_run["evaluation"]["gate_calibration_performed"] is False
    assert challenge_run["evaluation"]["gate_source"] == (
        "main_dataset_development"
    )
    for mode in DEFAULT_MODES:
        assert challenge_summary["gate"][mode]["frozen_config"] == (
            gate_bundle["gate_configs"][mode]
        )
        assert set(challenge_summary["ranking"][mode]) == {"holdout"}
    prediction_rows = (
        output_root / "challenge" / "gate_predictions.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(prediction_rows) == 24 * 4

    with pytest.raises(
        EvaluationContractError,
        match="output_directory_must_be_empty",
    ):
        run_benchmark_v2(
            corpus_dir=paths["corpus_dir"],
            main_dataset_path=paths["main_dataset"],
            main_dataset_manifest_path=paths["main_manifest"],
            challenge_dataset_path=paths["challenge_dataset"],
            challenge_manifest_path=paths["challenge_manifest"],
            challenge_frozen_config_path=paths["challenge_frozen_config"],
            output_root=output_root,
            allow_reranker_fallback=True,
            embedding_cost_per_1k=0.0,
            reranker_cost_per_1k=0.0,
            formal_run=False,
            bootstrap_iterations=100,
            bootstrap_seed=23,
        )

    corpus_manifest, _ = load_frozen_chunks(paths["corpus_dir"])
    with pytest.raises(
        EvaluationContractError,
        match="formal_challenge_requires_formal_main_run",
    ):
        _validate_gate_bundle_linkage(
            corpus_manifest=corpus_manifest,
            main_dataset_path=paths["main_dataset"],
            main_run_dir=output_root / "main",
            challenge_manifest_path=paths["challenge_manifest"],
            challenge_frozen_config_path=paths["challenge_frozen_config"],
            modes=DEFAULT_MODES,
            formal_run=True,
        )

    original_embedding_model = settings.rag_embedding_model
    monkeypatch.setattr(settings, "rag_embedding_model", "changed-after-main")
    with pytest.raises(
        EvaluationContractError,
        match="challenge_current_embedding_mismatch:model",
    ):
        run_challenge_evaluation(
            corpus_dir=paths["corpus_dir"],
            main_dataset_path=paths["main_dataset"],
            main_run_dir=output_root / "main",
            challenge_dataset_path=paths["challenge_dataset"],
            challenge_manifest_path=paths["challenge_manifest"],
            challenge_frozen_config_path=paths["challenge_frozen_config"],
            output_dir=tmp_path / "provider-mismatch-run",
            modes=DEFAULT_MODES,
            allow_reranker_fallback=True,
            embedding_cost_per_1k=0.0,
            reranker_cost_per_1k=0.0,
            formal_run=False,
            bootstrap_iterations=100,
            bootstrap_seed=23,
        )
    monkeypatch.setattr(
        settings,
        "rag_embedding_model",
        original_embedding_model,
    )

    gate_bundle_path = output_root / "main" / "frozen_gate_config.json"
    gate_bundle_path.write_text(
        gate_bundle_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationContractError,
        match="challenge_gate_bundle_hash_mismatch",
    ):
        run_challenge_evaluation(
            corpus_dir=paths["corpus_dir"],
            main_dataset_path=paths["main_dataset"],
            main_run_dir=output_root / "main",
            challenge_dataset_path=paths["challenge_dataset"],
            challenge_manifest_path=paths["challenge_manifest"],
            challenge_frozen_config_path=paths["challenge_frozen_config"],
            output_dir=tmp_path / "tampered-run",
            modes=DEFAULT_MODES,
            allow_reranker_fallback=True,
            embedding_cost_per_1k=0.0,
            reranker_cost_per_1k=0.0,
            formal_run=False,
            bootstrap_iterations=100,
            bootstrap_seed=23,
        )
