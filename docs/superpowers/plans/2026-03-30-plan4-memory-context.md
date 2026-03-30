# Plan 4: Memory 缁崵绮?+ 娑撳﹣绗呴弬鍥╊吀閻?
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three-layer memory system (working/short-term/long-term) and context window management to keep conversations coherent across sessions without blowing up the context window.

**Architecture:** Memory CRUD service handles persistence. Two new agent tools (`recall_memory`, `save_memory`) give the LLM on-demand access. Tool result compression summarizes verbose outputs inline. Session lifecycle hooks generate summaries and extract memories at session end. The system prompt builder loads hot/warm memories at session start.

**Tech Stack:** SQLAlchemy async (existing), OpenAI-compatible LLM for summarization, existing agent tool system

**Depends on:** Plan 1 (Memory, SessionSummary, ConversationMessage models), Plan 2 (agent loop, tool_executor, llm_client)

---

## File Structure

```
student-planner/
閳规壕鏀㈤埞鈧?app/
閳?  閳规壕鏀㈤埞鈧?services/
閳?  閳?  閳规壕鏀㈤埞鈧?memory_service.py          # Memory CRUD: create, query, update, delete, staleness
閳?  閳?  閳规柡鏀㈤埞鈧?context_compressor.py      # Tool result summarization + conversation compression
閳?  閳规壕鏀㈤埞鈧?agent/
閳?  閳?  閳规壕鏀㈤埞鈧?tools.py                   # (modify: add recall_memory, save_memory definitions)
閳?  閳?  閳规壕鏀㈤埞鈧?tool_executor.py           # (modify: add recall_memory, save_memory handlers)
閳?  閳?  閳规壕鏀㈤埞鈧?loop.py                    # (modify: add tool result compression after each tool call)
閳?  閳?  閳规壕鏀㈤埞鈧?context.py                 # (modify: add hot/warm memory loading)
閳?  閳?  閳规柡鏀㈤埞鈧?session_lifecycle.py       # Session end: generate summary + extract memories
閳?  閳规壕鏀㈤埞鈧?routers/
閳?  閳?  閳规柡鏀㈤埞鈧?chat.py                    # (modify: call session lifecycle on disconnect/timeout)
閳?  閳规柡鏀㈤埞鈧?config.py                      # (modify: add context window thresholds)
閳规壕鏀㈤埞鈧?tests/
閳?  閳规壕鏀㈤埞鈧?test_memory_service.py         # Memory CRUD unit tests
閳?  閳规壕鏀㈤埞鈧?test_context_compressor.py     # Compression logic tests
閳?  閳规壕鏀㈤埞鈧?test_memory_tools.py           # recall_memory / save_memory tool tests
閳?  閳规壕鏀㈤埞鈧?test_session_lifecycle.py      # Session end flow tests
閳?  閳规柡鏀㈤埞鈧?test_context_loading.py        # Hot/warm memory in system prompt tests
```

---

### Task 1: Memory CRUD Service

Pure data layer 閳?no LLM calls. Handles create, query by category, query by relevance, update `last_accessed`, and staleness marking.

**Files:**
- Create: `student-planner/app/services/memory_service.py`
- Create: `student-planner/tests/test_memory_service.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_memory_service.py
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.memory import Memory
from app.services.memory_service import (
    create_memory,
    delete_memory,
    get_hot_memories,
    get_warm_memories,
    mark_stale_memories,
    recall_memories,
)


@pytest.mark.asyncio
async def test_create_memory(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-1", username="memtest", hashed_password="x")
        db.add(user)
        await db.commit()

        mem = await create_memory(
            db=db,
            user_id="mem-user-1",
            category="preference",
            content="閸犳粍顐介弮鈺€绗傛径宥勭瘎閺佹澘顒?,
            source_session_id="session-abc",
        )
        assert mem.id is not None
        assert mem.category == "preference"
        assert mem.content == "閸犳粍顐介弮鈺€绗傛径宥勭瘎閺佹澘顒?
        assert mem.user_id == "mem-user-1"
        assert mem.source_session_id == "session-abc"
        assert mem.relevance_score == 1.0


@pytest.mark.asyncio
async def test_get_hot_memories_returns_preferences(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-2", username="memtest2", hashed_password="x")
        db.add(user)
        await db.commit()

        await create_memory(db, "mem-user-2", "preference", "閺冣晙绗傛径宥勭瘎閺佹澘顒?)
        await create_memory(db, "mem-user-2", "habit", "娑撯偓濞嗏剝娓舵径?鐏忓繑妞?)
        await create_memory(db, "mem-user-2", "decision", "妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣")

        hot = await get_hot_memories(db, "mem-user-2")
        categories = {m.category for m in hot}
        assert "preference" in categories
        assert "habit" in categories
        # decision is NOT hot 閳?it's cold (on-demand)
        assert "decision" not in categories


@pytest.mark.asyncio
async def test_get_warm_memories_returns_recent(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-3", username="memtest3", hashed_password="x")
        db.add(user)
        await db.commit()

        # Recent memory (within 7 days)
        await create_memory(db, "mem-user-3", "decision", "妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣")

        # Old memory (simulate 30 days ago)
        old_mem = Memory(
            user_id="mem-user-3",
            category="decision",
            content="缁惧じ鍞悽銊ュ煕妫版鐡ラ悾?,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
            last_accessed=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db.add(old_mem)
        await db.commit()

        warm = await get_warm_memories(db, "mem-user-3", days=7)
        assert len(warm) == 1
        assert warm[0].content == "妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣"


@pytest.mark.asyncio
async def test_recall_memories_keyword_search(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-4", username="memtest4", hashed_password="x")
        db.add(user)
        await db.commit()

        await create_memory(db, "mem-user-4", "decision", "妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣閿涘本鏅ラ弸婊€绗夐柨?)
        await create_memory(db, "mem-user-4", "preference", "閸犳粍顐介弮鈺€绗傛径宥勭瘎")
        await create_memory(db, "mem-user-4", "knowledge", "濮掑倻宸肩拋鐑樻付闂?)

        results = await recall_memories(db, "mem-user-4", query="妤傛ɑ鏆?)
        assert len(results) >= 1
        assert any("妤傛ɑ鏆? in m.content for m in results)


@pytest.mark.asyncio
async def test_recall_updates_last_accessed(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-5", username="memtest5", hashed_password="x")
        db.add(user)
        await db.commit()

        mem = await create_memory(db, "mem-user-5", "decision", "妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣")
        original_accessed = mem.last_accessed

        # Small delay to ensure timestamp differs
        results = await recall_memories(db, "mem-user-5", query="妤傛ɑ鏆?)
        assert len(results) == 1
        assert results[0].last_accessed >= original_accessed


@pytest.mark.asyncio
async def test_delete_memory(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-6", username="memtest6", hashed_password="x")
        db.add(user)
        await db.commit()

        mem = await create_memory(db, "mem-user-6", "preference", "閺冣晙绗傛径宥勭瘎")
        deleted = await delete_memory(db, "mem-user-6", mem.id)
        assert deleted is True

        result = await db.execute(select(Memory).where(Memory.id == mem.id))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_memory_wrong_user(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-7", username="memtest7", hashed_password="x")
        db.add(user)
        await db.commit()

        mem = await create_memory(db, "mem-user-7", "preference", "閺冣晙绗傛径宥勭瘎")
        deleted = await delete_memory(db, "wrong-user", mem.id)
        assert deleted is False


@pytest.mark.asyncio
async def test_mark_stale_memories(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-8", username="memtest8", hashed_password="x")
        db.add(user)
        await db.commit()

        # Create a memory that was last accessed 100 days ago
        old_mem = Memory(
            user_id="mem-user-8",
            category="decision",
            content="閺冄呮畱閸愬磭鐡?,
            last_accessed=datetime.now(timezone.utc) - timedelta(days=100),
            relevance_score=1.0,
        )
        db.add(old_mem)
        await db.commit()

        count = await mark_stale_memories(db, "mem-user-8", stale_days=90)
        assert count == 1

        await db.refresh(old_mem)
        assert old_mem.relevance_score < 1.0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_memory_service.py -v`
