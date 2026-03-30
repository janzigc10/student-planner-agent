import json

import pytest

from app.services.context_compressor import compress_tool_result


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
            {"id": "1", "name": "高数", "teacher": "张", "weekday": 1, "start_time": "08:00", "end_time": "09:40"},
            {"id": "2", "name": "线代", "teacher": "李", "weekday": 3, "start_time": "10:00", "end_time": "11:40"},
            {"id": "3", "name": "英语", "teacher": "王", "weekday": 2, "start_time": "08:00", "end_time": "09:40"},
        ],
        "count": 3,
    }
    compressed = compress_tool_result("list_courses", result)
    assert "3" in compressed
    assert "高数" in compressed


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