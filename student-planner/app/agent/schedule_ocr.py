"""Parse schedule screenshots with a vision-capable LLM."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.services.schedule_parser import RawCourse

_WEEK_RANGE_RE = re.compile(r"(\d{1,2})\s*[-~～—–]\s*(\d{1,2})\s*周?")
_WEEK_NUMBER_RE = re.compile(r"第?\s*(\d{1,2})\s*周")
_ODD_WEEK_RE = re.compile(r"(单周|奇数周|odd)", re.IGNORECASE)
_EVEN_WEEK_RE = re.compile(r"(双周|偶数周|even)", re.IGNORECASE)
_PERIOD_RANGE_RE = re.compile(r"(\d{1,2})\s*[-~～—–]\s*(\d{1,2})")
_WEEKDAY_TEXT_MAP = {
    "周一": 1,
    "星期一": 1,
    "周二": 2,
    "星期二": 2,
    "周三": 3,
    "星期三": 3,
    "周四": 4,
    "星期四": 4,
    "周五": 5,
    "星期五": 5,
    "周六": 6,
    "星期六": 6,
    "周日": 7,
    "周天": 7,
    "星期日": 7,
    "星期天": 7,
}

_PROMPT = (
    "这是大学课表截图。请提取课程并输出 JSON。"
    "如果图片不是大学课表截图，或没有周一至周日/节次网格，不要从简历、项目经历、普通文档或说明文字中提取课程。"
    "输出格式必须是一个 JSON 对象："
    '{"image_week": 3, "courses": [...]}。'
    "其中 image_week 是截图底部显示的教学周（例如第3周），识别不到就填 null。"
    "courses 每项包含 name, teacher, location, weekday, period, weeks。"
    "weekday 用 1-7（周一=1）。period 统一为如 1-2 的字符串。"
    "weeks 必须尽量给出周次信息："
    "如 1-18周、1-18周(单周)、1-18周(双周)。"
    "如果截图只展示某一周，请结合 image_week 推断单双周。"
    "只能输出 JSON，不要解释文本。识别失败时返回 "
    '{"image_week": null, "courses": []}。'
)
_WEEK_DETECT_PROMPT = (
    "请识别这张课表截图底部显示的教学周数（例如第3周）。"
    "只返回 JSON：{\"image_week\": 3}。"
    "如果看不清，返回 {\"image_week\": null}。"
)


async def parse_schedule_image(
    image_bytes: bytes,
    mime_type: str,
    fallback_week_number: int | None = None,
    prefer_parity_from_week_hint: bool = False,
) -> list[RawCourse]:
    response = await _vision_completion(image_bytes, mime_type)
    content = (response or {}).get("content")
    raw_items, image_week = _extract_courses_and_week(content)
    if not raw_items:
        return []

    week_hint = image_week if image_week is not None else fallback_week_number
    courses: list[RawCourse] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        weekday = _normalize_weekday(item.get("weekday"))
        period = _normalize_period(item.get("period"))
        if not name or weekday is None or period is None:
            continue
        week_start, week_end, week_pattern, week_text = _parse_weeks(
            item.get("weeks"),
            fallback_week_number=week_hint,
            prefer_parity_from_week_hint=prefer_parity_from_week_hint,
        )
        courses.append(
            RawCourse(
                name=str(name),
                teacher=_optional_str(item.get("teacher")),
                location=_optional_str(item.get("location")),
                weekday=weekday,
                period=period,
                week_start=week_start,
                week_end=week_end,
                week_pattern=week_pattern,
                week_text=week_text,
            )
        )
    return courses


async def _vision_completion(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    return await _vision_completion_with_prompt(
        image_bytes=image_bytes,
        mime_type=mime_type,
        system_prompt=_PROMPT,
        user_prompt="请识别这张课表截图。",
    )


async def detect_schedule_week(image_bytes: bytes, mime_type: str) -> int | None:
    response = await _vision_completion_with_prompt(
        image_bytes=image_bytes,
        mime_type=mime_type,
        system_prompt=_WEEK_DETECT_PROMPT,
        user_prompt="请只返回教学周数字。",
        max_tokens=min(settings.llm_max_tokens, 128),
    )
    payload = _extract_json_payload((response or {}).get("content"))
    if isinstance(payload, dict):
        return _coerce_week_number(payload.get("image_week"))
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return _coerce_week_number(first.get("image_week"))
    return None


async def _vision_completion_with_prompt(
    image_bytes: bytes,
    mime_type: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    client = AsyncOpenAI(
        api_key=settings.vision_llm_api_key or settings.llm_api_key,
        base_url=settings.vision_llm_base_url or settings.llm_base_url,
    )
    encoded = base64.b64encode(image_bytes).decode("ascii")
    response = await client.chat.completions.create(
        model=settings.vision_llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                ],
            },
        ],
        max_tokens=max_tokens or settings.llm_max_tokens,
        temperature=0,
    )
    message = response.choices[0].message
    return {"role": "assistant", "content": message.content}


def _extract_courses_and_week(content: Any) -> tuple[list[dict[str, Any]], int | None]:
    parsed = _extract_json_payload(content)
    if parsed is None:
        return [], None

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)], None

    if not isinstance(parsed, dict):
        return [], None

    raw_courses = parsed.get("courses")
    courses = [item for item in raw_courses if isinstance(item, dict)] if isinstance(raw_courses, list) else []
    image_week = _coerce_week_number(parsed.get("image_week"))
    if image_week is None:
        image_week = _coerce_week_number(parsed.get("week"))
    return courses, image_week


def _extract_json_payload(content: Any) -> dict[str, Any] | list[Any] | None:
    if content is None:
        return None

    text = str(content).strip()
    if not text:
        return None

    candidates = [text]
    if text.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        candidates.append(cleaned.strip())

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(text[first_brace:last_brace + 1].strip())

    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and first_bracket < last_bracket:
        candidates.append(text[first_bracket:last_bracket + 1].strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (list, dict)):
            return parsed

    return None


def _coerce_week_number(value: Any) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    text = _optional_str(value)
    if text is None:
        return None
    if text.isdigit():
        number = int(text)
        return number if number > 0 else None
    match = _WEEK_NUMBER_RE.search(text)
    if match is None:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def _parse_weeks(
    weeks: Any,
    fallback_week_number: int | None = None,
    prefer_parity_from_week_hint: bool = False,
) -> tuple[int, int, str, str]:
    default_start = 1
    default_end = 18
    week_pattern = "all"

    text = _optional_str(weeks)
    if text:
        normalized = (
            text.replace("（", "(")
            .replace("）", ")")
            .replace("～", "-")
            .replace("—", "-")
            .replace("–", "-")
            .replace("~", "-")
        )
        week_start = default_start
        week_end = default_end

        range_match = _WEEK_RANGE_RE.search(normalized)
        if range_match is not None:
            week_start = int(range_match.group(1))
            week_end = int(range_match.group(2))
            if week_start > week_end:
                week_start, week_end = week_end, week_start

        if _ODD_WEEK_RE.search(normalized):
            week_pattern = "odd"
        elif _EVEN_WEEK_RE.search(normalized):
            week_pattern = "even"
        elif range_match is None:
            single_week_match = _WEEK_NUMBER_RE.search(normalized)
            if single_week_match is not None:
                week_number = int(single_week_match.group(1))
                week_pattern = "odd" if week_number % 2 == 1 else "even"
        elif (
            prefer_parity_from_week_hint
            and week_pattern == "all"
            and fallback_week_number is not None
            and fallback_week_number > 0
        ):
            week_pattern = "odd" if fallback_week_number % 2 == 1 else "even"

        return week_start, week_end, week_pattern, _build_week_text(week_start, week_end, week_pattern)

    if fallback_week_number is not None and fallback_week_number > 0:
        week_pattern = "odd" if fallback_week_number % 2 == 1 else "even"
    return default_start, default_end, week_pattern, _build_week_text(default_start, default_end, week_pattern)


def _build_week_text(week_start: int, week_end: int, week_pattern: str) -> str:
    if week_pattern == "odd":
        return f"第{week_start}-{week_end}周(单周)"
    if week_pattern == "even":
        return f"第{week_start}-{week_end}周(双周)"
    return f"第{week_start}-{week_end}周"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_weekday(value: Any) -> int | None:
    if isinstance(value, int) and 1 <= value <= 7:
        return value

    text = _optional_str(value)
    if text is None:
        return None

    if text.isdigit():
        numeric = int(text)
        if 1 <= numeric <= 7:
            return numeric
        return None

    return _WEEKDAY_TEXT_MAP.get(text)


def _normalize_period(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            start = int(value[0])
            end = int(value[1])
        except (TypeError, ValueError):
            return None
        if start <= 0 or end <= 0:
            return None
        low, high = sorted((start, end))
        return f"{low}-{high}"

    text = _optional_str(value)
    if text is None:
        return None

    normalized = (
        text.replace("第", "")
        .replace("节", "")
        .replace(" ", "")
        .replace("～", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("~", "-")
    )
    match = _PERIOD_RANGE_RE.search(normalized)
    if match is None:
        return None

    start = int(match.group(1))
    end = int(match.group(2))
    low, high = sorted((start, end))
    return f"{low}-{high}"
