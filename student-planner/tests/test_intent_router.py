import pytest

from app.agent.contracts import AgentRoute
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