Expected: FAIL 閳?`ModuleNotFoundError: No module named 'app.services.memory_service'`

- [x] **Step 3: Implement memory_service.py**

```python
# app/services/memory_service.py
"""CRUD operations for the Memory table."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory

# Hot memory categories 閳?always loaded into system prompt
HOT_CATEGORIES = {"preference", "habit"}


async def create_memory(
    db: AsyncSession,
    user_id: str,
    category: str,
    content: str,
    source_session_id: str | None = None,
) -> Memory:
    """Create a new memory record."""
    mem = Memory(
        user_id=user_id,
        category=category,
        content=content,
        source_session_id=source_session_id,
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    return mem


async def get_hot_memories(db: AsyncSession, user_id: str) -> list[Memory]:
    """Get always-on memories (preferences + habits). Injected into every system prompt."""
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.category.in_(HOT_CATEGORIES),
            Memory.relevance_score > 0.3,
        )
        .order_by(Memory.created_at.desc())
        .limit(20)
    )
    return list(result.scalars().all())


async def get_warm_memories(
    db: AsyncSession,
    user_id: str,
    days: int = 7,
) -> list[Memory]:
    """Get recent memories (created in last N days). Injected at session start."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.created_at >= cutoff,
            Memory.category.notin_(HOT_CATEGORIES),
            Memory.relevance_score > 0.3,
        )
        .order_by(Memory.created_at.desc())
        .limit(10)
    )
    return list(result.scalars().all())


async def recall_memories(
    db: AsyncSession,
    user_id: str,
    query: str,
    limit: int = 5,
) -> list[Memory]:
    """Search memories by keyword (simple LIKE search).

    Updates last_accessed for returned memories.
    """
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.content.contains(query),
            Memory.relevance_score > 0.1,
        )
        .order_by(Memory.relevance_score.desc(), Memory.created_at.desc())
        .limit(limit)
    )
    memories = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    for mem in memories:
        mem.last_accessed = now
    if memories:
        await db.commit()

    return memories


async def delete_memory(
    db: AsyncSession,
    user_id: str,
    memory_id: str,
) -> bool:
    """Delete a memory. Returns True if deleted, False if not found or wrong user."""
    result = await db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    )
    mem = result.scalar_one_or_none()
    if not mem:
        return False
    await db.delete(mem)
    await db.commit()
    return True


async def mark_stale_memories(
    db: AsyncSession,
    user_id: str,
    stale_days: int = 90,
) -> int:
    """Mark memories not accessed in stale_days as low-relevance. Returns count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    result = await db.execute(
        update(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.last_accessed < cutoff,
            Memory.relevance_score > 0.3,
        )
        .values(relevance_score=0.2)
    )
    await db.commit()
    return result.rowcount
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_memory_service.py -v`
Expected: All 8 tests PASS

- [x] **Step 5: Commit**

```bash
cd student-planner
git add app/services/memory_service.py tests/test_memory_service.py
git commit -m "feat: add memory CRUD service with hot/warm/cold retrieval"
```

---

### Task 2: Tool Result Compressor

Summarizes verbose tool results into concise versions for the conversation history. The full result is already logged in AgentLog; the compressed version stays in the message history to save context window space.

**Files:**
- Create: `student-planner/app/services/context_compressor.py`
- Create: `student-planner/tests/test_context_compressor.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_context_compressor.py
import json

import pytest

from app.services.context_compressor import compress_tool_result


def test_compress_get_free_slots():
    """get_free_slots returns verbose per-day data; compress to summary."""
    result = {
        "slots": [
            {
                "date": "2026-04-01",
                "weekday": "閸涖劋绗?,
                "free_periods": [
                    {"start": "08:00", "end": "10:00", "duration_minutes": 120},
                    {"start": "14:00", "end": "16:00", "duration_minutes": 120},
                ],
                "occupied": [
                    {"start": "10:00", "end": "12:00", "type": "course", "name": "妤傛ɑ鏆?},
                ],
            },
            {
                "date": "2026-04-02",
                "weekday": "閸涖劌娲?,
                "free_periods": [
                    {"start": "09:00", "end": "11:00", "duration_minutes": 120},
                ],
                "occupied": [],
            },
        ],
        "summary": "2026-04-01 閼?2026-04-02 閸?3 娑擃亞鈹栭梻鍙夘唽閿涘本鈧槒顓?6 鐏忓繑妞?0 閸掑棝鎸?,
    }
    compressed = compress_tool_result("get_free_slots", result)
    # Should use the existing summary field
    assert "3 娑擃亞鈹栭梻鍙夘唽" in compressed
    assert "6 鐏忓繑妞? in compressed
    # Should NOT contain the full slot details
    assert "free_periods" not in compressed


def test_compress_list_courses():
    result = {
        "courses": [
            {"id": "1", "name": "妤傛ɑ鏆?, "teacher": "瀵?, "weekday": 1, "start_time": "08:00", "end_time": "09:40"},
            {"id": "2", "name": "缁惧じ鍞?, "teacher": "閺?, "weekday": 3, "start_time": "10:00", "end_time": "11:40"},
            {"id": "3", "name": "閼昏精顕?, "teacher": "閻?, "weekday": 2, "start_time": "08:00", "end_time": "09:40"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_courses", result)
    assert "3" in compressed
    assert "妤傛ɑ鏆? in compressed


def test_compress_list_tasks():
    result = {
        "tasks": [
            {"id": "1", "title": "婢跺秳绡勬妯绘殶缁楊兛绔寸粩?, "status": "completed"},
            {"id": "2", "title": "婢跺秳绡勬妯绘殶缁楊兛绨╃粩?, "status": "pending"},
            {"id": "3", "title": "婢跺秳绡勭痪澶稿敩", "status": "pending"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_tasks", result)
    assert "3" in compressed
    assert "1" in compressed  # completed count


def test_compress_create_study_plan():
    result = {
        "tasks": [
            {"title": "婢跺秳绡勬妯绘殶缁楊兛绔寸粩?, "date": "2026-04-01"},
            {"title": "婢跺秳绡勬妯绘殶缁楊兛绨╃粩?, "date": "2026-04-02"},
            {"title": "婢跺秳绡勭痪澶稿敩", "date": "2026-04-03"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("create_study_plan", result)
    assert "3" in compressed


def test_compress_unknown_tool_returns_json():
    """Unknown tools get their result JSON-serialized as-is."""
    result = {"status": "ok", "data": "something"}
    compressed = compress_tool_result("unknown_tool", result)
    assert "ok" in compressed


def test_compress_small_result_unchanged():
    """Small results (under threshold) are returned as-is JSON."""
    result = {"id": "abc", "status": "created"}
    compressed = compress_tool_result("add_course", result)
    parsed = json.loads(compressed)
    assert parsed["status"] == "created"


def test_compress_error_result_unchanged():
    """Error results are never compressed."""
    result = {"error": "Course not found"}
    compressed = compress_tool_result("delete_course", result)
    parsed = json.loads(compressed)
    assert parsed["error"] == "Course not found"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_context_compressor.py -v`
Expected: FAIL 閳?`ModuleNotFoundError: No module named 'app.services.context_compressor'`

- [x] **Step 3: Implement context_compressor.py**

