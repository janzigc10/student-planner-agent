import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.work_planner import generate_work_plan


@pytest.mark.asyncio
async def test_generate_work_plan_includes_work_context_and_caps_daily_limit():
    mock_tasks = [
        {
            "title": "机器学习报告 - 完成初稿",
            "work_item_name": "机器学习报告",
            "date": "2026-06-09",
            "start_time": "09:00",
            "end_time": "11:00",
            "description": "完成报告主体初稿。",
        }
    ]

    with patch("app.agent.work_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": json.dumps(mock_tasks, ensure_ascii=False)}

        result = await generate_work_plan(
            work_items=[{"title": "机器学习报告", "due_date": "2026-06-12"}],
            available_slots={"slots": []},
            strategy="staged",
            work_context={
                "requirements": "需要5页PDF，包括实验结果和参考文献",
                "daily_work_limit_minutes": 60,
                "raw_notes": "需要5页PDF，包括实验结果和参考文献，每天最多1小时",
            },
            llm_client=AsyncMock(),
        )

    messages = mock_chat_completion.call_args.args[1]
    prompt = messages[0]["content"]
    assert "工作上下文" in prompt
    assert "需要5页PDF" in prompt
    assert "daily_work_limit_minutes" in prompt
    assert result[0]["end_time"] == "10:00"


@pytest.mark.asyncio
async def test_generate_work_plan_falls_back_to_staged_tasks_when_json_invalid():
    available_slots = {
        "slots": [
            {
                "date": "2026-06-08",
                "free_periods": [
                    {"start": "09:00", "end": "11:00", "duration_minutes": 120},
                    {"start": "14:00", "end": "16:00", "duration_minutes": 120},
                ],
            },
            {
                "date": "2026-06-09",
                "free_periods": [
                    {"start": "10:00", "end": "12:00", "duration_minutes": 120},
                ],
            },
            {
                "date": "2026-06-10",
                "free_periods": [
                    {"start": "15:00", "end": "17:00", "duration_minutes": 120},
                ],
            },
        ]
    }

    with patch("app.agent.work_planner.chat_completion") as mock_chat_completion:
        mock_chat_completion.return_value = {"content": "不是 JSON"}

        result = await generate_work_plan(
            work_items=[{"title": "机器学习报告", "due_date": "2026-06-12"}],
            available_slots=available_slots,
            work_context={"daily_work_limit_minutes": 120, "raw_notes": "每天最多2小时"},
            llm_client=AsyncMock(),
        )

    assert len(result) == 3
    assert result[0]["title"] == "机器学习报告 - 整理要求和资料"
    assert result[1]["title"] == "机器学习报告 - 完成提纲或方案"
