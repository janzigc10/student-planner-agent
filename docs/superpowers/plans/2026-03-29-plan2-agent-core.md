# Plan 2: Agent 核心 — LLM Loop + 工具集 + Agent.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Agent core — the LLM-in-a-loop engine that receives user messages, calls tools, and returns responses. This is the product's brain.

**Architecture:** OpenAI-compatible LLM client with function calling. Agent loop runs tool calls sequentially, logs each step, and streams responses via WebSocket. Tools are thin wrappers around Plan 1's CRUD APIs and calendar service. Agent.md file defines all behavior rules.

**Tech Stack:** openai Python SDK (compatible with DeepSeek/Qwen/GLM), WebSocket (FastAPI), Agent.md (markdown)

**Depends on:** Plan 1 (all models, CRUD APIs, calendar service must be complete)

---

## File Structure

```
student-planner/
├── Agent.md                          # Agent behavior rules (static, version-controlled)
├── app/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py                   # Core agent loop (plan & execute)
│   │   ├── llm_client.py            # OpenAI-compatible LLM client (provider-switchable)
│   │   ├── tools.py                  # Tool definitions (JSON schemas for function calling)
│   │   ├── tool_executor.py          # Tool execution dispatcher
│   │   ├── context.py                # Dynamic context builder (time, schedule, preferences)
│   │   └── guardrails.py            # Safety checks (consecutive ask_user, max retries)
│   ├── routers/
│   │   └── chat.py                   # WebSocket chat endpoint
│   └── config.py                     # (modify: add LLM config fields)
├── tests/
│   ├── test_agent_loop.py            # Agent loop integration tests
│   ├── test_tools.py                 # Tool execution tests
│   ├── test_context.py               # Context builder tests
│   └── test_chat_ws.py               # WebSocket endpoint tests
```

---

### Task 1: LLM Client (Provider-Switchable)

**Files:**
- Create: `student-planner/app/agent/__init__.py`
- Create: `student-planner/app/agent/llm_client.py`
- Modify: `student-planner/app/config.py`
- Create: `student-planner/tests/test_llm_client.py`

- [x] **Step 1: Add LLM config fields**

Add to `app/config.py` Settings class:
```python
    # LLM settings
    llm_api_key: str = "sk-placeholder"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
```

- [x] **Step 2: Write LLM client**

```python
# app/agent/llm_client.py
from typing import Any

from openai import AsyncOpenAI

from app.config import settings


def create_llm_client() -> AsyncOpenAI:
    """Create an OpenAI-compatible async client. Works with DeepSeek, Qwen, GLM, etc."""
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


async def chat_completion(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call LLM with messages and optional tool definitions.

    Returns the raw response message dict with 'content' and/or 'tool_calls'.
    """
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    response = await client.chat.completions.create(**kwargs)
    msg = response.choices[0].message

    result: dict[str, Any] = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return result
```

- [x] **Step 3: Write test (mocked LLM)**

```python
# tests/test_llm_client.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.llm_client import chat_completion, create_llm_client


@pytest.mark.asyncio
async def test_chat_completion_text_response():
    mock_msg = MagicMock()
    mock_msg.content = "你好！有什么可以帮你的？"
    mock_msg.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await chat_completion(mock_client, [{"role": "user", "content": "你好"}])
    assert result["role"] == "assistant"
    assert result["content"] == "你好！有什么可以帮你的？"
    assert "tool_calls" not in result


@pytest.mark.asyncio
async def test_chat_completion_tool_call():
    mock_tc = MagicMock()
    mock_tc.id = "call_123"
    mock_tc.function.name = "list_courses"
    mock_tc.function.arguments = "{}"

    mock_msg = MagicMock()
    mock_msg.content = None
    mock_msg.tool_calls = [mock_tc]

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await chat_completion(
        mock_client,
        [{"role": "user", "content": "我有什么课"}],
        tools=[{"type": "function", "function": {"name": "list_courses"}}],
    )
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "list_courses"
```

- [x] **Step 4: Run tests**

Run: `cd student-planner && pip install openai && pytest tests/test_llm_client.py -v`
Expected: All 2 tests PASS

