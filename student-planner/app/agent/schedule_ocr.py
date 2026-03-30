"""Parse schedule screenshots with a vision-capable LLM."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.services.schedule_parser import RawCourse

_WEEK_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*周")

_PROMPT = (
    "这是一张大学课表的照片或截图。请提取所有课程信息，输出 JSON 数组。"
    "每个对象包含 name、teacher、location、weekday、period、weeks。"
    "只输出 JSON 数组；如果不是课表或无法识别，输出 []。"
)


async def parse_schedule_image(image_bytes: bytes, mime_type: str) -> list[RawCourse]:
    response = await _vision_completion(image_bytes, mime_type)
    content = (response or {}).get("content")
    if not content:
        return []

    try:
        raw_items = json.loads(content)
    except json.JSONDecodeError:
        return []

    if not isinstance(raw_items, list):
        return []

    courses: list[RawCourse] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        weekday = item.get("weekday")
        period = item.get("period")
        if not name or weekday is None or not period:
            continue
        week_start, week_end = _parse_weeks(item.get("weeks"))
        courses.append(
            RawCourse(
                name=str(name),
                teacher=_optional_str(item.get("teacher")),
                location=_optional_str(item.get("location")),
                weekday=int(weekday),
                period=str(period),
                week_start=week_start,
                week_end=week_end,
            )
        )
    return courses


async def _vision_completion(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    client = AsyncOpenAI(
        api_key=settings.vision_llm_api_key or settings.llm_api_key,
        base_url=settings.vision_llm_base_url or settings.llm_base_url,
    )
    encoded = base64.b64encode(image_bytes).decode("ascii")
    response = await client.chat.completions.create(
        model=settings.vision_llm_model,
        messages=[
            {"role": "system", "content": _PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别这张课表图片。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                ],
            },
        ],
        max_tokens=settings.llm_max_tokens,
        temperature=0,
    )
    message = response.choices[0].message
    return {"role": "assistant", "content": message.content}


def _parse_weeks(weeks: Any) -> tuple[int, int]:
    if not weeks:
        return 1, 16
    match = _WEEK_RANGE_RE.search(str(weeks))
    if match is None:
        return 1, 16
    return int(match.group(1)), int(match.group(2))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None