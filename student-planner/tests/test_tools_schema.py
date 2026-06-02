from app.agent.prompt import TASK_TOOL_RULES
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


def test_agent_task_rules_route_cancel_reminder_through_update_task():
    assert "不提醒" in TASK_TOOL_RULES
    assert "取消提醒" in TASK_TOOL_RULES
    assert "update_task" in TASK_TOOL_RULES
    assert "reminder_advance_minutes=null" in TASK_TOOL_RULES
