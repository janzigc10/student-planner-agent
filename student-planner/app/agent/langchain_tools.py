"""LangChain-facing tool schema adapters."""

from __future__ import annotations

from typing import Any

from app.agent.tools import TOOL_DEFINITIONS


def langchain_assignment_tool_names() -> set[str]:
    """Tools highlighted in the course-assignment LangGraph flow."""

    return {
        "list_courses",
        "list_tasks",
        "get_free_slots",
        "create_study_plan",
        "create_work_plan",
        "create_task",
        "update_task",
        "ask_user",
    }


def langchain_tool_schemas(tool_names: set[str] | None = None) -> list[dict[str, Any]]:
    """Return dict schemas compatible with LangChain ``bind_tools``."""

    schemas: list[dict[str, Any]] = []
    for definition in TOOL_DEFINITIONS:
        function = dict(definition.get("function") or {})
        name = str(function.get("name") or "")
        if tool_names is not None and name not in tool_names:
            continue
        schemas.append(function)
    return schemas
