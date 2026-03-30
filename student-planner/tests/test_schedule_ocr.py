import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.schedule_ocr import parse_schedule_image
from app.services.schedule_parser import RawCourse

MOCK_LLM_RESPONSE = json.dumps([
    {
        "name": "高等数学",
        "teacher": "张老师",
        "location": "教学楼A301",
        "weekday": 1,
        "period": "1-2",
        "weeks": "1-16周",
    },
    {
        "name": "线性代数",
        "teacher": "李老师",
        "location": "教学楼B205",
        "weekday": 3,
        "period": "1-2",
        "weeks": "1-16周",
    },
])


@pytest.mark.asyncio
async def test_parse_image_returns_raw_courses() -> None:
    mock_response = {"role": "assistant", "content": MOCK_LLM_RESPONSE}
    with patch(
        "app.agent.schedule_ocr._vision_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    assert len(courses) == 2
    assert all(isinstance(course, RawCourse) for course in courses)


@pytest.mark.asyncio
async def test_parse_image_extracts_fields() -> None:
    mock_response = {"role": "assistant", "content": MOCK_LLM_RESPONSE}
    with patch(
        "app.agent.schedule_ocr._vision_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    gaoshu = next(course for course in courses if course.name == "高等数学")
    assert gaoshu.weekday == 1
    assert gaoshu.period == "1-2"
    assert gaoshu.teacher == "张老师"
    assert gaoshu.location == "教学楼A301"
    assert gaoshu.week_start == 1
    assert gaoshu.week_end == 16


@pytest.mark.asyncio
async def test_parse_image_handles_llm_error() -> None:
    mock_response = {"role": "assistant", "content": "抱歉，我无法识别这张图片"}
    with patch(
        "app.agent.schedule_ocr._vision_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    assert courses == []


@pytest.mark.asyncio
async def test_parse_image_handles_missing_weeks() -> None:
    response_data = json.dumps([
        {
            "name": "体育",
            "teacher": None,
            "location": "操场",
            "weekday": 5,
            "period": "7-8",
            "weeks": None,
        }
    ])
    mock_response = {"role": "assistant", "content": response_data}
    with patch(
        "app.agent.schedule_ocr._vision_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    assert len(courses) == 1
    assert courses[0].week_start == 1
    assert courses[0].week_end == 16