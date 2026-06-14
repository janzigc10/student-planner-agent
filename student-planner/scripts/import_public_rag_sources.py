from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR


WIKIPEDIA_API_URL = "https://zh.wikipedia.org/w/api.php"
WIKIPEDIA_PAGE_URL = "https://zh.wikipedia.org/wiki/{title}"
WIKIPEDIA_VARIANT = "zh-cn"
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "rag" / "public"
DEFAULT_MAX_CHARS = 18000
DEFAULT_DELAY_SECONDS = 0.8


@dataclass(frozen=True)
class PublicSource:
    title: str
    topic: str


CORE_SOURCES = (
    PublicSource("五四运动", "中国近现代史"),
    PublicSource("辛亥革命", "中国近现代史"),
    PublicSource("中国抗日战争", "中国近现代史"),
    PublicSource("国共内战", "中国近现代史"),
    PublicSource("鸦片战争", "中国近现代史"),
    PublicSource("冷战", "世界现代史"),
    PublicSource("马歇尔计划", "世界现代史"),
    PublicSource("欧洲一体化", "世界现代史"),
    PublicSource("中华人民共和国宪法", "思想政治理论"),
    PublicSource("全过程人民民主", "思想政治理论"),
    PublicSource("共同富裕", "思想政治理论"),
)

EXPANDED_SOURCES = CORE_SOURCES + (
    PublicSource("第一次鸦片战争", "中国近现代史"),
    PublicSource("第二次鸦片战争", "中国近现代史"),
    PublicSource("太平天国", "中国近现代史"),
    PublicSource("洋务运动", "中国近现代史"),
    PublicSource("甲午战争", "中国近现代史"),
    PublicSource("戊戌变法", "中国近现代史"),
    PublicSource("义和团运动", "中国近现代史"),
    PublicSource("中华民国大陆时期", "中国近现代史"),
    PublicSource("新文化运动", "中国近现代史"),
    PublicSource("中国共产党", "中国近现代史"),
    PublicSource("北伐战争", "中国近现代史"),
    PublicSource("第一次国共合作", "中国近现代史"),
    PublicSource("南昌起义", "中国近现代史"),
    PublicSource("秋收起义", "中国近现代史"),
    PublicSource("井冈山革命根据地", "中国近现代史"),
    PublicSource("长征", "中国近现代史"),
    PublicSource("遵义会议", "中国近现代史"),
    PublicSource("抗日民族统一战线", "中国近现代史"),
    PublicSource("九一八事变", "中国近现代史"),
    PublicSource("西安事变", "中国近现代史"),
    PublicSource("南京大屠杀", "中国近现代史"),
    PublicSource("中华人民共和国成立", "中国近现代史"),
    PublicSource("土地改革运动", "中国近现代史"),
    PublicSource("抗美援朝", "中国近现代史"),
    PublicSource("改革开放", "中国近现代史"),
    PublicSource("第一次世界大战", "世界现代史"),
    PublicSource("巴黎和会", "世界现代史"),
    PublicSource("凡尔赛条约", "世界现代史"),
    PublicSource("国际联盟", "世界现代史"),
    PublicSource("第二次世界大战", "世界现代史"),
    PublicSource("雅尔塔会议", "世界现代史"),
    PublicSource("联合国", "世界现代史"),
    PublicSource("杜鲁门主义", "世界现代史"),
    PublicSource("北大西洋公约组织", "世界现代史"),
    PublicSource("华沙条约组织", "世界现代史"),
    PublicSource("柏林墙", "世界现代史"),
    PublicSource("古巴导弹危机", "世界现代史"),
    PublicSource("苏联解体", "世界现代史"),
    PublicSource("欧洲联盟", "世界现代史"),
    PublicSource("第三次科技革命", "世界现代史"),
    PublicSource("经济全球化", "世界现代史"),
    PublicSource("人民代表大会制度", "思想政治理论"),
    PublicSource("中国人民政治协商会议", "思想政治理论"),
    PublicSource("民族区域自治制度", "思想政治理论"),
    PublicSource("基层群众自治制度", "思想政治理论"),
    PublicSource("中国特色社会主义", "思想政治理论"),
    PublicSource("中国特色社会主义理论体系", "思想政治理论"),
    PublicSource("社会主义核心价值观", "思想政治理论"),
    PublicSource("依法治国", "思想政治理论"),
    PublicSource("法治中国", "思想政治理论"),
    PublicSource("新发展理念", "思想政治理论"),
    PublicSource("中国式现代化", "思想政治理论"),
    PublicSource("人类命运共同体", "思想政治理论"),
    PublicSource("马克思主义中国化", "思想政治理论"),
    PublicSource("习近平新时代中国特色社会主义思想", "思想政治理论"),
    PublicSource("机器学习", "机器学习课程报告"),
    PublicSource("监督学习", "机器学习课程报告"),
    PublicSource("无监督学习", "机器学习课程报告"),
    PublicSource("决策树", "机器学习课程报告"),
    PublicSource("支持向量机", "机器学习课程报告"),
    PublicSource("线性回归", "机器学习课程报告"),
    PublicSource("逻辑回归", "机器学习课程报告"),
    PublicSource("人工神经网络", "机器学习课程报告"),
    PublicSource("深度学习", "机器学习课程报告"),
    PublicSource("过拟合", "机器学习课程报告"),
    PublicSource("交叉验证", "机器学习课程报告"),
    PublicSource("主成分分析", "机器学习课程报告"),
    PublicSource("特征工程", "机器学习课程报告"),
    PublicSource("数据清洗", "机器学习课程报告"),
)


