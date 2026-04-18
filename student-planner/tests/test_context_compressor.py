import json

import pytest

from app.services.context_compressor import compress_tool_result

LIST_COURSES_PREFIX = "[TOOL_SUMMARY:list_courses:v1] "


def _parse_list_courses_summary(compressed: str) -> dict:
    assert compressed.startswith(LIST_COURSES_PREFIX)
    return json.loads(compressed[len(LIST_COURSES_PREFIX) :])


def test_compress_get_free_slots():
    result = {
        "slots": [
            {
                "date": "2026-04-01",
                "weekday": "周三",
                "free_periods": [
                    {"start": "08:00", "end": "10:00", "duration_minutes": 120},
                    {"start": "14:00", "end": "16:00", "duration_minutes": 120},
                ],
                "occupied": [
                    {"start": "10:00", "end": "12:00", "type": "course", "name": "高数"},
                ],
            },
            {
                "date": "2026-04-02",
                "weekday": "周四",
                "free_periods": [
                    {"start": "09:00", "end": "11:00", "duration_minutes": 120},
                ],
                "occupied": [],
            },
        ],
        "summary": "2026-04-01 至 2026-04-02 共 3 个空闲段，总计 6 小时 0 分钟",
    }
    compressed = compress_tool_result("get_free_slots", result)
    assert "3 个空闲段" in compressed
    assert "6 小时" in compressed
    assert "free_periods" not in compressed


def test_compress_list_courses():
    result = {
        "courses": [
            {
                "id": "c3",
                "name": "自然语言处理",
                "teacher": "张",
                "location": "会展-324",
                "weekday": 4,
                "start_time": "08:30",
                "end_time": "10:05",
            },
            {
                "id": "c2",
                "name": "自然语言处理",
                "teacher": "李",
                "location": "会展-305",
                "weekday": 3,
                "start_time": "08:30",
                "end_time": "10:05",
            },
            {
                "id": "c1",
                "name": "高等数学",
                "teacher": "王",
                "location": "厚德楼C206",
                "weekday": 1,
                "start_time": "10:20",
                "end_time": "11:55",
            },
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_courses", result)
    payload = _parse_list_courses_summary(compressed)
    assert payload["total"] == 3
    assert payload["truncated"] is False
    assert payload["omitted_groups"] == 0
    assert payload["omitted_options"] == 0
    assert [group["name"] for group in payload["groups"]] == ["自然语言处理", "高等数学"]
    options = payload["groups"][0]["options"]
    assert [option["location"] for option in options] == ["会展-305", "会展-324"]
    assert set(options[0].keys()) == {
        "id",
        "name",
        "location",
        "weekday",
        "start_time",
        "end_time",
    }


def test_compress_list_courses_is_deterministic_for_same_data():
    courses = [
        {
            "id": "c3",
            "name": "自然语言处理",
            "location": "会展-324",
            "weekday": 4,
            "start_time": "08:30",
            "end_time": "10:05",
        },
        {
            "id": "c2",
            "name": "自然语言处理",
            "location": "会展-305",
            "weekday": 3,
            "start_time": "08:30",
            "end_time": "10:05",
        },
        {
            "id": "c1",
            "name": "高等数学",
            "location": "厚德楼C206",
            "weekday": 1,
            "start_time": "10:20",
            "end_time": "11:55",
        },
    ]
    first = compress_tool_result("list_courses", {"courses": courses, "count": len(courses)})
    second = compress_tool_result(
        "list_courses",
        {"courses": list(reversed(courses)), "count": len(courses)},
    )
    assert first == second


def test_compress_list_courses_marks_truncated_with_counts():
    courses = []
    for group_index in range(12):
        for option_index in range(3):
            courses.append(
                {
                    "id": f"c-{group_index:02d}-{option_index:02d}",
                    "name": f"课程{group_index:02d}",
                    "location": f"教学楼{option_index}",
                    "weekday": option_index + 1,
                    "start_time": "08:30",
                    "end_time": "10:05",
                }
            )

    compressed = compress_tool_result("list_courses", {"courses": courses, "count": len(courses)})
    payload = _parse_list_courses_summary(compressed)
    assert payload["total"] == len(courses)
    assert payload["total_groups"] == 12
    assert payload["returned_groups"] < payload["total_groups"]
    assert payload["omitted_groups"] == payload["total_groups"] - payload["returned_groups"]
    assert payload["truncated"] is True
    assert payload["omitted_options"] > 0


def test_compress_list_tasks():
    result = {
        "tasks": [
            {"id": "1", "title": "复习高数第一章", "status": "completed"},
            {"id": "2", "title": "复习高数第二章", "status": "pending"},
            {"id": "3", "title": "复习线代", "status": "pending"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_tasks", result)
    assert "3" in compressed
    assert "1" in compressed


def test_compress_create_study_plan():
    result = {
        "tasks": [
            {"title": "复习高数第一章", "date": "2026-04-01"},
            {"title": "复习高数第二章", "date": "2026-04-02"},
            {"title": "复习线代", "date": "2026-04-03"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("create_study_plan", result)
    assert "3" in compressed


def test_compress_unknown_tool_returns_json():
    result = {"status": "ok", "data": "something"}
    compressed = compress_tool_result("unknown_tool", result)
    assert "ok" in compressed


def test_compress_small_result_unchanged():
    result = {"id": "abc", "status": "created"}
    compressed = compress_tool_result("add_course", result)
    parsed = json.loads(compressed)
    assert parsed["status"] == "created"


def test_compress_error_result_unchanged():
    result = {"error": "Course not found"}
    compressed = compress_tool_result("delete_course", result)
    parsed = json.loads(compressed)
    assert parsed["error"] == "Course not found"
