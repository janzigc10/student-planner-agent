from app.agent.tools import TOOL_DEFINITIONS


def test_parse_schedule_tool_defined() -> None:
    names = [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
    assert "parse_schedule" in names


def test_parse_schedule_image_tool_defined() -> None:
    names = [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
    assert "parse_schedule_image" in names


def test_parse_schedule_requires_file_id() -> None:
    tool = next(tool for tool in TOOL_DEFINITIONS if tool["function"]["name"] == "parse_schedule")
    assert "file_id" in tool["function"]["parameters"]["required"]


def test_parse_schedule_image_requires_file_id() -> None:
    tool = next(
        tool for tool in TOOL_DEFINITIONS if tool["function"]["name"] == "parse_schedule_image"
    )
    assert "file_id" in tool["function"]["parameters"]["required"]