from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag import clear_rag_cache, get_rag_retriever


QUERY_PREFIXES = (
    "帮我复习这个考点：{seed}",
    "期末简答题怎么回答：{seed}",
    "把这些概念串成一段复习提纲：{seed}",
    "如果老师问原因和意义，应该怎么解释：{seed}",
    "我做错题复盘时要抓哪些关键词：{seed}",
)


@dataclass(frozen=True)
class RAGEvalScenario:
    name: str
    label: str
    expected_sources: tuple[str, ...]
    expected_terms: tuple[str, ...]
    seeds: tuple[str, ...]


@dataclass(frozen=True)
class RAGEvalItem:
    scenario: RAGEvalScenario
    query: str


EVAL_SCENARIOS = (
    RAGEvalScenario(
        name="modern_chinese_history_wusi",
        label="中国近现代史：五四运动",
        expected_sources=(
            "public/维基百科-五四运动.md",
            "public/维基百科-新文化运动.md",
            "public/维基百科-巴黎和会.md",
            "public/维基百科-马克思主义中国化.md",
            "中国近现代史复习大纲.md",
        ),
        expected_terms=("五四运动", "新民主主义革命", "工人阶级"),
        seeds=(
            "五四运动为什么是新民主主义革命开端",
            "五四运动中工人阶级登上政治舞台",
            "马克思主义传播和五四运动关系",
            "五四运动的历史意义和爱国学生运动",
            "新文化运动到五四运动的背景",
            "五四运动和中国共产党成立的思想条件",
            "巴黎和会外交失败为什么引发五四运动",
            "五四运动中的学生商人工人作用",
            "五四运动对近代中国革命方向的影响",
            "五四运动为什么不是普通学生运动",
        ),
    ),
    RAGEvalScenario(
        name="politics_democracy",
        label="思想政治理论：全过程人民民主",
        expected_sources=("public/维基百科-全过程人民民主.md", "思想政治理论复习大纲.md"),
        expected_terms=("全过程人民民主", "民主协商", "民主监督"),
        seeds=(
            "全过程人民民主的完整制度链条",
            "民主选举民主协商民主决策民主监督之间的关系",
            "全过程人民民主和人民代表大会制度",
            "全过程人民民主为什么强调人民主体地位",
            "基层民主实践如何体现全过程人民民主",
            "协商民主在全过程人民民主中的作用",
            "民主监督为什么是全过程人民民主的重要环节",
            "全过程人民民主和西式选举民主有什么区别",
            "法治中国建设如何保障全过程人民民主",
            "全过程人民民主的制度优势怎么答",
        ),
    ),
    RAGEvalScenario(
        name="world_history_cold_war",
        label="世界现代史：冷战格局",
        expected_sources=(
            "public/维基百科-冷战.md",
            "public/维基百科-杜鲁门主义.md",
            "public/维基百科-马歇尔计划.md",
            "public/维基百科-北大西洋公约组织.md",
            "public/维基百科-华沙条约组织.md",
            "public/维基百科-古巴导弹危机.md",
            "public/维基百科-柏林墙.md",
            "public/维基百科-苏联解体.md",
            "世界现代史专题案例.md",
        ),
        expected_terms=("马歇尔计划", "杜鲁门主义", "北约", "华约"),
        seeds=(
            "杜鲁门主义如何标志冷战开始",
            "马歇尔计划和冷战遏制政策",
            "北约和华约为什么代表两极格局",
            "冷战格局形成的政治经济军事因素",
            "铁幕演说杜鲁门主义马歇尔计划的联系",
            "美国遏制战略和苏联回应",
            "欧洲分裂怎样推动冷战升级",
            "冷战中意识形态对立和军事同盟",
            "两极格局形成过程中的关键事件",
            "冷战早期国际关系变化怎么梳理",
        ),
    ),
    RAGEvalScenario(
        name="world_history_marshall_plan",
        label="世界现代史：马歇尔计划",
        expected_sources=(
            "public/维基百科-马歇尔计划.md",
            "public/维基百科-欧洲一体化.md",
            "public/维基百科-欧洲联盟.md",
            "世界现代史专题案例.md",
        ),
        expected_terms=("马歇尔计划", "援助", "冷战"),
        seeds=(
            "马歇尔计划为什么既是经济援助也是冷战政策",
            "马歇尔计划对西欧复兴的作用",
            "马歇尔计划和美国遏制战略",
            "苏联为什么反对马歇尔计划",
            "马歇尔计划如何影响欧洲分裂",
            "经济援助和政治控制在马歇尔计划中的关系",
            "马歇尔计划对西欧一体化的影响",
            "马歇尔计划与杜鲁门主义之间的联系",
            "马歇尔计划在冷战形成中的地位",
            "马歇尔计划的背景内容和影响",
        ),
    ),
    RAGEvalScenario(
        name="politics_constitution",
        label="思想政治理论：宪法与国家机构",
        expected_sources=(
            "public/维基百科-中华人民共和国宪法.md",
            "public/维基百科-人民代表大会制度.md",
            "public/维基百科-中国人民政治协商会议.md",
            "public/维基百科-依法治国.md",
            "思想政治理论复习大纲.md",
        ),
        expected_terms=("中华人民共和国宪法", "国家机构", "人民代表大会"),
        seeds=(
            "中华人民共和国宪法规定的基本政治制度",
            "人民代表大会制度在宪法中的地位",
            "宪法如何规定国家机构体系",
            "宪法中的公民基本权利和义务",
            "宪法和国家根本制度之间的关系",
            "全国人民代表大会的宪法地位",
            "宪法修改和宪法监督怎么理解",
            "中华人民共和国宪法为什么是根本法",
            "国家机构职权和人民代表大会关系",
            "宪法序言总纲国家机构怎么复习",
        ),
    ),
    RAGEvalScenario(
        name="machine_learning_report",
        label="机器学习课程报告",
        expected_sources=("机器学习报告要求.md",),
        expected_terms=("数据预处理", "模型训练", "误差分析"),
        seeds=(
            "机器学习报告的数据预处理怎么写",
            "机器学习报告中模型训练和验证集划分应该怎么安排",
            "机器学习报告误差分析部分要解释哪些问题",
            "机器学习报告最终展示需要包含哪些图表和指标",
            "机器学习报告实验流程从数据清洗到模型评估怎么组织",
            "机器学习报告如何描述特征工程",
            "机器学习报告模型对比和消融实验应该放在哪里",
            "机器学习报告结论如何总结模型效果和局限",
            "机器学习课程项目时间安排怎么拆分",
            "数据预处理模型训练误差分析如何串起来",
        ),
    ),
)


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _build_eval_items(queries_per_case: int) -> list[RAGEvalItem]:
    items: list[RAGEvalItem] = []
    for scenario in EVAL_SCENARIOS:
        queries = [
            prefix.format(seed=seed)
            for prefix in QUERY_PREFIXES
            for seed in scenario.seeds
        ]
        if queries_per_case > len(queries):
            raise ValueError(
                f"{scenario.name} only has {len(queries)} generated queries; "
                f"requested {queries_per_case}"
            )
        items.extend(RAGEvalItem(scenario=scenario, query=query) for query in queries[:queries_per_case])
    return items


