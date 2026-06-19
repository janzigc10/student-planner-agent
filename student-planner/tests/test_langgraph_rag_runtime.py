import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent import rag as rag_module
from app.agent.langchain_tools import langchain_assignment_tool_names, langchain_tool_schemas
from app.agent.langgraph_loop import (
    get_langgraph_router_shell_mermaid,
    prepare_langgraph_state,
    run_langgraph_agent_loop,
)
from app.agent.loop import (
    _looks_like_task_write_context,
    _should_require_task_tool_response,
    run_agent_loop,
    run_review_override_plan_write,
)
from app.agent.rag import LocalRAGRetriever, OpenAICompatibleEmbeddings, build_rag_context, clear_rag_cache
from app.config import settings
from app.models.task import Task
from app.models.user import User
from tests.conftest import TestSession


def stream_response_chunks(*, response: dict):
    async def _generator():
        yield {"type": "response", "response": response}

    return _generator()


@pytest.fixture(autouse=True)
def disable_real_rag_embedding_key(monkeypatch):
    clear_rag_cache()
    monkeypatch.setattr(settings, "rag_embedding_provider", "dashscope")
    monkeypatch.setattr(settings, "rag_embedding_model", "text-embedding-v4")
    monkeypatch.setattr(settings, "rag_embedding_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(settings, "rag_embedding_api_key", "")
    monkeypatch.setattr(settings, "rag_vector_store_provider", "memory")
    yield
    clear_rag_cache()


def test_local_rag_retrieves_course_materials(tmp_path):
    (tmp_path / "大学英语3复习资料.md").write_text(
        "\n".join(
            [
                "# 大学英语3复习资料",
                "Unit1-6 复习重点包括听力精听、作文模板、课后词汇和长难句整理。",
                "建议先完成 Unit1-3 的听力跟读，再集中写作训练，最后用错题回顾补弱。",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "世界现代史专题案例.md").write_text(
        "冷战、马歇尔计划、北约、华约和欧洲一体化是世界现代史专题复习材料。",
        encoding="utf-8",
    )

    result = build_rag_context("大学英语3 Unit1-6 听力写作复习计划", corpus_dir=tmp_path)

    assert result["document_count"] > 0
    assert result["hits"]
    assert "大学英语3" in result["context"]
    assert result["corpus_dir"] == str(tmp_path)
    assert result["chunk_size"] == 520
    assert result["chunk_overlap"] == 150


def test_dashscope_embedding_config_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "rag_embedding_provider", "dashscope")
    monkeypatch.setattr(settings, "rag_embedding_model", "text-embedding-v4")
    monkeypatch.setattr(settings, "rag_embedding_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(settings, "rag_embedding_api_key", "")

    result = build_rag_context("大学英语3 Unit1-6 听力写作复习计划")

    assert result["embedding_configured_provider"] == "dashscope"
    assert result["embedding_configured_model"] == "text-embedding-v4"
    assert result["embedding_provider"] == "hash-fallback"
    assert result["embedding_model"] == "local-hash"
    assert result["embedding_fallback_reason"] == "missing_api_key"


def test_large_rag_corpus_routes_history_and_politics_queries(tmp_path):
    (tmp_path / "世界现代史专题案例.md").write_text(
        "冷战格局复习重点包括马歇尔计划、杜鲁门主义、北约、华约和两极对峙。",
        encoding="utf-8",
    )
    (tmp_path / "思想政治理论复习大纲.md").write_text(
        "共同富裕、新发展格局、全过程人民民主、民主协商、民主监督和法治中国是政治理论重点。",
        encoding="utf-8",
    )
    (tmp_path / "中国近现代史复习大纲.md").write_text(
        "五四运动、新民主主义革命、抗日民族统一战线、遵义会议和工人阶级是近现代史重点。",
        encoding="utf-8",
    )
    cases = [
        ("马歇尔计划 北约 华约 冷战 杜鲁门主义", {"世界现代史专题案例.md"}),
        ("共同富裕 新发展格局 全过程人民民主 法治中国", {"思想政治理论复习大纲.md"}),
        ("五四运动 新民主主义革命 抗日民族统一战线 遵义会议", {"中国近现代史复习大纲.md"}),
    ]

    for query, expected_sources in cases:
        result = build_rag_context(query, corpus_dir=tmp_path, top_k=3)
        sources = [str(hit["metadata"].get("source", "")).replace("\\", "/") for hit in result["hits"]]
        assert expected_sources.intersection(sources)


def test_rag_context_uses_query_relevant_excerpt(tmp_path):
    (tmp_path / "维基百科-改革开放.md").write_text(
        "改革开放是在 1978 年 12 月中共十一届三中全会后开始正式实施的。"
        "无关尾部内容用于模拟同一 chunk 中和问题无关的长背景材料，不应进入最终 RAG 提示。",
        encoding="utf-8",
    )

    result = build_rag_context("改革开放是什么时候开始的", corpus_dir=tmp_path, top_k=1)

    assert "1978 年" in result["context"]
    assert "无关尾部内容" not in result["context"]


def test_rag_context_marks_insufficient_evidence_for_uncovered_questions(tmp_path):
    (tmp_path / "维基百科-改革开放.md").write_text(
        "改革开放是在 1978 年 12 月中共十一届三中全会后开始正式实施的。",
        encoding="utf-8",
    )

    hit = build_rag_context("改革开放是什么时候开始的", corpus_dir=tmp_path, top_k=1)
    miss = build_rag_context("量子计算的退相干错误怎么解释", corpus_dir=tmp_path, top_k=1)

    assert hit["evidence_sufficient"] is True
    assert hit["evidence_count"] == 1
    assert "1978 年" in hit["context"]
    assert miss["hits"], "retrieval may still return a nearest chunk"
    assert miss["evidence_sufficient"] is False
    assert miss["evidence_count"] == 0
    assert miss["context"] == ""


def test_rag_context_rejects_topic_only_overlap_when_requested_detail_is_absent(tmp_path):
    (tmp_path / "机器学习课程资料.md").write_text(
        "机器学习课程资料：监督学习、特征工程、模型训练与过拟合。",
        encoding="utf-8",
    )

    result = build_rag_context("机器学习里的量子退相干错误怎么解释", corpus_dir=tmp_path, top_k=1)

    assert result["hits"], "retrieval may return a topical nearest chunk"
    assert result["evidence_sufficient"] is False
    assert result["evidence_count"] == 0
    assert result["context"] == ""

    no_separator_result = build_rag_context(
        "机器学习监督学习特征工程模型训练过拟合火星殖民关系是什么",
        corpus_dir=tmp_path,
        top_k=1,
    )

    assert no_separator_result["hits"], "retrieval may return a strong topical nearest chunk"
    assert no_separator_result["evidence_sufficient"] is False
    assert no_separator_result["evidence_count"] == 0
    assert no_separator_result["context"] == ""


def test_rag_context_rejects_mixed_query_when_new_concept_is_absent(tmp_path):
    (tmp_path / "机器学习课程资料.md").write_text(
        "机器学习课程资料：监督学习、特征工程、模型训练与过拟合。",
        encoding="utf-8",
    )

    result = build_rag_context(
        "机器学习监督学习特征工程模型训练过拟合与火星殖民关系是什么",
        corpus_dir=tmp_path,
        top_k=1,
    )

    assert result["hits"], "retrieval may return a strong topical nearest chunk"
    assert result["evidence_sufficient"] is False
    assert result["evidence_count"] == 0
    assert result["context"] == ""


def test_rag_context_keeps_public_hits_and_context_within_requested_top_k(tmp_path):
    for index in range(12):
        (tmp_path / f"改革开放资料{index}.md").write_text(
            f"改革开放是在 1978 年 12 月中共十一届三中全会后开始正式实施的。资料编号 {index}。",
            encoding="utf-8",
        )

    result = build_rag_context("改革开放是什么时候开始的", corpus_dir=tmp_path, top_k=3)

    assert result["requested_top_k"] == 3
    assert result["candidate_top_k"] == 10
    assert len(result["hits"]) == 3
    assert len(result["candidate_hits"]) == 10
    assert result["evidence_sufficient"] is True
    assert result["evidence_count"] >= 3
    assert result["evidence_context_count"] == 3
    assert result["context"].count("来源：") == 3


def test_openai_compatible_embeddings_calls_dashscope_config(monkeypatch):
    captured: dict[str, object] = {}
    calls: list[list[str]] = []

    class FakeEmbeddingsResource:
        def create(self, *, model, input):
            captured["model"] = model
            captured["input"] = input
            calls.append(input)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[float(index), float(index + 1)])
                    for index, _ in enumerate(input)
                ]
            )

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            self.embeddings = FakeEmbeddingsResource()

    monkeypatch.setattr(rag_module, "OpenAI", FakeOpenAI)

    embeddings = OpenAICompatibleEmbeddings(
        api_key="dashscope-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="text-embedding-v4",
    )

    texts = [f"文本{index}" for index in range(12)]
    vectors = embeddings.embed_documents(texts)

    assert len(vectors) == 12
    assert calls == [texts[:10], texts[10:]]
    assert captured["api_key"] == "dashscope-key"
    assert captured["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert captured["model"] == "text-embedding-v4"
    assert captured["input"] == texts[10:]


def test_sqlite_vector_store_reuses_document_embeddings(tmp_path, monkeypatch):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "课程资料.md").write_text(
        "# 课程资料\n\n五四运动 新民主主义革命 工人阶级 马克思主义传播",
        encoding="utf-8",
    )
    vector_store_dir = tmp_path / "vectors"
    monkeypatch.setattr(settings, "rag_vector_store_provider", "sqlite")
    monkeypatch.setattr(settings, "rag_vector_store_dir", str(vector_store_dir))

    class CountingEmbeddings:
        def __init__(self) -> None:
            self.document_calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.document_calls += len(texts)
            return [[float(index + 1), 1.0] for index, _ in enumerate(texts)]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 1.0]

    first_embeddings = CountingEmbeddings()
    first = LocalRAGRetriever(corpus_dir, embeddings=first_embeddings)

    assert first_embeddings.document_calls == len(first.documents)
    assert first.embedding_info["vector_store_provider"] == "sqlite"
    assert first.embedding_info["vector_store_misses"] == str(len(first.documents))

    second_embeddings = CountingEmbeddings()
    second = LocalRAGRetriever(corpus_dir, embeddings=second_embeddings)

    assert second_embeddings.document_calls == 0
    assert second.embedding_info["vector_store_hits"] == str(len(second.documents))
    assert second.embedding_info["vector_store_misses"] == "0"


