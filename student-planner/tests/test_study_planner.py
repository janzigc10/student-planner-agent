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

    with patch("app.agent.study_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": json.dumps(mock_tasks, ensure_ascii=False)}

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
    with patch("app.agent.study_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": "这不是JSON"}

        result = await generate_study_plan(
            exams=[],
            available_slots={},
            llm_client=AsyncMock(),
        )
        assert result == []