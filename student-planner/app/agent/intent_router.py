from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.agent.contracts import (
    AgentRoute,
    RouteDecision,
    decide_agent_route,
    decide_hard_agent_route,
    resolve_route_policy,
)
from app.config import settings


_ALLOWED_LLM_ROUTES = {
    AgentRoute.NO_WEB.value: AgentRoute.NO_WEB,
    AgentRoute.RAG_QA.value: AgentRoute.RAG_QA,
    AgentRoute.STUDY_PLAN.value: AgentRoute.STUDY_PLAN,
    AgentRoute.SCHEDULE_IMPORT.value: AgentRoute.SCHEDULE_IMPORT,
    AgentRoute.COURSE_MAINTENANCE.value: AgentRoute.COURSE_MAINTENANCE,
    AgentRoute.TOOL_WORKFLOW.value: AgentRoute.TOOL_WORKFLOW,
    AgentRoute.PLAIN_CHAT.value: AgentRoute.PLAIN_CHAT,
    "unclear": AgentRoute.PLAIN_CHAT,
}

_LOW_CONFIDENCE_THRESHOLD = 0.70
_SHORT_UNCLEAR_MAX_LEN = 8


@dataclass(frozen=True)
class LLMIntentDecision:
    route: AgentRoute
    use_rag: bool
    confidence: float
    reason: str


SYSTEM_PROMPT = """你是 Student Planner 的意图路由分类器，只做主意图分类，不回答用户问题，不执行工具。

可选 route 只能是：
- no_web: 用户要求当前、最新、实时、外部公网信息。
- rag_qa: 用户主要是在提问资料/知识/概念/总结/解释/对比。
- study_plan: 用户主要要求生成复习计划、学习计划、备考计划、作业/报告/项目拆解计划。
- schedule_import: 用户要导入课表、识别课表截图、写入课表文件。
- course_maintenance: 用户要修改、删除、合并、修正已有课程或课表课程。
- tool_workflow: 用户要创建/修改/删除任务、日程、提醒、待办。
- plain_chat: 普通聊天、情绪支持、反馈、或信息不足无法确定具体工具/RAG路径。
- unclear: 只有在必须追问时使用。

判断规则：
1. 按用户主意图分类，不要按关键词分类。
2. 用户要“办事/改变状态/生成计划”时，action 优先；课程名、报告名、知识点只是上下文。
3. RAG 是知识问答的主路径；在 action 中只可能作为参考资料 side-channel。
4. use_rag 只表示 action 是否明确要求参考本地资料；route=rag_qa 时后续系统会自动使用 RAG。
5. 极短、省略、指代不明的输入，如果不能确定要办什么事或问什么问题，返回 plain_chat 或 unclear。

输出必须是 JSON 对象，不要加 Markdown：
{
  "route": "study_plan",
  "use_rag": true,
  "confidence": 0.0到1.0,
  "reason": "一句话中文理由"
}
"""


def _has_real_key(value: str) -> bool:
    stripped = str(value or "").strip()
    return bool(stripped) and stripped not in {"sk-placeholder", "placeholder", "changeme"}


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM intent response is not a JSON object")
    return parsed


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


async def classify_intent_with_llm(user_message: str) -> LLMIntentDecision:
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    response = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": str(user_message or "")},
        ],
        temperature=0,
        max_tokens=512,
    )
    content = response.choices[0].message.content or "{}"
    parsed = _extract_json_object(content)
    route = _ALLOWED_LLM_ROUTES.get(str(parsed.get("route") or "").strip(), AgentRoute.PLAIN_CHAT)
    confidence = _normalize_confidence(parsed.get("confidence"))
    return LLMIntentDecision(
        route=route,
        use_rag=bool(parsed.get("use_rag")),
        confidence=confidence,
        reason=str(parsed.get("reason") or "llm_intent_router"),
    )


def _looks_too_short_for_direct_action_or_rag(user_message: str) -> bool:
    compact = str(user_message or "").strip().replace(" ", "")
    return 0 < len(compact) <= _SHORT_UNCLEAR_MAX_LEN and not any(
        marker in compact for marker in ("？", "?", "提醒", "任务", "课表", "导入", "删除", "修改", "计划")
    )


async def decide_agent_route_hybrid(
    user_message: str,
    rag_result: dict[str, Any] | None = None,
) -> RouteDecision:
    hard_decision = decide_hard_agent_route(user_message, rag_result=rag_result)
    if hard_decision is not None:
        return hard_decision

    if _looks_too_short_for_direct_action_or_rag(user_message):
        return RouteDecision(
            AgentRoute.PLAIN_CHAT,
            "short_underspecified_input",
            expected_next_step="delegate_to_text_loop",
        )

    if not _has_real_key(settings.llm_api_key):
        return decide_agent_route(user_message, rag_result=rag_result)

    try:
        intent = await classify_intent_with_llm(user_message)
    except Exception:
        return decide_agent_route(user_message, rag_result=rag_result)

    if intent.confidence < _LOW_CONFIDENCE_THRESHOLD:
        return RouteDecision(
            AgentRoute.PLAIN_CHAT,
            f"llm_low_confidence:{intent.reason}",
            expected_next_step="delegate_to_text_loop",
        )

    return resolve_route_policy(
        intent.route,
        f"llm_intent:{intent.reason}",
        rag_result=rag_result,
        use_rag=intent.use_rag,
        confidence=intent.confidence,
    )
