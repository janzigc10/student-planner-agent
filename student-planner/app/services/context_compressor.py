"""Compression helpers for tool results and long conversation histories."""

import json
from collections import defaultdict
from typing import Any

from app.agent.llm_client import chat_completion

_SMALL_THRESHOLD = 300
_SUMMARIZE_PROMPT = """请用 1 到 3 句话总结以下较早的对话内容，保留用户做了什么、确认了什么、表达了什么偏好。"""
_LIST_COURSES_PREFIX = "[TOOL_SUMMARY:list_courses:v1] "
_MAX_LIST_COURSE_GROUPS = 8
_MAX_LIST_COURSE_OPTIONS_PER_GROUP = 8


def compress_tool_result(tool_name: str, result: dict) -> str:
    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    if tool_name == "list_courses":
        return _compress_list_courses(result)

    raw = json.dumps(result, ensure_ascii=False)
    if len(raw) < _SMALL_THRESHOLD:
        return raw

    compressor = _COMPRESSORS.get(tool_name)
    if compressor is not None:
        return compressor(result)

    return raw


async def compress_conversation_history(
    messages: list[dict],
    llm_client,
    max_messages: int = 12,
) -> list[dict]:
    system_messages = [message for message in messages if message.get("role") == "system"]
    conversation_messages = [message for message in messages if message.get("role") != "system"]

    if len(conversation_messages) <= max_messages:
        return messages

    cutoff = len(conversation_messages) - max_messages
    old_messages = conversation_messages[:cutoff]
    recent_messages = conversation_messages[cutoff:]

    old_text = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        for message in old_messages
        if message.get("content")
    )

    try:
        response = await chat_completion(
            llm_client,
            [
                {"role": "system", "content": _SUMMARIZE_PROMPT},
                {"role": "user", "content": old_text},
            ],
        )
        summary = response.get("content") or "早期对话摘要不可用。"
    except Exception:
        summary = "早期对话摘要生成失败。"

    summary_message = {
        "role": "user",
        "content": f"[之前的对话摘要] {summary}",
    }
    return system_messages + [summary_message] + recent_messages


def _compress_get_free_slots(result: dict) -> str:
    summary = result.get("summary")
    if summary:
        return f"[空闲时段查询结果] {summary}"

    slots = result.get("slots", [])
    free_count = sum(len(day.get("free_periods", [])) for day in slots)
    return f"[空闲时段查询结果] {len(slots)} 天，共 {free_count} 个空闲段"


def _compress_list_courses(result: dict) -> str:
    courses = result.get("courses", [])
    grouped_options: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for course in courses:
        course_name = _normalize_text(course.get("name"), default="未命名课程")
        grouped_options[course_name].append(
            {
                "id": _normalize_text(course.get("id"), default=""),
                "name": course_name,
                "location": _normalize_text(course.get("location"), default="未提供"),
                "weekday": _normalize_weekday(course.get("weekday")),
                "start_time": _normalize_text(course.get("start_time"), default=""),
                "end_time": _normalize_text(course.get("end_time"), default=""),
            }
        )

    sorted_group_names = sorted(grouped_options.keys())
    total_groups = len(sorted_group_names)
    selected_group_names = sorted_group_names[:_MAX_LIST_COURSE_GROUPS]
    omitted_groups = max(total_groups - len(selected_group_names), 0)
    omitted_options = sum(
        len(grouped_options[group_name]) for group_name in sorted_group_names[len(selected_group_names) :]
    )

    groups: list[dict[str, Any]] = []
    for group_name in selected_group_names:
        options = sorted(grouped_options[group_name], key=_list_course_option_sort_key)
        if len(options) > _MAX_LIST_COURSE_OPTIONS_PER_GROUP:
            omitted_options += len(options) - _MAX_LIST_COURSE_OPTIONS_PER_GROUP
            options = options[:_MAX_LIST_COURSE_OPTIONS_PER_GROUP]
        groups.append({"name": group_name, "options": options})

    count_value = _normalize_count(result.get("count"), fallback=len(courses))
    truncated = omitted_groups > 0 or omitted_options > 0
    summary = {
        "total": count_value,
        "total_groups": total_groups,
        "returned_groups": len(groups),
        "omitted_groups": omitted_groups,
        "omitted_options": omitted_options,
        "truncated": truncated,
        "groups": groups,
    }
    payload = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{_LIST_COURSES_PREFIX}{payload}"


def _compress_list_tasks(result: dict) -> str:
    tasks = result.get("tasks", [])
    count = result.get("count", len(tasks))
    completed_count = sum(1 for task in tasks if task.get("status") == "completed")
    return f"[任务列表] 共 {count} 个任务，其中 {completed_count} 个已完成"


def _compress_create_study_plan(result: dict) -> str:
    tasks = result.get("tasks", [])
    count = result.get("count", len(tasks))
    titles = ", ".join(task.get("title", "") for task in tasks[:3] if task.get("title"))
    if titles:
        return f"[学习计划] 已生成 {count} 个任务，包含：{titles}"
    return f"[学习计划] 已生成 {count} 个任务"


_COMPRESSORS = {
    "get_free_slots": _compress_get_free_slots,
    "list_courses": _compress_list_courses,
    "list_tasks": _compress_list_tasks,
    "create_study_plan": _compress_create_study_plan,
}


def _normalize_text(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    stripped = value.strip()
    return stripped or default


def _normalize_weekday(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _normalize_count(value: Any, fallback: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return fallback


def _list_course_option_sort_key(option: dict[str, Any]) -> tuple[str, int, str, str, str]:
    weekday = option.get("weekday")
    weekday_value = weekday if isinstance(weekday, int) else 999
    return (
        _normalize_text(option.get("location"), default=""),
        weekday_value,
        _normalize_text(option.get("start_time"), default=""),
        _normalize_text(option.get("end_time"), default=""),
        _normalize_text(option.get("id"), default=""),
    )
