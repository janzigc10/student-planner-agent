"""Executable contracts for the future LangGraph-native agent loop.

This module is intentionally small.  It captures the route, state, event, and
tool-boundary invariants that a later graph migration must preserve without
moving the legacy agent loop yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentRoute(str, Enum):
    NO_WEB = "no_web"
    RAG_QA = "rag_qa"
    RAG_INSUFFICIENT = "rag_insufficient"
    TOOL_WORKFLOW = "tool_workflow"
    SCHEDULE_IMPORT = "schedule_import"
    STUDY_PLAN = "study_plan"
    COURSE_MAINTENANCE = "course_maintenance"
    PLAIN_CHAT = "plain_chat"


@dataclass(frozen=True)
class RouteDecision:
    route: AgentRoute
    reason: str
    should_retrieve: bool = False
    should_gate_rag_answer: bool = False
    retrieval_mode: str = "none"
    expected_next_step: str = "delegate_to_agent_loop"


MATERIAL_REFERENCE_MARKERS = (
    "根据",
    "按照",
    "参考",
    "结合",
    "基于",
    "上传",
    "资料",
    "材料",
    "大纲",
    "课件",
    "讲义",
    "老师发",
    "实验要求",
    "报告要求",
    "课程要求",
    "unit",
    "Unit",
    "知识库",
)

QUESTION_INTENT_MARKERS = (
    "是什么",
    "为什么",
    "怎么理解",
    "解释",
    "说明",
    "总结",
    "梳理",
    "区别",
    "关系",
    "共同点",
    "主要目的",
    "怎么形成",
    "怎么写",
    "怎么回答",
    "有哪些",
    "什么意思",
)

CURRENT_INFO_TIME_MARKERS = (
    "今天",
    "现在",
    "当前",
    "最新",
    "实时",
    "明天",
    "昨天",
    "今年",
    "此刻",
    "刚刚",
)

CURRENT_INFO_OBJECT_MARKERS = (
    "天气",
    "股价",
    "汇率",
    "价格",
    "api价格",
    "总统",
    "主席",
    "总理",
    "新闻",
    "赛程",
    "比分",
    "利率",
)


@dataclass(frozen=True)
class PendingConfirmation:
    confirmation_id: str
    route: str
    tool_name: str
    ask_type: str
    question: str
    options: tuple[str, ...]
    data: dict[str, Any] | None = None
    allowed_tool_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class DBWritePlan:
    confirmation_id: str
    route: str
    tool_name: str
    args: dict[str, Any]
    description: str


STATE_SCHEMA_FIELDS = (
    "route",
    "messages",
    "runtime_hints",
    "rag_result",
    "should_retrieve",
    "should_gate_rag_answer",
    "retrieval_mode",
    "pending_confirmation",
    "tool_history",
    "preflight_reference_texts",
    "preflight_user_texts",
    "error_count",
    "last_tool_result",
    "last_free_slots_result",
    "review_data",
    "db_write_plan",
    "stream_state",
    "step",
    "pending_tool_call",
    "initial_study_context_text",
    "graph_nodes",
    "uses_langgraph",
    "uses_langchain_tools",
)

EVENT_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "connected": ("type", "session_id"),
    "text_delta": ("type", "message_id", "delta"),
    "text": ("type", "message_id", "content"),
    "result": ("type", "message_id", "content"),
    "tool_call": ("type", "name", "args"),
    "tool_result": ("type", "name", "result"),
    "ask_user": ("type", "question", "ask_type"),
    "done": ("type",),
    "error": ("type", "message"),
}

CONFIRMATION_REQUIRED_TOOLS = (
    "add_course",
    "update_course",
    "delete_course",
    "create_task",
    "update_task",
    "complete_task",
    "set_reminder",
    "save_period_times",
    "bulk_import_courses",
    "save_memory",
    "delete_memory",
)

CONFIRMATION_ENFORCEMENT_GAP = (
    "execute_tool remains a direct dispatcher for non-agent callers. Agent loop "
    "database writes must validate a pending_confirmation/db_write_plan ticket "
    "before write tools execute; later LangGraph-native tool nodes must preserve "
    "that stateful gate."
)

CONFIRMATION_STATE_V1_PILOTS = (
    "schedule_import",
    "agent_loop_write_tools",
)

PLAN_REVIEW_TOOLS = (
    "create_study_plan",
    "create_work_plan",
)

TOOL_BOUNDARY_STEPS = (
    "unknown_tool_guard",
    "loop_guardrails",
    "task_tool_preflight",
    "schema_preflight",
    "argument_preflight",
    "execute_tool",
    "tool_result_event",
    "persist_tool_summary",
    "persist_agent_log",
    "append_tool_message",
    "update_tool_history",
    "update_error_count",
)

STREAMING_MODES = (
    "text_only_stream",
    "tool_call_preamble_buffer",
    "rag_retrieve_then_inner_stream",
    "rag_insufficient_text_done",
    "no_web_text_done",
    "structured_result",
)

GOLDEN_E2E_MATRIX: tuple[dict[str, str], ...] = (
    {
        "id": "rag_hit",
        "route": AgentRoute.RAG_QA.value,
        "assertion": "RAG tool events precede grounded answer; stream still ends with done.",
    },
    {
        "id": "rag_insufficient",
        "route": AgentRoute.RAG_INSUFFICIENT.value,
        "assertion": "Returns local insufficient-evidence text and never delegates to free LLM.",
    },
    {
        "id": "no_web",
        "route": AgentRoute.NO_WEB.value,
        "assertion": "Skips RAG and LLM for current public information requests.",
    },
    {
        "id": "create_task_confirmed",
        "route": AgentRoute.TOOL_WORKFLOW.value,
        "assertion": "ask_user confirmation occurs before create_task writes the database.",
    },
    {
        "id": "study_plan_confirmed_write",
        "route": AgentRoute.STUDY_PLAN.value,
        "assertion": "Plan generation is reviewed before generated tasks are written.",
    },
    {
        "id": "schedule_import_confirmed",
        "route": AgentRoute.SCHEDULE_IMPORT.value,
        "assertion": "Parsed courses require ask_user confirmation before bulk_import_courses.",
    },
    {
        "id": "reminder_set",
        "route": AgentRoute.TOOL_WORKFLOW.value,
        "assertion": "Reminder writes follow the same confirmation and tool-result contract.",
    },
    {
        "id": "ask_user_multiturn",
        "route": AgentRoute.TOOL_WORKFLOW.value,
        "assertion": "ask_user pauses the generator and resumes with the submitted answer.",
    },
    {
        "id": "tool_failure_recovery",
        "route": AgentRoute.TOOL_WORKFLOW.value,
        "assertion": "Tool errors update error_count and stay inside max-retry guardrails.",
    },
    {
        "id": "plain_chat_stream",
        "route": AgentRoute.PLAIN_CHAT.value,
        "assertion": "Plain chat can emit text_delta before final text and done.",
    },
    {
        "id": "tool_preamble_buffer",
        "route": AgentRoute.TOOL_WORKFLOW.value,
        "assertion": "Buffered preamble text is not emitted when the model returns tool calls.",
    },
    {
        "id": "course_maintenance_confirmed",
        "route": AgentRoute.COURSE_MAINTENANCE.value,
        "assertion": "Course update/delete flows confirm the reviewed target before writing.",
    },
    {
        "id": "schedule_empty_no_review",
        "route": AgentRoute.SCHEDULE_IMPORT.value,
        "assertion": "Empty parsed schedules return text and done without showing a review card.",
    },
)


_RAG_ANSWER_MARKERS = (
    "复习",
    "考试",
    "备考",
    "考点",
    "简答",
    "论述",
    "解释",
    "说明",
    "为什么",
    "是什么",
    "怎么答",
    "怎么回答",
    "作用",
    "意义",
    "关系",
    "区别",
    "总结",
    "梳理",
    "范围",
    "薄弱",
    "unit",
    "作业",
    "报告",
    "大作业",
    "算法",
    "冷战",
    "五四",
    "杜鲁门",
    "马歇尔",
    "北约",
    "华约",
    "机器学习",
    "欠拟合",
    "过拟合",
)
_RAG_WORKFLOW_MARKERS = (
    "复习计划",
    "学习计划",
    "作业计划",
    "帮我做个计划",
    "帮我做一个计划",
    "帮我安排",
    "帮我规划",
    "给我安排",
    "请安排",
    "安排一下",
    "提醒",
    "日程",
    "课表",
    "导入",
    "上传",
    "file_id",
)
_TOOL_ACTION_MARKERS = (
    "安排",
    "创建",
    "新建",
    "写入",
    "加入",
    "添加",
    "修改",
    "改到",
    "改成",
    "改为",
    "删除",
    "取消",
    "提醒",
    "提前",
    "拆成",
    "拆解",
    "分解",
)
_TOOL_OBJECT_MARKERS = (
    "任务",
    "提醒",
    "日程",
    "课表",
    "计划",
    "待办",
    "作业",
    "报告",
    "大作业",
    "项目",
    "复习",
)
_SCHEDULE_IMPORT_MARKERS = ("file_id", "上传", "导入", "课表", "图片", "截图", "excel", "xlsx", "xls")
_STUDY_PLAN_MARKERS = ("复习计划", "学习计划", "备考计划", "作业计划")
_COURSE_MAINTENANCE_ACTIONS = ("改名", "改成", "改为", "修改", "修正", "纠正", "合并", "删除", "删掉")
_COURSE_MAINTENANCE_OBJECTS = ("课程", "课表", "两门课")


def decide_agent_route(user_message: str, rag_result: dict[str, Any] | None = None) -> RouteDecision:
    """Classify the agent path without executing tools or calling an LLM."""

    hard_decision = decide_hard_agent_route(user_message, rag_result=rag_result)
    if hard_decision is not None:
        return hard_decision

    message = str(user_message or "")
    compact = message.strip().lower().replace(" ", "")
    if not compact:
        return RouteDecision(AgentRoute.PLAIN_CHAT, "empty_message")

    if _looks_like_no_web_request(message):
        return RouteDecision(
            AgentRoute.NO_WEB,
            "current_public_information_guard",
            expected_next_step="return_no_web_text",
        )

    rag_candidate = any(marker.lower() in compact for marker in _RAG_ANSWER_MARKERS)
    rag_answer_request = rag_candidate and not _looks_like_rag_tool_workflow(compact)
    retrieval_mode = "local_rag_context" if rag_candidate else "none"
    if rag_answer_request:
        evidence_sufficient = bool((rag_result or {}).get("evidence_sufficient"))
        if rag_result is not None and not evidence_sufficient:
            return RouteDecision(
                AgentRoute.RAG_INSUFFICIENT,
                "rag_candidate_without_sufficient_local_evidence",
                should_retrieve=True,
                should_gate_rag_answer=True,
                retrieval_mode=retrieval_mode,
                expected_next_step="return_rag_insufficient_text",
            )
        return RouteDecision(
            AgentRoute.RAG_QA,
            "rag_candidate_with_local_evidence_or_pending_retrieval",
            should_retrieve=True,
            should_gate_rag_answer=True,
            retrieval_mode=retrieval_mode,
            expected_next_step="retrieve_then_answer_with_local_context",
        )

    if _looks_like_schedule_import(compact):
        return RouteDecision(
            AgentRoute.SCHEDULE_IMPORT,
            "schedule_upload_or_import",
            should_retrieve=rag_candidate,
            retrieval_mode=retrieval_mode,
            expected_next_step="run_schedule_import_shortcut",
        )

    if _looks_like_course_maintenance(compact):
        return RouteDecision(
            AgentRoute.COURSE_MAINTENANCE,
            "course_write_or_merge",
            should_retrieve=rag_candidate,
            retrieval_mode=retrieval_mode,
            expected_next_step="route_to_course_tool_workflow",
        )

    if _looks_like_study_plan(compact):
        return RouteDecision(
            AgentRoute.STUDY_PLAN,
            "study_or_work_plan",
            should_retrieve=rag_candidate,
            retrieval_mode=retrieval_mode,
            expected_next_step="collect_context_then_plan",
        )

    if _looks_like_tool_workflow(compact):
        return RouteDecision(
            AgentRoute.TOOL_WORKFLOW,
            "task_reminder_or_schedule_tool_workflow",
            should_retrieve=rag_candidate,
            retrieval_mode=retrieval_mode,
            expected_next_step="delegate_to_tool_loop",
        )

    return RouteDecision(AgentRoute.PLAIN_CHAT, "no_agent_tool_or_rag_route")


def decide_hard_agent_route(user_message: str, rag_result: dict[str, Any] | None = None) -> RouteDecision | None:
    """Return only high-confidence deterministic routes.

    This layer intentionally avoids broad RAG keyword matching.  Ambiguous
    semantic cases are left to the hybrid LLM classifier.
    """

    message = str(user_message or "")
    compact = message.strip().lower().replace(" ", "")
    if not compact:
        return RouteDecision(AgentRoute.PLAIN_CHAT, "empty_message")

    if _looks_like_no_web_request(message) or _looks_like_current_info_request(compact):
        return RouteDecision(
            AgentRoute.NO_WEB,
            "hard_current_public_information_guard",
            expected_next_step="return_no_web_text",
        )

    if _looks_like_schedule_import(compact):
        return RouteDecision(
            AgentRoute.SCHEDULE_IMPORT,
            "hard_schedule_upload_or_import",
            should_retrieve=False,
            retrieval_mode="none",
            expected_next_step="run_schedule_import_shortcut",
        )

    if _looks_like_course_maintenance(compact):
        return RouteDecision(
            AgentRoute.COURSE_MAINTENANCE,
            "hard_course_write_or_merge",
            should_retrieve=False,
            retrieval_mode="none",
            expected_next_step="route_to_course_tool_workflow",
        )

    if _looks_like_explicit_study_plan(compact):
        should_retrieve = _looks_like_material_reference(compact)
        return RouteDecision(
            AgentRoute.STUDY_PLAN,
            "hard_explicit_study_or_work_plan",
            should_retrieve=should_retrieve,
            retrieval_mode="local_rag_context" if should_retrieve else "none",
            expected_next_step="collect_context_then_plan",
        )

    if _looks_like_tool_workflow(compact):
        should_retrieve = _looks_like_material_reference(compact)
        return RouteDecision(
            AgentRoute.TOOL_WORKFLOW,
            "hard_task_reminder_or_schedule_tool_workflow",
            should_retrieve=should_retrieve,
            retrieval_mode="local_rag_context" if should_retrieve else "none",
            expected_next_step="delegate_to_tool_loop",
        )

    if _looks_like_explicit_rag_question(compact):
        return resolve_route_policy(
            AgentRoute.RAG_QA,
            "hard_explicit_knowledge_question",
            rag_result=rag_result,
            use_rag=True,
        )

    return None


def resolve_route_policy(
    route: AgentRoute,
    reason: str,
    *,
    rag_result: dict[str, Any] | None = None,
    use_rag: bool | None = None,
    confidence: float | None = None,
) -> RouteDecision:
    """Derive safety-sensitive routing flags from the selected primary route."""

    if route == AgentRoute.RAG_QA:
        evidence_sufficient = bool((rag_result or {}).get("evidence_sufficient"))
        if rag_result is not None and not evidence_sufficient:
            return RouteDecision(
                AgentRoute.RAG_INSUFFICIENT,
                reason,
                should_retrieve=True,
                should_gate_rag_answer=True,
                retrieval_mode="local_rag_context",
                expected_next_step="return_rag_insufficient_text",
            )
        return RouteDecision(
            AgentRoute.RAG_QA,
            reason,
            should_retrieve=True,
            should_gate_rag_answer=True,
            retrieval_mode="local_rag_context",
            expected_next_step="retrieve_then_answer_with_local_context",
        )

    if route == AgentRoute.NO_WEB:
        return RouteDecision(route, reason, expected_next_step="return_no_web_text")

    if route == AgentRoute.SCHEDULE_IMPORT:
        return RouteDecision(route, reason, expected_next_step="run_schedule_import_shortcut")

    if route == AgentRoute.COURSE_MAINTENANCE:
        return RouteDecision(route, reason, expected_next_step="route_to_course_tool_workflow")

    if route == AgentRoute.STUDY_PLAN:
        should_retrieve = bool(use_rag)
        return RouteDecision(
            route,
            reason,
            should_retrieve=should_retrieve,
            should_gate_rag_answer=False,
            retrieval_mode="local_rag_context" if should_retrieve else "none",
            expected_next_step="collect_context_then_plan",
        )

    if route == AgentRoute.TOOL_WORKFLOW:
        should_retrieve = bool(use_rag)
        return RouteDecision(
            route,
            reason,
            should_retrieve=should_retrieve,
            should_gate_rag_answer=False,
            retrieval_mode="local_rag_context" if should_retrieve else "none",
            expected_next_step="delegate_to_tool_loop",
        )

    return RouteDecision(
        AgentRoute.PLAIN_CHAT,
        reason if route == AgentRoute.PLAIN_CHAT else f"{reason}_resolved_to_plain_chat",
        expected_next_step="delegate_to_text_loop",
    )


def _looks_like_no_web_request(message: str) -> bool:
    from app.agent.loop import _looks_like_current_public_info_request

    return _looks_like_current_public_info_request(message)


def _looks_like_rag_tool_workflow(compact: str) -> bool:
    if any(marker.lower() in compact for marker in _RAG_WORKFLOW_MARKERS):
        return True
    return any(action in compact for action in _TOOL_ACTION_MARKERS) and any(
        target in compact for target in _TOOL_OBJECT_MARKERS
    )


def _looks_like_material_reference(compact: str) -> bool:
    return any(marker.lower() in compact for marker in MATERIAL_REFERENCE_MARKERS)


def _looks_like_current_info_request(compact: str) -> bool:
    return any(marker in compact for marker in CURRENT_INFO_TIME_MARKERS) and any(
        marker in compact for marker in CURRENT_INFO_OBJECT_MARKERS
    )


def _looks_like_explicit_study_plan(compact: str) -> bool:
    if any(marker in compact for marker in ("复习计划", "学习计划", "备考计划", "作业计划", "写作计划", "复习安排")):
        return True
    return any(target in compact for target in ("考试", "作业", "报告", "大作业", "项目", "论文", "期末")) and any(
        marker in compact for marker in ("安排", "规划", "计划", "拆成", "拆解", "分解", "准备")
    )


def _looks_like_explicit_rag_question(compact: str) -> bool:
    if not any(marker in compact for marker in QUESTION_INTENT_MARKERS):
        return False
    if _looks_like_rag_tool_workflow(compact):
        return False
    return True


def _looks_like_schedule_import(compact: str) -> bool:
    return "file_id" in compact and any(marker.lower() in compact for marker in _SCHEDULE_IMPORT_MARKERS)


def _looks_like_study_plan(compact: str) -> bool:
    if any(marker in compact for marker in _STUDY_PLAN_MARKERS):
        return True
    return any(target in compact for target in ("考试", "作业", "报告", "大作业", "项目", "论文")) and any(
        marker in compact for marker in ("安排", "规划", "计划", "拆成", "拆解", "分解")
    )


def _looks_like_course_maintenance(compact: str) -> bool:
    return any(action in compact for action in _COURSE_MAINTENANCE_ACTIONS) and any(
        target in compact for target in _COURSE_MAINTENANCE_OBJECTS
    )


def _looks_like_tool_workflow(compact: str) -> bool:
    return any(action in compact for action in _TOOL_ACTION_MARKERS) and any(
        target in compact for target in _TOOL_OBJECT_MARKERS
    )