```python
# app/services/context_compressor.py
"""Compress tool results to save context window space.

Full results are logged in AgentLog. These compressed versions stay in
the conversation history for the LLM to reference.
"""

import json

# Results shorter than this (in chars) are kept as-is
_SMALL_THRESHOLD = 300


def compress_tool_result(tool_name: str, result: dict) -> str:
    """Compress a tool result dict into a concise string for conversation history.

    Returns a JSON string (for small/error results) or a natural language summary.
    """
    # Never compress errors
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    raw = json.dumps(result, ensure_ascii=False)

    # Small results don't need compression
    if len(raw) < _SMALL_THRESHOLD:
        return raw

    # Tool-specific compression
    compressor = _COMPRESSORS.get(tool_name)
    if compressor:
        return compressor(result)

    # Fallback: truncate large unknown results
    return raw[:_SMALL_THRESHOLD] + "..."


def _compress_get_free_slots(result: dict) -> str:
    summary = result.get("summary", "")
    if summary:
        return f"[缁屾椽妫介弮鑸殿唽閺屻儴顕楃紒鎾寸亯] {summary}"
    slots = result.get("slots", [])
    total = sum(len(d.get("free_periods", [])) for d in slots)
    return f"[缁屾椽妫介弮鑸殿唽閺屻儴顕楃紒鎾寸亯] {len(slots)} 婢垛晪绱濋崗?{total} 娑擃亞鈹栭梻鍙夘唽"


def _compress_list_courses(result: dict) -> str:
    courses = result.get("courses", [])
    count = result.get("count", len(courses))
    names = [c["name"] for c in courses[:5]]
    names_str = "閵?.join(names)
    if count > 5:
        names_str += f" 缁?{count} 闂?
    return f"[鐠囧墽鈻奸崚妤勩€僝 閸?{count} 闂傘劏顕抽敍姝縩ames_str}"


def _compress_list_tasks(result: dict) -> str:
    tasks = result.get("tasks", [])
    count = result.get("count", len(tasks))
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    pending = count - completed
    return f"[娴犺濮熼崚妤勩€僝 閸?{count} 娑擃亙鎹㈤崝鈽呯礉{completed} 娑擃亜鍑＄€瑰本鍨氶敍瀵媝ending} 娑擃亜绶熺€瑰本鍨?


def _compress_create_study_plan(result: dict) -> str:
    tasks = result.get("tasks", [])
    count = result.get("count", len(tasks))
    return f"[婢跺秳绡勭拋鈥冲灊] 瀹歌尙鏁撻幋?{count} 娑擃亜顦叉稊鐘辨崲閸?


_COMPRESSORS = {
    "get_free_slots": _compress_get_free_slots,
    "list_courses": _compress_list_courses,
    "list_tasks": _compress_list_tasks,
    "create_study_plan": _compress_create_study_plan,
}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_context_compressor.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd student-planner
git add app/services/context_compressor.py tests/test_context_compressor.py
git commit -m "feat: add tool result compressor for context window management"
```

---

### Task 3: Agent Tools 閳?recall_memory + save_memory

Two new tools for the LLM to interact with the memory system. `recall_memory` does keyword search (cold memory). `save_memory` creates a new memory with ask_user confirmation baked into the flow.

**Files:**
- Modify: `student-planner/app/agent/tools.py` (add 2 tool definitions)
- Modify: `student-planner/app/agent/tool_executor.py` (add 2 handlers)
- Create: `student-planner/tests/test_memory_tools.py`

- [ ] **Step 1: Add tool definitions to tools.py**

Append these two entries to the `TOOL_DEFINITIONS` list in `app/agent/tools.py`:

```python
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "娴犲海鏁ら幋椋庢畱闂€鎸庢埂鐠佹澘绻傛稉顓燁梾缁便垻娴夐崗鍏呬繆閹垬鈧倸缍嬮棁鈧憰浣告礀韫囧棛鏁ら幋铚傜閸撳秶娈戦崑蹇撱偨閵嗕椒绡勯幆顖涘灗閸愬磭鐡ラ弮鏈靛▏閻劊鈧倽绻戦崶鐐插爱闁板秶娈戠拋鏉跨箓閸掓銆冮妴?,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "閹兼粎鍌ㄩ崗鎶芥暛鐠囧稄绱濇俊?閺佹澘顒熸径宥勭瘎缁涙牜鏆?閹?鐎涳缚绡勬稊鐘冲劵'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "娣囨繂鐡ㄦ稉鈧弶锛勬暏閹撮娈戦梹鎸庢埂鐠佹澘绻傞妴鍌氬涧娣囨繂鐡ㄩ悽銊﹀煕閺勫海鈥樼悰銊ㄦ彧閻ㄥ嫬浜告總濮愨偓浣风瘎閹垱鍨ㄩ柌宥堫洣閸愬磭鐡ラ敍灞肩瑝鐟曚焦甯归弬顓溾偓鍌欑箽鐎涙ê澧犺箛鍛淬€忛崗鍫㈡暏 ask_user 绾喛顓婚妴?,
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["preference", "habit", "decision", "knowledge"],
                        "description": "鐠佹澘绻傜猾璇插焼閿涙reference=閸嬪繐銈? habit=娑旂姵鍎? decision=閸愬磭鐡? knowledge=鐠併倗鐓?,
                    },
                    "content": {
                        "type": "string",
                        "description": "鐠佹澘绻傞崘鍛啇閿涘矁鍤滈悞鎯邦嚔鐟封偓閹诲繗鍫?,
                    },
                },
                "required": ["category", "content"],
            },
        },
    },
```

Also append a `delete_memory` tool definition:

```python
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "閸掔娀娅庢稉鈧弶锛勬暏閹撮娈戦梹鎸庢埂鐠佹澘绻傞妴鍌氱秼閻劍鍩涚拠?韫囨ɑ甯€xxx'閺冭绱濋崗鍫㈡暏 recall_memory 閹垫儳鍩岀€电懓绨茬拋鏉跨箓閻?ID閿涘苯鍟€鐠嬪啰鏁ゅ銈呬紣閸忓嘲鍨归梽銈冣偓?,
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "鐟曚礁鍨归梽銈囨畱鐠佹澘绻?ID閿涘牅绮?recall_memory 缂佹挻鐏夋稉顓″箯閸欐牭绱?,
                    },
                },
                "required": ["memory_id"],
            },
        },
    },
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_memory_tools.py
import pytest
from sqlalchemy import select

from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.memory import Memory
from app.models.user import User


def test_recall_memory_tool_defined():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "recall_memory" in names


def test_save_memory_tool_defined():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "save_memory" in names


def test_recall_memory_requires_query():
    tool = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "recall_memory")
    assert "query" in tool["function"]["parameters"]["required"]


def test_save_memory_requires_category_and_content():
    tool = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "save_memory")
    required = tool["function"]["parameters"]["required"]
    assert "category" in required
    assert "content" in required


def test_delete_memory_tool_defined():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "delete_memory" in names


def test_delete_memory_requires_memory_id():
    tool = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "delete_memory")
    assert "memory_id" in tool["function"]["parameters"]["required"]


@pytest.mark.asyncio
async def test_recall_memory_returns_results(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="tool-mem-1", username="toolmem1", hashed_password="x")
        db.add(user)
        mem = Memory(
            user_id="tool-mem-1",
            category="preference",
            content="閸犳粍顐介弮鈺€绗傛径宥勭瘎閺佹澘顒?,
        )
        db.add(mem)
        await db.commit()

        result = await execute_tool(
            "recall_memory",
            {"query": "閺佹澘顒?},
            db=db,
            user_id="tool-mem-1",
        )
        assert "memories" in result
        assert len(result["memories"]) >= 1
        assert "閺佹澘顒? in result["memories"][0]["content"]


@pytest.mark.asyncio
async def test_recall_memory_empty_results(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="tool-mem-2", username="toolmem2", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "recall_memory",
            {"query": "娑撳秴鐡ㄩ崷銊ф畱閸愬懎顔?},
            db=db,
            user_id="tool-mem-2",
        )
        assert result["memories"] == []
        assert result["count"] == 0


@pytest.mark.asyncio
async def test_save_memory_creates_record(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="tool-mem-3", username="toolmem3", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "save_memory",
            {"category": "preference", "content": "閸犳粍顐介弲姘瑐婢跺秳绡勯弬鍥╊潠"},
            db=db,
            user_id="tool-mem-3",
        )
        assert result["status"] == "saved"

        mems = await db.execute(
            select(Memory).where(Memory.user_id == "tool-mem-3")
        )
        saved = mems.scalars().all()
        assert len(saved) == 1
        assert saved[0].content == "閸犳粍顐介弲姘瑐婢跺秳绡勯弬鍥╊潠"
        assert saved[0].category == "preference"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_memory_tools.py -v`