- [x] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: OpenAI-compatible LLM client with provider switching"
```

---

### Task 2: Tool Definitions (JSON Schemas)

**Files:**
- Create: `student-planner/app/agent/tools.py`

- [x] **Step 1: Write tool definitions**

These are the JSON schemas that tell the LLM what tools are available and how to call them.

```python
# app/agent/tools.py
"""Tool definitions for LLM function calling.

Each tool is a dict matching the OpenAI tools format:
{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
"""

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_courses",
            "description": "查看用户当前的所有课程。返回课程列表，包含课程名、教师、地点、时间、周次。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_course",
            "description": "添加一门课程到用户课表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "课程名称"},
                    "teacher": {"type": "string", "description": "教师姓名"},
                    "location": {"type": "string", "description": "上课地点"},
                    "weekday": {"type": "integer", "description": "周几上课，1=周一，7=周日", "minimum": 1, "maximum": 7},
                    "start_time": {"type": "string", "description": "开始时间，格式 HH:MM", "pattern": "^\\d{2}:\\d{2}$"},
                    "end_time": {"type": "string", "description": "结束时间，格式 HH:MM", "pattern": "^\\d{2}:\\d{2}$"},
                    "week_start": {"type": "integer", "description": "开始周次", "default": 1},
                    "week_end": {"type": "integer", "description": "结束周次", "default": 16},
                },
                "required": ["name", "weekday", "start_time", "end_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_course",
            "description": "删除一门课程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "课程ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_free_slots",
            "description": "查询指定日期范围内用户的空闲时间段。返回每天的空闲时段列表，精确到分钟。已排除课程和已安排的任务。在安排任何新任务之前必须先调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
                    "min_duration_minutes": {"type": "integer", "description": "最短有效时段（分钟），默认30", "default": 30},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_study_plan",
            "description": "根据考试列表和可用时间，生成复习计划。返回结构化的任务列表。必须先调用 get_free_slots 获取可用时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "exams": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "course_name": {"type": "string"},
                                "exam_date": {"type": "string", "description": "格式 YYYY-MM-DD"},
                                "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                            },
                            "required": ["course_name", "exam_date"],
                        },
                        "description": "考试列表",
                    },
                    "available_slots": {"type": "object", "description": "get_free_slots 的返回结果"},
                    "strategy": {
                        "type": "string",
                        "enum": ["balanced", "intensive", "spaced"],
                        "description": "复习策略：balanced=均衡, intensive=考前密集, spaced=间隔重复",
                        "default": "balanced",
                    },
                },
                "required": ["exams", "available_slots"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "查看指定日期范围内的任务列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "开始日期，格式 YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "结束日期，格式 YYYY-MM-DD"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "修改一个已有的任务（时间、标题、状态等）。修改时间前应先用 get_free_slots 检查目标时段是否空闲。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "scheduled_date": {"type": "string", "description": "格式 YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "格式 HH:MM"},
                    "end_time": {"type": "string", "description": "格式 HH:MM"},
                    "status": {"type": "string", "enum": ["pending", "completed", "skipped"]},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "标记一个任务为已完成。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "为课程或任务设置提醒。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_type": {"type": "string", "enum": ["course", "task"]},
                    "target_id": {"type": "string", "description": "课程或任务的ID"},
                    "advance_minutes": {"type": "integer", "description": "提前多少分钟提醒", "default": 15},
                },
                "required": ["target_type", "target_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "查看用户的所有提醒。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "向用户展示信息并请求确认或选择。用于关键操作前的确认。不要连续调用两次 ask_user，中间至少做一步实际操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要问用户的问题"},
                    "type": {"type": "string", "enum": ["confirm", "select", "review"], "description": "confirm=是否确认, select=从选项中选, review=展示计划请求确认"},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "选项列表（select类型时必填）"},
                    "data": {"type": "object", "description": "需要展示给用户的结构化数据"},
                },
                "required": ["question", "type"],
            },
        },
    },
]
```

- [x] **Step 2: Verify tool definitions are valid JSON schema**

```python
# Quick validation — run as script
# tests/test_tools_schema.py
import json

from app.agent.tools import TOOL_DEFINITIONS


def test_tool_definitions_valid():
    """All tool definitions must have required fields."""
    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        func = tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        # Ensure parameters is valid JSON schema
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_tool_names_unique():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))


def test_expected_tools_present():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    expected = {
        "list_courses", "add_course", "delete_course",
        "get_free_slots", "create_study_plan",
        "list_tasks", "update_task", "complete_task",
        "set_reminder", "list_reminders",
        "ask_user",
    }
    assert expected.issubset(names)
```

- [x] **Step 3: Run tests**

Run: `cd student-planner && pytest tests/test_tools_schema.py -v`
Expected: All 3 tests PASS

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: tool definitions for LLM function calling"
```

---

### Task 3: Tool Executor

The executor maps tool names to actual Python functions that call Plan 1's CRUD APIs/services.

**Files:**
- Create: `student-planner/app/agent/tool_executor.py`
- Create: `student-planner/tests/test_tool_executor.py`

- [x] **Step 1: Write tool executor**

