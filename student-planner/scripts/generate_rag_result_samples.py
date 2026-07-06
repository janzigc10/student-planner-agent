from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag import build_rag_context, clear_rag_cache
from app.config import settings


@dataclass(frozen=True)
class ResultSample:
    scenario: str
    query: str


SAMPLES = (
    ResultSample(
        "中国近现代史：五四运动",
        "五四运动为什么是新民主主义革命开端？请按期末简答题方式回答。",
    ),
    ResultSample(
        "思想政治理论：全过程人民民主",
        "全过程人民民主包括哪些环节，民主协商和民主监督分别起什么作用？",
    ),
    ResultSample(
        "世界现代史：冷战格局",
        "杜鲁门主义、马歇尔计划、北约和华约怎样推动冷战格局形成？",
    ),
    ResultSample(
        "世界现代史：马歇尔计划",
        "马歇尔计划为什么既是经济援助，也是冷战中的遏制政策？",
    ),
    ResultSample(
        "思想政治理论：宪法与国家机构",
        "中华人民共和国宪法如何规定国家机构和人民代表大会制度？",
    ),
    ResultSample(
        "机器学习课程报告",
        "机器学习报告应该怎样安排数据预处理、模型训练、误差分析和最终展示？",
    ),
)


def _has_real_key(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped not in {"sk-placeholder", "placeholder", "changeme"}


def _answer_client() -> tuple[AsyncOpenAI, str, str]:
    if _has_real_key(settings.llm_api_key):
        return (
            AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url),
            settings.llm_model,
            settings.llm_base_url,
        )
    if _has_real_key(settings.rag_embedding_api_key):
        return (
            AsyncOpenAI(api_key=settings.rag_embedding_api_key, base_url=settings.rag_embedding_base_url),
            "qwen-plus",
            settings.rag_embedding_base_url,
        )
    raise RuntimeError("No valid LLM key found: set SP_LLM_API_KEY or SP_RAG_EMBEDDING_API_KEY")


async def _answer_completion(client: AsyncOpenAI, model: str, messages: list[dict[str, str]]) -> str:
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=min(settings.llm_max_tokens, 1600),
        temperature=settings.llm_temperature,
    )
    return response.choices[0].message.content or ""


def _snippet(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _build_messages(query: str, rag_context: dict[str, Any]) -> list[dict[str, str]]:
    context = rag_context["context"]
    return [
        {
            "role": "system",
            "content": (
                "你是学生复习规划应用中的 RAG 回答器。"
                "只根据给定资料回答，不要编造资料外事实。"
                "回答要像期末复习助手：先给结论，再列 3-5 个要点。"
                "如果资料不足，明确说明不足。"
            ),
        },
        {
            "role": "user",
            "content": f"问题：{query}\n\nRAG 资料：\n{context}\n\n请给出最终 result。",
        },
    ]


async def generate(top_k: int) -> dict[str, Any]:
    clear_rag_cache()
    client, llm_model, llm_base_url = _answer_client()
    cases = []
    started = time.perf_counter()
    for sample in SAMPLES:
        rag_context = build_rag_context(sample.query, top_k=top_k)
        messages = _build_messages(sample.query, rag_context)
        answer_started = time.perf_counter()
        answer = await _answer_completion(client, llm_model, messages)
        answer_ms = round((time.perf_counter() - answer_started) * 1000, 2)
        hits = rag_context["hits"]
        cases.append(
            {
                "scenario": sample.scenario,
                "query": sample.query,
                "answer_ms": answer_ms,
                "result": answer,
                "top_sources": [
                    str(hit.get("metadata", {}).get("source", "")).replace("\\", "/")
                    for hit in hits
                ],
                "top_scores": [hit.get("score") for hit in hits],
                "top_hits": [
                    {
                        "source": str(hit.get("metadata", {}).get("source", "")).replace("\\", "/"),
                        "score": hit.get("score"),
                        "snippet": _snippet(str(hit.get("content", ""))),
                    }
                    for hit in hits
                ],
            }
        )
    return {
        "sample_count": len(cases),
        "top_k": top_k,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "embedding_model": settings.rag_embedding_model,
        "cases": cases,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RAG 最终 Result 样例",
        "",
        "说明：这里展示的是 `query -> RAG top5 context -> LLM answer` 的最终回答样例。",
        "它和 `RAG_QUALITY_SAMPLE_QA.md` 不同，后者只展示召回证据。",
        "",
        f"- 样例数：{report['sample_count']}",
        f"- Top K：{report['top_k']}",
        f"- LLM：{report['llm_model']}",
        f"- Embedding：{report['embedding_model']}",
        "",
    ]
    for index, case in enumerate(report["cases"], 1):
        lines.extend(
            [
                f"## {index}. {case['scenario']}",
                "",
                f"**Query**：{case['query']}",
                "",
                f"**Answer latency**：{case['answer_ms']} ms",
                "",
                "**Top sources**：",
                "",
            ]
        )
        for source, score in zip(case["top_sources"], case["top_scores"], strict=False):
            lines.append(f"- `{source}`，score={score}")
        lines.extend(["", "**Result**：", "", case["result"].strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Generate final LLM result samples with RAG context.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json-output", type=Path, default=Path("data/rag/RAG_RESULT_SAMPLE_ANSWERS.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("data/rag/RAG_RESULT_SAMPLE_ANSWERS.md"))
    args = parser.parse_args()

    report = await generate(top_k=args.top_k)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