Expected: FAIL 閳?`recall_memory` not found in TOOL_DEFINITIONS

- [ ] **Step 4: Add handlers to tool_executor.py**

Add this import at the top of `app/agent/tool_executor.py`:

```python
from app.services.memory_service import create_memory, delete_memory, recall_memories
```

Add these handler functions:

```python
async def _recall_memory(
    db: AsyncSession, user_id: str, query: str, **kwargs
) -> dict[str, Any]:
    """Search user's long-term memories by keyword."""
    memories = await recall_memories(db, user_id, query)
    return {
        "memories": [
            {
                "id": m.id,
                "category": m.category,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in memories
        ],
        "count": len(memories),
    }


async def _save_memory(
    db: AsyncSession, user_id: str, category: str, content: str, **kwargs
) -> dict[str, Any]:
    """Save a new long-term memory for the user."""
    mem = await create_memory(
        db=db,
        user_id=user_id,
        category=category,
        content=content,
    )
    return {
        "status": "saved",
        "id": mem.id,
        "message": f"瀹歌尪顔囨担蹇ョ窗{content}",
    }


async def _delete_memory_handler(
    db: AsyncSession, user_id: str, memory_id: str, **kwargs
) -> dict[str, Any]:
    """Delete a long-term memory by ID."""
    deleted = await delete_memory(db, user_id, memory_id)
    if deleted:
        return {"status": "deleted", "message": "瀹告彃鍨归梽銈堫嚉鐠佹澘绻?}
    return {"error": "鐠佹澘绻傛稉宥呯摠閸︺劍鍨ㄩ弮鐘虫綀閸掔娀娅?}
```

Add all three to the `TOOL_HANDLERS` dict:

```python
TOOL_HANDLERS = {
    # ... existing entries ...
    "recall_memory": _recall_memory,
    "save_memory": _save_memory,
    "delete_memory": _delete_memory_handler,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_memory_tools.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
cd student-planner
git add app/agent/tools.py app/agent/tool_executor.py tests/test_memory_tools.py
git commit -m "feat: add recall_memory and save_memory agent tools"
```

---

### Task 4: Integrate Tool Result Compression into Agent Loop

Modify the agent loop to compress tool results before appending them to the conversation history. The full result is already saved in AgentLog (via `_log_step`). The compressed version goes into `messages[]` for the LLM.

**Files:**
- Modify: `student-planner/app/agent/loop.py:106-118`
- Create: `student-planner/tests/test_loop_compression.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop_compression.py
"""Test that the agent loop compresses tool results in conversation history."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.loop import run_agent_loop
from app.models.user import User


@pytest.mark.asyncio
async def test_loop_compresses_large_tool_result(setup_db):
    """When a tool returns a large result, the message history should contain the compressed version."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="loop-comp-1",
            username="loopcomp",
            hashed_password="x",
        )
        db.add(user)
        await db.commit()

        # Mock LLM: first call returns a tool call, second call returns text
        large_result = {
            "slots": [{"date": f"2026-04-{i:02d}", "weekday": "閸涖劋绔?, "free_periods": [{"start": "08:00", "end": "22:00", "duration_minutes": 840}], "occupied": []} for i in range(1, 8)],
            "summary": "2026-04-01 閼?2026-04-07 閸?7 娑擃亞鈹栭梻鍙夘唽閿涘本鈧槒顓?98 鐏忓繑妞?0 閸掑棝鎸?,
        }

        call_count = 0

        async def mock_chat_completion(client, messages, tools=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_free_slots",
                            "arguments": json.dumps({"start_date": "2026-04-01", "end_date": "2026-04-07"}),
                        },
                    }],
                }
            else:
                # Check that the tool result in messages is compressed
                tool_msg = next(m for m in messages if m.get("role") == "tool")
                content = tool_msg["content"]
                # Compressed version should NOT contain "free_periods"
                assert "free_periods" not in content
                assert "7 娑擃亞鈹栭梻鍙夘唽" in content
                return {"role": "assistant", "content": "娴ｇ姾绻栭崨銊︽箒瀵板牆顦跨粚娲＝閺冨爼妫块敍?}

        with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
            with patch("app.agent.loop.execute_tool", new_callable=AsyncMock, return_value=large_result):
                events = []
                gen = run_agent_loop("閺屻儳婀呯粚娲＝閺冨爼妫?, user, "test-session", db, AsyncMock())
                try:
                    event = await gen.__anext__()
                    while True:
                        events.append(event)
                        if event["type"] == "done":
                            break
                        event = await gen.__anext__()
                except StopAsyncIteration:
                    pass

        # The frontend should still get the full result
        tool_result_events = [e for e in events if e.get("type") == "tool_result"]
        assert len(tool_result_events) == 1
        assert "slots" in tool_result_events[0]["result"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd student-planner && python -m pytest tests/test_loop_compression.py -v`
Expected: FAIL 閳?assertion `"free_periods" not in content` fails (no compression yet)

- [ ] **Step 3: Modify loop.py to add compression**

In `app/agent/loop.py`, add this import at the top:

```python
from app.services.context_compressor import compress_tool_result
```

Then modify the section where tool results are appended to messages (around line 106-118). Replace the block that handles non-ask_user tool results:

Current code (lines 105-110):
```python
            else:
                result = await execute_tool(tool_name, tool_args, db, user.id)
                tool_result_content = json.dumps(result, ensure_ascii=False)
                if "error" in result:
                    error_count[tool_name] = error_count.get(tool_name, 0) + 1
                yield {"type": "tool_result", "name": tool_name, "result": result}
```

New code:
```python
            else:
                result = await execute_tool(tool_name, tool_args, db, user.id)
                # Compress for LLM context; full result already goes to AgentLog
                tool_result_content = compress_tool_result(tool_name, result)
                if "error" in result:
                    error_count[tool_name] = error_count.get(tool_name, 0) + 1
                # Frontend gets the full result for display
                yield {"type": "tool_result", "name": tool_name, "result": result}
```

The only change is replacing `json.dumps(result, ensure_ascii=False)` with `compress_tool_result(tool_name, result)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd student-planner && python -m pytest tests/test_loop_compression.py -v`
Expected: PASS

- [ ] **Step 5: Run existing loop tests to verify no regression**

Run: `cd student-planner && python -m pytest tests/ -v -k "loop or agent"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd student-planner
git add app/agent/loop.py tests/test_loop_compression.py
git commit -m "feat: compress tool results in agent loop conversation history"
```

---

### Task 5: Hot/Warm Memory Loading into System Prompt