```python
# app/agent/tool_executor.py
import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.exam import Exam
from app.models.reminder import Reminder
from app.models.task import Task
from app.services.calendar import TimeSlot, compute_free_slots

# Maps tool name -> handler function
# Each handler takes (db: AsyncSession, user_id: str, **kwargs) and returns a dict


async def execute_tool(
    tool_name: str, arguments: dict[str, Any], db: AsyncSession, user_id: str
) -> dict[str, Any]:
    """Dispatch a tool call to the appropriate handler. Returns result dict."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await handler(db=db, user_id=user_id, **arguments)
    except Exception as e:
        return {"error": str(e)}


async def _list_courses(db: AsyncSession, user_id: str, **kwargs) -> dict:
    result = await db.execute(select(Course).where(Course.user_id == user_id))
    courses = result.scalars().all()
    return {
        "courses": [
            {
                "id": c.id, "name": c.name, "teacher": c.teacher,
                "location": c.location, "weekday": c.weekday,
                "start_time": c.start_time, "end_time": c.end_time,
                "week_start": c.week_start, "week_end": c.week_end,
            }
            for c in courses
        ],
        "count": len(courses),
    }


async def _add_course(db: AsyncSession, user_id: str, **kwargs) -> dict:
    course = Course(user_id=user_id, **kwargs)
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return {"id": course.id, "name": course.name, "status": "created"}


async def _delete_course(db: AsyncSession, user_id: str, course_id: str, **kwargs) -> dict:
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    course = result.scalar_one_or_none()
    if not course:
        return {"error": "Course not found"}
    await db.delete(course)
    await db.commit()
    return {"status": "deleted", "name": course.name}


async def _get_free_slots(
    db: AsyncSession, user_id: str,
    start_date: str, end_date: str, min_duration_minutes: int = 30, **kwargs,
) -> dict:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    days = []
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    current = start
    while current <= end:
        wd = current.isoweekday()  # 1=Monday

        # Get courses for this weekday
        course_result = await db.execute(
            select(Course).where(Course.user_id == user_id, Course.weekday == wd)
        )
        courses = course_result.scalars().all()

        # Get tasks for this date
        date_str = current.isoformat()
        task_result = await db.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.scheduled_date == date_str,
                Task.status != "skipped",
            )
        )
        tasks = task_result.scalars().all()

        occupied = []
        for c in courses:
            occupied.append(TimeSlot(start=c.start_time, end=c.end_time, type="course", name=c.name))
        for t in tasks:
            occupied.append(TimeSlot(start=t.start_time, end=t.end_time, type="task", name=t.title))

        free = compute_free_slots(occupied, min_duration_minutes=min_duration_minutes)

        days.append({
            "date": date_str,
            "weekday": weekday_names[wd - 1],
            "free_periods": [{"start": s.start, "end": s.end, "duration_minutes": s.duration_minutes} for s in free],
            "occupied": [{"start": o.start, "end": o.end, "type": o.type, "name": o.name} for o in occupied],
        })
        current += timedelta(days=1)

    total_free = sum(
        slot["duration_minutes"]
        for day in days
        for slot in day["free_periods"]
    )
    return {
        "slots": days,
        "summary": f"{start_date} 至 {end_date} 共 {sum(len(d['free_periods']) for d in days)} 个空闲段，总计 {total_free // 60} 小时 {total_free % 60} 分钟",
    }


async def _list_tasks(
    db: AsyncSession, user_id: str,
    date_from: str | None = None, date_to: str | None = None, **kwargs,
) -> dict:
    query = select(Task).where(Task.user_id == user_id)
    if date_from:
        query = query.where(Task.scheduled_date >= date_from)
    if date_to:
        query = query.where(Task.scheduled_date <= date_to)
    query = query.order_by(Task.scheduled_date, Task.start_time)
    result = await db.execute(query)
    tasks = result.scalars().all()
    return {
        "tasks": [
            {
                "id": t.id, "title": t.title, "description": t.description,
                "scheduled_date": t.scheduled_date,
                "start_time": t.start_time, "end_time": t.end_time,
                "status": t.status,
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


async def _update_task(db: AsyncSession, user_id: str, task_id: str, **kwargs) -> dict:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": "Task not found"}
    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    return {"id": task.id, "title": task.title, "status": "updated"}


async def _complete_task(db: AsyncSession, user_id: str, task_id: str, **kwargs) -> dict:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": "Task not found"}
    task.status = "completed"
    await db.commit()
    return {"id": task.id, "title": task.title, "status": "completed"}


async def _set_reminder(
    db: AsyncSession, user_id: str,
    target_type: str, target_id: str, advance_minutes: int = 15, **kwargs,
) -> dict:
    # Calculate remind_at based on target
    if target_type == "course":
        result = await db.execute(select(Course).where(Course.id == target_id))
        target = result.scalar_one_or_none()
        if not target:
            return {"error": "Course not found"}
        # For courses, remind_at is relative — stored as a pattern, actual scheduling done by APScheduler (Plan 5)
        remind_at = f"course:{target_id}:-{advance_minutes}min"
    else:
        result = await db.execute(select(Task).where(Task.id == target_id))
        target = result.scalar_one_or_none()
        if not target:
            return {"error": "Task not found"}
        remind_at = f"{target.scheduled_date}T{target.start_time}:00"

    reminder = Reminder(
        user_id=user_id, target_type=target_type,
        target_id=target_id, remind_at=remind_at,
    )
    db.add(reminder)
    await db.commit()
    return {"id": reminder.id, "status": "reminder_set", "remind_at": remind_at}


async def _list_reminders(db: AsyncSession, user_id: str, **kwargs) -> dict:
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at)
    )
    reminders = result.scalars().all()
    return {
        "reminders": [
            {"id": r.id, "target_type": r.target_type, "target_id": r.target_id, "remind_at": r.remind_at, "status": r.status}
            for r in reminders
        ],
        "count": len(reminders),
    }


async def _ask_user(question: str, type: str = "confirm", **kwargs) -> dict:
    """Special tool — returns the question to be sent to the user. The agent loop handles the actual user interaction."""
    return {
        "action": "ask_user",
        "question": question,
        "type": type,
        "options": kwargs.get("options"),
        "data": kwargs.get("data"),
    }


TOOL_HANDLERS = {
    "list_courses": _list_courses,
    "add_course": _add_course,
    "delete_course": _delete_course,
    "get_free_slots": _get_free_slots,
    "list_tasks": _list_tasks,
    "update_task": _update_task,
    "complete_task": _complete_task,
    "set_reminder": _set_reminder,
    "list_reminders": _list_reminders,
    "ask_user": _ask_user,
    "create_study_plan": None,  # Placeholder — implemented in Task 5 (uses LLM internally)
}
```

- [x] **Step 2: Write executor tests**

```python
# tests/test_tool_executor.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_executor import execute_tool
from app.models.course import Course


@pytest.mark.asyncio
async def test_execute_unknown_tool(setup_db):
    """Unknown tool returns error."""
    async with TestSession() as db:
        result = await execute_tool("nonexistent_tool", {}, db, "user-1")
        assert "error" in result
        assert "Unknown tool" in result["error"]


@pytest.mark.asyncio
async def test_list_courses_empty(setup_db):
    async with TestSession() as db:
        result = await execute_tool("list_courses", {}, db, "user-1")
        assert result["count"] == 0
        assert result["courses"] == []


@pytest.mark.asyncio
async def test_add_and_list_course(setup_db):
    async with TestSession() as db:
        # Need a user first
        from app.models.user import User
        user = User(id="user-1", username="test", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool("add_course", {
            "name": "高等数学", "weekday": 1,
            "start_time": "08:00", "end_time": "09:40",
        }, db, "user-1")
        assert result["status"] == "created"

        result = await execute_tool("list_courses", {}, db, "user-1")
        assert result["count"] == 1
        assert result["courses"][0]["name"] == "高等数学"


@pytest.mark.asyncio
async def test_ask_user_returns_action(setup_db):
    async with TestSession() as db:
        result = await execute_tool("ask_user", {
            "question": "确认吗？", "type": "confirm",
        }, db, "user-1")
        assert result["action"] == "ask_user"
        assert result["question"] == "确认吗？"
```

