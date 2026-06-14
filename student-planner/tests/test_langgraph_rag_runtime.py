import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent import rag as rag_module
from app.agent.langchain_tools import langchain_assignment_tool_names, langchain_tool_schemas
from app.agent.langgraph_loop import prepare_langgraph_state, run_langgraph_agent_loop
from app.agent.loop import run_review_override_plan_write
from app.agent.rag import LocalRAGRetriever, OpenAICompatibleEmbeddings, build_rag_context, clear_rag_cache
from app.config import settings
from app.models.task import Task
from app.models.user import User
from tests.conftest import TestSession


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


@pytest.mark.asyncio
async def test_prepare_langgraph_state_adds_rag_runtime_hint():
    state = await prepare_langgraph_state("下周四有大学英语3考试，帮我做复习计划")

    assert state["should_retrieve"] is True
    assert "retrieve_study_materials" in state["graph_nodes"]
    assert state["uses_langchain_tools"] is True
    assert any("RAG 检索上下文" in hint for hint in state["runtime_hints"])


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
                "下周四有大学英语3考试，帮我做复习计划",
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
async def test_review_override_fallback_writes_tasks_when_pending_generator_is_gone(setup_db):
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

    assert [event["type"] for event in events[:2]] == ["tool_call", "tool_result"]
    assert any(
        event["type"] == "result"
        and event["data"]["kind"] == "plan_write"
        and event["data"]["created_count"] == 1
        for event in events
    )
    assert len(tasks) == 1
    assert tasks[0].title == "大学英语3 - 听力专项"
