from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.contracts import decide_agent_route  # noqa: E402
from app.agent.intent_router import decide_agent_route_hybrid  # noqa: E402
from app.config import settings  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402


ALLOWED_ROUTES = {
    "no_web",
    "rag_qa",
    "study_plan",
    "schedule_import",
    "course_maintenance",
    "tool_workflow",
    "plain_chat",
    "unclear",
}


@dataclass(frozen=True)
class RouterCase:
    id: str
    category: str
    message: str
    expected_route: str
    expected_use_rag: bool
    expected_gate_rag_answer: bool
    note: str


CASES: list[RouterCase] = [
    RouterCase("A01", "pure_action_task", "明天下午3点提醒我复习线性代数，提前30分钟提醒", "tool_workflow", False, False, "创建提醒是办事，不是知识问答"),
    RouterCase("A02", "pure_action_task", "把刚才那个复习线代的任务改到明天下午4点到5点，提前15分钟提醒", "tool_workflow", False, False, "修改任务和提醒"),
    RouterCase("A03", "pure_action_task", "取消明天晚上那个英语听力提醒", "tool_workflow", False, False, "取消提醒"),
    RouterCase("A04", "pure_action_task", "今天晚上8点到9点新建一个做高数作业的任务", "tool_workflow", False, False, "新建普通任务"),
    RouterCase("A05", "pure_action_task", "把明天的复习任务删掉", "tool_workflow", False, False, "删除任务"),
    RouterCase("S01", "study_plan", "下周四有大学英语3考试，帮我安排一个复习计划", "study_plan", False, False, "复习计划生成"),
    RouterCase("S02", "study_plan", "2026-07-03要交机器学习报告，帮我拆成任务", "study_plan", False, False, "作业报告拆解默认不需要 RAG"),
    RouterCase("S03", "study_plan", "把NLP大作业拆成每天2小时的计划", "study_plan", False, False, "作业计划"),
    RouterCase("S04", "study_plan", "我还有两门考试，近代史7月1日，英语7月3日，帮我做备考计划", "study_plan", False, False, "多考试计划"),
    RouterCase("S05", "study_plan", "帮我规划一下这周怎么准备概率论期末", "study_plan", False, False, "计划生成"),
    RouterCase("SR01", "action_with_material_reference", "根据大学英语3 Unit1-6的复习资料，帮我安排复习计划", "study_plan", True, False, "RAG 只做 side-channel"),
    RouterCase("SR02", "action_with_material_reference", "按照我上传的机器学习报告要求，帮我拆成任务", "study_plan", True, False, "资料辅助拆任务"),
    RouterCase("SR03", "action_with_material_reference", "结合近现代史复习大纲，帮我做一个三天复习安排", "study_plan", True, False, "资料辅助复习安排"),
    RouterCase("SR04", "action_with_material_reference", "参考课程资料，把Transformer报告拆成5个待办", "study_plan", True, False, "资料辅助待办拆解"),
    RouterCase("SR05", "action_with_material_reference", "根据老师发的实验要求，给我生成实验报告写作计划", "study_plan", True, False, "资料辅助写作计划"),
    RouterCase("R01", "pure_rag_qa", "五四运动是什么？", "rag_qa", True, True, "本地知识问答"),
    RouterCase("R02", "pure_rag_qa", "全过程人民民主是什么意思？", "rag_qa", True, True, "本地知识问答"),
    RouterCase("R03", "pure_rag_qa", "机器学习报告里的误差分析应该怎么写？", "rag_qa", True, True, "问资料内容"),
    RouterCase("R04", "pure_rag_qa", "冷战两极格局是怎么形成的？", "rag_qa", True, True, "历史知识问答"),
    RouterCase("R05", "pure_rag_qa", "马歇尔计划的主要目的是什么？", "rag_qa", True, True, "历史知识问答"),
    RouterCase("R06", "pure_rag_qa", "北约和华约有什么区别？", "rag_qa", True, True, "对比型知识问答"),
    RouterCase("R07", "pure_rag_qa", "总结一下大学英语3 Unit1-6的复习重点", "rag_qa", True, True, "总结本地资料"),
    RouterCase("R08", "pure_rag_qa", "这份机器学习材料主要讲了哪些模型？", "rag_qa", True, True, "问本地资料"),
    RouterCase("M01", "rag_mixed_scope", "五四运动和法国大革命有什么共同点？", "rag_qa", True, True, "纯提问，但有部分可能超出本地资料"),
    RouterCase("M02", "rag_mixed_scope", "机器学习报告和Transformer公式推导有什么关系？", "rag_qa", True, True, "纯提问，可能部分无资料"),
    RouterCase("M03", "rag_mixed_scope", "结合近现代史资料解释一下美国独立战争", "rag_qa", True, True, "纯提问，但主题可能错配"),
    RouterCase("M04", "rag_mixed_scope", "根据课程资料，过拟合和量子退相干有什么区别？", "rag_qa", True, True, "纯提问，混合越界"),
    RouterCase("N01", "no_web_current", "今天美国总统是谁？", "no_web", False, False, "当前公网信息"),
    RouterCase("N02", "no_web_current", "2026年最新的OpenAI API价格是多少？", "no_web", False, False, "最新外部信息"),
    RouterCase("N03", "no_web_current", "明天北京天气怎么样？", "no_web", False, False, "实时天气"),
    RouterCase("N04", "no_web_current", "现在英伟达股价是多少？", "no_web", False, False, "实时金融信息"),
    RouterCase("C01", "course_maintenance", "把自然语言处理课程改名为NLP", "course_maintenance", False, False, "课程改名"),
    RouterCase("C02", "course_maintenance", "删除课表里的大学物理这门课", "course_maintenance", False, False, "课程删除"),
    RouterCase("C03", "course_maintenance", "把两门重复的高等数学课程合并", "course_maintenance", False, False, "课程合并"),
    RouterCase("C04", "course_maintenance", "把课表里周三的英语课修正成大学英语3", "course_maintenance", False, False, "课程修正"),
    RouterCase("I01", "schedule_import", "上传课表 file_id=abc123 请导入", "schedule_import", False, False, "课表导入"),
    RouterCase("I02", "schedule_import", "file_id=img_001 这是我的课表截图，帮我识别并写入", "schedule_import", False, False, "截图课表导入"),
    RouterCase("I03", "schedule_import", "导入这个xlsx课表 file_id=sheet789", "schedule_import", False, False, "Excel 课表导入"),
    RouterCase("P01", "plain_chat", "你好，今天状态怎么样？", "plain_chat", False, False, "普通闲聊"),
    RouterCase("P02", "plain_chat", "谢谢你，刚才那个计划很好", "plain_chat", False, False, "反馈闲聊"),
    RouterCase("P03", "plain_chat", "我有点焦虑，不知道该怎么开始", "plain_chat", False, False, "泛化建议，不直接工具/RAG"),
    RouterCase("U01", "unclear", "机器学习", "plain_chat", False, False, "过短，不应强行 RAG gate"),
    RouterCase("U02", "unclear", "复习一下", "plain_chat", False, False, "意图不完整，应追问或普通对话"),
    RouterCase("U03", "unclear", "那个报告怎么办", "plain_chat", False, False, "缺少明确动作和对象"),
]