def _document_text(document: Any) -> str:
    return str(getattr(document, "page_content", "")).strip()


def _document_metadata(document: Any) -> dict[str, Any]:
    return dict(getattr(document, "metadata", {}) or {})


def _retrieve_with_vector(retriever: Any, query_vector: list[float], top_k: int) -> list[dict[str, Any]]:
    if hasattr(retriever, "retrieve_by_vector"):
        return retriever.retrieve_by_vector(query_vector, top_k=top_k)
    scored = [
        (_cosine(query_vector, vector), document)
        for document, vector in zip(retriever.documents, retriever.vectors, strict=False)
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    hits: list[dict[str, Any]] = []
    for score, document in scored[:top_k]:
        content = _document_text(document)
        if not content:
            continue
        hits.append(
            {
                "score": round(float(score), 4),
                "content": content,
                "metadata": _document_metadata(document),
            }
        )
    return hits


def _source(value: str) -> str:
    return value.replace("\\", "/")


def _snippet(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def _evaluate_item(item: RAGEvalItem, hits: list[dict[str, Any]]) -> dict[str, Any]:
    sources = [_source(str(hit.get("metadata", {}).get("source", ""))) for hit in hits]
    combined = "\n".join(str(hit.get("content", "")) for hit in hits)
    expected_sources = set(item.scenario.expected_sources)
    source_hit = any(source in expected_sources for source in sources)
    top1_source_hit = bool(sources) and sources[0] in expected_sources
    term_hits = [term for term in item.scenario.expected_terms if term in combined]
    strict_ok = source_hit and len(term_hits) >= min(2, len(item.scenario.expected_terms))
    return {
        "scenario": item.scenario.name,
        "query": item.query,
        "source_hit": source_hit,
        "top1_source_hit": top1_source_hit,
        "strict_ok": strict_ok,
        "expected_sources": item.scenario.expected_sources,
        "top_sources": sources,
        "top_scores": [hit.get("score") for hit in hits],
        "top_hits": [
            {
                "source": _source(str(hit.get("metadata", {}).get("source", ""))),
                "score": hit.get("score"),
                "snippet": _snippet(str(hit.get("content", ""))),
            }
            for hit in hits
        ],
        "term_hits": term_hits,
    }


def _summarize_scenario(scenario: RAGEvalScenario, rows: list[dict[str, Any]], failure_limit: int) -> dict[str, Any]:
    count = len(rows)
    source_hits = sum(1 for row in rows if row["source_hit"])
    top1_hits = sum(1 for row in rows if row["top1_source_hit"])
    strict_passes = sum(1 for row in rows if row["strict_ok"])
    failures = [row for row in rows if not row["source_hit"]]
    strict_failures = [row for row in rows if not row["strict_ok"]]
    return {
        "name": scenario.name,
        "label": scenario.label,
        "query_count": count,
        "expected_sources": scenario.expected_sources,
        "source_hits": source_hits,
        "source_recall_at_k": round(source_hits / count, 4) if count else 0.0,
        "top1_source_hits": top1_hits,
        "top1_source_hit_rate": round(top1_hits / count, 4) if count else 0.0,
        "strict_passes": strict_passes,
        "strict_pass_rate": round(strict_passes / count, 4) if count else 0.0,
        "source_failure_samples": [
            {
                "query": row["query"],
                "top_sources": row["top_sources"],
                "top_scores": row["top_scores"],
                "term_hits": row["term_hits"],
            }
            for row in failures[:failure_limit]
        ],
        "strict_failure_samples": [
            {
                "query": row["query"],
                "top_sources": row["top_sources"],
                "top_scores": row["top_scores"],
                "term_hits": row["term_hits"],
            }
            for row in strict_failures[:failure_limit]
        ],
    }


def _sample_rows(rows: list[dict[str, Any]], samples_per_case: int) -> list[dict[str, Any]]:
    passed = [row for row in rows if row["strict_ok"]]
    failed = [row for row in rows if not row["strict_ok"]]
    selected = passed[: max(samples_per_case - 1, 0)]
    if failed and len(selected) < samples_per_case:
        selected.append(failed[0])
    selected.extend(passed[len(selected) : samples_per_case])
    return selected[:samples_per_case]


def render_sample_markdown(report: dict[str, Any], samples_per_case: int) -> str:
    detail_rows = list(report.get("cases", []))
    lines = [
        "# RAG 300 条评测问答样例",
        "",
        "说明：这里展示的是 RAG 召回证据视图，不是再调用 LLM 生成的最终自然语言答案。"
        "每条样例包含问题、命中情况、top 召回来源和可用于回答的片段。",
        "",
        f"- 总问题数：{report['total_queries']}",
        f"- 案例数：{report['scenario_count']}",
        f"- 每案例问题数：{report['queries_per_case']}",
        f"- Top K：{report['top_k']}",
        f"- Recall@K：{report['source_recall_at_k']}",
        f"- Top1 source hit：{report['top1_source_hit_rate']}",
        f"- 严格术语通过率：{report['strict_pass_rate']}",
        f"- Embedding：{report['embedding_provider']} / {report['embedding_model']}",
        "",
    ]

    for scenario in report["scenarios"]:
        rows = [row for row in detail_rows if row["scenario"] == scenario["name"]]
        lines.extend(
            [
                f"## {scenario['label']}",
                "",
                f"- Recall@K：{scenario['source_recall_at_k']}",
                f"- Top1 source hit：{scenario['top1_source_hit_rate']}",
                f"- 严格术语通过率：{scenario['strict_pass_rate']}",
                "",
            ]
        )
        for index, row in enumerate(_sample_rows(rows, samples_per_case), 1):
            lines.extend(
                [
                    f"### 样例 {index}",
                    "",
                    f"**问题**：{row['query']}",
                    "",
                    (
                        f"**命中情况**：source_hit={row['source_hit']}，"
                        f"top1_source_hit={row['top1_source_hit']}，strict_ok={row['strict_ok']}，"
                        f"term_hits={', '.join(row['term_hits']) if row['term_hits'] else '无'}"
                    ),
                    "",
                    "**Top 召回证据**：",
                    "",
                ]
            )
            for hit in row["top_hits"][:3]:
                lines.extend(
                    [
                        f"- `{hit['source']}`，score={hit['score']}",
                        f"  {hit['snippet']}",
                    ]
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def evaluate(
    *,
    top_k: int,
    queries_per_case: int,
    failure_limit: int,
    include_details: bool,
) -> dict[str, Any]:
    clear_rag_cache()
    started = time.perf_counter()
    retriever = get_rag_retriever()
    build_ms = round((time.perf_counter() - started) * 1000, 2)

    items = _build_eval_items(queries_per_case)
    query_texts = [item.query for item in items]
    embed_started = time.perf_counter()
    query_vectors = retriever.embeddings.embed_documents(query_texts)
    query_embedding_ms = round((time.perf_counter() - embed_started) * 1000, 2)

    rank_started = time.perf_counter()
    rows = [
        _evaluate_item(item, _retrieve_with_vector(retriever, query_vector, top_k))
        for item, query_vector in zip(items, query_vectors, strict=True)
    ]
    ranking_ms = round((time.perf_counter() - rank_started) * 1000, 2)

    scenario_summaries = [
        _summarize_scenario(
            scenario,
            [row for row in rows if row["scenario"] == scenario.name],
            failure_limit=failure_limit,
        )
        for scenario in EVAL_SCENARIOS
    ]
    total = len(rows)
    source_hits = sum(1 for row in rows if row["source_hit"])
    top1_hits = sum(1 for row in rows if row["top1_source_hit"])
    strict_passes = sum(1 for row in rows if row["strict_ok"])
    report: dict[str, Any] = {
        "total_queries": total,
        "queries_per_case": queries_per_case,
        "scenario_count": len(EVAL_SCENARIOS),
        "top_k": top_k,
        "source_hits": source_hits,
        "source_recall_at_k": round(source_hits / total, 4) if total else 0.0,
        "top1_source_hits": top1_hits,
        "top1_source_hit_rate": round(top1_hits / total, 4) if total else 0.0,
        "strict_passes": strict_passes,
        "strict_pass_rate": round(strict_passes / total, 4) if total else 0.0,
        "build_ms": build_ms,
        "query_embedding_ms": query_embedding_ms,
        "ranking_ms": ranking_ms,
        "chunk_count": len(retriever.documents),
        **retriever.embedding_info,
        "scenarios": scenario_summaries,
    }
    if include_details:
        report["cases"] = rows
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate local RAG retrieval quality at scale.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--queries-per-case", type=int, default=50)
    parser.add_argument("--failure-limit", type=int, default=5)
    parser.add_argument("--include-details", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--sample-output", type=Path)
    parser.add_argument("--samples-per-case", type=int, default=3)
    parser.add_argument("--min-source-recall", type=float, default=0.0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    report = evaluate(
        top_k=args.top_k,
        queries_per_case=args.queries_per_case,
        failure_limit=args.failure_limit,
        include_details=args.include_details or bool(args.sample_output),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.summary_output:
        summary_report = {key: value for key, value in report.items() if key != "cases"}
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(summary_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.sample_output:
        args.sample_output.parent.mkdir(parents=True, exist_ok=True)
        args.sample_output.write_text(
            render_sample_markdown(report, samples_per_case=args.samples_per_case),
            encoding="utf-8",
        )
    if not args.quiet:
        print(rendered)
    return 0 if report["source_recall_at_k"] >= args.min_source_recall else 1


if __name__ == "__main__":
    raise SystemExit(main())
