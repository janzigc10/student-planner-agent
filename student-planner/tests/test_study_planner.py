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


@pytest.mark.asyncio
async def test_generate_study_plan_falls_back_when_json_invalid_with_slots():
    with patch("app.agent.study_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": "这不是JSON"}

        result = await generate_study_plan(
            exams=[
                {"course_name": "高等数学", "exam_date": "2026-06-10"},
                {"course_name": "大学英语3", "exam_date": "2026-06-12"},
            ],
            available_slots={
                "slots": [
                    {
                        "date": "2026-06-08",
                        "free_periods": [{"start": "09:00", "end": "11:00", "duration_minutes": 120}],
                    },
                    {
                        "date": "2026-06-09",
                        "free_periods": [{"start": "14:00", "end": "16:00", "duration_minutes": 120}],
                    },
                ]
            },
            study_context={
                "exam_scope": "高数第1-5章；英语Unit1-6",
                "weak_areas": ["听力"],
                "daily_study_limit_minutes": 120,
            },
            llm_client=AsyncMock(),
        )

    assert len(result) == 2
    assert any(task["exam_name"] == "高等数学" for task in result)
    assert any(task["exam_name"] == "大学英语3" for task in result)
    assert all(task["end_time"] <= "16:00" for task in result)


@pytest.mark.asyncio
async def test_generate_study_plan_binds_optional_scope_and_weakness_to_each_exam():
    raw_notes = (
        "2026-06-10 有高等数学考试，范围第1-5章；"
        "2026-06-12 有大学英语3考试，范围 Unit1-6，听力薄弱。"
        "帮我做复习计划，每天最多2小时。"
    )
    with patch("app.agent.study_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": "这不是JSON"}

        result = await generate_study_plan(
            exams=[
                {"course_name": "高等数学", "exam_date": "2026-06-10"},
                {"course_name": "大学英语3", "exam_date": "2026-06-12"},
            ],
            available_slots={
                "slots": [
                    {
                        "date": "2026-06-08",
                        "free_periods": [{"start": "09:00", "end": "11:00", "duration_minutes": 120}],
                    },
                    {
                        "date": "2026-06-09",
                        "free_periods": [{"start": "14:00", "end": "16:00", "duration_minutes": 120}],
                    },
                ]
            },
            study_context={
                "exam_scope": raw_notes,
                "weak_areas": ["听力"],
                "daily_study_limit_minutes": 120,
                "raw_notes": raw_notes,
            },
            llm_client=AsyncMock(),
        )

    math_tasks = [task for task in result if task["exam_name"] == "高等数学"]
    english_tasks = [task for task in result if task["exam_name"] == "大学英语3"]
    assert math_tasks
    assert english_tasks
    assert any("第1-5章" in task["description"] for task in math_tasks)
    assert not any("Unit1-6" in task["description"] or "听力" in task["description"] for task in math_tasks)
    assert any("Unit1-6" in task["description"] and "听力" in task["description"] for task in english_tasks)


@pytest.mark.asyncio
async def test_generate_study_plan_adds_missing_exam_from_fallback():
    model_tasks = [
        {
            "title": "大学英语3 - 听力突破",
            "exam_name": "大学英语3",
            "date": "2026-06-09",
            "start_time": "14:00",
            "end_time": "15:00",
            "description": "完成Unit1-6听力专项训练。",
        }
    ]

    with patch("app.agent.study_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": json.dumps(model_tasks, ensure_ascii=False)}

        result = await generate_study_plan(
            exams=[
                {"course_name": "高等数学", "exam_date": "2026-06-10"},
                {"course_name": "大学英语3", "exam_date": "2026-06-12"},
            ],
            available_slots={
                "slots": [
                    {
                        "date": "2026-06-08",
                        "free_periods": [{"start": "09:00", "end": "11:00", "duration_minutes": 120}],
                    },
                    {
                        "date": "2026-06-09",
                        "free_periods": [{"start": "14:00", "end": "16:00", "duration_minutes": 120}],
                    },
                ]
            },
            study_context={
                "exam_scope": "高数第1-5章；英语Unit1-6",
                "weak_areas": ["听力"],
                "daily_study_limit_minutes": 120,
            },
            llm_client=AsyncMock(),
        )

    assert any(task["exam_name"] == "大学英语3" for task in result)
    assert any(task["exam_name"] == "高等数学" for task in result)


@pytest.mark.asyncio
async def test_generate_study_plan_includes_study_context_in_prompt():
    mock_tasks = [
        {
            "title": "大学英语3 - 听力突破",
            "exam_name": "大学英语3",
            "date": "2026-06-05",
            "start_time": "09:00",
            "end_time": "10:30",
            "description": "围绕 Unit1-6 的听力薄弱点做专项练习。",
        }
    ]

    with patch("app.agent.study_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": json.dumps(mock_tasks, ensure_ascii=False)}

        result = await generate_study_plan(
            exams=[{"course_name": "大学英语3", "exam_date": "2026-06-11"}],
            available_slots={"slots": []},
            strategy="balanced",
            study_context={
                "exam_scope": "Unit1-6",
                "weak_areas": ["听力", "写作"],
                "target_score": "80分",
                "daily_study_limit_minutes": 120,
                "raw_notes": "Unit1-6，听力和写作薄弱，目标80分，每天最多2小时",
            },
            llm_client=AsyncMock(),
        )

    messages = mock_chat_completion.call_args.args[1]
    prompt = messages[0]["content"]
    assert result[0]["title"] == "大学英语3 - 听力突破"
    assert "学习上下文" in prompt
    assert "Unit1-6" in prompt
    assert "听力" in prompt
    assert "daily_study_limit_minutes" in prompt
