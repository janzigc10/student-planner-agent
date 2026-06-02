from app.agent.tool_preflight import (
    apply_tool_preflight,
    extract_reminder_slot,
    task_tool_preflight_error,
    tool_schema_preflight_error,
)


SAMPLE_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "scheduled_date": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "completed"]},
                },
                "required": ["title", "scheduled_date"],
            },
        },
    }
]


def test_extract_reminder_slot_from_advance_minutes():
    slot = extract_reminder_slot(["把刚才的任务改到下午4点到5点，提前15分钟提醒"])

    assert slot is not None
    assert slot.advance_minutes == 15


def test_extract_reminder_slot_supports_hour_and_at_time():
    hour_slot = extract_reminder_slot(["提前半小时提醒我"])
    at_time_slot = extract_reminder_slot(["准点提醒"])

    assert hour_slot is not None
    assert hour_slot.advance_minutes == 30
    assert at_time_slot is not None
    assert at_time_slot.advance_minutes == 0


def test_apply_tool_preflight_fills_missing_task_reminder_minutes():
    args, changed = apply_tool_preflight(
        "update_task",
        {"task_id": "task-1", "start_time": "16:00", "end_time": "17:00"},
        ["把刚才的任务改到下午4点到5点，提前15分钟提醒"],
    )

    assert changed is True
    assert args["reminder_advance_minutes"] == 15


def test_apply_tool_preflight_does_not_add_reminder_without_explicit_slot():
    args, changed = apply_tool_preflight(
        "update_task",
        {"task_id": "task-1", "start_time": "16:00", "end_time": "17:00"},
        ["把刚才的任务改到下午4点到5点"],
    )

    assert changed is False
    assert "reminder_advance_minutes" not in args


def test_apply_tool_preflight_sets_none_for_explicit_cancel_reminder():
    args, changed = apply_tool_preflight(
        "update_task",
        {"task_id": "task-1", "start_time": "16:00", "end_time": "17:00"},
        ["\u628a\u521a\u624d\u7684\u4efb\u52a1\u6539\u5230\u4e0b\u53484\u70b9\u52305\u70b9\uff0c\u4e0d\u63d0\u9192"],
    )

    assert changed is True
    assert "reminder_advance_minutes" in args
    assert args["reminder_advance_minutes"] is None


def test_apply_tool_preflight_uses_latest_explicit_slot():
    args, changed = apply_tool_preflight(
        "update_task",
        {"task_id": "task-1", "reminder_advance_minutes": 30},
        ["提前30分钟提醒", "不对，提前10分钟提醒"],
    )

    assert changed is True
    assert args["reminder_advance_minutes"] == 10


def test_task_tool_preflight_blocks_create_for_update_intent():
    error = task_tool_preflight_error(
        "create_task",
        ["把刚才的复习任务改到明天下午4点到5点，提前15分钟提醒"],
    )

    assert error is not None
    assert "update an existing task" in error["error"]


def test_task_tool_preflight_allows_clear_create_intent():
    error = task_tool_preflight_error(
        "create_task",
        ["帮我创建一个复习任务，明天下午4点到5点，提前15分钟提醒"],
    )

    assert error is None


def test_tool_schema_preflight_blocks_missing_required_argument():
    error = tool_schema_preflight_error(
        "create_task",
        {"title": "review"},
        SAMPLE_TOOL_DEFINITIONS,
    )

    assert error is not None
    assert "scheduled_date" in error["error"]


def test_tool_schema_preflight_blocks_invalid_enum_argument():
    error = tool_schema_preflight_error(
        "create_task",
        {"title": "review", "scheduled_date": "2026-08-01", "status": "done"},
        SAMPLE_TOOL_DEFINITIONS,
    )

    assert error is not None
    assert "invalid enum" in error["error"]


def test_tool_schema_preflight_allows_complete_arguments():
    error = tool_schema_preflight_error(
        "create_task",
        {"title": "review", "scheduled_date": "2026-08-01", "status": "pending"},
        SAMPLE_TOOL_DEFINITIONS,
    )

    assert error is None