Note: These tests need the same `TestSession` and `setup_db` fixtures from `conftest.py`. The test file should import them.

- [x] **Step 3: Run tests**

Run: `cd student-planner && pytest tests/test_tool_executor.py -v`
Expected: All 4 tests PASS

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: tool executor dispatching tool calls to CRUD handlers"
```

---

### Task 4: Dynamic Context Builder

Builds the dynamic portion of the system prompt — current time, today's schedule, user preferences.

**Files:**
- Create: `student-planner/app/agent/context.py`
- Create: `student-planner/tests/test_context.py`

- [ ] **Step 1: Write context builder**

```python
# app/agent/context.py
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.task import Task
from app.models.user import User

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


async def build_dynamic_context(user: User, db: AsyncSession) -> str:
    """Build the dynamic portion of the system prompt."""
    now = datetime.now(timezone.utc)
    today = now.date()
    wd = today.isoweekday()

    parts = []

    # Current time
    parts.append(f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}（{WEEKDAY_NAMES[wd - 1]}）")

    # Current semester week
    if user.current_semester_start:
        delta = (today - user.current_semester_start).days
        week_num = delta // 7 + 1
        parts.append(f"当前学期：第{week_num}周")

    # Today's courses
    course_result = await db.execute(
        select(Course).where(Course.user_id == user.id, Course.weekday == wd)
        .order_by(Course.start_time)
    )
    courses = course_result.scalars().all()

    # Today's tasks
    task_result = await db.execute(
        select(Task).where(Task.user_id == user.id, Task.scheduled_date == today.isoformat())
        .order_by(Task.start_time)
    )
    tasks = task_result.scalars().all()

    parts.append("\n今天的日程：")
    if not courses and not tasks:
        parts.append("- 无安排")
    else:
        for c in courses:
            loc = f" @ {c.location}" if c.location else ""
            parts.append(f"- {c.start_time}-{c.end_time} {c.name}{loc}（课程）")
        for t in tasks:
            status_mark = "✓" if t.status == "completed" else "○"
            parts.append(f"- {t.start_time}-{t.end_time} {t.title}（{status_mark}）")

    # User preferences
    prefs = user.preferences or {}
    if prefs:
        parts.append("\n用户偏好：")
        if "earliest_study" in prefs:
            parts.append(f"- 最早学习时间：{prefs['earliest_study']}")
        if "latest_study" in prefs:
            parts.append(f"- 最晚学习时间：{prefs['latest_study']}")
        if "lunch_break" in prefs:
            parts.append(f"- 午休：{prefs['lunch_break']}")
        if "min_slot_minutes" in prefs:
            parts.append(f"- 最短有效时段：{prefs['min_slot_minutes']}分钟")
        if "school_schedule" in prefs:
            parts.append("- 已配置作息时间表")

    return "\n".join(parts)
```

- [ ] **Step 2: Write context tests**

```python
# tests/test_context.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.context import build_dynamic_context


@pytest.mark.asyncio
async def test_context_includes_current_time(setup_db):
    user = MagicMock()
    user.id = "user-1"
    user.current_semester_start = None
    user.preferences = {}

    async with TestSession() as db:
        ctx = await build_dynamic_context(user, db)
        assert "当前时间" in ctx
        assert "今天的日程" in ctx


@pytest.mark.asyncio
async def test_context_includes_preferences(setup_db):
    user = MagicMock()
    user.id = "user-1"
    user.current_semester_start = None
    user.preferences = {"earliest_study": "08:00", "latest_study": "22:00"}

    async with TestSession() as db:
        ctx = await build_dynamic_context(user, db)
        assert "08:00" in ctx
        assert "22:00" in ctx
```

- [ ] **Step 3: Run tests**

Run: `cd student-planner && pytest tests/test_context.py -v`
Expected: All 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: dynamic context builder for system prompt"
```

---

### Task 5: Agent.md + System Prompt Assembly

**Files:**
- Create: `student-planner/Agent.md`
- Create: `student-planner/app/agent/prompt.py`

- [ ] **Step 1: Write Agent.md**

```markdown
# Agent.md — 学生时间规划助手

## 身份

你是一个大学生时间规划助手。你帮助用户管理课表、安排复习计划、设置提醒。

## 语言

- 与用户对话使用中文
- 保持简洁友好，像一个靠谱的学长/学姐

## 行为准则

### 硬性规则
- 任何写入操作（添加课程、创建任务、设置提醒）必须先用 ask_user 确认
- 时间必须精确到小时和分钟，不要用"上午/下午/晚上"这种模糊表达
- 不要编造课程信息、考试日期或教室地点
- 如果用户的请求信息不完整，用 ask_user 追问，不要自己猜
- 一次只做一件事，不要在一个循环里同时处理多个不相关的请求

### 工具使用
- get_free_slots：在安排任何新任务之前必须先调用，确认有空闲时段
- create_study_plan：必须先有 get_free_slots 的结果才能调用
- ask_user：不要连续调用两次，中间至少做一步实际操作
- 当课表中出现"第N节课"但用户未配置作息时间表时，必须先用 ask_user 追问作息时间

### 错误处理
- 工具调用失败时：告诉用户出了什么问题，不要静默重试超过2次
- 用户拒绝确认时：询问用户想怎么调整，不要重复提交同样的方案
- 时间冲突时：明确告诉用户哪些时段冲突了，提供替代方案

## 示例对话（Few-Shot）

### 示例1：添加考试 → 生成复习计划

用户: "4月5号有高数、线代、概率论三门考试"

→ ask_user 确认: "确认：4月5日有高等数学、线性代数、概率论三门考试？"
→ 用户确认 → get_free_slots("2026-03-30", "2026-04-04")
→ create_study_plan(exams=[...], available_slots=上一步结果, strategy="balanced")
→ ask_user(type="review"): 展示计划请求确认
→ 用户确认 → set_reminder(每个任务)

注意：如果用户说"第1-2节有高数"但没配置作息时间表，必须先 ask_user 追问"第1-2节是几点到几点"，拿到后存入偏好。

### 示例2：调整任务（含冲突处理）

用户: "把高数复习改到下午4点"

→ get_free_slots(当天) 检查 16:00 是否空闲
→ 空闲: update_task → ask_user 确认
→ 冲突: ask_user 告知冲突，提供选项（换时间/互换/取消）

只读查询（如"明天有什么课"）直接调 list_courses 后回复，不需要 ask_user。

## 时间解析规则

用户自然语言时间 → 精确日期（结合当前上下文中的日期）：
- "今天/明天/后天" → 当前日期 +0/+1/+2
- "下周三" → 计算具体日期
- "4.5号" → 2026-04-05
- "考试前一周" → exam_date - 7 到 exam_date - 1

解析后必须用 YYYY-MM-DD 格式传给工具。
```