SYSTEM_PROMPT = """你是 Student Planner 的意图路由分类器，只做分类，不回答用户问题，不执行工具。

可选 route 只能是：
- no_web: 用户要求当前、最新、实时、外部公网信息。
- rag_qa: 用户主要是在提问资料/知识/概念/总结/解释/对比，需要本地资料作为答案依据。
- study_plan: 用户主要要求生成复习计划、学习计划、备考计划、作业/报告/项目拆解计划。
- schedule_import: 用户要导入课表、识别课表截图、写入课表文件。
- course_maintenance: 用户要修改、删除、合并、修正已有课程或课表课程。
- tool_workflow: 用户要创建/修改/删除任务、日程、提醒、待办。
- plain_chat: 普通聊天、情绪支持、反馈、或信息不足无法确定具体工具/RAG路径。
- unclear: 只有在 plain_chat 也不合适且必须追问时使用。

重要规则：
1. 按用户主意图分类，不要按出现了什么关键词分类。
2. 用户要“办事/改变状态/生成计划”时，action 优先，不要因为出现课程名、报告名、知识点就改成 rag_qa。
3. RAG 是纯知识问答的主路径；在 action 中只可能作为参考资料 side-channel。
4. gate_rag_answer 只有 route=rag_qa 时才允许为 true；所有 action route 必须为 false。
5. use_rag 只有用户明确在问资料/知识，或明确要求“根据/按照/参考/结合/上传的资料”时才为 true。

输出必须是 JSON 数组，不要加 Markdown。每个元素格式：
{
  "case_id": "A01",
  "route": "study_plan",
  "use_rag": true,
  "gate_rag_answer": false,
  "confidence": 0.0到1.0,
  "reason": "一句话中文理由"
}
"""


