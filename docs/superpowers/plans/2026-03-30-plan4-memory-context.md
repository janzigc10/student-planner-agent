# Plan 4: Memory 缂傚倸鍊风欢锟犲垂闂堟稓鏆﹂柣銏ゆ涧閸?+ 婵犵數鍋為崹鍫曞箰閹间焦鏅濋柨婵嗘川缁犳棃鏌涘☉娆愮稇婵☆偅锕㈤弻娑㈠Ψ閵忊剝鐝﹂梺鍛婂焹閸嬫捇姊?
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three-layer memory system (working/short-term/long-term) and context window management to keep conversations coherent across sessions without blowing up the context window.

**Architecture:** Memory CRUD service handles persistence. Two new agent tools (`recall_memory`, `save_memory`) give the LLM on-demand access. Tool result compression summarizes verbose outputs inline. Session lifecycle hooks generate summaries and extract memories at session end. The system prompt builder loads hot/warm memories at session start.

**Tech Stack:** SQLAlchemy async (existing), OpenAI-compatible LLM for summarization, existing agent tool system

**Depends on:** Plan 1 (Memory, SessionSummary, ConversationMessage models), Plan 2 (agent loop, tool_executor, llm_client)

---

## File Structure

```
student-planner/
闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?app/
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?services/
闂?  闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?memory_service.py          # Memory CRUD: create, query, update, delete, staleness
闂?  闂?  闂傚倷绀侀悿鍥綖婢舵劕钃熼柨鐔哄Т缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?context_compressor.py      # Tool result summarization + conversation compression
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?agent/
闂?  闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?tools.py                   # (modify: add recall_memory, save_memory definitions)
闂?  闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?tool_executor.py           # (modify: add recall_memory, save_memory handlers)
闂?  闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?loop.py                    # (modify: add tool result compression after each tool call)
闂?  闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?context.py                 # (modify: add hot/warm memory loading)
闂?  闂?  闂傚倷绀侀悿鍥綖婢舵劕钃熼柨鐔哄Т缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?session_lifecycle.py       # Session end: generate summary + extract memories
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?routers/
闂?  闂?  闂傚倷绀侀悿鍥綖婢舵劕钃熼柨鐔哄Т缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?chat.py                    # (modify: call session lifecycle on disconnect/timeout)
闂?  闂傚倷绀侀悿鍥綖婢舵劕钃熼柨鐔哄Т缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?config.py                      # (modify: add context window thresholds)
闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?tests/
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?test_memory_service.py         # Memory CRUD unit tests
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?test_context_compressor.py     # Compression logic tests
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?test_memory_tools.py           # recall_memory / save_memory tool tests
闂?  闂傚倷绀侀悿鍥綖婢跺鐝堕柡鍥ュ灩缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?test_session_lifecycle.py      # Session end flow tests
闂?  闂傚倷绀侀悿鍥綖婢舵劕钃熼柨鐔哄Т缂佲晠鏌曡箛瀣偓鏇㈡偂濮椻偓閺?test_context_loading.py        # Hot/warm memory in system prompt tests
```

---

### Task 1: Memory CRUD Service