- [ ] **Step 2: Write prompt assembly**

```python
# app/agent/prompt.py
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import build_dynamic_context
from app.models.user import User

AGENT_MD_PATH = Path(__file__).parent.parent.parent / "Agent.md"


def load_agent_md() -> str:
    """Load Agent.md static rules. Cached after first read."""
    return AGENT_MD_PATH.read_text(encoding="utf-8")


async def build_system_prompt(user: User, db: AsyncSession) -> str:
    """Assemble full system prompt = Agent.md + dynamic context."""
    agent_md = load_agent_md()
    dynamic_ctx = await build_dynamic_context(user, db)
    return f"{agent_md}\n\n---\n\n## 当前上下文\n\n{dynamic_ctx}"
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: Agent.md behavior rules and system prompt assembly"
```

---

### Task 6: Guardrails

Safety checks that run in the agent loop to prevent bad behavior.

**Files:**
- Create: `student-planner/app/agent/guardrails.py`
- Create: `student-planner/tests/test_guardrails.py`

- [ ] **Step 1: Write guardrails**

```python
# app/agent/guardrails.py


class GuardrailViolation(Exception):
    """Raised when a guardrail is violated."""
    def __init__(self, message: str, suggestion: str):
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


def check_consecutive_ask_user(tool_history: list[str]) -> None:
    """Prevent LLM from calling ask_user twice in a row without doing actual work."""
    if len(tool_history) >= 2 and tool_history[-1] == "ask_user" and tool_history[-2] == "ask_user":
        raise GuardrailViolation(
            message="不能连续两次调用 ask_user，中间需要执行一步实际操作。",
            suggestion="请先执行一个工具操作，然后再询问用户。",
        )


def check_max_loop_iterations(iteration: int, max_iterations: int = 20) -> None:
    """Prevent infinite loops."""
    if iteration >= max_iterations:
        raise GuardrailViolation(
            message=f"Agent loop 已执行 {iteration} 步，超过最大限制 {max_iterations}。",
            suggestion="任务可能过于复杂，请拆分成更小的请求。",
        )


def check_unknown_tool(tool_name: str, known_tools: set[str]) -> None:
    """Prevent LLM from calling non-existent tools."""
    if tool_name not in known_tools:
        raise GuardrailViolation(
            message=f"工具 '{tool_name}' 不存在。",
            suggestion=f"可用的工具有：{', '.join(sorted(known_tools))}",
        )


def check_max_retries(tool_name: str, error_count: dict[str, int], max_retries: int = 2) -> None:
    """Prevent retrying the same failed tool more than max_retries times."""
    if error_count.get(tool_name, 0) >= max_retries:
        raise GuardrailViolation(
            message=f"工具 '{tool_name}' 已失败 {max_retries} 次。",
            suggestion="请告诉用户出了问题，不要继续重试。",
        )
```

- [ ] **Step 2: Write guardrail tests**

```python
# tests/test_guardrails.py
import pytest

from app.agent.guardrails import (
    GuardrailViolation,
    check_consecutive_ask_user,
    check_max_loop_iterations,
    check_max_retries,
    check_unknown_tool,
)


def test_consecutive_ask_user_violation():
    with pytest.raises(GuardrailViolation):
        check_consecutive_ask_user(["ask_user", "ask_user"])


def test_consecutive_ask_user_ok():
    check_consecutive_ask_user(["list_courses", "ask_user"])  # No exception
    check_consecutive_ask_user(["ask_user", "list_courses"])  # No exception


def test_max_iterations():
    with pytest.raises(GuardrailViolation):
        check_max_loop_iterations(20, max_iterations=20)
    check_max_loop_iterations(19, max_iterations=20)  # No exception


def test_unknown_tool():
    with pytest.raises(GuardrailViolation):
        check_unknown_tool("hack_system", {"list_courses", "ask_user"})
    check_unknown_tool("list_courses", {"list_courses", "ask_user"})  # No exception


def test_max_retries():
    errors = {"list_courses": 2}
    with pytest.raises(GuardrailViolation):
        check_max_retries("list_courses", errors, max_retries=2)
    check_max_retries("list_courses", {"list_courses": 1}, max_retries=2)  # No exception
```

- [ ] **Step 3: Run tests**

