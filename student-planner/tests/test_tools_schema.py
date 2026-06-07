from app.agent.prompt import RESPONSE_FORMAT_RULES, TASK_TOOL_RULES
from app.agent.tools import TOOL_DEFINITIONS


def _tool_by_name(name: str) -> dict:
    return next(tool for tool in TOOL_DEFINITIONS if tool["function"]["name"] == name)


def test_tool_definitions_valid():
    """All tool definitions must have required fields."""
    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        function = tool["function"]
        assert "name" in function
        assert "description" in function
        assert "parameters" in function
        parameters = function["parameters"]
        assert parameters["type"] == "object"
        assert "properties" in parameters


def test_tool_names_unique():
    names = [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))


def test_expected_tools_present():
    names = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
    expected = {
        "list_courses",
        "add_course",
        "update_course",
        "delete_course",
        "get_free_slots",
        "create_study_plan",
        "create_work_plan",
        "list_tasks",
        "create_task",
        "update_task",
        "complete_task",
        "set_reminder",
        "list_reminders",
        "ask_user",
    }
    assert expected.issubset(names)


def test_update_task_contract_exposes_task_reminder_cancellation():
    tool = _tool_by_name("update_task")
    function = tool["function"]
    reminder_schema = function["parameters"]["properties"]["reminder_advance_minutes"]

    assert "null" in function["description"]
    assert "remove/cancel" in function["description"]
    assert reminder_schema["nullable"] is True
    assert "null" in reminder_schema["description"]
    assert "remove/cancel" in reminder_schema["description"]


def test_create_study_plan_contract_exposes_study_context():
    tool = _tool_by_name("create_study_plan")
    study_context = tool["function"]["parameters"]["properties"]["study_context"]

    assert "study-quality context" in study_context["description"]
    assert "exam_scope" in study_context["properties"]
    assert "weak_areas" in study_context["properties"]
    assert "target_score" in study_context["properties"]
    assert "daily_study_limit_minutes" in study_context["properties"]
    assert "raw_notes" in study_context["properties"]


def test_create_work_plan_contract_exposes_work_context():
    tool = _tool_by_name("create_work_plan")
    work_context = tool["function"]["parameters"]["properties"]["work_context"]

    assert "work-quality context" in work_context["description"]
    assert "requirements" in work_context["properties"]
    assert "current_progress" in work_context["properties"]
    assert "daily_work_limit_minutes" in work_context["properties"]
    assert "raw_notes" in work_context["properties"]
    assert "work_items" in tool["function"]["parameters"]["required"]
    assert "available_slots" in tool["function"]["parameters"]["required"]


def test_agent_task_rules_route_cancel_reminder_through_update_task():
    assert "不提醒" in TASK_TOOL_RULES
    assert "取消提醒" in TASK_TOOL_RULES
    assert "update_task" in TASK_TOOL_RULES
    assert "reminder_advance_minutes=null" in TASK_TOOL_RULES


def test_agent_task_rules_allow_default_study_context_for_simple_plans():
    assert "学习上下文" in TASK_TOOL_RULES
    assert "create_study_plan" in TASK_TOOL_RULES
    assert "study_context" in TASK_TOOL_RULES
    assert "using_defaults" in TASK_TOOL_RULES
    assert "简单要求安排复习" in TASK_TOOL_RULES
    assert "详细" in TASK_TOOL_RULES


def test_agent_task_rules_require_work_context_before_work_planning():
    assert "工作上下文" in TASK_TOOL_RULES
    assert "create_work_plan" in TASK_TOOL_RULES
    assert "work_context" in TASK_TOOL_RULES
    assert "每日最大可工作时长" in TASK_TOOL_RULES


def test_response_format_rules_keep_plain_replies_compact():
    assert "1-3 个短段落" in RESPONSE_FORMAT_RULES
    assert "Markdown 表格" in RESPONSE_FORMAT_RULES
    assert "ask_user" in RESPONSE_FORMAT_RULES