Modify `context.py` to load hot memories (preferences + habits) into every system prompt, and warm memories (recent decisions/knowledge) at session start.

**Files:**
- Modify: `student-planner/app/agent/context.py`
- Create: `student-planner/tests/test_context_loading.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_context_loading.py
import pytest

from app.agent.context import build_dynamic_context
from app.models.memory import Memory
from app.models.user import User


@pytest.mark.asyncio
async def test_hot_memories_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-1", username="ctxtest1", hashed_password="x")
        db.add(user)
        pref = Memory(user_id="ctx-user-1", category="preference", content="閸犳粍顐介弮鈺€绗傛径宥勭瘎閺佹澘顒?)
        habit = Memory(user_id="ctx-user-1", category="habit", content="娑撯偓濞嗏剝娓舵径姘舵肠娑?鐏忓繑妞?)
        db.add_all([pref, habit])
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "閸犳粍顐介弮鈺€绗傛径宥勭瘎閺佹澘顒? in context
        assert "娑撯偓濞嗏剝娓舵径姘舵肠娑?鐏忓繑妞? in context


@pytest.mark.asyncio
async def test_warm_memories_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-2", username="ctxtest2", hashed_password="x")
        db.add(user)
        decision = Memory(user_id="ctx-user-2", category="decision", content="妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣")
        db.add(decision)
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣" in context


@pytest.mark.asyncio
async def test_no_memories_still_works(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-3", username="ctxtest3", hashed_password="x")
        db.add(user)
        await db.commit()

        context = await build_dynamic_context(user, db)
        # Should still have time info, just no memory section
        assert "瑜版挸澧犻弮鍫曟？" in context


@pytest.mark.asyncio
async def test_last_session_summary_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.session_summary import SessionSummary

        user = User(id="ctx-user-4", username="ctxtest4", hashed_password="x")
        db.add(user)
        summary = SessionSummary(
            user_id="ctx-user-4",
            session_id="prev-session",
            summary="娑撳﹥顐肩€电鐦介敍姘辨暏閹村嘲顕遍崗銉ょ啊鐠囨崘銆冮敍宀冾啎缂冾喕绨?闂傘劏鈧啳鐦惃鍕槻娑旂姾顓搁崚?,
        )
        db.add(summary)
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "鐎电厧鍙嗘禍鍡氼嚦鐞? in context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_context_loading.py -v`
Expected: FAIL 閳?memories not appearing in context output

- [ ] **Step 3: Modify context.py to load memories**

Replace the full `app/agent/context.py` with:

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.session_summary import SessionSummary
from app.models.task import Task
from app.models.user import User
from app.services.memory_service import get_hot_memories, get_warm_memories