def route_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def normalize_rule_route(route: str) -> str:
    if route == "rag_insufficient":
        return "rag_qa"
    return route


def evaluate_rule(case: RouterCase) -> dict[str, Any]:
    initial = decide_agent_route(case.message)
    no_evidence = decide_agent_route(case.message, rag_result={"evidence_sufficient": False})
    return {
        "initial_route": route_value(initial.route),
        "initial_should_retrieve": initial.should_retrieve,
        "initial_should_gate_rag_answer": initial.should_gate_rag_answer,
        "initial_reason": initial.reason,
        "no_evidence_route": route_value(no_evidence.route),
        "no_evidence_should_retrieve": no_evidence.should_retrieve,
        "no_evidence_should_gate_rag_answer": no_evidence.should_gate_rag_answer,
        "no_evidence_reason": no_evidence.reason,
        "route_ok": normalize_rule_route(route_value(initial.route)) == case.expected_route,
        "use_rag_ok": initial.should_retrieve == case.expected_use_rag,
        "gate_ok": initial.should_gate_rag_answer == case.expected_gate_rag_answer,
        "would_refuse_without_evidence": route_value(no_evidence.route) == "rag_insufficient",
    }


async def evaluate_hybrid(case: RouterCase) -> dict[str, Any]:
    initial = await decide_agent_route_hybrid(case.message)
    no_evidence = await decide_agent_route_hybrid(case.message, rag_result={"evidence_sufficient": False})
    return {
        "initial_route": route_value(initial.route),
        "initial_should_retrieve": initial.should_retrieve,
        "initial_should_gate_rag_answer": initial.should_gate_rag_answer,
        "initial_reason": initial.reason,
        "no_evidence_route": route_value(no_evidence.route),
        "no_evidence_should_retrieve": no_evidence.should_retrieve,
        "no_evidence_should_gate_rag_answer": no_evidence.should_gate_rag_answer,
        "no_evidence_reason": no_evidence.reason,
        "route_ok": normalize_rule_route(route_value(initial.route)) == case.expected_route,
        "use_rag_ok": initial.should_retrieve == case.expected_use_rag,
        "gate_ok": initial.should_gate_rag_answer == case.expected_gate_rag_answer,
        "would_refuse_without_evidence": route_value(no_evidence.route) == "rag_insufficient",
    }


def extract_json_array(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", stripped)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("LLM response is not a JSON array")
    return parsed


async def classify_with_llm(cases: list[RouterCase], *, batch_size: int = 8) -> dict[str, dict[str, Any]]:
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    results: dict[str, dict[str, Any]] = {}
    for start in range(0, len(cases), batch_size):
        batch = cases[start : start + batch_size]
        user_payload = [
            {"case_id": case.id, "message": case.message}
            for case in batch
        ]
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "请分类这些输入：\n" + json.dumps(user_payload, ensure_ascii=False, indent=2),
                },
            ],
            temperature=0,
            max_tokens=2048,
        )
        content = response.choices[0].message.content or ""
        parsed = extract_json_array(content)
        for item in parsed:
            case_id = str(item.get("case_id") or "")
            route = str(item.get("route") or "")
            if route not in ALLOWED_ROUTES:
                route = "unclear"
            results[case_id] = {
                "route": route,
                "use_rag": bool(item.get("use_rag")),
                "gate_rag_answer": bool(item.get("gate_rag_answer")),
                "confidence": item.get("confidence"),
                "reason": str(item.get("reason") or ""),
            }
    return results