def test_chroma_vector_store_falls_back_to_sqlite_when_runtime_is_unavailable(tmp_path, monkeypatch):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "课程资料.md").write_text(
        "# 课程资料\n\n五四运动 新民主主义革命 工人阶级 马克思主义传播",
        encoding="utf-8",
    )
    vector_store_dir = tmp_path / "chroma"
    monkeypatch.setattr(settings, "rag_vector_store_provider", "chroma")
    monkeypatch.setattr(settings, "rag_vector_store_dir", str(vector_store_dir))
    monkeypatch.setattr(
        rag_module,
        "_chroma_runtime_available",
        lambda: (False, "chroma_probe_failed:returncode=1"),
    )

    class CountingEmbeddings:
        def __init__(self) -> None:
            self.document_calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.document_calls += len(texts)
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    first_embeddings = CountingEmbeddings()
    first = LocalRAGRetriever(corpus_dir, embeddings=first_embeddings)

    assert first_embeddings.document_calls == len(first.documents)
    assert first.embedding_info["vector_store_requested_provider"] == "chroma"
    assert first.embedding_info["vector_store_provider"] == "sqlite"
    assert first.embedding_info["vector_store_effective_provider"] == "sqlite"
    assert first.embedding_info["vector_store_fallback_reason"] == "chroma_probe_failed:returncode=1"
    assert first.embedding_info["vector_store_misses"] == str(len(first.documents))

    second_embeddings = CountingEmbeddings()
    second = LocalRAGRetriever(corpus_dir, embeddings=second_embeddings)

    assert second_embeddings.document_calls == 0
    assert second.embedding_info["vector_store_requested_provider"] == "chroma"
    assert second.embedding_info["vector_store_provider"] == "sqlite"
    assert second.embedding_info["vector_store_hits"] == str(len(second.documents))
    assert second.embedding_info["vector_store_misses"] == "0"
    assert second.retrieve("五四运动", top_k=1)[0]["metadata"]["source"] == "课程资料.md"