Run: `cd student-planner && pytest tests/test_guardrails.py -v`
Expected: All 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: agent guardrails — consecutive ask_user, max iterations, retries"
```

---

### Task 7: Agent Loop (Core Engine)

The heart of the product. Receives a user message, runs the LLM-in-a-loop, returns the final response.

**Files:**
- Create: `student-planner/app/agent/loop.py`
- Create: `student-planner/tests/test_agent_loop.py`

- [ ] **Step 1: Write agent loop**

```python
# app/agent/loop.py
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.guardrails import (
    GuardrailViolation,
    check_consecutive_ask_user,
    check_max_loop_iterations,
    check_max_retries,
    check_unknown_tool,
)
from app.agent.llm_client import AsyncOpenAI, chat_completion
from app.agent.prompt import build_system_prompt
from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.agent_log import AgentLog
from app.models.conversation_message import ConversationMessage
from app.models.user import User

KNOWN_TOOLS = {t["function"]["name"] for t in TOOL_DEFINITIONS}
MAX_ITERATIONS = 20


async def run_agent_loop(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
    llm_client: AsyncOpenAI,
) -> AsyncGenerator[dict[str, Any], str | None]:
    """Run the agent loop. Yields events for the frontend.

    Event types:
    - {"type": "text", "content": "..."} — agent text response
    - {"type": "tool_call", "name": "...", "args": {...}} — tool being called
    - {"type": "tool_result", "name": "...", "result": {...}} — tool result
    - {"type": "ask_user", "question": "...", ...} — needs user input
    - {"type": "error", "message": "..."} — error
    - {"type": "done"} — loop finished

    When ask_user is yielded, the caller should send() the user's response back.
    """
    # Build system prompt
    system_prompt = await build_system_prompt(user, db)

    # Load conversation history for this session
    history_result = await db.execute(
        ConversationMessage.__table__.select()
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.timestamp)
    )
    history_rows = history_result.fetchall()

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for row in history_rows:
        messages.append({"role": row.role, "content": row.content})

    # Add current user message
    messages.append({"role": "user", "content": user_message})
    await _save_message(db, session_id, "user", user_message)

    tool_history: list[str] = []
    error_count: dict[str, int] = {}
    step = 0

    for iteration in range(MAX_ITERATIONS):
        check_max_loop_iterations(iteration, MAX_ITERATIONS)

        # Call LLM
        response = await chat_completion(llm_client, messages, tools=TOOL_DEFINITIONS)

        # If LLM returns text (no tool calls), we're done
        if "tool_calls" not in response:
            text = response.get("content", "")
            if text:
                yield {"type": "text", "content": text}
                await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return

        # Process tool calls
        messages.append(response)  # Add assistant message with tool_calls

        for tc in response["tool_calls"]:
            tool_name = tc["function"]["name"]
            tool_args_str = tc["function"]["arguments"]
            tool_call_id = tc["id"]

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            # Guardrails
            try:
                check_unknown_tool(tool_name, KNOWN_TOOLS)
                check_consecutive_ask_user(tool_history)
                check_max_retries(tool_name, error_count)
            except GuardrailViolation as e:
                tool_result = {"error": e.message, "suggestion": e.suggestion}
                messages.append({
                    "role": "tool", "tool_call_id": tool_call_id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })
                yield {"type": "error", "message": e.message}
                continue

            yield {"type": "tool_call", "name": tool_name, "args": tool_args}

            # Execute tool
            if tool_name == "ask_user":
                # Special handling: yield to frontend, wait for user response
                result = await execute_tool(tool_name, tool_args, db, user.id)
                yield {"type": "ask_user", **result}

                # The caller sends the user's response back via generator.send()
                user_response = yield  # Wait for user input
                if user_response is None:
                    user_response = "确认"

                tool_result_content = json.dumps(
                    {"user_response": user_response}, ensure_ascii=False
                )
            else:
                result = await execute_tool(tool_name, tool_args, db, user.id)
                tool_result_content = json.dumps(result, ensure_ascii=False)

                if "error" in result:
                    error_count[tool_name] = error_count.get(tool_name, 0) + 1

                yield {"type": "tool_result", "name": tool_name, "result": result}

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_result_content,
            })

            # Log step
            step += 1
            tool_history.append(tool_name)
            await _log_step(db, user.id, session_id, step, tool_name, tool_args, result)

    yield {"type": "error", "message": "Agent loop 达到最大迭代次数"}
    yield {"type": "done"}


async def _save_message(db: AsyncSession, session_id: str, role: str, content: str):
    msg = ConversationMessage(session_id=session_id, role=role, content=content)
    db.add(msg)
    await db.commit()


async def _log_step(
    db: AsyncSession, user_id: str, session_id: str,
    step: int, tool_name: str, tool_args: dict, tool_result: dict,
):
    log = AgentLog(
        user_id=user_id, session_id=session_id, step=step,
        tool_called=tool_name, tool_args=tool_args, tool_result=tool_result,
    )
    db.add(log)
    await db.commit()
```

- [ ] **Step 2: Write agent loop test (mocked LLM)**

```python
# tests/test_agent_loop.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.loop import run_agent_loop
from app.models.user import User


@pytest.mark.asyncio
async def test_simple_text_response(setup_db):
    """LLM returns text without tool calls — loop ends immediately."""
    mock_client = AsyncMock()

    # LLM returns a simple text response
    with patch("app.agent.loop.chat_completion") as mock_cc:
        mock_cc.return_value = {"role": "assistant", "content": "你好！有什么可以帮你的？"}

        async with TestSession() as db:
            user = User(id="u1", username="test", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            gen = run_agent_loop("你好", user, "session-1", db, mock_client)
            async for event in gen:
                events.append(event)

            assert any(e["type"] == "text" for e in events)
            assert any(e["type"] == "done" for e in events)
            text_event = next(e for e in events if e["type"] == "text")
            assert "你好" in text_event["content"]


@pytest.mark.asyncio
async def test_tool_call_then_text(setup_db):
    """LLM calls a tool, gets result, then responds with text."""
    mock_client = AsyncMock()

    call_count = 0

    async def mock_cc(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: LLM wants to call list_courses
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "list_courses", "arguments": "{}"},
                }],
            }
        else:
            # Second call: LLM responds with text
            return {"role": "assistant", "content": "你目前没有课程。"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_cc):
        async with TestSession() as db:
            user = User(id="u2", username="test2", hashed_password="x")
            db.add(user)
            await db.commit()

            events = []
            gen = run_agent_loop("我有什么课", user, "session-2", db, mock_client)
            async for event in gen:
                events.append(event)

            types = [e["type"] for e in events]
            assert "tool_call" in types
            assert "tool_result" in types
            assert "text" in types
            assert "done" in types