def _dedupe_sources(sources: tuple[PublicSource, ...]) -> tuple[PublicSource, ...]:
    seen: set[str] = set()
    deduped: list[PublicSource] = []
    for source in sources:
        if source.title in seen:
            continue
        seen.add(source.title)
        deduped.append(source)
    return tuple(deduped)


SOURCE_PRESETS = {
    "core": _dedupe_sources(CORE_SOURCES),
    "expanded": _dedupe_sources(EXPANDED_SOURCES),
}


def _slug(text: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE)
    return normalized.strip("-") or "source"


def _fetch_wikipedia_extract(title: str, *, retries: int = 2) -> dict[str, str]:
    query = urlencode(
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "format": "json",
            "titles": title,
            "variant": WIKIPEDIA_VARIANT,
        }
    )
    request = Request(
        f"{WIKIPEDIA_API_URL}?{query}",
        headers={"User-Agent": "StudentPlannerRAGImporter/1.0 (coursework demo)"},
    )
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as exc:
            if exc.code != 429 or attempt >= retries:
                raise
            time.sleep(2.0 + attempt * 3.0)

    pages = payload.get("query", {}).get("pages", {})
    if not pages:
        raise RuntimeError(f"No page returned for {title}")
    page = next(iter(pages.values()))
    if "missing" in page:
        raise RuntimeError(f"Missing page: {title}")
    return {
        "title": str(page.get("title") or title),
        "extract": str(page.get("extract") or "").strip(),
    }


def _trim_extract(text: str, max_chars: int) -> str:
    stop_markers = (
        "\n== 参见 ==",
        "\n== 參見 ==",
        "\n== 注释 ==",
        "\n== 註釋 ==",
        "\n== 参考文献 ==",
        "\n== 參考文獻 ==",
        "\n== 外部链接 ==",
        "\n== 外部連結 ==",
    )
    for marker in stop_markers:
        index = text.find(marker)
        if index >= 0:
            text = text[:index].strip()
            break
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars]
    paragraph_end = trimmed.rfind("\n\n")
    if paragraph_end > max_chars * 0.7:
        trimmed = trimmed[:paragraph_end]
    return trimmed.strip()


def _render_markdown(source: PublicSource, _resolved_title: str, extract: str, max_chars: int) -> str:
    display_title = source.title
    source_url = WIKIPEDIA_PAGE_URL.format(title=quote(display_title.replace(" ", "_")))
    trimmed = _trim_extract(extract, max_chars=max_chars)
    return (
        f"# 公开资料：{display_title}\n\n"
        f"- 主题：{source.topic}\n"
        f"- 来源：中文维基百科\n"
        f"- URL：{source_url}\n"
        f"- 许可：Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)\n"
        f"- 处理：用于课程 RAG 检索测试，按中文维基百科 zh-cn 变体获取简体正文，去除参考文献/外部链接等尾部章节，并按长度上限截取。\n\n"
        f"{trimmed}\n"
    )


def import_sources(
    output_dir: Path,
    max_chars: int,
    *,
    sources: tuple[PublicSource, ...],
    delay_seconds: float,
    skip_existing: bool,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    imported: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for source in sources:
        path = output_dir / f"维基百科-{_slug(source.title)}.md"
        try:
            if skip_existing and path.exists():
                imported.append(
                    {
                        "title": source.title,
                        "resolved_title": source.title,
                        "topic": source.topic,
                        "path": str(path.relative_to(BASE_DIR)),
                        "url": WIKIPEDIA_PAGE_URL.format(title=quote(source.title.replace(" ", "_"))),
                        "chars": len(path.read_text(encoding="utf-8")),
                        "skipped_existing": True,
                    }
                )
                continue
            time.sleep(delay_seconds)
            page = _fetch_wikipedia_extract(source.title)
            content = _render_markdown(source, page["title"], page["extract"], max_chars)
            path.write_text(content, encoding="utf-8")
            imported.append(
                {
                    "title": source.title,
                    "resolved_title": page["title"],
                    "topic": source.topic,
                    "path": str(path.relative_to(BASE_DIR)),
                    "url": WIKIPEDIA_PAGE_URL.format(title=quote(source.title.replace(" ", "_"))),
                    "chars": len(content),
                }
            )
        except Exception as exc:
            errors.append({"title": source.title, "error": f"{exc.__class__.__name__}: {exc}"})

    attribution = {
        "source": "中文维基百科",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/deed.zh-hans",
        "api": WIKIPEDIA_API_URL,
        "variant": WIKIPEDIA_VARIANT,
        "max_chars": max_chars,
        "requested_count": len(sources),
        "imported": imported,
        "errors": errors,
    }
    (output_dir / "PUBLIC_SOURCES.json").write_text(
        json.dumps(attribution, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return attribution


def main() -> int:
    parser = argparse.ArgumentParser(description="Import public open-license RAG sources.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--preset", choices=sorted(SOURCE_PRESETS), default="expanded")
    parser.add_argument("--limit", type=int, default=0, help="Import only the first N sources from the preset.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    sources = SOURCE_PRESETS[args.preset]
    if args.limit > 0:
        sources = sources[: args.limit]
    report = import_sources(
        args.output_dir,
        args.max_chars,
        sources=sources,
        delay_seconds=max(args.delay, 0.0),
        skip_existing=args.skip_existing,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["imported"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