def test_chroma_vector_store_reuses_document_embeddings_with_available_runtime(tmp_path, monkeypatch):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "课程资料.md").write_text(
        "# 课程资料\n\n五四运动 新民主主义革命 工人阶级 马克思主义传播",
        encoding="utf-8",
    )
    vector_store_dir = tmp_path / "chroma"
    monkeypatch.setattr(settings, "rag_vector_store_provider", "chroma")
    monkeypatch.setattr(settings, "rag_vector_store_dir", str(vector_store_dir))
    monkeypatch.setattr(rag_module, "_chroma_runtime_available", lambda: (True, ""))

    class FakeCollection:
        def __init__(self) -> None:
            self.records: dict[str, dict[str, object]] = {}

        def get(self, *, ids, include):
            existing_ids = [item_id for item_id in ids if item_id in self.records]
            return {
                "ids": existing_ids,
                "metadatas": [self.records[item_id]["metadata"] for item_id in existing_ids],
            }

        def upsert(self, *, ids, documents, embeddings, metadatas):
            for item_id, document, embedding, metadata in zip(
                ids, documents, embeddings, metadatas, strict=True
            ):
                self.records[item_id] = {
                    "document": document,
                    "embedding": embedding,
                    "metadata": metadata,
                }

        def query(self, *, query_embeddings, n_results, where, include):
            corpus_key = where["corpus_key"]
            matches = [
                record
                for record in self.records.values()
                if record["metadata"]["corpus_key"] == corpus_key
            ][:n_results]
            return {
                "documents": [[record["document"] for record in matches]],
                "metadatas": [[record["metadata"] for record in matches]],
                "distances": [[0.0 for _ in matches]],
            }

    fake_collection = FakeCollection()
    fake_client = SimpleNamespace(
        get_or_create_collection=lambda *args, **kwargs: fake_collection,
    )
    fake_chromadb = SimpleNamespace(PersistentClient=lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(rag_module, "chromadb", fake_chromadb)

    class CountingEmbeddings:
        def __init__(self) -> None:
            self.document_calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.document_calls += len(texts)
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    first_embeddings = CountingEmbeddings()
    first = LocalRAGRetriever(corpus_dir, embeddings=first_embeddings)

    assert first_embeddings.document_calls == len(first.documents)
    assert first.embedding_info["vector_store_provider"] == "chroma"
    assert first.embedding_info["vector_store_misses"] == str(len(first.documents))

    second_embeddings = CountingEmbeddings()
    second = LocalRAGRetriever(corpus_dir, embeddings=second_embeddings)

    assert second_embeddings.document_calls == 0
    assert second.embedding_info["vector_store_provider"] == "chroma"
    assert second.embedding_info["vector_store_hits"] == str(len(second.documents))
    assert second.retrieve("五四运动", top_k=1)[0]["metadata"]["source"] == "课程资料.md"


def test_chroma_vector_store_refreshes_stale_corpus_metadata(tmp_path, monkeypatch):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "a.md").write_text("五四运动 新民主主义革命 工人阶级", encoding="utf-8")
    vector_store_dir = tmp_path / "chroma"
    monkeypatch.setattr(settings, "rag_vector_store_provider", "chroma")
    monkeypatch.setattr(settings, "rag_vector_store_dir", str(vector_store_dir))
    monkeypatch.setattr(rag_module, "_chroma_runtime_available", lambda: (True, ""))

    class FakeCollection:
        def __init__(self) -> None:
            self.records: dict[str, dict[str, object]] = {}

        def get(self, *, ids, include):
            existing_ids = [item_id for item_id in ids if item_id in self.records]
            return {
                "ids": existing_ids,
                "metadatas": [self.records[item_id]["metadata"] for item_id in existing_ids],
            }

        def upsert(self, *, ids, documents, embeddings, metadatas):
            for item_id, document, embedding, metadata in zip(
                ids, documents, embeddings, metadatas, strict=True
            ):
                self.records[item_id] = {
                    "document": document,
                    "embedding": embedding,
                    "metadata": metadata,
                }

        def query(self, *, query_embeddings, n_results, where, include):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    fake_collection = FakeCollection()
    fake_client = SimpleNamespace(
        get_or_create_collection=lambda *args, **kwargs: fake_collection,
    )
    fake_chromadb = SimpleNamespace(PersistentClient=lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(rag_module, "chromadb", fake_chromadb)

    class CountingEmbeddings:
        def __init__(self) -> None:
            self.document_calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.document_calls += len(texts)
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [1.0, 0.0]

    first_embeddings = CountingEmbeddings()
    first = LocalRAGRetriever(corpus_dir, embeddings=first_embeddings)

    (corpus_dir / "z.md").write_text("马歇尔计划 冷战 欧洲复兴", encoding="utf-8")
    second_embeddings = CountingEmbeddings()
    second = LocalRAGRetriever(corpus_dir, embeddings=second_embeddings)

    assert first.corpus_key != second.corpus_key
    assert second.embedding_info["vector_store_hits"] == "0"
    assert second.embedding_info["vector_store_misses"] == str(len(second.documents))
    assert second_embeddings.document_calls == len(second.documents)


def test_langchain_tool_schemas_expose_assignment_tools():
    schemas = langchain_tool_schemas(langchain_assignment_tool_names())
    names = {schema["name"] for schema in schemas}

    assert {"get_free_slots", "create_study_plan", "create_task", "ask_user"} <= names
    assert all("parameters" in schema for schema in schemas)


def test_review_qa_is_not_forced_into_task_write_context():
    qa_message = "帮我复习一下：冷战格局形成过程中，杜鲁门主义、马歇尔计划、北约和华约分别起什么作用？"

    assert _looks_like_task_write_context([qa_message]) is False
    assert _should_require_task_tool_response([qa_message], []) is False
    assert _looks_like_task_write_context(["下周四有大学英语3考试，帮我做复习计划"]) is True


def test_langgraph_router_shell_mermaid_exposes_route_nodes():
    mermaid = get_langgraph_router_shell_mermaid()

    for node_name in (
        "route",
        "no_web",
        "retrieve_rag",
        "compose_runtime_hints",
        "rag_insufficient",
        "tool_workflow",
        "study_plan",
        "schedule_import",
        "course_maintenance",
        "delegate_legacy_loop",
    ):
        assert node_name in mermaid


@pytest.mark.asyncio
async def test_prepare_langgraph_state_routes_no_web_inside_graph(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: (_ for _ in ()).throw(AssertionError("no-web should not retrieve RAG")),
    )

    state = await prepare_langgraph_state("最新政策是什么")

    assert state["route"] == "no_web"
    assert state["should_retrieve"] is False
    assert state["should_delegate_legacy_loop"] is False
    assert state["terminal_response"] == "no_web"
    assert state["graph_nodes"] == ["route", "no_web"]


@pytest.mark.asyncio
async def test_prepare_langgraph_state_adds_rag_runtime_hint():
    state = await prepare_langgraph_state("改革开放是什么时候开始的")

    assert state["route"] == "rag_qa"
    assert state["should_retrieve"] is True
    assert "retrieve_rag" in state["graph_nodes"]
    assert "compose_runtime_hints" in state["graph_nodes"]
    assert "delegate_legacy_loop" in state["graph_nodes"]
    assert state["should_delegate_legacy_loop"] is True
    assert state["uses_langchain_tools"] is True
    assert any("RAG 检索上下文" in hint for hint in state["runtime_hints"])
    assert any("复习问答" in hint for hint in state["runtime_hints"])
    assert any("不要在结尾追加" in hint for hint in state["runtime_hints"])


@pytest.mark.asyncio
async def test_prepare_langgraph_state_routes_rag_insufficient_inside_graph(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: {
            "hits": [],
            "context": "",
            "evidence_sufficient": False,
            "evidence_count": 0,
            "evidence_reason": "no_relevant_local_evidence",
        },
    )

    state = await prepare_langgraph_state("量子计算的退相干错误怎么解释")

    assert state["route"] == "rag_insufficient"
    assert state["should_gate_rag_answer"] is True
    assert state["should_delegate_legacy_loop"] is False
    assert state["terminal_response"] == "rag_insufficient"
    assert state["graph_nodes"] == ["route", "retrieve_rag", "rag_insufficient"]


@pytest.mark.asyncio
async def test_prepare_langgraph_state_routes_study_plan_to_native_action_node(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: {
            "hits": [],
            "context": "",
            "evidence_sufficient": False,
            "evidence_count": 0,
            "evidence_reason": "no_relevant_local_evidence",
        },
    )

    state = await prepare_langgraph_state("下周四有大学英语3考试，帮我安排一下")

    assert state["route"] == "study_plan"
    assert state["should_retrieve"] is True
    assert state["should_gate_rag_answer"] is False
    assert state["should_delegate_legacy_loop"] is False
    assert state["runtime_hints"] == []
    assert state["graph_nodes"] == [
        "route",
        "retrieve_rag",
        "compose_runtime_hints",
        "study_plan",
    ]
    assert "delegate_legacy_loop" not in state["graph_nodes"]


@pytest.mark.asyncio
async def test_prepare_langgraph_state_routes_schedule_import_to_native_action_node(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: (_ for _ in ()).throw(AssertionError("schedule import should not retrieve RAG")),
    )

    state = await prepare_langgraph_state("上传课表 file_id=abc123 请导入")

    assert state["route"] == "schedule_import"
    assert state["should_retrieve"] is False
    assert state["should_gate_rag_answer"] is False
    assert state["should_delegate_legacy_loop"] is False
    assert state["graph_nodes"] == ["route", "schedule_import"]
    assert "delegate_legacy_loop" not in state["graph_nodes"]


@pytest.mark.asyncio
async def test_prepare_langgraph_state_keeps_reminder_route_non_gating_with_rag_side_channel(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: {
            "hits": [],
            "context": "",
            "evidence_sufficient": False,
            "evidence_count": 0,
            "evidence_reason": "no_relevant_local_evidence",
        },
    )

    state = await prepare_langgraph_state("明天下午3点提醒我复习线代")

    assert state["route"] == "tool_workflow"
    assert state["should_retrieve"] is True
    assert state["should_gate_rag_answer"] is False
    assert state["should_delegate_legacy_loop"] is False
    assert state["graph_nodes"] == [
        "route",
        "retrieve_rag",
        "compose_runtime_hints",
        "tool_workflow",
    ]
    assert "delegate_legacy_loop" not in state["graph_nodes"]


@pytest.mark.asyncio
async def test_prepare_langgraph_state_routes_task_update_reminder_to_native_action_node(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: (_ for _ in ()).throw(AssertionError("task update should not retrieve RAG")),
    )

    state = await prepare_langgraph_state("把刚才的任务改到2099-06-01 16:00-17:00，提前15分钟提醒")

    assert state["route"] == "tool_workflow"
    assert state["should_retrieve"] is False
    assert state["should_gate_rag_answer"] is False
    assert state["should_delegate_legacy_loop"] is False
    assert state["graph_nodes"] == ["route", "tool_workflow"]
    assert "delegate_legacy_loop" not in state["graph_nodes"]


@pytest.mark.asyncio
async def test_prepare_langgraph_state_routes_course_maintenance_to_native_action_node(monkeypatch):
    monkeypatch.setattr(
        "app.agent.langgraph_loop.build_rag_context",
        lambda _: (_ for _ in ()).throw(AssertionError("course maintenance should not retrieve RAG")),
    )

    state = await prepare_langgraph_state("把自然语言处理课程改名为 NLP")

    assert state["route"] == "course_maintenance"
    assert state["should_retrieve"] is False
    assert state["should_gate_rag_answer"] is False
    assert state["should_delegate_legacy_loop"] is False
    assert state["graph_nodes"] == ["route", "course_maintenance"]
    assert "delegate_legacy_loop" not in state["graph_nodes"]


@pytest.mark.asyncio
async def test_review_qa_agent_loop_does_not_require_tools_or_ask_user(setup_db):
    captured_tool_choices: list[str | None] = []

    def mock_chat_completion_stream(client, messages, tools=None, tool_choice=None):
        captured_tool_choices.append(tool_choice)
        return stream_response_chunks(
            response={
                "role": "assistant",
                "content": "杜鲁门主义提出遏制共产主义，马歇尔计划用经济援助巩固西欧，北约把阵营军事化，华约则是苏联阵营的回应。",
            }
        )

    with patch("app.agent.loop.chat_completion_stream", side_effect=mock_chat_completion_stream):
        async with TestSession() as db:
            user = User(id="user-review-qa", username="review-qa", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_agent_loop(
                "帮我复习一下：冷战格局形成过程中，杜鲁门主义、马歇尔计划、北约和华约分别起什么作用？",
                user,
                "session-review-qa",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert captured_tool_choices == [None]
    assert not any(event["type"] == "ask_user" for event in events)
    assert any(event["type"] == "text" and "杜鲁门主义" in event["content"] for event in events)


@pytest.mark.asyncio
async def test_langgraph_agent_loop_emits_rag_events_and_delegates_with_hints(setup_db):
    captured: dict[str, object] = {}

    async def fake_run_agent_loop(*args, **kwargs):
        captured["runtime_hints"] = kwargs.get("runtime_hints")
        yield {"type": "done"}

    with patch("app.agent.langgraph_loop.run_agent_loop", side_effect=fake_run_agent_loop):
        async with TestSession() as db:
            user = User(id="user-langgraph-runtime", username="langgraph-runtime", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "改革开放是什么时候开始的",
                user,
                "session-langgraph-runtime",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert events[0]["type"] == "tool_call"
    assert events[0]["name"] == "rag_retrieve_study_materials"
    assert events[1]["type"] == "tool_result"
    assert events[1]["result"]["count"] > 0
    assert events[1]["result"]["embedding_configured_model"] == "text-embedding-v4"
    assert events[-1]["type"] == "done"
    assert any("RAG 检索上下文" in hint for hint in captured["runtime_hints"])


@pytest.mark.asyncio
async def test_langgraph_agent_loop_blocks_rag_qa_when_evidence_is_insufficient(setup_db):
    insufficient_rag = {
        "query": "量子计算的退相干错误怎么解释",
        "hits": [{"score": 0.01, "content": "改革开放材料", "metadata": {"source": "a.md"}}],
        "context": "",
        "evidence_sufficient": False,
        "evidence_count": 0,
        "evidence_reason": "no_relevant_local_evidence",
    }

    with (
        patch("app.agent.langgraph_loop.build_rag_context", return_value=insufficient_rag),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("RAG evidence gate should not delegate to the LLM loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-rag-gate-miss", username="rag-gate-miss", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "量子计算的退相干错误怎么解释",
                user,
                "session-rag-gate-miss",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[1]["result"]["evidence_sufficient"] is False
    assert events[2]["content"] == "当前知识库没有足够资料，无法基于本地资料可靠回答这个问题。"


@pytest.mark.asyncio
async def test_langgraph_agent_loop_blocks_topic_only_rag_candidate_without_question_word(setup_db):
    insufficient_rag = {
        "query": "冷战格局形成过程",
        "hits": [],
        "context": "",
        "evidence_sufficient": False,
        "evidence_count": 0,
        "evidence_reason": "no_relevant_local_evidence",
    }

    with (
        patch("app.agent.langgraph_loop.build_rag_context", return_value=insufficient_rag),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Topic-only RAG candidates should still be evidence gated"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-rag-gate-topic", username="rag-gate-topic", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "冷战格局形成过程",
                user,
                "session-rag-gate-topic",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[1]["result"]["evidence_sufficient"] is False
    assert events[2]["content"] == "当前知识库没有足够资料，无法基于本地资料可靠回答这个问题。"


@pytest.mark.asyncio
async def test_langgraph_agent_loop_blocks_rag_qa_when_task_is_domain_word(setup_db):
    insufficient_rag = {
        "query": "机器学习任务中的欠拟合是什么",
        "hits": [],
        "context": "",
        "evidence_sufficient": False,
        "evidence_count": 0,
        "evidence_reason": "no_relevant_local_evidence",
    }

    with (
        patch("app.agent.langgraph_loop.build_rag_context", return_value=insufficient_rag),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Domain-word task questions should still be evidence gated"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-rag-gate-domain-task", username="rag-gate-domain-task", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "机器学习任务中的欠拟合是什么",
                user,
                "session-rag-gate-domain-task",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[1]["result"]["evidence_sufficient"] is False


@pytest.mark.asyncio
async def test_langgraph_agent_loop_blocks_arrangement_question_when_evidence_is_insufficient(setup_db):
    insufficient_rag = {
        "query": "二战后的国际秩序安排是什么",
        "hits": [],
        "context": "",
        "evidence_sufficient": False,
        "evidence_count": 0,
        "evidence_reason": "no_relevant_local_evidence",
    }

    with (
        patch("app.agent.langgraph_loop.build_rag_context", return_value=insufficient_rag),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Knowledge questions using 安排 should still be evidence gated"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-rag-gate-arrangement", username="rag-gate-arrangement", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "二战后的国际秩序安排是什么",
                user,
                "session-rag-gate-arrangement",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[1]["result"]["evidence_sufficient"] is False
    assert events[2]["content"] == "当前知识库没有足够资料，无法基于本地资料可靠回答这个问题。"


@pytest.mark.asyncio
async def test_langgraph_agent_loop_keeps_task_planning_path_when_rag_evidence_is_insufficient(setup_db):
    captured: dict[str, object] = {}
    insufficient_rag = {
        "query": "下周四有大学英语3考试，帮我做复习计划",
        "hits": [],
        "context": "",
        "evidence_sufficient": False,
        "evidence_count": 0,
        "evidence_reason": "no_relevant_local_evidence",
    }

    async def fake_run_agent_action_loop(*args, **kwargs):
        captured["runtime_hints"] = kwargs.get("runtime_hints")
        yield {"type": "done"}

    with (
        patch("app.agent.langgraph_loop.build_rag_context", return_value=insufficient_rag),
        patch("app.agent.langgraph_loop.run_agent_action_loop", side_effect=fake_run_agent_action_loop),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Action routes should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-rag-gate-plan", username="rag-gate-plan", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "下周四有大学英语3考试，帮我做复习计划",
                user,
                "session-rag-gate-plan",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "done"]
    assert events[1]["result"]["evidence_sufficient"] is False
    assert captured["runtime_hints"] == []


@pytest.mark.asyncio
async def test_langgraph_agent_loop_keeps_arrangement_workflow_when_rag_evidence_is_insufficient(setup_db):
    captured: dict[str, object] = {}
    insufficient_rag = {
        "query": "下周四有大学英语3考试，帮我安排一下",
        "hits": [],
        "context": "",
        "evidence_sufficient": False,
        "evidence_count": 0,
        "evidence_reason": "no_relevant_local_evidence",
    }

    async def fake_run_agent_action_loop(*args, **kwargs):
        captured["runtime_hints"] = kwargs.get("runtime_hints")
        yield {"type": "done"}

    with (
        patch("app.agent.langgraph_loop.build_rag_context", return_value=insufficient_rag),
        patch("app.agent.langgraph_loop.run_agent_action_loop", side_effect=fake_run_agent_action_loop),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Action routes should not delegate to run_agent_loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-rag-gate-arrange-workflow", username="rag-gate-arrange-workflow", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "下周四有大学英语3考试，帮我安排一下",
                user,
                "session-rag-gate-arrange-workflow",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "done"]
    assert events[1]["result"]["evidence_sufficient"] is False
    assert captured["runtime_hints"] == []


@pytest.mark.asyncio
async def test_langgraph_agent_loop_preserves_no_web_guard_for_current_public_events(setup_db):
    with (
        patch(
            "app.agent.langgraph_loop.build_rag_context",
            side_effect=AssertionError("Current public event questions should skip RAG"),
        ),
        patch(
            "app.agent.loop.chat_completion_stream",
            side_effect=AssertionError("Current public event questions should not reach the LLM"),
        ),
        patch(
            "app.agent.loop.chat_completion",
            side_effect=AssertionError("Current public event questions should not reach the LLM fallback"),
        ),
        patch(
            "app.agent.langgraph_loop.run_agent_loop",
            side_effect=AssertionError("Current public event questions should not delegate to legacy loop"),
        ),
    ):
        async with TestSession() as db:
            user = User(id="user-langgraph-no-web", username="langgraph-no-web", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            async for event in run_langgraph_agent_loop(
                "最新政策是什么",
                user,
                "session-langgraph-no-web",
                db,
                AsyncMock(),
            ):
                events.append(event)

    assert [event["type"] for event in events] == ["text", "done"]
    assert "没有联网检索" in events[0]["content"]


@pytest.mark.asyncio
async def test_langgraph_agent_loop_forwards_ask_user_answers_to_inner_loop(setup_db):
    captured: dict[str, object] = {}

    async def fake_run_agent_loop(*args, **kwargs):
        answer = yield {"type": "ask_user", "question": "确认写入吗？", "ask_type": "confirm"}
        captured["answer"] = answer
        yield {"type": "done"}

    with patch("app.agent.langgraph_loop.run_agent_loop", side_effect=fake_run_agent_loop):
        async with TestSession() as db:
            user = User(id="user-langgraph-ask", username="langgraph-ask", hashed_password="x")
            db.add(user)
            await db.commit()

            generator = run_langgraph_agent_loop(
                "帮我确认一下",
                user,
                "session-langgraph-ask",
                db,
                AsyncMock(),
            )
            ask_event = await generator.__anext__()
            done_event = await generator.asend("确认")

    assert ask_event["type"] == "ask_user"
    assert done_event["type"] == "done"
    assert captured["answer"] == "确认"


def test_chat_runtime_selector_can_use_langgraph(monkeypatch):
    from app.routers import chat

    monkeypatch.setattr(chat.settings, "agent_runtime", "langgraph")
    assert chat._select_agent_loop() is chat.run_langgraph_agent_loop

    monkeypatch.setattr(chat.settings, "agent_runtime", "legacy")
    assert chat._select_agent_loop() is chat.run_agent_loop


@pytest.mark.asyncio
async def test_review_override_fallback_without_pending_confirmation_does_not_write(setup_db):
    async with TestSession() as db:
        user = User(id="user-review-fallback", username="review-fallback", hashed_password="x")
        db.add(user)
        await db.commit()

        answer = "确认\nreview_override=" + json.dumps(
            {
                "tasks": [
                    {
                        "title": "大学英语3 - 听力专项",
                        "scheduled_date": "2026-07-01",
                        "start_time": "19:00",
                        "end_time": "20:00",
                        "description": "围绕 Unit1-6 做听力训练。",
                    }
                ]
            },
            ensure_ascii=False,
        )

        events = []
        async for event in run_review_override_plan_write(answer, user, "session-review-fallback", db):
            events.append(event)

        result = await db.execute(select(Task).where(Task.user_id == user.id))
        tasks = result.scalars().all()

    assert [event["type"] for event in events] == ["error", "done"]
    assert "确认状态已失效" in events[0]["message"]
    assert list(tasks) == []