```

- [ ] **Step 3: Run tests**

Run: `cd student-planner && pytest tests/test_agent_loop.py -v`
Expected: All 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: agent loop core engine with tool execution and guardrails"
```

---

### Task 8: WebSocket Chat Endpoint

Connects the agent loop to the frontend via WebSocket.

**Files:**
- Create: `student-planner/app/routers/chat.py`
- Modify: `student-planner/app/main.py`
- Create: `student-planner/tests/test_chat_ws.py`

- [ ] **Step 1: Write WebSocket chat endpoint**

```python
# app/routers/chat.py
import json
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_client import create_llm_client
from app.agent.loop import run_agent_loop
from app.auth.jwt import verify_token
from app.database import get_db
from app.models.user import User
from sqlalchemy import select

router = APIRouter(tags=["chat"])


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()

    # Authenticate via first message
    try:
        auth_msg = await websocket.receive_json()
        token = auth_msg.get("token")
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

    # Create session
    session_id = str(uuid.uuid4())
    llm_client = create_llm_client()

    await websocket.send_json({"type": "connected", "session_id": session_id})

    # Message loop
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            if not user_message:
                continue

            # Get fresh DB session and user for each message
            async for db in get_db():
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if not user:
                    await websocket.send_json({"type": "error", "message": "User not found"})
                    break

                # Run agent loop
                gen = run_agent_loop(user_message, user, session_id, db, llm_client)
                try:
                    event = await gen.__anext__()
                    while True:
                        await websocket.send_json(event)

                        if event["type"] == "ask_user":
                            # Wait for user response
                            user_resp = await websocket.receive_json()
                            user_answer = user_resp.get("answer", "确认")
                            event = await gen.asend(user_answer)
                        elif event["type"] == "done":
                            break
                        else:
                            event = await gen.__anext__()
                except StopAsyncIteration:
                    pass

    except WebSocketDisconnect:
        pass
```

- [ ] **Step 2: Mount chat router in main.py**

Add to `app/main.py` `create_app()`:
```python
from app.routers import auth, courses, exams, tasks, reminders, chat

app.include_router(chat.router)
```

- [ ] **Step 3: Write WebSocket test**

```python
# tests/test_chat_ws.py
import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_ws_auth_required(client: AsyncClient):
    """WebSocket without auth should be rejected."""
    from app.main import create_app
    from app.database import get_db

    app = create_app()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # We can't easily test WebSocket with httpx, so just verify the endpoint exists
    # Full WebSocket testing would use websockets library or starlette.testclient
    # For now, verify the route is registered
    routes = [r.path for r in app.routes]
    assert "/ws/chat" in routes
```

- [ ] **Step 4: Run all tests**

Run: `cd student-planner && pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: WebSocket chat endpoint connecting frontend to agent loop"
```

---

### Task 9: create_study_plan Tool Implementation

This tool uses LLM internally to generate study plans. It's the most complex tool.

**Files:**
- Create: `student-planner/app/agent/study_planner.py`
- Modify: `student-planner/app/agent/tool_executor.py` (wire up create_study_plan)
- Create: `student-planner/tests/test_study_planner.py`

- [ ] **Step 1: Write study planner**

```python
# app/agent/study_planner.py
import json
from typing import Any

from app.agent.llm_client import AsyncOpenAI, chat_completion, create_llm_client

PLAN_PROMPT = """你是一个复习计划生成器。根据以下信息生成复习计划：

考试列表：
{exams}

可用时间段：
{slots}

复习策略：{strategy}
- balanced：每门课均匀分配时间
- intensive：考前几天集中复习
- spaced：间隔重复，越早开始越好

要求：
1. 每个任务必须在一个空闲时段内，不能跨时段
2. 难度高的课程分配更多时间
3. 同一门课的复习任务不要连续安排（除非时间不够）
4. 每个任务的时长在 1-2 小时之间
5. 任务标题格式："课程名 - 具体内容"
6. description 要具体，写清楚复习哪些章节/知识点

示例输入：
考试：高等数学(4月5日, hard), 线性代数(4月5日, medium)
空闲：3月30日 10:00-12:00, 14:00-17:00; 3月31日 10:00-12:00, 14:00-16:00
策略：balanced

示例输出：
[
  {{
    "title": "高数 - 极限与连续",
    "exam_name": "高等数学",
    "date": "2026-03-30",
    "start_time": "10:00",
    "end_time": "12:00",
    "description": "复习第1-3章：极限定义、夹逼定理、连续性判断、间断点分类"
  }},
  {{
    "title": "线代 - 行列式与矩阵",
    "exam_name": "线性代数",
    "date": "2026-03-30",
    "start_time": "14:00",
    "end_time": "16:00",
    "description": "复习第1-2章：行列式计算、矩阵运算、逆矩阵求法"
  }},
  {{
    "title": "高数 - 微分与积分",
    "exam_name": "高等数学",
    "date": "2026-03-30",
    "start_time": "16:00",
    "end_time": "17:00",
    "description": "复习第4-5章：导数计算、微分中值定理、不定积分基本方法"
  }},
  {{
    "title": "线代 - 向量与线性方程组",
    "exam_name": "线性代数",
    "date": "2026-03-31",
    "start_time": "10:00",
    "end_time": "12:00",
    "description": "复习第3-4章：向量空间、线性相关性、齐次/非齐次方程组求解"
  }},
  {{
    "title": "高数 - 综合练习",
    "exam_name": "高等数学",
    "date": "2026-03-31",
    "start_time": "14:00",
    "end_time": "16:00",
    "description": "做2套历年真题，重点关注计算题和证明题"
  }}
]

注意示例中的特点：
- 高数(hard)分配了3个时段，线代(medium)分配了2个时段 — 难度高的课更多时间
- 高数和线代交替安排，没有连续复习同一门课
- 最后一个任务是综合练习，不只是看书
- description 具体到章节和知识点

输出格式（严格 JSON）：
[
  {{
    "title": "课程名 - 具体内容",
    "exam_name": "课程全名",
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM",
    "end_time": "HH:MM",
    "description": "具体复习内容，包含章节和知识点"
  }}
]

只输出 JSON 数组，不要输出其他内容。"""


async def generate_study_plan(
    exams: list[dict[str, Any]],
    available_slots: dict[str, Any],
    strategy: str = "balanced",
    llm_client: AsyncOpenAI | None = None,
) -> list[dict[str, Any]]:
    """Use LLM to generate a study plan. Returns list of task dicts."""
    if llm_client is None:
        llm_client = create_llm_client()

    prompt = PLAN_PROMPT.format(
        exams=json.dumps(exams, ensure_ascii=False, indent=2),
        slots=json.dumps(available_slots, ensure_ascii=False, indent=2),
        strategy=strategy,
    )

    response = await chat_completion(
        llm_client,
        [{"role": "user", "content": prompt}],
    )

    content = response.get("content", "")

    # Parse JSON from response (handle markdown code blocks)
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        tasks = json.loads(content)
        if not isinstance(tasks, list):
            return []
        return tasks
    except json.JSONDecodeError:
        return []
```

