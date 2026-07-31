import pytest

from app.agent.rag import LocalRAGRetriever
from app.agent.rerankers import (
    LocalFeatureReranker,
    Qwen3Reranker,
    RerankerResponseError,
    RerankerUnavailableError,
)
from app.config import settings


class KeywordEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [
            [1.0, 0.0] if "监督学习" in text else [0.0, 1.0]
            for text in texts
        ]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


def _build_corpus(tmp_path):
    (tmp_path / "a.md").write_text(
        "监督学习使用带标签样本训练模型，模型评估需要独立测试集。",
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text(
        "无监督学习处理没有人工标签的数据，常见任务包括聚类。",
        encoding="utf-8",
    )


def test_qwen3_reranker_uses_official_compatible_request_contract():
    captured = {}

    class FakeClient:
        def post(self, path, *, body, cast_to):
            captured.update({"path": path, "body": body, "cast_to": cast_to})
            return {
                "id": "rerank-request",
                "model": "qwen3-rerank",
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.42},
                ],
                "usage": {"total_tokens": 88},
            }

    reranker = Qwen3Reranker(
        api_key="test-key",
        base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-api/v1",
        instruct="Retrieve passages that answer the question.",
        client=FakeClient(),
    )
    ranked = reranker.rerank(
        "监督学习是什么",
        [
            {"content": "候选 A", "metadata": {"chunk_id": "a"}},
            {"content": "候选 B", "metadata": {"chunk_id": "b"}},
        ],
        2,
    )

    assert captured["path"] == "/reranks"
    assert captured["body"] == {
        "model": "qwen3-rerank",
        "query": "监督学习是什么",
        "documents": ["候选 A", "候选 B"],
        "top_n": 2,
        "instruct": "Retrieve passages that answer the question.",
    }
    assert [hit["chunk_id"] for hit in ranked] == ["b", "a"]
    assert [hit["final_rank"] for hit in ranked] == [1, 2]
    assert all(hit["rerank_provider"] == "qwen3-rerank" for hit in ranked)
    assert reranker.last_call_info["usage_total_tokens"] == 88


def test_qwen3_reranker_rejects_invalid_provider_indexes():
    class FakeClient:
        def post(self, path, *, body, cast_to):
            return {"results": [{"index": 9, "relevance_score": 1.0}]}

    reranker = Qwen3Reranker(
        api_key="test-key",
        base_url="https://workspace/compatible-api/v1",
        client=FakeClient(),
    )

    with pytest.raises(RerankerResponseError, match="index_invalid"):
        reranker.rerank("问题", [{"content": "候选"}], 1)


def test_local_feature_reranker_is_deterministic():
    candidates = [
        {
            "content": "A",
            "metadata": {"chunk_id": "a"},
            "hybrid_norm": 0.4,
            "vector_norm": 0.4,
            "bm25_norm": 0.4,
            "anchor_coverage": 0.4,
            "segment_coverage": 0.4,
            "exact_term_coverage": 0.4,
        },
        {
            "content": "B",
            "metadata": {"chunk_id": "b"},
            "hybrid_norm": 0.9,
            "vector_norm": 0.9,
            "bm25_norm": 0.9,
            "anchor_coverage": 0.9,
            "segment_coverage": 0.9,
            "exact_term_coverage": 0.9,
        },
    ]

    first = LocalFeatureReranker().rerank("问题", candidates, 2)
    second = LocalFeatureReranker().rerank("问题", candidates, 2)

    assert first == second
    assert [hit["chunk_id"] for hit in first] == ["b", "a"]


def test_retriever_exposes_four_modes_and_explicit_interactive_fallback(
    tmp_path,
    monkeypatch,
):
    _build_corpus(tmp_path)
    monkeypatch.setattr(settings, "rag_vector_store_provider", "memory")
    monkeypatch.setattr(settings, "rag_reranker_api_key", "")
    monkeypatch.setattr(settings, "rag_reranker_base_url", "")
    retriever = LocalRAGRetriever(tmp_path, embeddings=KeywordEmbeddings())

    embedding = retriever.retrieve("监督学习是什么", 2, mode="embedding_only")
    bm25 = retriever.retrieve("监督学习是什么", 2, mode="bm25_only")
    rrf = retriever.retrieve("监督学习是什么", 2, mode="hybrid_rrf")
    reranked = retriever.retrieve(
        "监督学习是什么",
        2,
        mode="hybrid_rerank",
        allow_reranker_fallback=True,
    )

    assert all(hit["rerank_provider"] == "none" for hit in embedding + bm25 + rrf)
    assert all(hit["final_rank"] >= 1 for hit in embedding + bm25 + rrf + reranked)
    assert retriever.last_retrieval_info["retrieval_mode"] == "hybrid_rerank"
    assert retriever.last_retrieval_info["reranker_provider"] == "local-feature-rerank"
    assert (
        retriever.last_retrieval_info["reranker_fallback_reason"]
        == "qwen3_reranker_missing_api_key"
    )


def test_formal_hybrid_rerank_does_not_silently_fallback(tmp_path, monkeypatch):
    _build_corpus(tmp_path)
    monkeypatch.setattr(settings, "rag_vector_store_provider", "memory")
    monkeypatch.setattr(settings, "rag_reranker_api_key", "")
    monkeypatch.setattr(settings, "rag_reranker_base_url", "")
    retriever = LocalRAGRetriever(tmp_path, embeddings=KeywordEmbeddings())

    with pytest.raises(RerankerUnavailableError, match="missing_api_key"):
        retriever.retrieve(
            "监督学习是什么",
            2,
            mode="hybrid_rerank",
            allow_reranker_fallback=False,
        )
