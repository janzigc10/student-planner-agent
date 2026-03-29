import pytest

from app.agent.tool_executor import execute_tool
from app.models.user import User
from tests.conftest import TestSession


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
        user = User(id="user-1", username="test", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "add_course",
            {
                "name": "高等数学",
                "weekday": 1,
                "start_time": "08:00",
                "end_time": "09:40",
            },
            db,
            "user-1",
        )
        assert result["status"] == "created"

        result = await execute_tool("list_courses", {}, db, "user-1")
        assert result["count"] == 1
        assert result["courses"][0]["name"] == "高等数学"


@pytest.mark.asyncio
async def test_ask_user_returns_action(setup_db):
    async with TestSession() as db:
        result = await execute_tool(
            "ask_user",
            {
                "question": "确认吗？",
                "type": "confirm",
            },
            db,
            "user-1",
        )
        assert result["action"] == "ask_user"
        assert result["question"] == "确认吗？"