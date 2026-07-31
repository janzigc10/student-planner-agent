import json

import pytest

from app.agent.rag_corpus import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CorpusContractError,
    build_corpus_artifacts,
    frozen_chunk_documents,
    load_course_sources,
    load_frozen_chunks,
    normalize_text,
    parse_front_matter,
    stable_chunk_id,
    write_corpus_artifacts,
)


def _write_source(root, *, body: str, source: str = "machine_learning/chapter/material.md"):
    path = root / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\ufeff---\r\n"
        "course_id: machine_learning\r\n"
        "chapter_id: model_evaluation\r\n"
        "material_type: review_outline\r\n"
        "synthetic: true\r\n"
        "corpus_version: rag-course-v1\r\n"
        "---\r\n"
        f"{body}",
        encoding="utf-8",
    )
    return path


def test_normalizer_and_front_matter_contract():
    metadata, body = parse_front_matter(
        "\ufeff---\r\nsynthetic: true\r\ncourse_id: machine_learning\r\n---\r\n"
        "Cafe\u0301   \r\n第二行\t \r\n"
    )

    assert metadata == {"synthetic": True, "course_id": "machine_learning"}
    assert body == "Café\n第二行"
    assert normalize_text("\ufeffA \r\nB\t\r") == "A\nB"


def test_frozen_corpus_builds_stable_provider_independent_chunk_ids(tmp_path):
    body = "\n\n".join(
        f"## 段落 {index}\n监督学习模型评估需要区分训练集、验证集和测试集。"
        f"第 {index} 段说明交叉验证、过拟合与泛化误差之间的关系。"
        for index in range(30)
    )
    _write_source(tmp_path, body=body)

    first_manifest, first_chunks = build_corpus_artifacts(tmp_path)
    second_manifest, second_chunks = build_corpus_artifacts(tmp_path)

    assert first_manifest == second_manifest
    assert [chunk.chunk_id for chunk in first_chunks] == [
        chunk.chunk_id for chunk in second_chunks
    ]
    assert first_manifest["source_count"] == 1
    assert first_manifest["chunk_count"] == len(first_chunks) > 1
    assert all(len(chunk.text) <= CHUNK_SIZE for chunk in first_chunks)
    assert all(chunk.metadata["synthetic"] is True for chunk in first_chunks)
    assert all("course_id:" not in chunk.text for chunk in first_chunks)
    assert first_manifest["chunker"]["chunk_overlap"] == CHUNK_OVERLAP
    assert first_chunks[0].chunk_id == stable_chunk_id(
        first_chunks[0].source_id,
        first_chunks[0].chunk_index,
        first_chunks[0].text,
    )


def test_write_and_load_frozen_artifacts_reject_source_drift(tmp_path):
    source_path = _write_source(
        tmp_path,
        body="# 模型评估\n准确率、精确率、召回率和 F1 各自回答不同问题。",
    )
    manifest_path, chunks_path, manifest = write_corpus_artifacts(tmp_path)

    loaded_manifest, chunks = load_frozen_chunks(tmp_path)

    assert loaded_manifest == manifest
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["manifest_sha256"]
    assert chunks_path.read_text(encoding="utf-8").count("\n") == len(chunks)

    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "\n新增内容。",
        encoding="utf-8",
    )
    with pytest.raises(
        CorpusContractError,
        match="corpus_sources_changed_rebuild_required",
    ):
        load_frozen_chunks(tmp_path)


def test_strict_metadata_requires_synthetic_flag(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text(
        "---\n"
        "course_id: history\n"
        "chapter_id: intro\n"
        "material_type: notes\n"
        "synthetic: false\n"
        "corpus_version: rag-course-v1\n"
        "---\n"
        "正文",
        encoding="utf-8",
    )

    with pytest.raises(CorpusContractError, match="synthetic_flag_required"):
        build_corpus_artifacts(tmp_path)


def test_ad_hoc_runtime_corpus_without_front_matter_still_gets_stable_chunks(tmp_path):
    (tmp_path / "legacy.md").write_text(
        "改革开放是在 1978 年 12 月中共十一届三中全会后开始正式实施的。",
        encoding="utf-8",
    )

    sources = load_course_sources(tmp_path, strict_metadata=False)
    documents = frozen_chunk_documents(tmp_path)

    assert sources[0].source_id == "legacy.md"
    assert documents[0]["metadata"]["source"] == "legacy.md"
    assert documents[0]["metadata"]["chunk_id"]