- [ ] **Step 2: Wire up in tool_executor.py**

Replace the `create_study_plan: None` line in `TOOL_HANDLERS`:

```python
# In app/agent/tool_executor.py, add import at top:
from app.agent.study_planner import generate_study_plan

# Add handler function:
async def _create_study_plan(
    db: AsyncSession, user_id: str,
    exams: list, available_slots: dict, strategy: str = "balanced", **kwargs,
) -> dict:
    tasks = await generate_study_plan(exams, available_slots, strategy)
    if not tasks:
        return {"error": "Failed to generate study plan. Please try again."}
    return {"tasks": tasks, "count": len(tasks)}

# Update TOOL_HANDLERS:
# "create_study_plan": _create_study_plan,
```

- [ ] **Step 3: Write test (mocked LLM)**

```python
# tests/test_study_planner.py
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.study_planner import generate_study_plan


@pytest.mark.asyncio
async def test_generate_study_plan():
    mock_tasks = [
        {
            "title": "高数 - 极限复习",
            "exam_name": "高等数学",
            "date": "2026-03-30",
            "start_time": "10:00",
            "end_time": "12:00",
            "description": "复习极限",
        }
    ]

    with patch("app.agent.study_planner.chat_completion") as mock_cc:
        mock_cc.return_value = {"content": json.dumps(mock_tasks, ensure_ascii=False)}

        result = await generate_study_plan(
            exams=[{"course_name": "高等数学", "exam_date": "2026-04-05"}],
            available_slots={"slots": []},
            strategy="balanced",
            llm_client=AsyncMock(),
        )
        assert len(result) == 1
        assert result[0]["title"] == "高数 - 极限复习"


@pytest.mark.asyncio
async def test_generate_study_plan_invalid_json():
    with patch("app.agent.study_planner.chat_completion") as mock_cc:
        mock_cc.return_value = {"content": "这不是JSON"}

        result = await generate_study_plan(
            exams=[], available_slots={}, llm_client=AsyncMock(),
        )
        assert result == []
```

- [ ] **Step 4: Run tests**

Run: `cd student-planner && pytest tests/test_study_planner.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: create_study_plan tool using LLM to generate review schedules"
```

---

### Task 10: Full Integration Test

End-to-end test with mocked LLM to verify the complete flow.

**Files:**
- Create: `student-planner/tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""End-to-end test: user asks to create a study plan, agent calls tools, returns result."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.loop import run_agent_loop
from app.models.course import Course
from app.models.user import User


@pytest.mark.asyncio
async def test_full_flow_list_courses(setup_db):
    """User asks 'what courses do I have', agent calls list_courses, responds."""
    call_count = 0

    async def mock_cc(client, messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "list_courses", "arguments": "{}"},
                }],
            }
        else:
            return {"role": "assistant", "content": "你有1门课：高等数学，周一 08:00-09:40。"}

    with patch("app.agent.loop.chat_completion", side_effect=mock_cc):
        async with TestSession() as db:
            user = User(id="u-int", username="inttest", hashed_password="x")
            db.add(user)
            course = Course(
                user_id="u-int", name="高等数学", weekday=1,
                start_time="08:00", end_time="09:40",
            )
            db.add(course)
            await db.commit()

            events = []
            gen = run_agent_loop("我有什么课", user, "s-int", db, AsyncMock())
            async for event in gen:
                events.append(event)

            # Verify flow: tool_call -> tool_result -> text -> done
            types = [e["type"] for e in events]
            assert "tool_call" in types
            assert "tool_result" in types
            assert "text" in types
            assert "done" in types

            # Verify tool was called correctly
            tool_result_event = next(e for e in events if e["type"] == "tool_result")
            assert tool_result_event["result"]["count"] == 1
```

- [ ] **Step 2: Run full test suite**

Run: `cd student-planner && pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: full integration test for agent loop"
```