Pure data layer 闂?no LLM calls. Handles create, query by category, query by relevance, update `last_accessed`, and staleness marking.

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
            content="闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婄儤娼幍顔煎濠电姰鍨洪敃銏ゃ€?,
            source_session_id="session-abc",
        )
        assert mem.id is not None
        assert mem.category == "preference"
        assert mem.content == "闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婄儤娼幍顔煎濠电姰鍨洪敃銏ゃ€?
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

        await create_memory(db, "mem-user-2", "preference", "闂傚倷绀侀幖顐﹀疮閻樿鐤炬繛鍡樺灩缁犳棃鏌涚仦鍓р槈缂佸墎鍋熼埀顒€绠嶉崕杈┾偓姘煎櫍閹焦鎯旈妸锔惧幐婵炶揪缍€椤娆㈤崣澶堜簻?)
        await create_memory(db, "mem-user-2", "habit", "婵犵數鍋為崹鍫曞箰閹绢喖纾婚柟鎯ь嚟缁犻箖鏌涢垾宕囩濠⒀冨级缁绘盯骞橀悷鎵帿閻?闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞?)
        await create_memory(db, "mem-user-2", "decision", "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥?)

        hot = await get_hot_memories(db, "mem-user-2")
        categories = {m.category for m in hot}
        assert "preference" in categories
        assert "habit" in categories
        # decision is NOT hot 闂?it's cold (on-demand)
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
        await create_memory(db, "mem-user-3", "decision", "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥?)

        # Old memory (simulate 30 days ago)
        old_mem = Memory(
            user_id="mem-user-3",
            category="decision",
            content="缂傚倸鍊烽悞锕傚磿閹惰棄桅婵せ鍋撶€规洦鍓熼、妤呭礋椤掆偓娴犳椽姊洪棃娑辩劸闁稿酣浜堕幃锟犲即閻愬秵鐩幃褔宕奸銈呭Ш闂備礁顓介弶鍨Е闂?,
            created_at=datetime.now(timezone.utc) - timedelta(days=30),
            last_accessed=datetime.now(timezone.utc) - timedelta(days=30),
        )
        db.add(old_mem)
        await db.commit()

        warm = await get_warm_memories(db, "mem-user-3", days=7)
        assert len(warm) == 1
        assert warm[0].content == "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥?


@pytest.mark.asyncio
async def test_recall_memories_keyword_search(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-4", username="memtest4", hashed_password="x")
        db.add(user)
        await db.commit()

        await create_memory(db, "mem-user-4", "decision", "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥鍛存⒒娴ｇ懓顕滅紒瀣灴瀵敻顢楅崟顐ゆ煣闂侀潧顦弲娑㈠礄閻樺磭绡€濠电偞鍎虫禍鍓х磽娴ｈ娈旀い锔炬暬瀵?)
        await create_memory(db, "mem-user-4", "preference", "闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊?)
        await create_memory(db, "mem-user-4", "knowledge", "濠电姵顔栭崰妤冩暜閹烘纾归悹鍥ф▕閸熷懘鏌ゅù瀣珕濠殿垰銈搁弻锝夊箣閻愬棙鍨剁粋鎺戭潨閳ь剙顫?)

        results = await recall_memories(db, "mem-user-4", query="婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻?)
        assert len(results) >= 1
        assert any("婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻? in m.content for m in results)


@pytest.mark.asyncio
async def test_recall_updates_last_accessed(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        from app.models.user import User

        user = User(id="mem-user-5", username="memtest5", hashed_password="x")
        db.add(user)
        await db.commit()

        mem = await create_memory(db, "mem-user-5", "decision", "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥?)
        original_accessed = mem.last_accessed

        # Small delay to ensure timestamp differs
        results = await recall_memories(db, "mem-user-5", query="婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻?)
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

        mem = await create_memory(db, "mem-user-6", "preference", "闂傚倷绀侀幖顐﹀疮閻樿鐤炬繛鍡樺灩缁犳棃鏌涚仦鍓р槈缂佸墎鍋熼埀顒€绠嶉崕杈┾偓姘煎櫍閹?)
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

        mem = await create_memory(db, "mem-user-7", "preference", "闂傚倷绀侀幖顐﹀疮閻樿鐤炬繛鍡樺灩缁犳棃鏌涚仦鍓р槈缂佸墎鍋熼埀顒€绠嶉崕杈┾偓姘煎櫍閹?)
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
            content="闂傚倷绀侀幖顐﹀船閺屻儱宸濇い鏃傚亾濞堟悂姊绘担鍛婂暈闁告梹娲滄竟鏇㈩敇閵忊€充槐?,
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
Expected: FAIL 闂?`ModuleNotFoundError: No module named 'app.services.memory_service'`

- [x] **Step 3: Implement memory_service.py**

```python
# app/services/memory_service.py
"""CRUD operations for the Memory table."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory

# Hot memory categories 闂?always loaded into system prompt
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
                "weekday": "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悗锝庡墰缁?,
                "free_periods": [
                    {"start": "08:00", "end": "10:00", "duration_minutes": 120},
                    {"start": "14:00", "end": "16:00", "duration_minutes": 120},
                ],
                "occupied": [
                    {"start": "10:00", "end": "12:00", "type": "course", "name": "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻?},
                ],
            },
            {
                "date": "2026-04-02",
                "weekday": "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悘鐐电叓?,
                "free_periods": [
                    {"start": "09:00", "end": "11:00", "duration_minutes": 120},
                ],
                "occupied": [],
            },
        ],
        "summary": "2026-04-01 闂?2026-04-02 闂?3 婵犵數鍋為崹鍫曞箹閳哄倻顩查柣鎰惈閻撴﹢鏌″搴″箺闁抽攱甯￠弻娑樷枎韫囷絾鈻撻梺鍝ュ仒缁瑩寮婚妸銉㈡婵☆垳绮幏閬嶆⒑闁偛鑻晶顖涗繆閸欏娴い?6 闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞?0 闂傚倷绀侀幉锛勬暜閹烘嚦娑樷攽鐎ｎ亞顔?,
    }
    compressed = compress_tool_result("get_free_slots", result)
    # Should use the existing summary field
    assert "3 婵犵數鍋為崹鍫曞箹閳哄倻顩查柣鎰惈閻撴﹢鏌″搴″箺闁抽攱甯￠弻娑樷枎韫囷絾鈻撻梺? in compressed
    assert "6 闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞? in compressed
    # Should NOT contain the full slot details
    assert "free_periods" not in compressed


def test_compress_list_courses():
    result = {
        "courses": [
            {"id": "1", "name": "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻?, "teacher": "闂?, "weekday": 1, "start_time": "08:00", "end_time": "09:40"},
            {"id": "2", "name": "缂傚倸鍊烽悞锕傚磿閹惰棄桅婵せ鍋撶€?, "teacher": "闂?, "weekday": 3, "start_time": "10:00", "end_time": "11:40"},
            {"id": "3", "name": "闂傚倷绀侀崥瀣ｉ幒鏂垮灊濡わ絽鍠氶弫?, "teacher": "闂?, "weekday": 2, "start_time": "08:00", "end_time": "09:40"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_courses", result)
    assert "3" in compressed
    assert "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻? in compressed


def test_compress_list_tasks():
    result = {
        "tasks": [
            {"id": "1", "title": "婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌澧绘繛鍫燁殕娣囧﹪顢涘鍛濠电偛鐗嗘晶搴ｆ閹烘嚦鏃€绻濋崒姘缂傚倷鐒﹂弻銊╊敋椤撶姴鍨?, "status": "completed"},
            {"id": "2", "title": "婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌澧绘繛鍫燁殕娣囧﹪顢涘鍛濠电偛鐗嗘晶搴ｆ閹烘嚦鏃€绻濋崒姘缂傚倷闄嶉崝澶愬疾濠靛牆鍨?, "status": "pending"},
            {"id": "3", "title": "婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌骞樻俊顐灠椤潡宕滄笟鍥╁姼闂?, "status": "pending"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_tasks", result)
    assert "3" in compressed
    assert "1" in compressed  # completed count


def test_compress_create_study_plan():
    result = {
        "tasks": [
            {"title": "婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌澧绘繛鍫燁殕娣囧﹪顢涘鍛濠电偛鐗嗘晶搴ｆ閹烘嚦鏃€绻濋崒姘缂傚倷鐒﹂弻銊╊敋椤撶姴鍨?, "date": "2026-04-01"},
            {"title": "婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌澧绘繛鍫燁殕娣囧﹪顢涘鍛濠电偛鐗嗘晶搴ｆ閹烘嚦鏃€绻濋崒姘缂傚倷闄嶉崝澶愬疾濠靛牆鍨?, "date": "2026-04-02"},
            {"title": "婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌骞樻俊顐灠椤潡宕滄笟鍥╁姼闂?, "date": "2026-04-03"},
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
Expected: FAIL 闂?`ModuleNotFoundError: No module named 'app.services.context_compressor'`

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
        return f"[缂傚倸鍊风粈渚€寮甸鈧—鍐寠婢光晜绋掔粋鎺斺偓锝庝簽閻嫰姊洪悡搴㈠暈妞ゆ梹鐗犲畷顒佺鐎ｎ偆鍘搁柣蹇曞仩椤曆囧礉閵夛负浜滈柡鍥╁櫏濞堟绱掓潏銊ユ诞妤犵偞顭囬埀顒傛暬閺呮煡宕欑徊?{summary}"
    slots = result.get("slots", [])
    total = sum(len(d.get("free_periods", [])) for d in slots)
    return f"[缂傚倸鍊风粈渚€寮甸鈧—鍐寠婢光晜绋掔粋鎺斺偓锝庝簽閻嫰姊洪悡搴㈠暈妞ゆ梹鐗犲畷顒佺鐎ｎ偆鍘搁柣蹇曞仩椤曆囧礉閵夛负浜滈柡鍥╁櫏濞堟绱掓潏銊ユ诞妤犵偞顭囬埀顒傛暬閺呮煡宕欑徊?{len(slots)} 婵犵數濮伴崹褰掓倶閸儱鐤炬い蹇撴椤洘绻濋棃娑卞剰缂佲偓?{total} 婵犵數鍋為崹鍫曞箹閳哄倻顩查柣鎰惈閻撴﹢鏌″搴″箺闁抽攱甯￠弻娑樷枎韫囷絾鈻撻梺?


def _compress_list_courses(result: dict) -> str:
    courses = result.get("courses", [])
    count = result.get("count", len(courses))
    names = [c["name"] for c in courses[:5]]
    names_str = "闂?.join(names)
    if count > 5:
        names_str += f" 缂?{count} 闂?
    return f"[闂備浇宕垫慨鏉懨洪妶鍡樻珷濞寸姴顑呴悡婵嗏攽閸屾粠鐒剧紒鈧崱妯圭箚闁靛牆鎳庨銉╂煃瑜滈崜娆撳磿?闂?{count} 闂傚倸鍊搁崐鎼佸磹閸洖绀夐煫鍥ㄤ緱閺佸鏌熼幆鏉啃撻柡鍜佸墯閹便劌鈹戦崼婊冨灁ames_str}"


def _compress_list_tasks(result: dict) -> str:
    tasks = result.get("tasks", [])
    count = result.get("count", len(tasks))
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    pending = count - completed
    return f"[婵犵數鍋涢顓熸叏妤ｅ喚鏁嬬憸搴ㄥ箞閵娾晜鍋勯柣鎾虫捣椤︻偄鈹戞幊閸婃洜鈧哎鍔戦崺鈧い鎺嗗亾闁?闂?{count} 婵犵數鍋為崹鍫曞箹閳哄倻顩叉繛鍡樻尭缁犳煡鏌曡箛瀣偓鏇犵矆婢舵劖鐓冮柦妯侯槹閸ｇ晫绱掗埀顒佹櫠閸у潵mpleted} 婵犵數鍋為崹鍫曞箹閳哄倻顩叉繝濠傜墕缁€鍕煥濞戞ê顏ら柛瀣崌閹兘鎮ч崼鐔稿闂備焦鎮堕崝宥呯暆閹间礁鏋佺€广儱娲犻崑鎾绘濞戞艾閱噀nding} 婵犵數鍋為崹鍫曞箹閳哄倻顩叉繝濠傛噺椤愪粙鏌ｉ弮鍥モ偓鈧柛瀣崌閹兘鎮ч崼鐔稿闂?


def _compress_create_study_plan(result: dict) -> str:
    tasks = result.get("tasks", [])
    count = result.get("count", len(tasks))
    return f"[婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨顒勬煕閺囥劌骞楀┑顖氥偢閺屽秹濡烽妷銉︽瘣闂佽绻愰妶?闂佽姘﹂～澶愭偤閺囩姳鐒婃繛鍡樻尭閺嬩線鏌熼幑鎰靛殭缂?{count} 婵犵數鍋為崹鍫曞箹閳哄倻顩叉繝濠傜吇閸ヮ剙鐭楀璺哄閺嬫瑩姊虹紒姗嗙劸濡炲顭堥悾鐑藉蓟閵夛妇鍘?


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

- [x] **Step 5: Commit**

```bash
cd student-planner
git add app/services/context_compressor.py tests/test_context_compressor.py
git commit -m "feat: add tool result compressor for context window management"
```

---

### Task 3: Agent Tools 闂?recall_memory + save_memory

Two new tools for the LLM to interact with the memory system. `recall_memory` does keyword search (cold memory). `save_memory` creates a new memory with ask_user confirmation baked into the flow.

**Files:**
- Modify: `student-planner/app/agent/tools.py` (add 2 tool definitions)
- Modify: `student-planner/app/agent/tool_executor.py` (add 2 handlers)
- Create: `student-planner/tests/test_memory_tools.py`

- [x] **Step 1: Add tool definitions to tools.py**

Append these two entries to the `TOOL_DEFINITIONS` list in `app/agent/tools.py`:

```python
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "婵犵數鍋涢顓熸叏閺夋嚚褰掓倻閽樺鐎梺闈涚墕椤︻垳绮婚敐鍜佹富閻庯綆浜滈銏ゆ煟閿濆鎲炬慨濠傤煼閸┾偓妞ゆ帒瀚粻浼村箹濞ｎ剙鐏╅柣鎺撴倐閺岋綁鎮╂潏鈺佸濠电姰鍨洪…鍥箲閵忋倕纾兼繛鎴炲焹閺嬫牕顪冮妶鍡樺暗闁革絻鍎遍～蹇涘礈瑜忕壕鐓庛€掑顒備虎闁诲浚鍠楃换娑㈠级閹搭厽鈻堥悗瑙勬礃椤ㄥ﹤鐣峰Δ鍛窛妞ゆ帒鍊婚悾楣冩⒒娴ｇ瓔鍤冮柛娆忛叄瀹曞綊顢楅崟顐ゅ姦濡炪倖宸婚崑鎾绘煕婵犲倹鎲哥紒杈╁仧閳ь剨缍嗛崰妤吽夐崱娑欑厓鐟滄粓宕滃☉銏犵疅闁绘鐗婃刊鎾煕濞戞﹫鍔熸い锔哄劦濡懘顢曢姀鈩冩倷濠碘槅鍋呴惄顖氼嚕椤愶箑围濠㈣泛锕﹂娲⒑閻愵剝澹橀柛濠傤煼椤㈡ê煤椤忓懐鍘遍梺瑙勫劤绾绢叀鍊存繝鐢靛仜閻楀﹪宕归崹顔炬殾闁硅揪绲块悿鈧梺瑙勫劤瀹曨剚绂掑ú顏呪拺闂傚牊绋掗ˉ娆愪繆閻愭潙绗х€殿啫鍥х妞ゆ牗姘ㄩ悾鎯ь渻閵堝棛澧紒瀣灴閹ê螖閸涱喚鍘遍梺褰掑亰閸撴盯鏁嶅澶嬬厽閹烘娊宕曢棃娑卞殨妞ゆ洍鍋撶€殿喚鏁诲Λ鍐ㄢ槈閹烘挾鈧ジ姊绘担瑙勩仧婵炵厧娼″畷婵囩節閸パ呭姦濡炪倖宸婚崑鎾绘煕婵犲嫭娅曢柟骞垮灲楠炲鏁冮埀顒勬倷婵犲洦鐓熼柟閭﹀幖缁插鏌ｉ弽顓濇喚婵﹥妞藉鍓佹崉閵婃劑鍊栫换娑㈠醇閻旈浠奸梺鐟板槻椤戝顕ｉ崜浣瑰磯闁靛ě鍛闂傚倷绀侀幉锛勬暜濡ゅ懌鈧啯寰勯幇顑┿儵鏌涢幇闈涙灈鏉?,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "闂傚倷鑳堕幊鎾诲触鐎ｎ剙鍨濋幖娣妼绾惧ジ鏌曟繛鐐珔缂佲偓閸岀偞鐓欓柟顖涙緲琚氶梺鍝勬閻╊垶骞冭ぐ鎺戠倞鐟滃繘鍩㈠畝鈧槐鎺撴綇閵娧呯暫婵?闂傚倷娴囧銊╂倿閿曗偓椤灝顫滈埀顒勩€佸Δ鍛亜缂佸娉曠粣鐐烘倵楠炲灝鍔氶悗姘煎櫍閹焦鎯旈敐鍥╋紲濠电偞鍨堕悷褎鏅堕柆宥嗙厸?闂?闂備浇顕х€涒晠宕橀懡銈囩＝婵ê宕慨顒勬煕閺囥劌澧伴柍缁樻礋閺岋絽螣閸濆嫭姣愰梺?",
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
            "description": "婵犵數鍎戠徊钘壝洪敂鐐床闁稿瞼鍋為崑銈夋煏婵犲繐顩柍缁樻閺屽秷顧侀柛鎾跺枎椤曪綁宕奸弴鐔告珫闂佸憡娲﹂崜姘枔閵忋倖鈷戦悷娆忓鐏忥附銇勯妷锔藉碍闁崇粯鎹囬獮瀣晜鐟欙絾瀚婚梻浣告贡椤牏鈧稈鏅犲畷娲磼閻愭潙浠繛杈剧秬椤娆㈤懠顒傜＜閻犲洦褰冮埀顒佸娣囧﹪骞橀鑲╋紲濠殿喗锕╅崜姘舵煥椤撶喓绠鹃柨婵嗘噺婢跺嫮绱掔拠鎻掆偓鍧楀箖濞差亜惟闁冲搫鍊告禒娲⒑闂堟侗鐓紒鐘冲灴閹繝寮撮姀锛勫幐闂佸憡娲﹂崑鍛村箲閿濆鐓冮柕澶涘瘜閻掍粙鏌熼璇插祮濠碘剝鎮傛俊鎼佹晝閳ь剙鈽夎濮婂搫效閸パ冾瀳闁诲孩鍑归崜姘辩矉瀹ュ宸濆┑鐘插濡绢喗绻濆▓鍨灍闁告柨绻樺畷鎴﹀箻鐎涙ê顎撴俊鐐差儏濞村嘲危閹达附鈷戦悹鍥ｂ偓宕囦紘闂佹悶鍔戞禍璺虹暦瑜版帒惟闁冲搫鍊婚崢鎺楁倵楠炲灝鍔氶柣妤佺矊鐓ら柨婵嗩槹閻撴洟鏌熼柇锕€澧伴柨娑樼Ч閺岋絾骞婇柛搴ｆ暬瀵偄顓奸崶锔藉媰闂佸吋绁撮弲婵嬪箟瑜版帗鐓熼柣鏂挎啞绾惧鏌ｉ幒鐐差洭闁轰緡鍠涢妵鎰板箳閹寸儐妫熸俊鐐€栭幐缁樼珶閺囥垹纾婚柟鎹愵嚙绾惧吋绻涢崱妯虹仼妞ゆ梹妫冮弻锝嗘償閵忊懇濮囬梺鎸庤壘椤儻顦村┑顔煎⒔缁鈽夐姀鐘茬獩濠电儑缍嗛崗姗€宕戦幘鍦杸婵炴垶顭囬ˇ褔姊洪崜鎻掍簴闁搞劍妞藉?ask_user 缂傚倷鑳堕搹搴ㄥ矗鎼淬劌绐楁繛鎴欏焺閺佸洤鈹戦悩瀹犲鏉?,
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["preference", "habit", "decision", "knowledge"],
                        "description": "闂備浇宕垫慨鎶芥倿閿曗偓椤灝螣閸忕厧搴婇梺绋挎湰缁海浜搁悽鍛婂仯闁搞儯鍔岀徊濠氭煟閹烘垯鍋㈤柡灞诲妼閳藉鈻庡Ο鍝勵潏reference=闂傚倷鑳堕…鍫ヮ敄閸涱垱宕查柟鐗堟緲鍥? habit=婵犵數鍋為崹璺侯潖缂佹ɑ鍙忛柣銏㈩焾绾? decision=闂傚倷绀侀幉锟犲礉閺囩姴顥氭い鎾卞灪閸? knowledge=闂備浇宕垫慨鎶芥⒔瀹ュ纾规俊銈呮噺閸?,
                    },
                    "content": {
                        "type": "string",
                        "description": "闂備浇宕垫慨鎶芥倿閿曗偓椤灝螣閸忕厧搴婇梺绋跨灱閸嬫稓绮堥崘顔界厱婵炴垵宕楣冩煕閻旈攱鍠橀柡灞诲妼閳藉螣閼测晛濮伴梻浣规偠閸婃牜鍒掗幘璇茬畺闁绘劕鎼粻姘舵⒑椤撱劎鐣辨繛鍫佸洦鐓熼柣鏃堫棑濞堥亶鏌涚€ｎ偅宕岄柡宀€鍠撻幏鐘绘嚑椤掑偆鍟堥梻?,
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
            "description": "闂傚倷绀侀幉锛勬暜閻愬绠鹃柍褜鍓氱换娑㈠川椤撶儐鍔夌紓浣割儏椤︾敻宕洪埀顒併亜閹烘垵顏╃紒鐙欏洦鐓ユ繛鎴灻顏堟煛閸℃绠婚柡宀€鍠栭獮姗€顢氶崨顕呮婵犵數鍋涢悧濠囧垂閸噮娼栫憸鐗堝笒缁犱即骞栧ǎ顒€鐏╅柣鎺撴倐閺岋綁鎮╂潏鈺佸濠电姰鍨洪…鍥箲閵忋倕纾奸柣鎰棘閵夆晜鐓曢悘鐐靛亾閻ㄦ垹绱掓径濞垮仮闁哄矉缍侀敐鐐侯敆閳ь剚淇婃禒瀣厱闁冲搫鍊婚妴鎺楁煙?闂傚倸顭崑鍕洪敃浣规噷闂佹眹鍩勯崹顏堝磻閹兼獰x'闂傚倷绀侀幖顐﹀疮閹剁瓔鏁婇柟閭﹀枟椤洘绻濋棃娑卞剰缂佲偓閸岀偞鐓曟い鎰Т閻忣亪鏌?recall_memory 闂傚倷鑳堕幊鎾绘倶濮樿泛纾块柟鎯版閺勩儳鈧厜鍋撻柍褜鍓熼崺鈧い鎺戝€归弳鈺呮煙閾忣偅灏甸柤娲憾閹崇娀顢楁担鍓测偓娑㈡⒑閸濆嫷妲兼繛澶嬫礈缁骞樼紒妯煎幗?ID闂傚倷鐒︾€笛呯矙閹达附鍤愭い鏍仜閻ゎ噣鏌嶈閸撶喖骞冮崷顓涘亾閿濆簼绨婚柡鍡欏枛閺屸剝鎷呴棃娑掑亾閺囶澁缍栭柕蹇嬪€曞洿闂佸憡渚楅崜娑㈡儗濡ゅ懏鈷戠紒瀣硶缁犱即鏌涢姀锛勫弨鐎规洜顢婇妵鎰板箳閹绢垱瀵栭梻渚€娼ч悧鍡涘疮閻樿纾?,
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "闂備浇宕甸崰鎰洪幋鐘电焼濞撴埃鍋撶€规洜顢婇妵鎰板箳閹绢垱瀵栭梻渚€娼ч悧鍡椕洪敃鍌涘仼闂侇剙绉甸崑锝吤归敐鍫綈缂佹儼灏欑槐?ID闂傚倷鐒︾€笛呯矙閹达附鍋嬮柛娑卞灠閸?recall_memory 缂傚倸鍊搁崐鐑芥倿閿曞倸绠板┑鐘崇閸婅泛顭跨捄渚剳闁崇粯姊归妵鍕箻椤栨浜剧€规洖娴傞崬鐢告⒒娴ｅ憡鍟為柣鐕傜畵閹囶敇閻樻剚娼?,
                    },
                },
                "required": ["memory_id"],
            },
        },
    },
```

- [x] **Step 2: Write the failing tests**

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
            content="闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婄儤娼幍顔煎濠电姰鍨洪敃銏ゃ€?,
        )
        db.add(mem)
        await db.commit()

        result = await execute_tool(
            "recall_memory",
            {"query": "闂傚倷娴囧銊╂倿閿曗偓椤灝顫滈埀顒勩€?},
            db=db,
            user_id="tool-mem-1",
        )
        assert "memories" in result
        assert len(result["memories"]) >= 1
        assert "闂傚倷娴囧銊╂倿閿曗偓椤灝顫滈埀顒勩€? in result["memories"][0]["content"]


@pytest.mark.asyncio
async def test_recall_memory_empty_results(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="tool-mem-2", username="toolmem2", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "recall_memory",
            {"query": "婵犵數鍋為崹鍫曞箰閸濄儳鐭撻柟缁㈠枟閸嬨倝鏌曟繛鐐珔闁圭懓鐖奸弻鏇熺箾瑜嶇€氼噣寮抽悩缁樷拺闁告稑锕ゆ慨鍥煙閸愭煡鍙勬い?},
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
            {"category": "preference", "content": "闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰闁汇倗鍋撻幈銊ヮ潨閸℃ぞ绨介梺鑽ゅ枑閸旀洟鈥︾捄銊﹀磯闁惧繐澧ｉ敍鍕＜闁炽儱鍟块顓犫偓娈垮櫘閸撶喎鐣烽崼鏇炵厸濠电姴鍟扮粙?},
            db=db,
            user_id="tool-mem-3",
        )
        assert result["status"] == "saved"

        mems = await db.execute(
            select(Memory).where(Memory.user_id == "tool-mem-3")
        )
        saved = mems.scalars().all()
        assert len(saved) == 1
        assert saved[0].content == "闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰闁汇倗鍋撻幈銊ヮ潨閸℃ぞ绨介梺鑽ゅ枑閸旀洟鈥︾捄銊﹀磯闁惧繐澧ｉ敍鍕＜闁炽儱鍟块顓犫偓娈垮櫘閸撶喎鐣烽崼鏇炵厸濠电姴鍟扮粙?
        assert saved[0].category == "preference"
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_memory_tools.py -v`
Expected: FAIL 闂?`recall_memory` not found in TOOL_DEFINITIONS

- [x] **Step 4: Add handlers to tool_executor.py**

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
        "message": f"闂佽姘﹂～澶愭偤閺囩姳鐒婃い蹇撶墱閺佸﹪鏌涢妷锝呭濠殿垱鎸抽悡顐﹀炊閵夈儱濮㈢紓浣瑰姈閳峰獚ontent}",
    }


async def _delete_memory_handler(
    db: AsyncSession, user_id: str, memory_id: str, **kwargs
) -> dict[str, Any]:
    """Delete a long-term memory by ID."""
    deleted = await delete_memory(db, user_id, memory_id)
    if deleted:
        return {"status": "deleted", "message": "闂佽娴烽幊鎾诲箟闄囬妵鎰板礃椤旂厧鐎悷婊呭鐢鍩涢弮鍫熺厪闁割偅绻勬晶閬嶆煕閵堝拋妯€闁诡喛顫夐幏鍛喆閸曨厼鍤掔紓?}
    return {"error": "闂備浇宕垫慨鎶芥倿閿曗偓椤灝螣閸忕厧搴婇梺绋挎湰缁嬫捇鍩㈤弮鍌楀亾楠炲灝鍔氶柟铏姍楠炴鎮╃紒妯煎幈闂佹寧鏌ㄩ幖顐ｄ繆娴犲鐓曢柕濠忕到婵倻鈧鍣崳锝夊箖閳哄懏鎯炴い鎰╁€楄ⅲ闂傚倷绀侀幉锛勬暜閻愬绠鹃柍褜鍓氱换?}
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

- [x] **Step 5: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_memory_tools.py -v`
Expected: All 9 tests PASS

- [x] **Step 6: Commit**

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

- [x] **Step 1: Write the failing test**

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
            "slots": [{"date": f"2026-04-{i:02d}", "weekday": "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悗锝庡墰閸?, "free_periods": [{"start": "08:00", "end": "22:00", "duration_minutes": 840}], "occupied": []} for i in range(1, 8)],
            "summary": "2026-04-01 闂?2026-04-07 闂?7 婵犵數鍋為崹鍫曞箹閳哄倻顩查柣鎰惈閻撴﹢鏌″搴″箺闁抽攱甯￠弻娑樷枎韫囷絾鈻撻梺鍝ュ仒缁瑩寮婚妸銉㈡婵☆垳绮幏閬嶆⒑闁偛鑻晶顖涗繆閸欏娴い?98 闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞?0 闂傚倷绀侀幉锛勬暜閹烘嚦娑樷攽鐎ｎ亞顔?,
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
                assert "7 婵犵數鍋為崹鍫曞箹閳哄倻顩查柣鎰惈閻撴﹢鏌″搴″箺闁抽攱甯￠弻娑樷枎韫囷絾鈻撻梺? in content
                return {"role": "assistant", "content": "婵犵數鍋犻幓顏嗗緤閹稿孩鍙忛柛鎾楀嫬搴婇梺鍝勭▉閸樼厧顔忓┑瀣厪濠电姴绻樺顔剧磼閻樺啿绗ч柍褜鍓欓悘姘熆濮椻偓閹囧幢濞存澘娲ㄩ幑鍕Ω瑜忛悡鏂库攽閻愬弶鈻曞ù婊勭箞閺佸秴鈹戠€ｎ偆鍘搁梺鍛婂姂閸斿酣宕洪敐鍡曠箚妞ゆ劑鍨洪崑銉╂煛?}

        with patch("app.agent.loop.chat_completion", side_effect=mock_chat_completion):
            with patch("app.agent.loop.execute_tool", new_callable=AsyncMock, return_value=large_result):
                events = []
                gen = run_agent_loop("闂傚倷绀侀幖顐ゆ偖椤愶箑纾块柛鎰嚋閼板潡鏌涘☉鍗炵仯闁活厽纰嶇换娑橆啅椤旇崵鍑归梺鎸庣⊕缁诲牓寮婚敓鐘茬闁靛ě鍐幗婵?, user, "test-session", db, AsyncMock())
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

- [x] **Step 2: Run test to verify it fails**

Run: `cd student-planner && python -m pytest tests/test_loop_compression.py -v`
Expected: FAIL 闂?assertion `"free_periods" not in content` fails (no compression yet)

- [x] **Step 3: Modify loop.py to add compression**

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

- [x] **Step 4: Run test to verify it passes**

Run: `cd student-planner && python -m pytest tests/test_loop_compression.py -v`
Expected: PASS

- [x] **Step 5: Run existing loop tests to verify no regression**

Run: `cd student-planner && python -m pytest tests/ -v -k "loop or agent"`
Expected: All PASS

- [x] **Step 6: Commit**

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

- [x] **Step 1: Write the failing tests**

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
        pref = Memory(user_id="ctx-user-1", category="preference", content="闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婄儤娼幍顔煎濠电姰鍨洪敃銏ゃ€?)
        habit = Memory(user_id="ctx-user-1", category="habit", content="婵犵數鍋為崹鍫曞箰閹绢喖纾婚柟鎯ь嚟缁犻箖鏌涢垾宕囩濠⒀冨级缁绘盯骞橀悷鎵帿閻庡灚婢樼€氼剟锝炲┑瀣殝濞达絽鍟禍鏍р攽?闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞?)
        db.add_all([pref, habit])
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婄儤娼幍顔煎濠电姰鍨洪敃銏ゃ€? in context
        assert "婵犵數鍋為崹鍫曞箰閹绢喖纾婚柟鎯ь嚟缁犻箖鏌涢垾宕囩濠⒀冨级缁绘盯骞橀悷鎵帿閻庡灚婢樼€氼剟锝炲┑瀣殝濞达絽鍟禍鏍р攽?闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞? in context


@pytest.mark.asyncio
async def test_warm_memories_in_context(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-2", username="ctxtest2", hashed_password="x")
        db.add(user)
        decision = Memory(user_id="ctx-user-2", category="decision", content="婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥?)
        db.add(decision)
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥? in context


@pytest.mark.asyncio
async def test_no_memories_still_works(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="ctx-user-3", username="ctxtest3", hashed_password="x")
        db.add(user)
        await db.commit()

        context = await build_dynamic_context(user, db)
        # Should still have time info, just no memory section
        assert "闂佽崵鍠愮划搴㈡櫠濡ゅ懎绠伴柛娑橈攻濞呯娀鏌ｅΟ娆惧殭缂侇偄绉归弻娑㈩敃閿濆棛顦ㄩ梺? in context


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
            summary="婵犵數鍋為崹鍫曞箰閹间焦鏅濋柕澶嗘櫓閺佸啴鏌ゅù瀣澒闁稿鎹囬幃钘夆枔閹稿孩鏆為梻浣风串缂傛氨鍒掑▎鎾虫瀬鐎广儱鎷嬪鈺呭级閸稑濡芥繛鍫涘灲濮婅櫣鎲撮崟顒傜▏闂佹悶鍨洪悡锟犮€佸鑸电劶鐎广儱鎳愰ˇ褔姊洪棃娑辨Ф闁稿﹥顨婂畷顖涚節閸ャ劌浠梺鎼炲劘閸斿瞼绮堥崘顔界厪闁糕剝顨呴弳锝夋煛娴ｅ摜孝闁伙絾绻堝畷姗€骞嗚濞呮绱撻崒姘偓鎼佸窗濮樿泛绐楅柡鍥╁Ь婵?闂傚倸鍊搁崐鎼佸磹閸洖绀夐煫鍥ㄧ☉閻掑灚銇勯幒鍡椾壕闂佸摜鍠愭繛濠囧箚娓氣偓椤㈡盯鎮欓弶鎴濆闂備礁鎲″ú锕傚磻閹烘嚦锝囨嫚濞村顫嶉梺鍝勫暙閸婃悂鐎锋俊鐐€栭幐濠氬箖閸屾氨鏆?,
        )
        db.add(summary)
        await db.commit()

        context = await build_dynamic_context(user, db)
        assert "闂備浇顕уù鐑藉极閹间礁鍌ㄧ憸鏂跨暦閿濆骞㈡俊顖溾拡濞叉悂姊虹化鏇炲⒉闁告垵缍婂畷鐢告晝閸屾稑浠? in context
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_context_loading.py -v`
Expected: FAIL 闂?memories not appearing in context output

- [x] **Step 3: Modify context.py to load memories**

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

WEEKDAY_NAMES = ["闂傚倷绀侀幉锛勭矙韫囨稑绀夐悗锝庡墰閸?, "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悗锝庡墲婵?, "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悗锝庡墰缁?, "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悘鐐电叓?, "闂傚倷绀侀幉锛勭矙韫囨稑绀夐悗锝庡墲婵?, "闂傚倷绀侀幉锛勭矙韫囨稑绀夌€光偓閸曨偆鐓?, "闂傚倷绀侀幉锛勭矙韫囨稑绀夌€广儱鎲?]


async def build_dynamic_context(user: User, db: AsyncSession) -> str:
    """Build the dynamic portion of the system prompt."""
    now = datetime.now(timezone.utc)
    today = now.date()
    weekday = today.isoweekday()

    parts: list[str] = []
    parts.append(f"闂佽崵鍠愮划搴㈡櫠濡ゅ懎绠伴柛娑橈攻濞呯娀鏌ｅΟ娆惧殭缂侇偄绉归弻娑㈩敃閿濆棛顦ㄩ梺鎸庣〒閸犳牠寮婚妸銉㈡婵炲棙锚婵湏ow.strftime('%Y-%m-%d %H:%M')}闂傚倷鐒︾€笛呯矙閹存繍鐔嗛柡鍫涒偓顨獽DAY_NAMES[weekday - 1]}闂?)

    if user.current_semester_start:
        delta = (today - user.current_semester_start).days
        week_num = delta // 7 + 1
        parts.append(f"闂佽崵鍠愮划搴㈡櫠濡ゅ懎绠伴柛娑橈攻濞呯娀鏌ｅΟ纰辨毌闁稿鎸搁埥澶愬箮閼恒儺鈧秴鈹戦悩顐壕闂佽法鍠撴慨鐢稿疾椤掍焦鍙忔慨妞诲亾缁绢厽鎮傚畷鏇㈠箟閹插當ek_num}闂?)

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

    parts.append("\n婵犵數鍋涢顓熸叏閹绢喗鏅濋柕鍫濐槸妗呮繝銏ｅ煐閸旀牠宕曞澶嬬厱闁哄洢鍔屾晶顖炴煥濞戞﹩妲虹紒杈ㄥ笧閳ь剨缍嗘禍鍫曞磿濠婂懐纾?)
    if not courses and not tasks:
        parts.append("- 闂傚倷绀侀幖顐﹀疮閻楀牊鍙忛柟缁㈠枟閸嬧晠鏌曟繛鐐珔缂?)
    else:
        for course in courses:
            location = f" @ {course.location}" if course.location else ""
            parts.append(f"- {course.start_time}-{course.end_time} {course.name}{location}闂傚倷鐒︾€笛呯矙閹达附鍋嬮柟浼村亰閺佸鈧娲栧ú銊╂儗濞嗘挻鍊甸柨婵嗘噹椤ｅ磭绱掗埀?)
        for task in tasks:
            status_mark = "闂? if task.status == "completed" else "闂?
            parts.append(f"- {task.start_time}-{task.end_time} {task.title}闂傚倷鐒︾€笛呯矙閹存繍鐔嗛柡澶嬫尋atus_mark}闂?)

    # User preferences
    preferences = user.preferences or {}
    if preferences:
        parts.append("\n闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰銉︾箾閹存瑥鐏╃痪鎯ь煼閻擃偊宕堕妸锕€钄奸梺绋款儍閸旀垿寮?)
        if "earliest_study" in preferences:
            parts.append(f"- 闂傚倷绀侀幖顐︽偋閸愵喖纾婚柟鍓х帛閻撴盯鏌涢幇鍓佺ɑ婵炲懎鎳忛妵鍕箳閺傛寧鐎剧紓浣割儏閿曨亪骞冮埡鍛優妞ゆ劦鍋呰ⅶ闂傚倸鍊搁崐鎼佸磹娴犲绠垫い蹇撴椤洟鏌ｉ妸锔瑰彏references['earliest_study']}")
        if "latest_study" in preferences:
            parts.append(f"- 闂傚倷绀侀幖顐︽偋閸愵喖纾婚柟鍓х帛閻撴盯鏌涘☉鍗炴灕濠㈣蓱閵囧嫰骞掗弬鎸庣€剧紓浣割儏閿曨亪骞冮埡鍛優妞ゆ劦鍋呰ⅶ闂傚倸鍊搁崐鎼佸磹娴犲绠垫い蹇撴椤洟鏌ｉ妸锔瑰彏references['latest_study']}")
        if "lunch_break" in preferences:
            parts.append(f"- 闂傚倷绀侀幉锟犮€冮崨瀛樺亱闁告侗鍨遍～鏇㈡煏閸繍妲归柡鍜佸墯閹便劌鈹戦崼鐔哥伋references['lunch_break']}")
        if "min_slot_minutes" in preferences:
            parts.append(f"- 闂傚倷绀侀幖顐︽偋閸愵喖纾婚柟鍓х帛閻撶喐銇勯幘妤€鍟粻鍝勨攽閻橆偄浜炬繛鎾村焹閸嬫挾鈧鍣崑濠傜暦婵傚憡鍋勯柛鎾冲级琚у┑鐘垫暩閸嬫盯鎮ц箛娑栤偓鍌烆敊閻愵剦娼熼梺姹囧妽閳殙eferences['min_slot_minutes']}闂傚倷绀侀幉锛勬暜閹烘嚦娑樷攽鐎ｎ亞顔?)
        if "school_schedule" in preferences:
            parts.append("- 闂佽娴烽幊鎾诲箟閿熺姵鍋傞柨鐔哄Т閸屻劑鏌曢崼婵囧窛缁惧墽鍋撻妵鍕籍閸パ冩優缂備礁顑呴敃顏堝蓟閻旂⒈鏁囩憸宥夋倶閳╁啩绻嗛柣鎰絻閳ь剙鐏濋～蹇涙嚒閵堝拋妫滈柣搴祷閸斿宕?)

    # Hot memories (preferences + habits) 闂?always loaded
    hot_memories = await get_hot_memories(db, user.id)
    if hot_memories:
        parts.append("\n闂傚倸鍊搁崐鐢稿磻閹剧粯鐓欑紒瀣仢椤掋垽鏌涢埡浣糕偓鍧楀箖鐟欏嫭濯撮悷娆忓閸戯紕绱撴担绛嬪殭闁稿﹤娼″顐㈩吋婢跺﹪鍞跺┑鐘绘涧閹虫劙宕滈妸锔剧瘈闂傚牊绋戦埀顒€缍婂畷鐟扳攽閸垻鐣堕柣蹇曞仜婢т粙鍩㈤弴銏＄厽婵☆垰鎼弳閬嶆煕閺冨倹鏆柡灞诲妼閳藉顫滈崱姗嗏偓鍡欑磽?)
        for mem in hot_memories:
            parts.append(f"- [{mem.category}] {mem.content}")

    # Warm memories (recent decisions/knowledge) 闂?loaded at session start
    warm_memories = await get_warm_memories(db, user.id, days=7)
    if warm_memories:
        parts.append("\n闂備礁鎼ˇ顐﹀疾濠婂牆鍨傞悹铏瑰皑閼板潡鏌ㄥ☉妯侯仾濠殿垰銈搁弻鈩冨緞鎼淬垻銆婄紓浣哄У閹瑰洭寮婚妸銉㈡婵☆垳鍘ч·鈧繝鐢靛仦閹逛線宕洪弽褜鐒?婵犵數濮伴崹褰掓倶閸儱鐤炬い蹇撴椤洘鎱ㄥΟ鍨厫闁?)
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
        parts.append(f"\n婵犵數鍋為崹鍫曞箰閹间焦鏅濋柕澶嗘櫓閺佸啴鏌ゅù瀣澒闁稿鎹囬幃钘夆枔閹稿孩鏆為梻浣风串缂傛氨鍒掑▎鎾跺祦婵°倐鍋撻摶锝嗙箾閸℃瑥浜鹃柣顓燁殜濮婃椽骞愭惔锝傚濡炪倖甯為悵鐢t_summary.summary}")

    return "\n".join(parts)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_context_loading.py -v`
Expected: All 4 tests PASS

- [x] **Step 5: Run existing context tests to verify no regression**

Run: `cd student-planner && python -m pytest tests/ -v -k "context"`
Expected: All PASS

- [x] **Step 6: Commit**

```bash
cd student-planner
git add app/agent/context.py tests/test_context_loading.py
git commit -m "feat: load hot/warm memories and session summary into system prompt"
```

---

### Task 6: Session Lifecycle 闂?Summary + Memory Extraction

When a session ends (WebSocket disconnect or timeout), generate a session summary and extract memories from the conversation. Both use the LLM.

**Files:**
- Create: `student-planner/app/agent/session_lifecycle.py`
- Create: `student-planner/tests/test_session_lifecycle.py`

- [x] **Step 1: Write the failing tests**

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
            ConversationMessage(session_id="sess-1", role="user", content="闂備焦鐪归崺鍕垂婵傜绐楁俊銈呮噹閸ㄥ倹绻濇繝鍌滃闁稿孩鍨块幃妤呮晲鎼粹€愁潽缂備胶濮甸悷鈺侇嚕閸洖鐓涢柛灞剧矋閸Ｑ囨⒑閻熸澘鏆辨俊顐ｇ箞楠炲棝宕橀鑲╊槹濡炪倖鎸荤粙鎺楀疾閻愮儤鈷掗柛灞捐壘閳ь剛顭堥锝囨崉娓氼垱瀵岄梺绋跨灱閸嬬偤鍩?),
            ConversationMessage(session_id="sess-1", role="assistant", content="婵犵數鍋犻幓顏嗗緤閹稿孩鍙忛柛鎾楀嫬搴婇梺鍝勭▉閸樼厧顔忓┑瀣厪濠电姴绻樺顔剧磼?2婵犵數鍋為崹鍫曞箹閳哄倻顩查柣鎰惈閻撴﹢鏌″搴″箺闁抽攱甯￠弻娑樷枎韫囷絾效濡炪伅浣稿缁?),
            ConversationMessage(session_id="sess-1", role="user", content="闂備焦鐪归崺鍕垂婵傜绐楁俊銈呮噹閸ㄥ倹绻濇繝鍌涘櫝闁稿鎹囬幃鐑芥焽閿斿彨褔鏌ｉ姀鈺佺仭闁圭顭烽妴鍐炊椤剛鍠撶槐鎺懳熷ú璇叉櫃婵犵數濮伴崹鐓庘枖濞戞氨鐭撶€规洖娲ゆ慨?),
            ConversationMessage(session_id="sess-1", role="assistant", content="闂佽姘﹂～澶愭偤閺囩姳鐒婃繛鍡樻尭閺嬩線鏌熼幑鎰靛殭缂?婵犵數鍋為崹鍫曞箹閳哄倻顩叉繝濠傜吇閸ヮ剙鐭楀璺哄閺嬫瑩姊虹紒姗嗙劸濡炲顭堥悾鐑藉蓟閵夛妇鍘?),
        ]
        db.add_all(msgs)
        await db.commit()

        mock_summary_response = {
            "role": "assistant",
            "content": json.dumps({
                "summary": "闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰銉︾箾閹存瑥鐏╅柦鍐枛閺屾洘绔熼姘伀闁伙綀濮ょ换娑氣偓娑欘焽閻﹥淇婇锝囨噧闁挎洏鍨虹€靛ジ寮堕幋婵堢崺闂備線娼ц噹闁逞屽墴瀵偊宕熼娑掓嫽闂佺鏈懝鍓х棯瑜庢穱濠囨倷閹绘巻鍋撻崹顕呮綎缂備焦蓱缂嶅洭鏌涢幘妤€鎷嬪Σ鐑芥⒑鐠囧弶鎹ｉ柟铏崌钘濋柟娈垮枟閺嗘粓鏌熼幆褜鍤熸い鈺傜叀閺屾盯鍩勯崘顏傗偓鎺旀喐闁箑鐏﹂柡灞稿墲閹峰懐鎲撮崟顓炲殥婵＄偑鍊х粻鎴濐嚕閸撲胶鐭欏┑鐘叉处閸嬫劕銆掑鐓庣仩闁诡喕绶氬娲川婵犲倻鐟查柣銏╁灱娴滅偛危?婵犵數鍋為崹鍫曞箹閳哄倻顩叉繛鍡樻尭缁犳煡鏌曡箛瀣偓鏇犵矆婢舵劖鐓冮柦妯侯槹閸ｇ晫绱掗埀?,
                "actions": ["闂傚倷绀侀幖顐ゆ偖椤愶箑纾块柟缁㈠櫘閺佸淇婇妶鍛殶闁活厽纰嶇换娑橆啅椤旇崵鍑归梺鎸庣⊕缁诲牓寮婚敓鐘茬闁靛ě鍐幗婵?, "闂傚倷鐒﹂惇褰掑垂婵犳艾绐楅柟鐗堟緲閸ㄥ倹鎱ㄥ鍡楀季婵炲牊顨嗘穱濠囶敍濠婂懎绗″┑鐐茬墣濞夋盯鈥︾捄銊﹀磯闁惧繐澧ｉ敍鍕＜闁炽儱鍟块顐︽煙瀹勯偊鍎旈柛銊╃畺瀹曟﹢鎳犻鍨瀳"],
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
        assert "婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴幇顒夊殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊? in summary.summary


@pytest.mark.asyncio
async def test_end_session_extracts_memories(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="sess-user-2", username="sesstest2", hashed_password="x")
        db.add(user)

        msgs = [
            ConversationMessage(session_id="sess-2", role="user", content="闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傞柣銏㈩焾閸戠娀鏌嶆潪鎷岊唹闁哄閰ｉ弻鏇＄疀婵犲倸鈷夐梺鎸庣☉缁夋挳鍩ユ径鎰缂佹稓鎳撴导鎰渻閵堝繒鐣辩€殿喖澧庣划娆愮節閸ャ劌浜归梺鍓茬厛閸嬪嫰鍩€椤掑倸浠х紒杈ㄥ笚瀵板嫮鈧綆浜為崢鎰磽娴ｄ粙鍝虹紒璇茬墕椤曪綁骞撻幒婵囧兊濡炪倖鍔戦崐妤呭箟椤忓牊鈷戞繛鑼额唺缁ㄧ粯銇勯幋婵囶棦鐎殿喗鎮傚畷姗€顢旈崱娆戝帬?),
            ConversationMessage(session_id="sess-2", role="assistant", content="婵犵數濞€濞佳囧磹婵犳艾鐤炬い鎰ㄦ噰閺嬫棃鏌熸潏楣冩闁哄拋鍓熼幃姗€鎮欓弶鎴濆Б闂佽绻愰ˇ鐢稿箖鐟欏嫮鐟归柍褜鍓熼妴鍌炴晜閸撗咁槸闂佹悶鍎崝搴ㄣ€?),
        ]
        db.add_all(msgs)
        await db.commit()

        mock_response = {
            "role": "assistant",
            "content": json.dumps({
                "summary": "闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰銉︾箾閹寸偟顣查柛瀣耿閺屾洘绻涢崹顔碱瀴閻熸粍濡搁崗鐘垫嚀椤劑宕橀埡濠冾棧婵＄偑鍊栫敮鐐哄窗閹邦喚鐭欏┑鐘叉处閸嬫劙鏌ц箛锝呬航婵″樊鍨跺濠氬磼濮橆兘鍋撻悷閭︾劷婵炲棙鍔楅々鏌ユ煕濞戞﹫鍔熼梻?,
                "actions": [],
                "memories": [
                    {"category": "preference", "content": "闂傚倷绀侀幗婊勬叏閻㈤潧鍨濈€广儱顦介弫鍐归悩宸剰缂侇偄绉归弻宥囨偘閳ュ厖澹曠紓鍌欑劍椤ㄥ懘宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婃椽鎳￠妶鍛捕濠碘槅鍋呴惄顖炴晲閻愬搫鍐€妞ゆ挾鍠愬▍鏍煟韫囨洖浠ч柛瀣崌閹敻骞橀弬銉︻潔闂佺懓澧介鏌ュ礉閻斿摜绡€闁逞屽墴瀹曘劑寮堕幋鐑嗘闂備焦鎮堕崕顕€寮查埡渚囩劷?},
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
        assert "闂傚倷娴囧畷鐢稿磻濞戞娑樷槈椤喚绋? in memories[0].content
        assert memories[0].source_session_id == "sess-2"


@pytest.mark.asyncio
async def test_end_session_empty_conversation(setup_db):
    """No messages 闂?no summary, no crash."""
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

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_session_lifecycle.py -v`
Expected: FAIL 闂?`ModuleNotFoundError: No module named 'app.agent.session_lifecycle'`

- [x] **Step 3: Implement session_lifecycle.py**

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

_EXTRACT_PROMPT = """闂傚倷绀侀幉锛勬暜閹烘嚦娑樷枎閹炬潙鈧敻鏌ら幁鎺戝姢妞も晝鍏橀弻鏇熷緞閸績鍋撳Δ鍛仭闁瑰墽绮崐鐢告煟閵忊槅鍟忛柡鈧导瀛樼厽闁挎棁娉曢惌娆撴煛娴ｅ摜孝闁伙絾绻堝畷姗€顢旈崱娆忊偓鎶芥⒒?JSON闂傚倷鐒︾€笛呯矙閹达附鍋嬮柛娑卞灣缁犳柨顭跨捄鐑樻拱闁哥喎鎼湁闁挎繂娲﹀▍鏇犵磽閸繍鐓奸柡灞剧洴楠炲鈹戦崶銊ュ壍闂備礁鎲￠悷褔宕戦幘鍓佺焿闁圭儤顨呴崘鈧悷婊冪Ч瀵偊宕奸弴鐔封偓鐢告煕閿旇骞楁い蹇曞枔缁辨帗娼忛妸銉ユ懙闂?
{
  "summary": "婵犵數鍋為崹鍫曞箰閹绢喖纾婚柟鍓х帛閻撴洘绻涢崱妤冃㈤柛鏂诲劦閺岋綁鏁傜捄銊х厯濡ょ姷鍋愰崑鎾绘⒑閻撳寒娼熼柛濠冾殔閳绘棃濮€閵堝懐楠囬梺鍐叉惈閸婂骞婇崟顑句簻闁归偊鍨版禍褰掓煃瑜滈崜娑㈠极閹间降鈧焦绻濋崶銊ュ墾婵炲濮撮鍛缂佹ɑ鍙忔慨妤€妫楁禍鐐烘煕閻斿嚖宸ラ棁澶愭煟濮楀棗浜滃ù婊呭亾缁?,
  "actions": ["闂傚倷绀佸﹢閬嶆偡閹惰棄骞㈤柍鍝勫€归弶鎼佹⒒娴ｅ湱婀介柛鏂跨灱閳ь剚鍑归崣鍐嵁閺嶎厽鐓ラ悗锝庡亜椤庢挸鈹戦悩璇у伐闁哥噥鍋婇幃妯衡枎閹炬潙浠?],
  "memories": [
    {"category": "preference|habit|decision|knowledge", "content": "闂傚倷鑳堕…鍫ユ晝閿曞倸鍌ㄧ憸蹇撯枎閵忋倖鐒肩€广儱妫岄幏褰掓⒑閸︻収鐒鹃悗娑掓櫊瀹曟椽宕掗悙鏉戜化婵炴挻鍩冮崑鎾淬亜閿濆繐顩紒杈╁仱瀹曞爼顢楁担绋垮闂備礁鎲″ú锔界濞嗘垶宕查柛鈩冪⊕閻?}
  ]
}

闂備浇宕甸崰鎰版偡閵壯€鍋撳鐓庡⒋鐎规洖缍婇、娑㈡倷鐎涙ɑ鐝?- summary 闂備浇宕甸崰鎰洪幋锔藉殑闁割偅娲橀崑鈺傜節闂堟稒鐏╅柣鎴烆焽閻熺懓鈹戦悩鎻掝伀妞わ富鍠楃换娑㈠箣閻愭潙鐨戦梺绋款儐閹告悂鍩ユ径鎰闁告鍋愰崑鎾诲即鎺虫禍褰掓煟閹邦剛浠涢悗?- memories 闂傚倷绀侀幉锟犳偡椤栨稓顩叉繝闈涱焾娴滅懓銆掑锝呬壕閻庤娲╃紞浣割嚕娴犲鏁冮柨婵嗘椤撳綊姊绘担绛嬫綈闁瑰憡濞婂銊╁础閻愬稄缍侀獮瀣偐閸愭彃骞戞俊鐐€栧Λ渚€鏁撻妷鈺佺劦妞ゆ巻鍋撻柛鐕佸灠椤洩绠涘☉妯碱槶閻熸粌閰ｉ幃楣冩焼瀹ュ棛鍘遍柣搴秵娴滅偟绮绘导瀛樼厪闁割偅绮庨惌娆忊攽閳ュ磭鎽犻柟宄版噺椤︾増鎯旈敐鍡╂綘闂傚倷娴囬鏍垂婵傜鍨傞梺顒€绉撮崹鍌炴煏婵炵偓娅嗛柣鎾冲€婚埀顒€绠嶉崕閬嶆偋濠婂厾娲晲婢跺鍘遍梺褰掑亰閸撴盯鏁嶅澶嬬厽?- 婵犵數鍋為崹鍫曞箰閸濄儳鐭撻柣鎴濐潟閳ь剙鎳橀弫鍐磼濮橀硸鍞洪梻渚€娼ч…顓㈡⒔閸曨垱鍊垮ù鐘差儐閻撱儲绻涢幋鐑嗙劷濠⒀佸灲閺屸剝鎷呴棃娑掑亾濠靛宓侀悗锝庡枟閸嬵亝銇勯弽鐢靛埌婵?闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傞柛顐ｆ礀濮规煡鏌ｉ弮鍥モ偓鈧柛瀣尭閳藉鐣烽崶鈺冪崶缂傚倷鐒﹂〃鍛此囬幍顔剧处?闂傚倷鐒﹂崜姘跺磻閸涱垱鏆滈柣鏃傗拡閺佸﹪鏌涢妷顔荤暗濞存粌缍婇弻锟犲炊閺堢數鏁栧Δ鐘靛亼閸ㄤ粙寮婚敐澶涚稏妞ゆ巻鍋撳┑鈥茬矙閺屾盯鍩￠崒婊勫垱闂佺娅曢幑鍥х暦濡妲鹃梺?0闂傚倷绀侀幉锛勬暜閹烘嚦娑樼暆閸曨偆鏌堥柣搴秵閸嬪棝鍩㈤弮鍌楀亾楠炲灝鍔氭俊顐ｎ殜閹虫瑨銇愰幒鎾跺幐闂佺琚崐鏇烆嚕鐠恒劎纾?- 婵犵數鍋為崹鍫曞箰閹间焦鍋ら柕濞垮労濞撳鏌涘畝鈧崑娑氱不閹寸姵鍠愰悘鐐插⒔閳瑰秴鈹戦悩鍙夋悙缂佺姵甯楅妵鍕冀閵娧勫櫘闂佽崵鍠愮换鍫ュ箖鐟欏嫭濯寸紒瀣硶閻╁海绱?婵犵數鍋涢顓熸叏閹绢喗鏅濋柕鍫濐槸妗呮繝銏ｆ硾椤戝洭鍩㈤弮鍌楀亾楠炲灝鍔氭俊顐ｎ殜瀹曘垽骞掑Δ浣糕偓鍨箾閹存繄锛嶇紒杈ㄥ缁?闂?- 婵犵數濮烽。浠嬪焵椤掆偓閸熷潡鍩€椤掆偓缂嶅﹪骞冨Ο璇茬窞濠电偟鍋撻悡銏ゆ⒑閺傘儲娅呴柛鐕佸灣缁骞掑Δ浣哄幈婵犵數濮寸€氼剛鏁崜浣虹＜闁诡垶顣﹂崥顐︽煙瀹勯偊鍎愰柨娑欏姈閹峰懘鎼归崜鎰╁€濆鍝勑ч崶褍顬堥柣搴㈠嚬娴滄繄绮氭潏銊х瘈闁搞儜鍛殺婵＄偑鍊栭悧鎾诲磹濡ゅ啰鐭嗗┑澶屻仏mories 婵犵數鍋為崹鍫曞箲娴ｇ硶鏋嶉柨婵嗩槸閻撴﹢鏌″搴″箹闁哄绶氶弻鐔封枔閸喗鐏撻梺?""


async def end_session(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    llm_client: AsyncOpenAI,
) -> None:
    """Process session end: generate summary and extract memories.

    This is called when the WebSocket disconnects or times out.
    Failures are logged but never raised 闂?session end must not crash.
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

- [x] **Step 4: Run tests to verify they pass**

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
    session_timeout_minutes: int = 120  # 2 hours inactivity 闂?new session
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
                            user_answer = user_response.get("answer", "缂傚倷鑳堕搹搴ㄥ矗鎼淬劌绐楁繛鎴欏焺閺?)
                            event = await generator.asend(user_answer)
                        elif event["type"] == "done":
                            break
                        else:
                            event = await generator.__anext__()
                except StopAsyncIteration:
                    pass
    except WebSocketDisconnect:
        # Session ended 闂?generate summary and extract memories
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

### Task 8: Update Agent.md 闂?Memory Tool Rules

Add behavior rules for the memory tools to Agent.md.

**Files:**
- Modify: `student-planner/Agent.md`

- [ ] **Step 1: Add memory tool usage rules**

Add the following under the `### 闂佽姘﹂～澶愬箖閸洖纾块梺顒€绉撮惌妤呮煙缁嬪灝顒㈠┑顖涙尦閹綊骞侀幒鎴濐瀴闂佸搫妫楅崠?section in `Agent.md`:

```markdown
- recall_memory闂傚倷鐒︾€笛呯矙閹烘鍤岄柛鎾楀懐顦柣搴秵閸犳藟閸℃稒鐓冪憸婊堝礈濞戙垹绠熼柣妤€鐗婃刊鎾煕濞戞﹫鍔熸い锔哄劦濡懘顢曢姀鈩冩倷濠碘槅鍋呴惄顖氼嚕椤愶箑围濠㈣泛锕﹂娲⒑閻愵剝澹橀柛濠傤煼椤㈡ê煤椤忓懐鍘遍梺瑙勫劤绾绢叀鍊存繝鐢靛仜閻楀﹪宕归崹顔炬殾闁硅揪绲块悿鈧梺瑙勫劤瀹曨剚绂掑ú顏呪拺闂傚牊绋掗ˉ娆愪繆閻愭潙绗х€殿啫鍥х妞ゆ牗姘ㄩ悾鎯ь渻閵堝棛澧紒瀣灴閹ê螖閸涱喚鍘遍梺褰掑亰閸撴盯鏁嶅澶嬬厽閹烘娊宕曢棃娑卞殨妞ゆ洍鍋撶€殿喚鏁诲Λ鍐ㄢ槈閹烘挾鈧ジ姊绘担瑙勩仧婵炵厧娼″畷婵囩節閸パ呭姦濡炪倖宸婚崑鎾绘煕婵犲浂妫戠紒顕呭幗瀵板嫮浠﹂幆褎姣囧┑鐐舵彧缁茶棄锕㈤崡鐐嶏綁濡搁敂鍓ь啎闂佺硶鈧磭绠氶柛瀣崌楠炲洦鎷呴崨濠庡晠闂備浇宕垫慨鏉懨洪敂鐐床闁割偁鍎辩粈鍌涗繆椤栨艾鎮戦悗姘煎墴閺屾盯骞囬崗鍝ュ嚬闂佸搫妫楃换姗€寮婚妸銉㈡婵☆垰鐏濋顓㈡偡濠婂嫬惟闁搞儜鍕ザ闂備線娼ц噹闁逞屽墴閸┾偓妞ゆ帊绶￠悞浠嬫煃瑜滈崜娆忥耿闁秴纾婚柕鍫濇噷閳ь剚甯″畷婊勬媴閻熺増姣囧┑鐐舵彧缁插潡鈥﹂崼銉ラ敜濠电姴娲﹂悡鏇熺箾閸℃ê绗掔紒鎲嬬畱鑿愰柛銉戝秷鍚Δ鐘靛仒缁舵岸銆佸☉妯锋婵炲棙蓱琚ф繝鐢靛仩閹活亞绱為埀顒佺箾婢跺绀嬬€?- save_memory闂傚倷鐒︾€笛呯矙閹烘鍤岄柟瑙勫姂娴滃湱鎲告惔锝囩煔闁告鍋愰弨浠嬫煕閳╁啰鎳勯柟鎻掋偢濮婂搫煤缂佹ê鈻忛梺鍛婃煥缁夌懓鐣烽崫鍕ㄦ闁靛繒濮村鐑芥煙閼圭増褰х紒鍙夋そ閸┾偓妞ゆ帊绶￠悞浠嬫煙椤旇宓嗗┑鈩冩倐婵℃悂鏁冮埀顒€鈽夎濮婂搫效閸パ冾瀳闁诲孩鍑规禍婵堢矚鏉堛劎绡€闁搞儜鍛殺婵＄偑鍊栭悧鎾诲磹濡ゅ啰鐭嗗璺号堝Σ鍫ユ煙閹咃紞閸熺顪冮妶鍌涙珨缂佺姵鎹囬悰顕€骞掑Δ鈧儫闂佹寧姊婚弲顐﹀礉閻戣姤鈷戦梻鍫熺⊕椤ユ粓鏌涙繝鍥舵闁瑰箍鍨归～婵嬪箥娴ｉ晲澹曞┑鐐村灦椤忣亪顢旈崨顔界彿闂佺粯顭堝▍锝夋偪閳ь剟姊洪崨濠勨姇闁伙綆浜崺鈧い鎺嗗亾缂佺粯锚閻ｅ嘲螖閸涱參鍞堕梺闈涚箚閸撴繂鈻?ask_user 缂傚倷鑳堕搹搴ㄥ矗鎼淬劌绐楁繛鎴欏焺閺佸洤鈹戦悩宕囶暡闁?闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傚┑鍌氬閺佸﹪鏌涢妷锝呭濠殿垱鎸抽悡顐﹀炊瑜庨幑锝夋煕閻斿嚖韬柡灞诲妼閳藉鈻庨幋鐐村暫闂傚倷绀侀幉锟犲礉閺囥垹绠犻幖鎼厛閺佸﹪鏌熼鍕暫闁哄本娲熷畷鍗炍旈埀顒勫焵椤掍焦鍊愭い銏″哺椤㈡岸鍩€椤掆偓閻ｇ兘濡烽妷搴㈡⒒閳ь剨缍嗛崜娆撳箚?
  - preference闂傚倷鐒︾€笛呯矙閹烘埈娼╅柕濞炬櫅閺嬩線鏌曢崼婵愭Ц缂佺媴绲块埀顒傛嚀鐎氫即銆傞敃鍌涘€垮┑鐘插€甸弨浠嬫煕鐏炲墽鈯曢柣蹇ｅ枤缁?闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傞柣銏㈩焾閸戠娀鏌嶆潪鎷岊唹闁哄閰ｉ弻鏇＄疀婵犲倸鈷夐梺鎸庣☉缁夋挳鍩ユ径鎰缂佹稓鎳撴导鎰渻閵堝繒鐣辩€殿喖澧庣划娆愮節閸ャ劌浜归梺鎯ф禋閸嬪懘顢欏澶嬬厽?闂?  - habit闂傚倷鐒︾€笛呯矙閹烘鍤屽Δ锝呭枤閺佸棝鏌ｉ弬鎸庢喐闁崇粯娲熼弻锝呂熸径绋挎儓闂佷紮绠戦柊锝夊蓟閻旂⒈鏁嶉柨婵嗘噽娴煎牏绱?闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傜€规洖娲ㄩ崡姘舵煛婢跺鐏嶉柡瀣叄閺屽秹鍩℃担鍛婃婵炲濮甸敋妞ゎ厼娼￠幊婊堟濞戞ɑ鎳欐繝鐢靛仜椤р偓闂傚嫬瀚划?闂備浇顕х换鎰崲閹邦喗宕查柟瀛樼箥濞?闂?  - decision闂傚倷鐒︾€笛呯矙閹烘垹鏆嗛柟闂寸闂傤垶鏌涘┑鍕姕闁哥喎鎼湁闁挎繂娴傞悞楣冩煛鐎Ｑ冧壕缂傚倸鍊烽悞锔剧矙閹烘鍋嬫い鎾跺У椤?婵犲痉鏉库偓鏇㈠磹绾懏鎳岄梻浣告惈濡盯宕伴弽顓炵畺濞寸姴顑呮儫闂侀潧顦崕鎶藉焵椤掑啫鍚圭紒杈ㄥ浮瀵噣宕掑В娆惧墮閳规垿鍩ラ崱妤€绠荤紓渚囧枤閺佽顕ｆ禒瀣垫晝闁挎繂妫崥?闂?  - knowledge闂傚倷鐒︾€笛呯矙閹烘挾鈹嶆繛宸憾閺佸鈧娲栧ú銊╂儗濞嗘挻鍊甸柨婵嗛瀵箖鏌涘顒佸枠闁哄矉缍侀、妯侯煥閸愩劌啸缂?闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰銉︾箾閹寸偟顣查柛鐘叉椤法鎹勯悮鏉戝缂備浇顔婇悞锕傚箞閵娾晛绠抽柟瀛樼妇閸嬫挾鎷犲顔兼櫊闂佸吋绁撮弲婊勫垔婵傚憡鐓熼柟瀵稿€栭幋鐐殿浄婵せ鍋撴慨?闂?- 婵犵數鍋為崹鍫曞箰閸濄儳鐭撻柣鎴濐潟閳ь剙鎳橀弫鍌炴偩鐏炲憡鏁垫繝鐢靛█濞佳兾涘☉銏犵闁绘ɑ绁村Σ鍫ユ煙閹咃紞闁圭晫濮垫穱濠囨倷閹绘巻鍋撻崸妤冨祦闁逞屽墰閹插摜浠﹂崜褉鏀虫繝鐢靛Т濞层倗绮婚幒鎾变簻闁哄秲鍎遍埀顒侇殘缁?婵犵數鍋涢顓熸叏閹绢喗鏅濋柕鍫濐槸妗呮繝銏ｆ硾椤戝洭鍩㈤弮鍌楀亾楠炲灝鍔氭俊顐ｎ殜瀹曘垽骞掑Δ浣糕偓鍨箾閹存繄锛嶇紒杈ㄥ缁?闂?- 婵犵數鍋為崹鍫曞箰閸濄儳鐭撻柣鎴濐潟閳ь剙鎳橀弫鍌炴偩鐏炲憡鏁垫繝鐢靛█濞佳兾涘☉銏犵闁绘顣介崑鎾舵喆閸曨厽鎲欓柣蹇撶箲閻熝囧礆閹烘鏅搁柣妯哄级瀹撳秹姊洪棃娑辩叚闂傚嫬瀚埢鎾诲醇閺囩喓鍘甸柣鐘叉礌閳ь剝娅曢悘鍫㈢磽娴ｉ潧濮€濡炴潙鎽滅划娆愬緞閹板灚鏅ｉ梺缁樏壕顓㈠汲閻樺磭绠鹃柨婵嗘噺缁€宀勬煕閹惧绠栭悗闈涖偢瀹曘劎鈧稒蓱濞呮牠姊洪崜鎻掍壕缂傚秴妫濆畷鐢告晜閸撗咃紲闁诲函缍嗘禍鍫曞磿瀹ュ鐓冪憸婊堝礂濞戞﹩娓婚柟鐑橆殔缁犳煡鏌曡箛瀣偓鏇犵矆婢舵劕绠抽柟鎯版閻掑灚銇勯幋鐐差嚋缂佷椒鍗抽弻宥堫檨闁告挻鐟╁畷顖炲箮閼恒儱鍓ㄥ銈嗙墱閸嬬偤寮?- 闂佽崵鍠愮划搴㈡櫠濡ゅ懎绠板Δ锝呭暙閺嬩線鏌曢崼婵愭Ц缂佺媴缍侀弻锝夊Χ鎼达紕浼囬梺?闂傚倸顭崑鍕洪敃浣规噷闂佹眹鍩勯崹顏堝磻閹兼獰x"闂傚倷绀侀幖顐﹀疮閹剁瓔鏁婇柟閭﹀枟椤洘绻濋棃娑卞剱闁?recall_memory 闂傚倷鑳堕幊鎾绘倶濮樿泛纾块柟鎯版閺勩儳鈧厜鍋撻柍褜鍓熼崺鈧い鎺戝€归弳鈺呮煙閾忣偅灏甸柤娲憾閹崇娀顢楁担鍓测偓娑㈡⒑閸濆嫷妲兼繛澶嬫礈缁骞樼紒妯煎弳濠电偞鍨堕…鍥倶闁秵鐓曢柡鍌滃仜濞层倗鎲撮敃鍌氱缂侇喚鎳撴晶鏌ユ煕閻斿搫浠遍柡宀嬬秮椤㈡ê顭ㄩ崘銊バ戦梻浣芥〃闂勫秹宕愬┑瀣祦閻庯綆浜為弳瀣煛婢跺﹦浠㈡繛鍫涘劦濮婃椽宕ㄦ繝鍌滎儌婵犵數鍋愰崑鎾斥攽?```

- [ ] **Step 2: Add few-shot example for memory**

Add the following as a new example after existing examples in `Agent.md`:

```markdown
### 缂傚倸鍊风拋鏌ュ磻閹捐绾ч柣鎰綑椤ュ霉?闂傚倷鐒︾€笛呯矙閹烘挾鈹嶆繛宸憾閺佸﹪鏌涢妷顔荤敖闁汇倐鍋撻梻浣虹《閸撴繈鎮烽鐐茶Е闁逞屽墴濮?
闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰? "闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傚ù锝呭暔娴滃綊鏌涘畝鈧崑鐐哄磻濠靛鐓熸俊銈傚亾闁绘锕幃鐢稿箻閺傘儲顫嶉梺鐟板⒔椤掓彃顔忛妷锔轰簻闁挎洍鍋撶€殿喖澧庣划娆愮節閸ャ劌浜归梺鎯ф禋閸嬪懘鎮甸敓鐘斥拺缂備焦顭囬惌濠冪箾鐠囇呯暠閻撱倝鏌熺粙鍨槰婵炲牊顨嗛幈銊ノ旈埀顒勬偋韫囨洜鐭嗗璺衡姇瑜版帗鍋愭い鏃傚帶婵酣姊虹拠鈥虫灍妞ゃ劌鐗撳顐︻敋閳ь剟銆佸▎鎾村癄濠㈣泛濂旈崙浠嬫⒒娴ｄ警鏀版繛澶嬬洴閺佸啴濡舵竟锕€娲畷锝嗗緞鐏炲憡鐏嗛梻浣虹帛椤牓顢氳瀹曘垽骞橀钘夆偓鐢告煟閻旂厧浜版俊鎻掔秺閹粙顢涘☉娆忕３閻庤娲滈崗妯讳繆閹间焦鏅滈柣锝呰嫰缁茬厧鈹戦悙鏉戠仸闁瑰憡鎮傞弫鍐Χ婢跺﹦鐣?

闂?save_memory(category="preference", content="闂傚倷绀侀幖顐﹀箠韫囨稒鍎楁い鏂垮⒔缁犳棃鏌涚仦鍓р槈缂佸墎鍋熼埀顒€绠嶉崕杈┾偓姘煎櫍閹焦鎯旈妸锔惧幐婵炶揪绲介幗婊勬櫠閵忊懇鍋撻崷顓х劸闁靛牏顭堥锝夊箻椤旇偐顔掑銈嗘⒐閸庢娊鎷忕€ｎ喗鈷戦柟绋挎捣閳藉鏌ゅú璇茬仭缂佸倸绉瑰畷銊︾節閸曨垱顎嶉梻浣稿悑娴滀粙宕曢弻銉﹀仧闁瑰墽绮埛鎺楁煕鐏炲墽鈯曠紓宥嗗灴閺岋綁鏁愰崘銊ヮ潎濡ょ姷鍋炵敮锟犵嵁閹烘绠ｆい鎾跺晿閳哄倻绠?)
闂?婵犵數鍋犻幓顏嗗緤閽樺）娑樜旈崨顓炲亶濠电偞鍨剁喊宥夊礂濠婂嫨浜滈柡鍐ｅ亾妞ゆ垶鐟╁畷銉╁炊椤掍胶鍙嗗┑鐐村灦閻熝囧箺椤ょ_user(type="confirm", question="闂傚倷鑳堕幊鎾绘偤閵娾晛鍨傚┑鍌氬閺佸﹪鏌涢妷锝呭濠殿垱鎸抽悡顐﹀炊瑜庨幑锝夋煕閻斿嚖韬柡灞诲妼閳藉鈻庨幋鐘插綆缂傚倸鍊哥粔鐢告晝閵忕媭鍤曢柟缁樺俯濞尖晜銇勯幇鈺佲偓妤呭箟椤忓懐绡€闁靛骏绲剧涵鍓х磼婢跺﹦锛嶇€殿啫鍥х妞ゆ牗纰嶉悗顒勬⒑閸撴彃浜栭柛銊ョ秺閹崇偤骞庨懞銉у幐闂佹悶鍎崝宥囦焊閿曞倹鐓熸繝鍨姇濞呭秹鏌℃担鍝バゅù鐙呯畵濮婅崵鈧灚鎮傞悗娲⒒娴ｅ憡鍟為柤鐟板⒔閼洪亶鎳栭埡鍌ゆ綗濡炪倖鎸堕崹鍦矆閸岀偞鐓曟い鎰剁悼缁犳﹢鏌￠崱妯活棃闁哄瞼鍠栭幃婊兾熼搹鍦嚃婵犵數鍋涢幊搴ｂ偓姘緲椤繑绻濆顒傞獓闂佽鎯岄崢鎴掔昂婵犵數鍋為崹璺侯潖缂佹ɑ鍙忓ù鍏兼綑閻掑灚銇勯幒鍡椾壕闂佺锕ラ幃鍌炪€佸棰濇晪闁逞屽墮閻ｇ兘濡烽妷搴㈡⒒閳ь剨缍嗛崜娆撳箚?)
闂?闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰銉︾箾閹寸偟顣查柛蹇旂矋閵囧嫰寮埀顒勵敄濞嗘挸瑙?闂?save_memory
闂?闂傚倷鐒﹂幃鍫曞磿閹惰棄纾绘繛鎴旀嚍? "婵犵數濞€濞佳囧磹婵犳艾鐤炬い鎰ㄦ噰閺嬫棃鏌熸潏楣冩闁哄拋鍓熼幃姗€鎮欓懜娈挎闂佹悶鍊栫敮锟犲箖鐟欏嫮鐟归柍褜鍓熼妴鍌炴晜閸撗咁槸闂佹悶鍎洪崜娆掔箽闂備胶顭堥張顒勬偡閵堝洩濮冲ù鐓庣摠閻撴洘鎱ㄥ鍡楀闁圭櫢缍侀弻鈩冩媴鐟欏嫬纾冲Δ鐘靛仜椤戝鐛崶顒夋晢濠㈣泛鐟╅埡鍌滅闁瑰鍋為埛鎺戔攽椤曗偓缁犳牠銆佸鈧獮鏍ㄦ媴閸濄儺妲撮梻浣告贡閸庛倝骞愭繝姣稿洩顦查棁澶愭煕韫囨艾浜归柣鎿冨灣缁辨帗顫戦弽褍绫嶉悗瑙勬礃椤ㄥ﹤鐣烽悡搴樻斀闁割偆鍠愰楣冩⒒娴ｅ憡璐￠柛搴涘€楅弫顔嘉旈埀顒勫煝瀹ュ绀嬫い鏍ㄧ▓閹峰鏌ｆ惔銏⑩姇閽冭鲸銇勮熁閸曨厾顔曢梺鍓插亖閸ㄨ绂掗鐐寸厓?

闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰? "闂傚倸顭崑鍕洪敃浣规噷闂佹眹鍩勯崹顏堝磻閹惧绠鹃柟瀵稿仦閻撱儲銇勯幋婵囧櫤闁哄懎鐖奸幃鈺呭垂椤愩垻褰撮梺璇查叄濞佳囧箟閿熺姵鍋╅梺顒€绉甸悡娑㈡煕閹板墎绋绘繛鍛暟缁辨帒螖閳ь剟宕愰悷閭﹀殫闁告洦鍋掗崥瀣煕閺囥劌骞樻俊鍙夊灴濮婄儤娼幍顔煎濠电姰鍨洪敃銏ゃ€?

闂?recall_memory(query="闂傚倷绀侀幖顐﹀疮閻樿鐤炬繛鍡樺灩缁犳棃鏌涚仦鍓р槈缂佸墎鍋熼埀顒€绠嶉崕杈┾偓姘煎櫍閹焦鎯旈妸锔惧幐婵炶揪缍€椤娆㈤崣澶堜簻?)
闂?闂傚倷鑳堕幊鎾绘倶濮樿泛纾块柟鎯版閺勩儳鈧厜鍋撻柍褜鍓熼獮蹇曗偓锝庡枛缁狙囨偣閹帒濡块柣?闂?闂傚倷绀侀幉锛勬暜閻愬绠鹃柍褜鍓氱换?闂?闂傚倷鐒﹂幃鍫曞磿閹惰棄纾绘繛鎴旀嚍? "闂佽娴烽幊鎾诲箟闄囬妵鎰板礃椤旂厧鐎悷婊呭鐢鍩涢弮鍫熺厪闁割偅绻勬晶銏㈢磼閻樿尙绉洪柡灞稿墲缁旂喎鈹冮崹顔瑰亾閵堝鑸归柛顐ｆ礈閸欐捇鏌涢妷鎴濆濡垿姊?
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
        {"role": "user", "content": "婵犵數鍋犻幓顏嗗緤閹稿孩鍙忛柟缁㈠枛鍥?},
        {"role": "assistant", "content": "婵犵數鍋犻幓顏嗗緤閹稿孩鍙忛柟缁㈠枛鍥存繛瀵稿Т椤戝棝寮查鈧湁闁挎繂鐗滃鎰磼閻樺啿绗掗棁澶愭煟濮楀棗浜滃ù婊呭亾缁绘盯骞嬮悙瀵稿弳闂佺粯顨呭Λ婊堝Φ閹版澘鐭楀璺虹焾濞村嫰姊洪棃娑辨Ф闁稿氦浜懞杈╂嫚鐟佷礁缍婇弫鎰板炊椤喓鍎茬换娑㈠醇閻旈浼岄梺?},
    ]
    result = await compress_conversation_history(messages, AsyncMock(), max_messages=10)
    assert result == messages


@pytest.mark.asyncio
async def test_compress_long_history():
    """Long conversations should have older messages compressed."""
    messages = [{"role": "system", "content": "System prompt"}]
    # Add 20 user/assistant pairs
    for i in range(20):
        messages.append({"role": "user", "content": f"闂傚倷鐒﹀鍨焽閸ф绀夌€广儱顦弰銉︾箾閹寸們姘ｉ崼銉︾厱妞ゆ劑鍊曢弸宥囩磼?{i}"})
        messages.append({"role": "assistant", "content": f"闂傚倷绀侀幉锟犲蓟閿熺姴鐤炬繝濠傚濞呯姵绻濇繝鍌滃闁绘劕锕弻锝夊箛椤掍讲鏋欏┑?{i}"})

    mock_response = {
        "role": "assistant",
        "content": "婵犵數鍋為崹鍫曞蓟閵娾晩鏁勯柛娑卞枟濞呯娀鏌ｅΟ鑲╁笡闁稿骸绉归弻娑㈠即閵娿儰鑸梺鎼炲€楁繛鈧柟顔肩秺瀹曞爼濡歌閻ｉ亶姊洪悡搴ｄ粵闁搞劌娼″顐㈩吋閸涱垱娈曢梺閫炲苯澧寸€殿噮鍋婃俊鑸靛緞婵犲嫷鍚呴柣搴ｆ嚀鐎氼厼顭垮Ο鐓庣筏婵炲樊浜濋埛鎴炪亜閹般劌澧叉い锕傤棑缁?0闂傚倷绀侀幖顐λ囬锕€绀堟繝闈涚墢閻捇鏌ｉ幋锝嗩棄缂佺姵甯楅妵鍕冀閵夈儮鍋撳Δ鍐焼濠㈣埖鍔栭悡鏇㈡煛閸屾粌鍔嬫繛鍛椤儻顦崇紒顔芥崌瀵宕奸妷锕€鐧勬繝銏ｆ硾椤﹁鲸銇欓搹顐ょ閻庢稒顭囬惌濠冧繆椤愶綆娈旈悡銈夋煛瀹ュ啫濡肩紒鍓佸仧閳ь剙绠嶉崕閬嶅疮閻樿纾?,
    }

    with patch("app.services.context_compressor.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        result = await compress_conversation_history(messages, AsyncMock(), max_messages=12)

    # System prompt should be preserved
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "System prompt"

    # Should have a summary message
    assert any("婵犵數鍋為崹鍫曞蓟閵娾晩鏁勯柛娑卞枟濞呯娀鏌ｅΟ鑲╁笡闁稿骸绉归弻娑㈠即閵娿儰鑸梺鎼炲€楁繛鈧柟? in m.get("content", "") for m in result)

    # Recent messages should be preserved (last 12 non-system messages = 6 pairs)
    assert len(result) <= 14  # system + summary + 12 recent


@pytest.mark.asyncio
async def test_compress_preserves_recent_messages():
    """The most recent messages should be kept intact."""
    messages = [{"role": "system", "content": "System prompt"}]
    for i in range(20):
        messages.append({"role": "user", "content": f"濠电姷鏁搁崑鐐哄垂閻㈠憡鍋嬪┑鐘插暙椤?{i}"})
        messages.append({"role": "assistant", "content": f"闂傚倷鐒﹂幃鍫曞磿閹惰棄纾绘繛鎴旀嚍?{i}"})

    mock_response = {
        "role": "assistant",
        "content": "闂傚倷绀侀幖顐﹀疮閻樿鐤炬繝濠傚枦閼板潡鏌ㄥ☉妯侯仱闁稿鎹囬幃钘夆枔閹稿孩鏆為梻浣风串缂傛氨鍒掑▎鎾跺祦婵°倐鍋撻摶锝嗙箾閸℃瑥浜鹃柣?,
    }

    with patch("app.services.context_compressor.chat_completion", new_callable=AsyncMock, return_value=mock_response):
        result = await compress_conversation_history(messages, AsyncMock(), max_messages=12)

    # Last message should be the most recent assistant reply
    assert result[-1]["content"] == "闂傚倷鐒﹂幃鍫曞磿閹惰棄纾绘繛鎴旀嚍?19"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_conversation_compression.py -v`
Expected: FAIL 闂?`ImportError: cannot import name 'compress_conversation_history'`

- [ ] **Step 3: Add compress_conversation_history to context_compressor.py**

Append to `app/services/context_compressor.py`:

```python
from app.agent.llm_client import chat_completion as _chat_completion

_SUMMARIZE_PROMPT = """闂備浇宕垫慨鏉懨洪鈶哄骞樼拠鍙夌€?-3闂傚倷绀侀幉锟犳偡閿濆纾块柟缁㈠枟閸庡﹤霉閻樺樊鍎忕紒鐘冲灴閺屻倖鎱ㄩ幇顑藉亾濡も偓閳绘棃濮€閻樺棗缍婇幃鈺咁敊閻撳骸顫掔紓鍌欑劍椤ㄥ懘骞婇幇鏉跨劦妞ゆ帒鍊归弳鈺傘亜閵忕媴韬柟顖欑劍缁傛帞鈧綆浜為ˇ銊╂⒑閸涘﹣绶遍柛娆忛叄瀹曨垶宕堕浣哄帾闂佺硶鍓濋〃鍛村焵椤掆偓濞尖€崇暦閹惰棄绠瑰ù锝囨嚀閳ь剛鍏樺娲敃閿濆洢鈧帞绱掗悩杈╃煓闁哄矉缍侀弫鎰板幢濞嗘劕娈忕紓鍌欑瑜板宕￠幎钘夌畺濞寸姴顑呮儫闂佹寧娲嶉崑鎾绘煟閹惧瓨绀嬮柡灞剧〒閳ь剨缍嗛崑鍡涙偂椤栨粎纾奸柕濞垮灩婢ц尙绱掗崒娑樻诞闁糕斁鍋撳銈嗗笂閼冲爼鍩㈤弴銏＄厱妞ゆ劑鍊曢弸鎴︽煙椤栨稓鎳冮棁澶愭煥濠靛棙顥滄繛鍫㈠█閺屽秷顧侀柛蹇旂洴閹虫宕奸弴鐐典紜濠碘槅鍨伴崥瀣垔婵傚憡鐓忛柛顐ｇ箓椤忣偊鏌涢悢鍑ゅ伐闂囧鏌ｅ鍡椾簻濞存粎鍋撶换娑㈠箣閻愬鍙嗛梺缁橆殔鐎氫即宕洪埀顒併亜閹寸偛顕滅紒浣峰嵆閺屾洟宕卞Δ鈧弳鐐寸箾閻撳海绠荤€规洩缍佹俊鐤槻闁哄應鏅滅换娑氣偓鐢殿焾琚ラ梺绋款儐閹告悂鍩ユ径鎰閻犳亽鍔岄。鐑樼箾鐎涙鐭婇柟璇х磿缂傛捇鎳為妷锕€寮块梺纭呭焽閸斿本绂?""


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
        summary = response.get("content", "闂傚倷鐒︾€笛呯矙閹达附鍋嬪┑鐘蹭迹濞戙埄鏁囬柕蹇曞Т閻濇﹢姊虹紒妯荤叆妞ゃ劌閰ｅ畷鐢告偐缂佹ê浠梺鎼炲劘閸斿海绮婚弽顓熺厵闁圭粯甯為敍宥夋煙閼碱剙顣奸柟宄版噺椤︾増鎯旈敐鍡楁灀闂傚倷绀侀幉锟犳偡椤栫偛鍨傞柟鎯版閺嬩線鏌曢崼婵愭Ч闁?)
    except Exception:
        summary = "闂傚倷鐒︾€笛呯矙閹达附鍋嬪┑鐘蹭迹濞戙埄鏁囬柕蹇曞Т閻濇﹢姊虹紒妯荤叆妞ゃ劌閰ｅ畷鐢告偐缂佹ê浠梺鎼炲劘閸斿海绮婚弽顓熺厵闁圭粯甯為敍宥夋煙閼碱剙顣奸柟宄版嚇閹粌螣缂佹﹩浠ч梻鍌欒兌閹虫捇鎮洪妸鈺佺闁哄洢鍨规闂佺懓顕慨鐢碘偓姘煼閺屾洘寰勫Ο铏逛化缂備讲鍋?

    summary_msg = {
        "role": "user",
        "content": f"[婵犵數鍋為崹鍫曞蓟閵娾晩鏁勯柛娑卞枟濞呯娀鏌ｅΟ鑲╁笡闁稿骸绉归弻娑㈠即閵娿儰鑸梺鎼炲€楁繛鈧柟顔肩秺瀹曞爼濡歌閻ｆ椽姊虹憴鍕祷缁剧虎鍙冮獮澶愭偋閸懇鏋?{summary}",
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

### Task 10: Update AGENTS.md 闂?Mark Plan 4 Progress

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update progress in AGENTS.md**

Update the Plan 4 line and current status:

```markdown
- [ ] Plan 4: Memory + 婵犵數鍋為崹鍫曞箰閹间焦鏅濋柨婵嗘川缁犳棃鏌涘☉娆愮稇婵☆偅锕㈤弻娑㈠Ψ閵忊剝鐝﹂梺鍛婂焹閸嬫捇姊绘担钘夊惞闁稿绋戣灋閻庨潧鎲￠～?0 婵?task闂?```

Update "闂佽崵鍠愮划搴㈡櫠濡ゅ懎绠伴柛娑橈攻濞呯娀鏌ｅΟ鐑樷枙婵為棿鍗抽弻銊モ攽閸℃ê娅ら梻濠庡墻閸撶喖寮婚悢铏圭當婵炴垶蓱閿涘秹鏌￠埀? to reflect Plan 4 completion.

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md with Plan 4 completion status"
```
