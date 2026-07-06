from app.agent.contracts import (
    CONFIRMATION_ENFORCEMENT_GAP,
    CONFIRMATION_REQUIRED_TOOLS,
    CONFIRMATION_STATE_V1_PILOTS,
    EVENT_REQUIRED_FIELDS,
    GOLDEN_E2E_MATRIX,
    STATE_SCHEMA_FIELDS,
    STREAMING_MODES,
    AgentRoute,
    decide_agent_route,
)
from app.agent.langgraph_loop import _route_node


def test_router_contract_prioritizes_no_web_before_rag_or_llm():
    decision = decide_agent_route("最新政策是什么")

    assert decision.route == AgentRoute.NO_WEB
    assert decision.should_retrieve is False
    assert decision.expected_next_step == "return_no_web_text"


def test_router_contract_routes_rag_candidate_without_evidence_to_insufficient_gate():
    decision = decide_agent_route(
        "机器学习里的量子退相干错误怎么解释",
        rag_result={"evidence_sufficient": False},
    )

    assert decision.route == AgentRoute.RAG_INSUFFICIENT
    assert decision.should_retrieve is True
    assert decision.should_gate_rag_answer is True
    assert decision.expected_next_step == "return_rag_insufficient_text"


def test_router_contract_routes_rag_candidate_with_evidence_to_rag_qa():
    decision = decide_agent_route(
        "改革开放是什么时候开始的",
        rag_result={"evidence_sufficient": True},
    )

    assert decision.route == AgentRoute.RAG_QA
    assert decision.should_retrieve is True
    assert decision.should_gate_rag_answer is True


def test_router_contract_keeps_exam_arrangement_on_study_plan_path():
    decision = decide_agent_route(
        "下周四有大学英语3考试，帮我安排一下",
        rag_result={"evidence_sufficient": False},
    )

    assert decision.route == AgentRoute.STUDY_PLAN
    assert decision.should_retrieve is True
    assert decision.should_gate_rag_answer is False
    assert decision.retrieval_mode == "local_rag_context"


def test_router_contract_keeps_assignment_breakdown_on_work_plan_path():
    decision = decide_agent_route(
        "2026-07-03 要交机器学习报告，帮我拆成任务。",
        rag_result={"evidence_sufficient": False},
    )

    assert decision.route == AgentRoute.STUDY_PLAN
    assert decision.should_retrieve is True
    assert decision.should_gate_rag_answer is False
    assert decision.retrieval_mode == "local_rag_context"


def test_router_contract_matches_current_langgraph_retrieval_side_channel():
    message = "下周四有大学英语3考试，帮我安排一下"

    decision = decide_agent_route(message, rag_result={"evidence_sufficient": False})
    state = _route_node({"user_message": message, "runtime_hints": [], "graph_nodes": []})

    assert decision.route == AgentRoute.STUDY_PLAN
    assert decision.should_retrieve == state["should_retrieve"] is True
    assert decision.should_gate_rag_answer == state["should_gate_rag_answer"] is False


def test_router_contract_matches_current_langgraph_rag_answer_gate_flags():
    message = "机器学习里的过拟合是什么"

    decision = decide_agent_route(message, rag_result={"evidence_sufficient": False})
    state = _route_node({"user_message": message, "runtime_hints": [], "graph_nodes": []})

    assert decision.route == AgentRoute.RAG_INSUFFICIENT
    assert decision.should_retrieve == state["should_retrieve"] is True
    assert decision.should_gate_rag_answer == state["should_gate_rag_answer"] is True


def test_router_contract_classifies_schedule_task_reminder_and_course_paths():
    assert decide_agent_route("上传课表 file_id=abc123 请导入").route == AgentRoute.SCHEDULE_IMPORT
    assert decide_agent_route("明天下午3点提醒我复习线代").route == AgentRoute.TOOL_WORKFLOW
    assert decide_agent_route("把自然语言处理课程改名为 NLP").route == AgentRoute.COURSE_MAINTENANCE


def test_event_contract_lists_required_agent_event_fields():
    assert {"text_delta", "text", "result", "tool_call", "tool_result", "ask_user", "done", "error"} <= set(
        EVENT_REQUIRED_FIELDS
    )
    assert EVENT_REQUIRED_FIELDS["text_delta"] == ("type", "message_id", "delta")
    assert EVENT_REQUIRED_FIELDS["result"] == ("type", "message_id", "content")
    assert EVENT_REQUIRED_FIELDS["tool_call"] == ("type", "name", "args")
    assert EVENT_REQUIRED_FIELDS["tool_result"] == ("type", "name", "result")
    assert "ask_type" in EVENT_REQUIRED_FIELDS["ask_user"]
    assert "structured_result" in STREAMING_MODES


def test_confirmation_contract_covers_database_and_scheduler_writes():
    expected = {
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
    }

    assert expected <= set(CONFIRMATION_REQUIRED_TOOLS)
    assert "execute_tool remains a direct dispatcher" in CONFIRMATION_ENFORCEMENT_GAP
    assert "pending_confirmation/db_write_plan ticket" in CONFIRMATION_ENFORCEMENT_GAP


def test_confirmation_state_v1_marks_schedule_import_pilot():
    assert "schedule_import" in CONFIRMATION_STATE_V1_PILOTS
    assert "agent_loop_write_tools" in CONFIRMATION_STATE_V1_PILOTS


def test_state_and_golden_matrix_contracts_cover_migration_surface():
    assert {
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
        "initial_study_context_text",
    } <= set(STATE_SCHEMA_FIELDS)

    matrix_ids = {case["id"] for case in GOLDEN_E2E_MATRIX}
    assert {
        "rag_hit",
        "rag_insufficient",
        "no_web",
        "create_task_confirmed",
        "study_plan_confirmed_write",
        "schedule_import_confirmed",
        "reminder_set",
        "ask_user_multiturn",
        "tool_failure_recovery",
        "plain_chat_stream",
        "tool_preamble_buffer",
        "course_maintenance_confirmed",
        "schedule_empty_no_review",
    } <= matrix_ids
