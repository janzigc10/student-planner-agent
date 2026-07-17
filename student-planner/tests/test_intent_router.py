import pytest

from app.agent.contracts import AgentRoute, decide_hard_agent_route
from app.agent.intent_router import LLMIntentDecision, decide_agent_route_hybrid


@pytest.mark.asyncio
async def test_hybrid_router_uses_llm_for_semantic_study_plan(monkeypatch):
    async def fake_classify(_message: str) -> LLMIntentDecision:
        return LLMIntentDecision(
            route=AgentRoute.STUDY_PLAN,
            use_rag=False,
            confidence=0.92,
            reason="user wants a preparation plan",
        )

    monkeypatch.setattr("app.agent.intent_router.classify_intent_with_llm", fake_classify)
    monkeypatch.setattr("app.agent.intent_router._has_real_key", lambda _value: True)

    decision = await decide_agent_route_hybrid("这周概率论怎么准备比较合理")

    assert decision.route == AgentRoute.STUDY_PLAN
    assert decision.should_retrieve is False
    assert decision.should_gate_rag_answer is False
    assert decision.reason.startswith("llm_intent:")


@pytest.mark.asyncio
async def test_hybrid_router_keeps_gate_policy_out_of_llm_control(monkeypatch):
    async def fake_classify(_message: str) -> LLMIntentDecision:
        return LLMIntentDecision(
            route=AgentRoute.STUDY_PLAN,
            use_rag=True,
            confidence=0.95,
            reason="material-backed plan",
        )

    monkeypatch.setattr("app.agent.intent_router.classify_intent_with_llm", fake_classify)
    monkeypatch.setattr("app.agent.intent_router._has_real_key", lambda _value: True)

    decision = await decide_agent_route_hybrid(
        "结合老师发的要求，看看这周怎么准备比较合理",
        rag_result={"evidence_sufficient": False},
    )

    assert decision.route == AgentRoute.STUDY_PLAN
    assert decision.should_retrieve is True
    assert decision.should_gate_rag_answer is False


@pytest.mark.asyncio
async def test_hybrid_router_sends_short_underspecified_input_to_plain_chat(monkeypatch):
    async def fake_classify(_message: str) -> LLMIntentDecision:
        raise AssertionError("short underspecified input should not call LLM")

    monkeypatch.setattr("app.agent.intent_router.classify_intent_with_llm", fake_classify)

    decision = await decide_agent_route_hybrid("机器学习")

    assert decision.route == AgentRoute.PLAIN_CHAT
    assert decision.should_retrieve is False
    assert decision.should_gate_rag_answer is False


@pytest.mark.parametrize(
    "message",
    [
        "最近学的中国近现代史怎么总结？",
        "现在政治经济学是什么意思？",
        "现在政策工具是什么意思？",
        "当前法律课程的核心概念是什么？",
        "根据课件总结当前利率政策的作用",
    ],
)
def test_hard_route_keeps_course_knowledge_questions_in_rag(message):
    decision = decide_hard_agent_route(message)

    assert decision is not None
    assert decision.route == AgentRoute.RAG_QA
    assert decision.route != AgentRoute.NO_WEB


@pytest.mark.parametrize(
    "message",
    [
        "现在中国有什么最新新闻？",
        "今天人民币汇率是多少？",
    ],
)
def test_hard_route_keeps_live_public_information_in_no_web(message):
    decision = decide_hard_agent_route(message)

    assert decision is not None
    assert decision.route == AgentRoute.NO_WEB


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "最近学的中国近现代史怎么总结？",
        "现在政治经济学是什么意思？",
        "现在政策工具是什么意思？",
        "当前法律课程的核心概念是什么？",
        "根据课件总结当前利率政策的作用",
    ],
)
async def test_hybrid_route_keeps_course_knowledge_questions_in_rag(message):
    decision = await decide_agent_route_hybrid(message)

    assert decision.route == AgentRoute.RAG_QA
    assert decision.should_retrieve is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "现在中国有什么最新新闻？",
        "今天人民币汇率是多少？",
    ],
)
async def test_hybrid_route_keeps_live_public_information_in_no_web(message):
    decision = await decide_agent_route_hybrid(message)

    assert decision.route == AgentRoute.NO_WEB