WEEKDAY_NAMES = ["閸涖劋绔?, "閸涖劋绨?, "閸涖劋绗?, "閸涖劌娲?, "閸涖劋绨?, "閸涖劌鍙?, "閸涖劍妫?]


async def build_dynamic_context(user: User, db: AsyncSession) -> str:
    """Build the dynamic portion of the system prompt."""
    now = datetime.now(timezone.utc)
    today = now.date()
    weekday = today.isoweekday()

    parts: list[str] = []
    parts.append(f"瑜版挸澧犻弮鍫曟？閿涙now.strftime('%Y-%m-%d %H:%M')}閿涘澖WEEKDAY_NAMES[weekday - 1]}閿?)

    if user.current_semester_start:
        delta = (today - user.current_semester_start).days
        week_num = delta // 7 + 1
        parts.append(f"瑜版挸澧犵€涳附婀￠敍姘鳖儑{week_num}閸?)

    # Today's schedule
    course_result = await db.execute(
        select(Course)
        .where(Course.user_id == user.id, Course.weekday == weekday)
        .order_by(Course.start_time)
    )
    courses = course_result.scalars().all()

    task_result = await db.execute(
        select(Task)
        .where(Task.user_id == user.id, Task.scheduled_date == today.isoformat())
        .order_by(Task.start_time)
    )
    tasks = task_result.scalars().all()

    parts.append("\n娴犲﹤銇夐惃鍕）缁嬪绱?)
    if not courses and not tasks:
        parts.append("- 閺冪姴鐣ㄩ幒?)
    else:
        for course in courses:
            location = f" @ {course.location}" if course.location else ""
            parts.append(f"- {course.start_time}-{course.end_time} {course.name}{location}閿涘牐顕崇粙瀣剁礆")
        for task in tasks:
            status_mark = "閴? if task.status == "completed" else "閳?
            parts.append(f"- {task.start_time}-{task.end_time} {task.title}閿涘澖status_mark}閿?)

    # User preferences
    preferences = user.preferences or {}
    if preferences:
        parts.append("\n閻劍鍩涢崑蹇撱偨閿?)
        if "earliest_study" in preferences:
            parts.append(f"- 閺堚偓閺冣晛顒熸稊鐘虫闂傝揪绱皗preferences['earliest_study']}")
        if "latest_study" in preferences:
            parts.append(f"- 閺堚偓閺呮艾顒熸稊鐘虫闂傝揪绱皗preferences['latest_study']}")
        if "lunch_break" in preferences:
            parts.append(f"- 閸楀牅绱ら敍姝縫references['lunch_break']}")
        if "min_slot_minutes" in preferences:
            parts.append(f"- 閺堚偓閻厽婀侀弫鍫熸濞堢绱皗preferences['min_slot_minutes']}閸掑棝鎸?)
        if "school_schedule" in preferences:
            parts.append("- 瀹告煡鍘ょ純顔荤稊閹垱妞傞梻纾嬨€?)

    # Hot memories (preferences + habits) 閳?always loaded
    hot_memories = await get_hot_memories(db, user.id)
    if hot_memories:
        parts.append("\n闂€鎸庢埂鐠佹澘绻傞敍鍫濅焊婵傛垝绗屾稊鐘冲劵閿涘绱?)
        for mem in hot_memories:
            parts.append(f"- [{mem.category}] {mem.content}")

    # Warm memories (recent decisions/knowledge) 閳?loaded at session start
    warm_memories = await get_warm_memories(db, user.id, days=7)
    if warm_memories:
        parts.append("\n鏉╂垶婀＄拋鏉跨箓閿涘牊娓舵潻?婢垛晪绱氶敍?)
        for mem in warm_memories:
            parts.append(f"- [{mem.category}] {mem.content}")

    # Last session summary (if within 24 hours)
    cutoff_24h = now - timedelta(hours=24)
    summary_result = await db.execute(
        select(SessionSummary)
        .where(
            SessionSummary.user_id == user.id,
            SessionSummary.created_at >= cutoff_24h,
        )
        .order_by(SessionSummary.created_at.desc())
        .limit(1)
    )
    last_summary = summary_result.scalar_one_or_none()
    if last_summary:
        parts.append(f"\n娑撳﹥顐肩€电鐦介幗妯款洣閿涙last_summary.summary}")

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_context_loading.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run existing context tests to verify no regression**

Run: `cd student-planner && python -m pytest tests/ -v -k "context"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
cd student-planner
git add app/agent/context.py tests/test_context_loading.py
git commit -m "feat: load hot/warm memories and session summary into system prompt"
```

---

### Task 6: Session Lifecycle 閳?Summary + Memory Extraction

When a session ends (WebSocket disconnect or timeout), generate a session summary and extract memories from the conversation. Both use the LLM.

**Files:**
- Create: `student-planner/app/agent/session_lifecycle.py`
- Create: `student-planner/tests/test_session_lifecycle.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_lifecycle.py
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.agent.session_lifecycle import end_session
from app.models.conversation_message import ConversationMessage
from app.models.memory import Memory
from app.models.session_summary import SessionSummary
from app.models.user import User


@pytest.mark.asyncio
async def test_end_session_creates_summary(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-1", username="sesstest1", hashed_password="x")
        db.add(user)

        # Simulate conversation messages
        msgs = [
            ConversationMessage(session_id="sess-1", role="user", content="鐢喗鍨滈惇瀣箙鏉╂瑥鎳嗛惃鍕敄闂傚弶妞傞梻?),
            ConversationMessage(session_id="sess-1", role="assistant", content="娴ｇ姾绻栭崨銊︽箒12娑擃亞鈹栭梻鍙夋濞?),
            ConversationMessage(session_id="sess-1", role="user", content="鐢喗鍨滅€瑰甯撴妯绘殶婢跺秳绡?),
            ConversationMessage(session_id="sess-1", role="assistant", content="瀹歌尙鏁撻幋?娑擃亜顦叉稊鐘辨崲閸?),
        ]
        db.add_all(msgs)
        await db.commit()

        mock_summary_response = {
            "role": "assistant",
            "content": json.dumps({
                "summary": "閻劍鍩涢弻銉ф箙娴滃棙婀伴崨銊р敄闂傚弶妞傞梻杈剧礉鐎瑰甯撴禍鍡涚彯閺佹澘顦叉稊鐘侯吀閸掓帪绱?娑擃亙鎹㈤崝鈽呯礆",
                "actions": ["閺屻儴顕楃粚娲＝閺冨爼妫?, "閻㈢喐鍨氭妯绘殶婢跺秳绡勭拋鈥冲灊"],
                "memories": [],
            }, ensure_ascii=False),
        }

        with patch("app.agent.session_lifecycle.chat_completion", new_callable=AsyncMock, return_value=mock_summary_response):
            await end_session(db, "sess-user-1", "sess-1", AsyncMock())

        result = await db.execute(
            select(SessionSummary).where(SessionSummary.session_id == "sess-1")
        )
        summary = result.scalar_one_or_none()
        assert summary is not None
        assert "妤傛ɑ鏆熸径宥勭瘎" in summary.summary


@pytest.mark.asyncio
async def test_end_session_extracts_memories(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-2", username="sesstest2", hashed_password="x")
        db.add(user)

        msgs = [
            ConversationMessage(session_id="sess-2", role="user", content="閹存垵鏋╁▎銏℃－娑撳﹤顦叉稊鐘垫倞缁夋埊绱濋弲姘瑐閻鏋冪粔?),
            ConversationMessage(session_id="sess-2", role="assistant", content="婵傜晫娈戦敍灞惧灉鐠侀缍囨禍?),
        ]
        db.add_all(msgs)
        await db.commit()

        mock_response = {
            "role": "assistant",
            "content": json.dumps({
                "summary": "閻劍鍩涚悰銊ㄦ彧娴滃棗顒熸稊鐘虫闂傛潙浜告總?,
                "actions": [],
                "memories": [
                    {"category": "preference", "content": "閸犳粍顐介弮鈺€绗傛径宥勭瘎閻炲棛顫栭敍灞炬珓娑撳﹦婀呴弬鍥╊潠"},
                ],
            }, ensure_ascii=False),
        }

        with patch("app.agent.session_lifecycle.chat_completion", new_callable=AsyncMock, return_value=mock_response):
            await end_session(db, "sess-user-2", "sess-2", AsyncMock())

        result = await db.execute(
            select(Memory).where(Memory.user_id == "sess-user-2")
        )
        memories = result.scalars().all()
        assert len(memories) == 1
        assert memories[0].category == "preference"
        assert "閻炲棛顫? in memories[0].content
        assert memories[0].source_session_id == "sess-2"


@pytest.mark.asyncio
async def test_end_session_empty_conversation(setup_db):
    """No messages 閳?no summary, no crash."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-3", username="sesstest3", hashed_password="x")
        db.add(user)
        await db.commit()

        await end_session(db, "sess-user-3", "sess-3", AsyncMock())

        result = await db.execute(
            select(SessionSummary).where(SessionSummary.session_id == "sess-3")
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_end_session_handles_llm_error(setup_db):
    """If LLM fails, session end should not crash."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-4", username="sesstest4", hashed_password="x")
        db.add(user)
        msg = ConversationMessage(session_id="sess-4", role="user", content="hello")
        db.add(msg)
        await db.commit()

        with patch("app.agent.session_lifecycle.chat_completion", new_callable=AsyncMock, side_effect=Exception("LLM down")):
            # Should not raise
            await end_session(db, "sess-user-4", "sess-4", AsyncMock())

        result = await db.execute(
            select(SessionSummary).where(SessionSummary.session_id == "sess-4")
        )
        assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_session_lifecycle.py -v`
Expected: FAIL 閳?`ModuleNotFoundError: No module named 'app.agent.session_lifecycle'`

- [ ] **Step 3: Implement session_lifecycle.py**

```python
# app/agent/session_lifecycle.py
"""Session end processing: generate summary and extract memories."""

import json
import logging

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import chat_completion
from app.models.conversation_message import ConversationMessage
from app.models.memory import Memory
from app.models.session_summary import SessionSummary

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """閸掑棙鐎芥禒銉ょ瑓鐎电鐦介敍宀冪翻閸?JSON閿涘牅绗夌憰浣界翻閸戝搫鍙炬禒鏍у敶鐎圭櫢绱氶敍?
{
  "summary": "娑撯偓閸欍儴鐦介幀鑽ょ波鏉╂瑦顐肩€电鐦介崑姘啊娴犫偓娑?,
  "actions": ["閹笛嗩攽閻ㄥ嫭鎼锋担婊冨灙鐞?],
  "memories": [
    {"category": "preference|habit|decision|knowledge", "content": "閸婄厧绶遍梹鎸庢埂鐠侀缍囬惃鍕繆閹?}
  ]
}

鐟欏嫬鍨敍?- summary 鐟曚胶鐣濆ú渚婄礉娑撯偓娑撱倕褰炵拠?- memories 閸欘亝褰侀崣鏍暏閹撮攱妲戠涵顔裤€冩潏鍓ф畱閸嬪繐銈介妴浣风瘎閹垱鍨ㄩ柌宥堫洣閸愬磭鐡?- 娑撳秷顩﹂幒銊︽焽閿涘牏鏁ら幋鐤嚛"閹存垶鏆熺€涳缚绗夋總?閳帟顔囪ぐ鏇幢閻劍鍩涢懓鍐х啊60閸掑棌鍟嬫稉宥嗗腹閺傤叏绱?- 娑撳瓨妞傞幀褌淇婇幁顖欑瑝鐠佸府绱?娴犲﹤銇夋稉宥嗗厒鐎涳缚绡?閿?- 婵″倹鐏夊▽鈩冩箒閸婄厧绶辩拋棰佺秶閻ㄥ嫪淇婇幁顖ょ礉memories 娑撹櫣鈹栭弫鎵矋"""


async def end_session(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    llm_client: AsyncOpenAI,
) -> None:
    """Process session end: generate summary and extract memories.

    This is called when the WebSocket disconnects or times out.
    Failures are logged but never raised 閳?session end must not crash.
    """
    # Load conversation messages
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.timestamp)
    )
    messages = result.scalars().all()

    if not messages:
        return

    # Build conversation text for the LLM
    conversation_text = "\n".join(
        f"{msg.role}: {msg.content}" for msg in messages if msg.content
    )

    try:
        response = await chat_completion(
            llm_client,
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
        )
        content = response.get("content", "").strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        data = json.loads(content)
    except Exception:
        logger.warning("Failed to generate session summary for %s", session_id, exc_info=True)
        return

    # Save session summary
    summary_text = data.get("summary", "")
    actions = data.get("actions", [])
    if summary_text:
        summary = SessionSummary(
            user_id=user_id,
            session_id=session_id,
            summary=summary_text,
            actions_taken=actions,
        )
        db.add(summary)

    # Extract and save memories
    for mem_data in data.get("memories", []):
        category = mem_data.get("category", "")
        mem_content = mem_data.get("content", "")
        if category and mem_content:
            mem = Memory(
                user_id=user_id,
                category=category,
                content=mem_content,
                source_session_id=session_id,
            )
            db.add(mem)

    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_session_lifecycle.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd student-planner
git add app/agent/session_lifecycle.py tests/test_session_lifecycle.py
git commit -m "feat: add session lifecycle with summary generation and memory extraction"
```

---

### Task 7: Wire Session Lifecycle into Chat WebSocket

Call `end_session` when the WebSocket disconnects. Also add a 2-hour inactivity timeout that triggers a new session.

**Files:**
- Modify: `student-planner/app/routers/chat.py`
- Modify: `student-planner/app/config.py` (add session timeout config)

- [ ] **Step 1: Add session timeout config**

Add to `app/config.py` Settings class:

```python
    # Session settings
    session_timeout_minutes: int = 120  # 2 hours inactivity 閳?new session
```

The full Settings class after modification:

```python
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./student_planner.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    llm_api_key: str = "sk-placeholder"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
    vision_llm_api_key: str = ""
    vision_llm_base_url: str = ""
    vision_llm_model: str = "qwen-vl-plus"
    session_timeout_minutes: int = 120

    model_config = {"env_prefix": "SP_"}
```

- [ ] **Step 2: Modify chat.py to call end_session on disconnect**

Replace `app/routers/chat.py` with:

```python
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agent.llm_client import create_llm_client
from app.agent.loop import run_agent_loop
from app.agent.session_lifecycle import end_session
from app.auth.jwt import verify_token
from app.database import get_db
from app.models.user import User

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        auth_message = await websocket.receive_json()
        token = auth_message.get("token")
        if not token:
            await websocket.send_json({"type": "error", "message": "Missing token"})
            await websocket.close()
            return

        user_id = verify_token(token)
        if not user_id:
            await websocket.send_json({"type": "error", "message": "Invalid token"})
            await websocket.close()
            return
    except Exception:
        await websocket.close()
        return

    session_id = str(uuid.uuid4())
    llm_client = create_llm_client()
    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")
            if not user_message:
                continue

            async for db in get_db():
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if not user:
                    await websocket.send_json({"type": "error", "message": "User not found"})
                    break

                generator = run_agent_loop(user_message, user, session_id, db, llm_client)
                try:
                    event = await generator.__anext__()
                    while True:
                        await websocket.send_json(event)
                        if event["type"] == "ask_user":
                            user_response = await websocket.receive_json()
                            user_answer = user_response.get("answer", "绾喛顓?)
                            event = await generator.asend(user_answer)
                        elif event["type"] == "done":
                            break
                        else:
                            event = await generator.__anext__()
                except StopAsyncIteration:
                    pass
    except WebSocketDisconnect:
        # Session ended 閳?generate summary and extract memories
        async for db in get_db():
            await end_session(db, user_id, session_id, llm_client)
```

- [ ] **Step 3: Commit**

```bash
cd student-planner
git add app/routers/chat.py app/config.py
git commit -m "feat: call session lifecycle on WebSocket disconnect"
```

---

### Task 8: Update Agent.md 閳?Memory Tool Rules

Add behavior rules for the memory tools to Agent.md.

**Files:**
- Modify: `student-planner/Agent.md`

- [ ] **Step 1: Add memory tool usage rules**

Add the following under the `### 瀹搞儱鍙挎担璺ㄦ暏` section in `Agent.md`:

```markdown
- recall_memory閿涙艾缍嬮棁鈧憰浣告礀韫囧棛鏁ら幋铚傜閸撳秶娈戦崑蹇撱偨閵嗕椒绡勯幆顖涘灗閸愬磭鐡ラ弮鏈靛▏閻劊鈧倷绗夌憰浣圭槨濞嗏€愁嚠鐠囨繈鍏樼拫鍐暏閿涘苯褰ч崷銊р€樼€圭偤娓剁憰浣稿坊閸欒弓淇婇幁顖涙娴ｈ法鏁?- save_memory閿涙艾褰ф穱婵嗙摠閻劍鍩涢弰搴ｂ€樼悰銊ㄦ彧閻ㄥ嫪淇婇幁顖ょ礉娑撳秷顩﹂幒銊︽焽閵嗗倷绻氱€涙ê澧犺箛鍛淬€忛崗鍫㈡暏 ask_user 绾喛顓婚敍?閹存垼顔囨担蹇庣啊閿涙瓟閸愬懎顔怾閵嗗倸顕崥妤嬬吹"
  - preference閿涙氨鏁ら幋宄颁焊婵傛枻绱?閹存垵鏋╁▎銏℃－娑撳﹤顦叉稊鐘虫殶鐎?閿?  - habit閿涙艾顒熸稊鐘辩瘎閹垽绱?閹存垳绔村▎鈩冩付婢舵岸娉︽稉?鐏忓繑妞?閿?  - decision閿涙岸鍣哥憰浣稿枀缁涙牭绱?妤傛ɑ鏆熼悽銊ュ瀻缁旂姾濡粵鏍殣"閿?  - knowledge閿涙俺顕崇粙瀣吇閻儻绱?閻劍鍩涚憴澶婄繁濮掑倻宸肩拋鐑樻付闂?閿?- 娑撳秷顩︽穱婵嗙摠娑撳瓨妞傞幀褌淇婇幁顖ょ礄"娴犲﹤銇夋稉宥嗗厒鐎涳缚绡?閿?- 娑撳秷顩︽穱婵嗙摠瀹歌尙绮￠崷銊︽殶閹诡喖绨辨稉顓犳畱娣団剝浼呴敍鍫ｎ嚦缁嬪鈧椒鎹㈤崝掳鈧浇鈧啳鐦敍?- 瑜版挾鏁ら幋鐤嚛"韫囨ɑ甯€xxx"閺冭绱濋悽?recall_memory 閹垫儳鍩岀€电懓绨茬拋鏉跨箓閿涘瞼鍔ч崥搴℃啞閻儳鏁ら幋宄板嚒閸掔娀娅?```

- [ ] **Step 2: Add few-shot example for memory**

Add the following as a new example after existing examples in `Agent.md`:

```markdown
### 缁€杞扮伐4閿涙俺顔囪箛鍡欘吀閻?
閻劍鍩? "閹存垵褰傞悳鐗堟珓娑撳﹤顦叉稊鐘虫櫏閻滃洦娲挎姗堢礉娴犮儱鎮楃敮顔藉灉閹跺﹤顦叉稊鐘诲厴鐎瑰甯撻崷銊︽珓娑撳﹤鎯?

閳?save_memory(category="preference", content="閺呮矮绗傛径宥勭瘎閺佸牏宸奸弴鎾彯閿涘苯浜告總鑺ユ珓闂傛潙鐣ㄩ幒鎺戭槻娑?)
閳?娴ｅ棗鍘涚涵顔款吇閿涙瓫sk_user(type="confirm", question="閹存垼顔囨担蹇庣啊閿涙矮缍橀弲姘瑐婢跺秳绡勯弫鍫㈠芳閺囨挳鐝敍灞间簰閸氬簼绱崗鍫濈暔閹烘帗娅勯梻鏉戭槻娑旂姰鈧倸顕崥妤嬬吹")
閳?閻劍鍩涚涵顔款吇 閳?save_memory
閳?閸ョ偛顦? "婵傜晫娈戦敍灞藉嚒鐠侀缍囬妴鍌欎簰閸氬海鏁撻幋鎰槻娑旂姾顓搁崚鎺撴娴兼矮绱崗鍫濈暔閹烘帗娅勯梻瀛樻濞堢偣鈧?

閻劍鍩? "韫囨ɑ甯€娑斿澧犵拠瀵告畱閺冣晙绗傛径宥勭瘎閺佹澘顒?

閳?recall_memory(query="閺冣晙绗傛径宥勭瘎閺佹澘顒?)
閳?閹垫儳鍩岀拋鏉跨箓 閳?閸掔娀娅?閳?閸ョ偛顦? "瀹告彃鍨归梽銈堢箹閺壜ゎ唶韫囧棎鈧?
```

- [ ] **Step 3: Commit**

```bash
cd student-planner
git add Agent.md
git commit -m "docs: add memory tool rules and few-shot to Agent.md"
```

---

### Task 9: Conversation History Compression (Sliding Window)

When the conversation history grows too long, compress older messages into a summary while keeping recent messages intact. This is the "second level" compression from the spec.

**Files:**
- Modify: `student-planner/app/agent/loop.py` (add compression check before LLM call)
- Modify: `student-planner/app/services/context_compressor.py` (add conversation compression function)
- Create: `student-planner/tests/test_conversation_compression.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_conversation_compression.py
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.context_compressor import compress_conversation_history


@pytest.mark.asyncio
async def test_compress_short_history_unchanged():
    """Short conversations should not be compressed."""
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "娴ｇ姴銈?},
        {"role": "assistant", "content": "娴ｇ姴銈介敍浣规箒娴犫偓娑斿牆褰叉禒銉ュ簻娴ｇ姷娈戦敍?},
    ]
    result = await compress_conversation_history(messages, AsyncMock(), max_messages=10)
    assert result == messages


@pytest.mark.asyncio
async def test_compress_long_history():
    """Long conversations should have older messages compressed."""
    messages = [{"role": "system", "content": "System prompt"}]
    # Add 20 user/assistant pairs
    for i in range(20):
        messages.append({"role": "user", "content": f"閻劍鍩涘☉鍫熶紖 {i}"})
        messages.append({"role": "assistant", "content": f"閸斺晜澧滈崶鐐差槻 {i}"})

    mock_response = {
        "role": "assistant",
        "content": "娑斿澧犻惃鍕嚠鐠囨繀鑵戦敍宀€鏁ら幋宄板絺闁椒绨?0閺夆剝绉烽幁顖ょ礉閸斺晜澧滈柈钘変粵娴滃棗娲栨径宥冣偓?,
    }

    with patch("app.services.context_compressor.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        result = await compress_conversation_history(messages, AsyncMock(), max_messages=12)

    # System prompt should be preserved
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "System prompt"

    # Should have a summary message
    assert any("娑斿澧犻惃鍕嚠鐠? in m.get("content", "") for m in result)

    # Recent messages should be preserved (last 12 non-system messages = 6 pairs)
    assert len(result) <= 14  # system + summary + 12 recent


@pytest.mark.asyncio
async def test_compress_preserves_recent_messages():
    """The most recent messages should be kept intact."""
    messages = [{"role": "system", "content": "System prompt"}]
    for i in range(20):
        messages.append({"role": "user", "content": f"濞戝牊浼?{i}"})
        messages.append({"role": "assistant", "content": f"閸ョ偛顦?{i}"})

    mock_response = {
        "role": "assistant",
        "content": "閺冣晜婀＄€电鐦介幗妯款洣",
    }

    with patch("app.services.context_compressor.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        result = await compress_conversation_history(messages, AsyncMock(), max_messages=12)

    # Last message should be the most recent assistant reply
    assert result[-1]["content"] == "閸ョ偛顦?19"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_conversation_compression.py -v`
Expected: FAIL 閳?`ImportError: cannot import name 'compress_conversation_history'`

- [ ] **Step 3: Add compress_conversation_history to context_compressor.py**

Append to `app/services/context_compressor.py`:

```python
from app.agent.llm_client import chat_completion as _chat_completion

_SUMMARIZE_PROMPT = """鐠囬鏁?-3閸欍儴鐦介幀鑽ょ波娴犮儰绗呯€电鐦介崘鍛啇閵嗗倿鍣搁悙閫涚箽閻ｆ瑱绱伴悽銊﹀煕閸嬫矮绨℃禒鈧稊鍫熸惙娴ｆ嚎鈧胶鈥樼拋銈勭啊娴犫偓娑斿牄鈧浇銆冩潏鍙ョ啊娴犫偓娑斿牆浜告總濮愨偓?""


async def compress_conversation_history(
    messages: list[dict],
    llm_client,
    max_messages: int = 12,
) -> list[dict]:
    """Compress conversation history when it exceeds max_messages.

    Keeps the system prompt and the most recent max_messages messages.
    Older messages are summarized into a single message.

    Args:
        messages: Full message list (system + user/assistant/tool messages).
        llm_client: OpenAI-compatible async client for summarization.
        max_messages: Max non-system messages to keep uncompressed.

    Returns:
        Compressed message list.
    """
    # Separate system prompt from conversation
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conv_msgs = [m for m in messages if m.get("role") != "system"]

    if len(conv_msgs) <= max_messages:
        return messages

    # Split: old messages to compress, recent messages to keep
    cutoff = len(conv_msgs) - max_messages
    old_msgs = conv_msgs[:cutoff]
    recent_msgs = conv_msgs[cutoff:]

    # Summarize old messages
    old_text = "\n".join(
        f"{m.get('role', 'unknown')}: {m.get('content', '')}"
        for m in old_msgs
        if m.get("content")
    )

    try:
        response = await _chat_completion(
            llm_client,
            [
                {"role": "system", "content": _SUMMARIZE_PROMPT},
                {"role": "user", "content": old_text},
            ],
        )
        summary = response.get("content", "閿涘牊妫張鐔奉嚠鐠囨繃鎲崇憰浣风瑝閸欘垳鏁ら敍?)
    except Exception:
        summary = "閿涘牊妫張鐔奉嚠鐠囨繃鎲崇憰浣烘晸閹存劕銇戠拹銉礆"

    summary_msg = {
        "role": "user",
        "content": f"[娑斿澧犻惃鍕嚠鐠囨繃鎲崇憰涔?{summary}",
    }

    return system_msgs + [summary_msg] + recent_msgs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_conversation_compression.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Integrate into agent loop**

In `app/agent/loop.py`, add this import:

```python
from app.services.context_compressor import compress_conversation_history
```

Then, inside the `for iteration in range(MAX_ITERATIONS):` loop, add compression check before the LLM call. Insert before `response = await chat_completion(...)`:

```python
        # Compress conversation history if it's getting too long
        if len(messages) > 14:  # system + 12+ conversation messages
            messages = await compress_conversation_history(messages, llm_client, max_messages=12)
```

- [ ] **Step 6: Run all tests**

Run: `cd student-planner && python -m pytest tests/test_conversation_compression.py tests/test_loop_compression.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd student-planner
git add app/services/context_compressor.py app/agent/loop.py tests/test_conversation_compression.py
git commit -m "feat: add sliding window conversation compression"
```

---

### Task 10: Update AGENTS.md 閳?Mark Plan 4 Progress

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update progress in AGENTS.md**

Update the Plan 4 line and current status:

```markdown
- [ ] Plan 4: Memory + 娑撳﹣绗呴弬鍥╊吀閻炲棴绱?0 娑?task閿?```

Update "瑜版挸澧犲锝呮躬閹笛嗩攽" to reflect Plan 4 completion.

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md with Plan 4 completion status"
```