def score_llm(case: RouterCase, llm: dict[str, Any]) -> dict[str, Any]:
    return {
        "route_ok": llm.get("route") == case.expected_route,
        "use_rag_ok": bool(llm.get("use_rag")) == case.expected_use_rag,
        "gate_ok": bool(llm.get("gate_rag_answer")) == case.expected_gate_rag_answer,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    def count(path: tuple[str, str]) -> int:
        outer, key = path
        return sum(1 for row in rows if row[outer][key])

    by_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = by_category.setdefault(
            row["category"],
            {
                "total": 0,
                "rule_route_ok": 0,
                "llm_route_ok": 0,
                "hybrid_route_ok": 0,
                "rule_all_ok": 0,
                "llm_all_ok": 0,
                "hybrid_all_ok": 0,
            },
        )
        bucket["total"] += 1
        bucket["rule_route_ok"] += int(row["rule"]["route_ok"])
        bucket["llm_route_ok"] += int(row["llm_score"]["route_ok"])
        bucket["hybrid_route_ok"] += int(row["hybrid"]["route_ok"])
        bucket["rule_all_ok"] += int(row["rule"]["route_ok"] and row["rule"]["use_rag_ok"] and row["rule"]["gate_ok"])
        bucket["llm_all_ok"] += int(
            row["llm_score"]["route_ok"] and row["llm_score"]["use_rag_ok"] and row["llm_score"]["gate_ok"]
        )
        bucket["hybrid_all_ok"] += int(
            row["hybrid"]["route_ok"] and row["hybrid"]["use_rag_ok"] and row["hybrid"]["gate_ok"]
        )

    return {
        "total": total,
        "rule_route_accuracy": count(("rule", "route_ok")) / total,
        "rule_use_rag_accuracy": count(("rule", "use_rag_ok")) / total,
        "rule_gate_accuracy": count(("rule", "gate_ok")) / total,
        "llm_route_accuracy": count(("llm_score", "route_ok")) / total,
        "llm_use_rag_accuracy": count(("llm_score", "use_rag_ok")) / total,
        "llm_gate_accuracy": count(("llm_score", "gate_ok")) / total,
        "hybrid_route_accuracy": count(("hybrid", "route_ok")) / total,
        "hybrid_use_rag_accuracy": count(("hybrid", "use_rag_ok")) / total,
        "hybrid_gate_accuracy": count(("hybrid", "gate_ok")) / total,
        "rule_all_fields_accuracy": sum(
            1 for row in rows if row["rule"]["route_ok"] and row["rule"]["use_rag_ok"] and row["rule"]["gate_ok"]
        ) / total,
        "llm_all_fields_accuracy": sum(
            1
            for row in rows
            if row["llm_score"]["route_ok"] and row["llm_score"]["use_rag_ok"] and row["llm_score"]["gate_ok"]
        ) / total,
        "hybrid_all_fields_accuracy": sum(
            1 for row in rows if row["hybrid"]["route_ok"] and row["hybrid"]["use_rag_ok"] and row["hybrid"]["gate_ok"]
        ) / total,
        "rule_false_refusals": [
            row["id"]
            for row in rows
            if row["expected_route"] != "rag_qa" and row["rule"]["would_refuse_without_evidence"]
        ],
        "hybrid_false_refusals": [
            row["id"]
            for row in rows
            if row["expected_route"] != "rag_qa" and row["hybrid"]["would_refuse_without_evidence"]
        ],
        "llm_action_gate_violations": [
            row["id"]
            for row in rows
            if row["expected_route"] not in {"rag_qa"} and row["llm"].get("gate_rag_answer")
        ],
        "by_category": by_category,
    }


def write_markdown_report(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# LLM Router Evaluation",
        "",
        f"- Cases: {summary['total']}",
        f"- Rule route accuracy: {summary['rule_route_accuracy']:.1%}",
        f"- LLM route accuracy: {summary['llm_route_accuracy']:.1%}",
        f"- Hybrid route accuracy: {summary['hybrid_route_accuracy']:.1%}",
        f"- Rule all-fields accuracy: {summary['rule_all_fields_accuracy']:.1%}",
        f"- LLM all-fields accuracy: {summary['llm_all_fields_accuracy']:.1%}",
        f"- Hybrid all-fields accuracy: {summary['hybrid_all_fields_accuracy']:.1%}",
        f"- Rule false refusals on non-RAG expected routes: {', '.join(summary['rule_false_refusals']) or 'none'}",
        f"- Hybrid false refusals on non-RAG expected routes: {', '.join(summary['hybrid_false_refusals']) or 'none'}",
        f"- LLM action gate violations: {', '.join(summary['llm_action_gate_violations']) or 'none'}",
        "",
        "## Category Summary",
        "",
        "| Category | Total | Rule Route OK | LLM Route OK | Hybrid Route OK | Rule All OK | LLM All OK | Hybrid All OK |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, item in summary["by_category"].items():
        lines.append(
            f"| {category} | {item['total']} | {item['rule_route_ok']} | {item['llm_route_ok']} | "
            f"{item['hybrid_route_ok']} | {item['rule_all_ok']} | {item['llm_all_ok']} | {item['hybrid_all_ok']} |"
        )
    lines.extend(["", "## Mismatches", ""])
    for row in rows:
        rule_all_ok = row["rule"]["route_ok"] and row["rule"]["use_rag_ok"] and row["rule"]["gate_ok"]
        llm_all_ok = row["llm_score"]["route_ok"] and row["llm_score"]["use_rag_ok"] and row["llm_score"]["gate_ok"]
        hybrid_all_ok = row["hybrid"]["route_ok"] and row["hybrid"]["use_rag_ok"] and row["hybrid"]["gate_ok"]
        if rule_all_ok and llm_all_ok and hybrid_all_ok:
            continue
        lines.extend(
            [
                f"### {row['id']} {row['category']}",
                "",
                f"- Message: {row['message']}",
                f"- Expected: route={row['expected_route']}, use_rag={row['expected_use_rag']}, gate={row['expected_gate_rag_answer']}",
                f"- Rule initial: route={row['rule']['initial_route']}, use_rag={row['rule']['initial_should_retrieve']}, gate={row['rule']['initial_should_gate_rag_answer']}, reason={row['rule']['initial_reason']}",
                f"- Rule no-evidence: route={row['rule']['no_evidence_route']}, refuse={row['rule']['would_refuse_without_evidence']}",
                f"- LLM: route={row['llm'].get('route')}, use_rag={row['llm'].get('use_rag')}, gate={row['llm'].get('gate_rag_answer')}, confidence={row['llm'].get('confidence')}, reason={row['llm'].get('reason')}",
                f"- Hybrid initial: route={row['hybrid']['initial_route']}, use_rag={row['hybrid']['initial_should_retrieve']}, gate={row['hybrid']['initial_should_gate_rag_answer']}, reason={row['hybrid']['initial_reason']}",
                f"- Hybrid no-evidence: route={row['hybrid']['no_evidence_route']}, refuse={row['hybrid']['would_refuse_without_evidence']}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(ROOT / "output" / "router_eval"))
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    llm_results = await classify_with_llm(CASES, batch_size=args.batch_size)
    rows: list[dict[str, Any]] = []
    for case in CASES:
        llm = llm_results.get(case.id, {"route": "unclear", "use_rag": False, "gate_rag_answer": False, "reason": "missing"})
        hybrid = await evaluate_hybrid(case)
        rows.append(
            {
                **asdict(case),
                "rule": evaluate_rule(case),
                "hybrid": hybrid,
                "llm": llm,
                "llm_score": score_llm(case, llm),
            }
        )

    summary = summarize(rows)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"llm_router_eval_{stamp}.json"
    md_path = out_dir / f"llm_router_eval_{stamp}.md"
    payload = {
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "summary": summary,
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(md_path, summary, rows)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
