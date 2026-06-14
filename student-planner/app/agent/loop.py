import json
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, AsyncGenerator, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.guardrails import (
    GuardrailViolation,
    check_consecutive_ask_user,
    check_max_loop_iterations,
    check_max_retries,
    check_unknown_tool,
)
from app.agent.llm_client import AsyncOpenAI, chat_completion, chat_completion_stream
from app.agent.prompt import build_system_prompt
from app.agent.tool_preflight import (
    apply_tool_preflight,
    extract_reminder_slot,
    looks_like_task_update_intent,
    should_include_confirmed_question,
    task_tool_preflight_error,
    tool_schema_preflight_error,
)
from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.agent_log import AgentLog
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.services.context_compressor import compress_conversation_history, compress_tool_result
from app.services.period_converter import normalize_period
from app.services.schedule_upload_cache import get_schedule_upload

KNOWN_TOOLS = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
MAX_ITERATIONS = 20
VALID_ASK_TYPES = {"confirm", "select", "review"}
_SCHEDULE_IMPORT_KEYWORDS = (
    "上传",
    "文件",
    "file_id",
    "图片",
    "截图",
    "照片",
    "excel",
    "xlsx",
    "xls",
    "导入",
)
_COURSE_CONTEXT_KEYWORDS = (
    "课表",
    "课程",
    "日历",
    "两门课",
)
_COURSE_VIEW_KEYWORDS = (
    "查看",
    "看看",
    "看下",
    "看一下",
    "查一下",
    "查查",
    "有哪些",
    "有什么课",
    "列出",
    "现在课表",
)
_COURSE_EDIT_KEYWORDS = (
    "改成",
    "改为",
    "改名",
    "改一下",
    "修正",
    "纠正",
    "合并",
    "重复",
    "删掉",
    "删除",
    "保留",
    "优化成一门",
    "错别字",
)
_COURSE_DISAMBIGUATION_KEYWORDS = (
    "哪两门",
    "具体是哪两门",
    "删掉其中一门",
    "合并成一门",
    "确认一下具体",
)
_TASK_WRITE_CONTEXT_KEYWORDS = (
    "任务",
    "提醒",
    "作业",
    "安排",
    "创建",
    "新建",
    "新增",
    "改到",
    "改成",
    "改为",
    "修改",
    "调整",
    "换到",
    "挪到",
)
_TASK_WRITE_CONTEXT_PHRASES = (
    "复习计划",
    "学习计划",
    "备考计划",
    "拆复习任务",
    "拆学习任务",
    "复习任务",
    "学习任务",
    "写入日程",
    "加入日程",
    "落到日程",
)
_TASK_WRITE_ACTION_MARKERS = (
    "任务",
    "提醒",
    "日程",
    "创建",
    "新建",
    "新增",
    "写入",
    "落库",
    "加入",
    "安排",
    "规划",
    "制定",
    "生成",
    "拆",
    "分解",
    "改到",
    "改成",
    "改为",
    "修改",
    "调整",
    "换到",
    "挪到",
)
_INFORMATIONAL_QA_MARKERS = (
    "是什么",
    "为什么",
    "怎么理解",
    "如何理解",
    "解释",
    "说明",
    "区别",
    "关系",
    "作用",
    "意义",
    "原因",
    "概念",
    "定义",
    "判断",
    "简述",
    "论述",
    "分析",
    "怎么答",
    "怎么回答",
    "如何回答",
    "简答题",
    "考点",
    "用一句话",
    "一句话",
    "讲讲",
    "梳理",
    "总结",
)
_PLAIN_TEXT_ASK_CONFIRM_MARKERS = (
    "确认",
    "可以吗",
    "是否",
)
_PLAIN_TEXT_ASK_INFO_MARKERS = (
    "请告诉我",
    "请补充",
    "还需要",
    "需要你",
    "哪天",
    "什么时候",
    "几点",
    "日期",
    "具体时间",
    "时间段",
    "多久",
    "提前多久",
)
_TASK_WRITE_TOOLS = {"create_task", "update_task", "complete_task", "set_reminder"}
_TEXT_ONLY_STREAM_AFTER_TOOLS = {"recall_memory"}
_TOOL_INTENT_KEYWORDS = (
    *_SCHEDULE_IMPORT_KEYWORDS,
    *_COURSE_CONTEXT_KEYWORDS,
    *_COURSE_VIEW_KEYWORDS,
    *_COURSE_EDIT_KEYWORDS,
    *_TASK_WRITE_CONTEXT_KEYWORDS,
    *_TASK_WRITE_CONTEXT_PHRASES,
    "course",
    "schedule",
    "timetable",
    "task",
    "todo",
    "reminder",
    "studyplan",
    "workplan",
    "deadline",
    "assignment",
    "exam",
    "memory",
    "今天",
    "明天",
    "后天",
    "下周",
    "本周",
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
    "星期",
    "几点",
    "时间",
    "课",
    "上课",
    "日程",
    "空闲",
    "有空",
    "计划",
    "考试",
    "截止",
    "记忆",
    "长期记忆",
    "记得",
    "记住",
    "保存",
    "偏好",
    "习惯",
    "帮我",
    "查看",
    "查一下",
    "列出",
    "删除",
    "完成",
)

_SCHEDULE_FILE_ID_RE = re.compile(r"file_id\s*=\s*([a-zA-Z0-9\-]+)")
_SCHEDULE_PERIOD_ENTRY_RE = re.compile(
    r"(?P<period>\d{1,2}\s*[-~～—–]\s*\d{1,2})\s*(?:节|节次)?\s*[:：]?\s*"
    r"(?P<start>(?:[01]?\d|2[0-3]):[0-5]\d)\s*[-~～—–]\s*"
    r"(?P<end>(?:[01]?\d|2[0-3]):[0-5]\d)"
)
_SEMESTER_START_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_TERM_TOTAL_WEEKS_RE = re.compile(
    r"(?:学期(?:总)?周数|总周数|这学期(?:一共|共)?|本学期(?:一共|共)?|一共|共)\D{0,6}(\d{1,2})\s*周"
)
_TASK_CREATE_TITLE_RE = re.compile(r"(?:创建|新建|新增|加)(?:一个|一条)?(?P<title>.+?)的?任务")
_ISO_DATE_RE = re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?")
_COLON_TIME_RANGE_RE = re.compile(
    r"(?P<start>[01]?\d|2[0-3]):(?P<start_min>[0-5]\d)\s*[-~～—–到]\s*"
    r"(?P<end>[01]?\d|2[0-3]):(?P<end_min>[0-5]\d)"
)
_CN_TIME_RANGE_RE = re.compile(
    r"(?P<period>凌晨|早上|上午|中午|下午|晚上)?\s*"
    r"(?P<start>\d{1,2})\s*点\s*"
    r"(?:到|至|-|~|～|—|–)\s*"
    r"(?P<end>\d{1,2})\s*点"
)
_DAILY_LIMIT_RE = re.compile(
    r"(?:每天|每日|一天|一日|单日).{0,12}?"
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)\s*"
    r"(?P<unit>小时|钟头|h|H|分钟|分)"
)
_TOTAL_STUDY_DURATION_RE = re.compile(
    r"(?:花|用|安排|学|复习)?\s*"
    r"(?P<value>\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)\s*"
    r"(?:个)?\s*"
    r"(?P<unit>小时|钟头|h|H|分钟|分)"
)
_TARGET_SCORE_RE = re.compile(r"(?:目标|希望|争取|想考|要考|至少).{0,10}?(?P<score>\d{2,3})\s*分?")
_SCOPE_HINT_RE = re.compile(
    r"(?:unit|Unit|UNIT)\s*\d+|第\s*\d+\s*(?:-|到|至|~|～)\s*\d+\s*章|"
    r"第\s*\d+\s*章|第\s*\d+\s*(?:-|到|至|~|～)\s*\d+\s*单元|范围|章节|单元|重点"
)
_STUDY_CONTEXT_DEFAULT_REPLIES = {
    "按默认",
    "默认",
    "不知道",
    "不确定",
    "都可以",
    "你来安排",
    "你安排",
    "没有",
    "无",
}
_STUDY_WEAK_AREA_KEYWORDS = (
    "听力",
    "写作",
    "作文",
    "阅读",
    "翻译",
    "语法",
    "词汇",
    "单词",
    "口语",
    "错题",
    "真题",
    "计算",
    "证明",
    "公式",
)
_STUDY_CONTEXT_DETAIL_KEYWORDS = (
    "详细",
    "具体",
    "精准",
    "精确",
    "定制",
    "个性化",
    "冲刺",
    "提分",
    "高分",
    "保过",
    "高效",
    "专项",
    "针对",
)
_WORK_PLAN_KEYWORDS = (
    "实验报告",
    "大作业",
    "presentation",
    "project",
    "报告",
    "作业",
    "论文",
    "项目",
    "展示",
)
_WORK_PLAN_DEADLINE_KEYWORDS = (
    "要交",
    "提交",
    "截止",
    "ddl",
    "deadline",
    "due",
    "交",
)
_WORK_CONTEXT_DEFAULT_REPLIES = {
    "按默认",
    "默认",
    "不知道",
    "不确定",
    "都可以",
    "你来安排",
    "你安排",
    "没有",
    "无",
}
_WORK_REQUIREMENT_HINT_RE = re.compile(
    r"(?:pdf|ppt|word|页|字|实验|参考文献|格式|要求|评分|代码|数据|图表|展示|答辩|初稿|已经|完成)"
)
_PLAN_ADJUSTMENT_KEYWORDS = (
    "太满",
    "太多",
    "压缩",
    "减少",
    "改成每天",
    "调整",
    "改成",
    "改为",
)
_COURSE_RENAME_PATTERNS = (
    re.compile(r"(?:把|将)?(?P<old>.+?)(?:改成|改为|改名为|统一成|统一为)(?P<new>.+)"),
    re.compile(r"(?:把|将)?(?P<old>.+?)(?:改名|更名)(?:为|成)?(?P<new>.+)"),
)
_COURSE_DELETE_RE = re.compile(r"(?:删掉|删除|去掉|移除)(?P<target>.+)")


def _normalize_ask_type(result: dict[str, Any]) -> str:
    ask_type = result.get("type")
    if ask_type not in VALID_ASK_TYPES:
        return "review"

    options = result.get("options")
    has_options = isinstance(options, list) and len(options) > 0
    has_data = result.get("data") is not None

    if ask_type == "confirm" and not has_options and not has_data:
        return "review"

    return ask_type


def _to_persisted_tool_summary(tool_name: str, tool_result_content: str) -> str:
    if tool_result_content.startswith("[TOOL_SUMMARY:"):
        return tool_result_content
    return f"[TOOL_SUMMARY:{tool_name}:v1] {tool_result_content}"


async def _persist_local_tool_step(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    step: int,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: dict[str, Any],
) -> None:
    await _save_message(
        db,
        session_id,
        "assistant",
        _to_persisted_tool_summary(tool_name, compress_tool_result(tool_name, tool_result)),
        is_compressed=True,
    )
    await _log_step(db, user_id, session_id, step, tool_name, tool_args, tool_result)


def _build_course_routing_hint(
    user_message: str,
    history_messages: list[ConversationMessage],
) -> str | None:
    compact_message = (user_message or "").strip().lower().replace(" ", "")
    if not compact_message:
        return None

    if any(keyword in compact_message for keyword in _SCHEDULE_IMPORT_KEYWORDS):
        return None

    mentions_course_context = any(keyword in compact_message for keyword in _COURSE_CONTEXT_KEYWORDS)
    wants_to_view_courses = mentions_course_context and any(
        keyword in compact_message for keyword in _COURSE_VIEW_KEYWORDS
    )
    wants_to_edit_courses = mentions_course_context and any(
        keyword in compact_message for keyword in _COURSE_EDIT_KEYWORDS
    )

    last_assistant_message = next(
        (
            str(message.content)
            for message in reversed(history_messages)
            if message.role == "assistant" and message.content
        ),
        "",
    )
    is_course_followup = bool(last_assistant_message) and any(
        keyword in last_assistant_message for keyword in _COURSE_DISAMBIGUATION_KEYWORDS
    )

    if wants_to_edit_courses or is_course_followup:
        return (
            "这是当前数据库里已有课程的管理请求，不是重新导入课表。"
            "不要要求用户重新上传文件，也不要只做寒暄。"
            "先调用 `list_courses` 查看现有课程。"
            "如果用户是在纠正 OCR/导入错字、统一课程名或合并重复课程，"
            "先用 `ask_user` 确认最终保留方案，再调用 `update_course` 修改要保留的课程，"
            "必要时调用 `delete_course` 删除重复或错误记录。"
        )

    if wants_to_view_courses:
        return (
            "这是查看当前课表的请求。"
            "直接调用 `list_courses` 查看现有课程，不要要求用户上传文件。"
        )

    return None


def _is_course_followup_message(
    user_message: str,
    history_messages: list[ConversationMessage],
) -> bool:
    compact_message = (user_message or "").strip().lower().replace(" ", "")
    if not compact_message:
        return False
    if any(keyword in compact_message for keyword in _SCHEDULE_IMPORT_KEYWORDS):
        return False

    last_assistant_message = next(
        (
            str(message.content)
            for message in reversed(history_messages)
            if message.role == "assistant" and message.content
        ),
        "",
    )
    return bool(last_assistant_message) and any(
        keyword in last_assistant_message for keyword in _COURSE_DISAMBIGUATION_KEYWORDS
    )


def _build_task_routing_hint(user_message: str) -> str | None:
    if not looks_like_task_update_intent([user_message]):
        return None
    return (
        "这是已有普通任务的修改请求，不是创建两个新任务。"
        "先调用 `list_tasks` 查找目标任务；确认后调用 `update_task` 修改同一个 task。"
        "如果用户同时提到提醒提前分钟，`update_task` 参数必须包含 `reminder_advance_minutes`。"
        "如果用户说不提醒或取消提醒，也要调用 `update_task`，并传入 `reminder_advance_minutes=null`。"
        "除非用户明确要求新建任务，否则不要调用 `create_task`。"
    )


def _compact_user_texts(user_texts: list[str]) -> str:
    texts = [str(text or "") for text in user_texts if str(text or "").strip()]
    return "\n".join(texts).lower().replace(" ", "")


def _latest_compact_user_text(user_texts: list[str]) -> str:
    texts = [str(text or "") for text in user_texts if str(text or "").strip()]
    return texts[-1].lower().replace(" ", "") if texts else ""


def _has_compact_keyword(compact_text: str, keywords: tuple[str, ...]) -> bool:
    return any(str(keyword).lower().replace(" ", "") in compact_text for keyword in keywords)


def _looks_like_task_write_context(user_texts: list[str]) -> bool:
    compact_text = _compact_user_texts(user_texts)
    if not compact_text:
        return False

    latest_text = _latest_compact_user_text(user_texts)
    explicit_write_intent = any(marker in latest_text for marker in _TASK_WRITE_ACTION_MARKERS)
    explicit_write_intent = explicit_write_intent or any(
        phrase in latest_text for phrase in _TASK_WRITE_CONTEXT_PHRASES
    )
    is_informational_qa = any(marker in latest_text for marker in _INFORMATIONAL_QA_MARKERS)
    if is_informational_qa and not explicit_write_intent:
        return False

    if any(phrase in compact_text for phrase in _TASK_WRITE_CONTEXT_PHRASES):
        return True
    return any(keyword in compact_text for keyword in _TASK_WRITE_CONTEXT_KEYWORDS)


def _looks_like_tool_intent(user_texts: list[str]) -> bool:
    compact_text = _compact_user_texts(user_texts)
    if not compact_text:
        return False

    latest_text = _latest_compact_user_text(user_texts)
    explicit_write_intent = any(marker in latest_text for marker in _TASK_WRITE_ACTION_MARKERS)
    explicit_write_intent = explicit_write_intent or any(
        phrase in latest_text for phrase in _TASK_WRITE_CONTEXT_PHRASES
    )
    is_informational_qa = any(marker in latest_text for marker in _INFORMATIONAL_QA_MARKERS)
    if is_informational_qa and not explicit_write_intent:
        return False

    if _looks_like_task_write_context(user_texts) or looks_like_task_update_intent(user_texts):
        return True
    return _has_compact_keyword(compact_text, _TOOL_INTENT_KEYWORDS)


def _looks_like_plain_text_ask(text: str) -> bool:
    compact_text = (text or "").strip().lower().replace(" ", "")
    if not compact_text:
        return False

    if _looks_like_plain_text_confirmation(text):
        return True
    return any(marker in compact_text for marker in _PLAIN_TEXT_ASK_INFO_MARKERS)


def _looks_like_plain_text_confirmation(text: str) -> bool:
    compact_text = (text or "").strip().lower().replace(" ", "")
    if "请确认" in compact_text or "确认以下" in compact_text or "确认一下" in compact_text:
        return True
    has_question_mark = "？" in compact_text or "?" in compact_text or "吗" in compact_text
    return has_question_mark and any(marker in compact_text for marker in _PLAIN_TEXT_ASK_CONFIRM_MARKERS)


def _plain_text_ask_tool_args(text: str) -> dict[str, Any]:
    compact_text = (text or "").strip().lower().replace(" ", "")
    asks_for_missing_info = any(marker in compact_text for marker in _PLAIN_TEXT_ASK_INFO_MARKERS)
    ask_type = "confirm" if _looks_like_plain_text_confirmation(text) and not asks_for_missing_info else "review"
    args: dict[str, Any] = {"question": text.strip(), "type": ask_type}
    if ask_type == "confirm":
        args["options"] = ["确认", "取消"]
    return args


def _should_require_task_tool_response(user_texts: list[str], tool_history: list[str]) -> bool:
    if not _looks_like_task_write_context(user_texts):
        return False
    return not any(tool_name in _TASK_WRITE_TOOLS for tool_name in tool_history)


def _should_use_text_only_stream(user_texts: list[str], tool_history: list[str]) -> bool:
    if tool_history:
        return tool_history[-1] in _TEXT_ONLY_STREAM_AFTER_TOOLS
    return not _looks_like_tool_intent(user_texts)


async def _build_initial_messages(
    system_prompt: str,
    history_messages: list[ConversationMessage],
    llm_client: AsyncOpenAI,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for message in history_messages:
        messages.append({"role": message.role, "content": message.content})

    return await compress_conversation_history(messages, llm_client)


def _should_handle_missing_task_create_locally(user_message: str) -> bool:
    compact_message = (user_message or "").strip().replace(" ", "")
    if not compact_message:
        return False
    if not any(keyword in compact_message for keyword in ("创建", "新建", "新增", "加")):
        return False
    if "任务" not in compact_message:
        return False
    has_date = _ISO_DATE_RE.search(compact_message) is not None
    has_time = _COLON_TIME_RANGE_RE.search(compact_message) is not None or _CN_TIME_RANGE_RE.search(compact_message) is not None
    return not (has_date and has_time)


def _extract_task_title(user_message: str, fallback_answer: str = "") -> str:
    for text in (user_message, fallback_answer):
        match = _TASK_CREATE_TITLE_RE.search(text or "")
        if match is not None:
            title = match.group("title").strip(" ：:，,。.")
            if title:
                return title
    return "学习任务"


def _normalize_hour(raw_hour: str, period: str | None) -> int:
    hour = int(raw_hour)
    if period in {"下午", "晚上"} and hour < 12:
        return hour + 12
    if period == "中午" and hour < 11:
        return hour + 12
    if period == "凌晨" and hour == 12:
        return 0
    return hour


def _extract_task_schedule(answer: str) -> dict[str, str] | None:
    date_match = _ISO_DATE_RE.search(answer or "")
    if date_match is None:
        return None
    year, month, day = (int(part) for part in date_match.groups())
    scheduled_date = f"{year:04d}-{month:02d}-{day:02d}"

    colon_match = _COLON_TIME_RANGE_RE.search(answer or "")
    if colon_match is not None:
        start_time = f"{int(colon_match.group('start')):02d}:{int(colon_match.group('start_min')):02d}"
        end_time = f"{int(colon_match.group('end')):02d}:{int(colon_match.group('end_min')):02d}"
        return {"scheduled_date": scheduled_date, "start_time": start_time, "end_time": end_time}

    cn_match = _CN_TIME_RANGE_RE.search(answer or "")
    if cn_match is None:
        return None
    period = cn_match.group("period")
    start_hour = _normalize_hour(cn_match.group("start"), period)
    end_hour = _normalize_hour(cn_match.group("end"), period)
    return {
        "scheduled_date": scheduled_date,
        "start_time": f"{start_hour:02d}:00",
        "end_time": f"{end_hour:02d}:00",
    }


def _is_cancelled_answer(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    return normalized.startswith(("取消", "先不", "不做", "不用", "no"))


def _parse_study_number(value: str) -> float | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    if value == "半":
        return 0.5
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1 if left == "" else None)
        ones = digits.get(right, 0 if right == "" else None)
        if tens is None or ones is None:
            return None
        return float(tens * 10 + ones)
    if value in digits:
        return float(digits[value])
    return None


def _extract_daily_study_limit_minutes(text: str) -> int | None:
    match = _DAILY_LIMIT_RE.search(text or "")
    if match is None:
        return None
    number = _parse_study_number(match.group("value"))
    if number is None:
        return None
    unit = match.group("unit")
    if unit in {"小时", "钟头", "h", "H"}:
        return int(number * 60)
    return int(number)


def _extract_study_context_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    compact = raw.strip().lower().replace(" ", "")
    if compact in _STUDY_CONTEXT_DEFAULT_REPLIES:
        return {"raw_notes": raw, "using_defaults": True}

    context: dict[str, Any] = {"raw_notes": raw}
    daily_limit = _extract_daily_study_limit_minutes(raw)
    if daily_limit is not None:
        context["daily_study_limit_minutes"] = daily_limit

    target_match = _TARGET_SCORE_RE.search(raw)
    if target_match is not None:
        context["target_score"] = f"{target_match.group('score')}分"

    weak_areas = [keyword for keyword in _STUDY_WEAK_AREA_KEYWORDS if keyword in raw]
    if "弱" in raw or "薄弱" in raw or weak_areas:
        context["weak_areas"] = weak_areas or ["用户提到薄弱项，但未明确具体科目"]

    if _SCOPE_HINT_RE.search(raw):
        context["exam_scope"] = raw

    if _study_context_has_quality(context):
        return context
    return {}


def _study_context_has_quality(study_context: Any) -> bool:
    if not isinstance(study_context, dict):
        return False
    if study_context.get("using_defaults") is True:
        return True
    for key in ("exam_scope", "weak_areas", "target_score", "daily_study_limit_minutes"):
        value = study_context.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and len(value) > 0:
            return True
        if isinstance(value, int) and value > 0:
            return True
    raw_notes = str(study_context.get("raw_notes") or "").strip()
    if not raw_notes:
        return False
    raw_compact = raw_notes.lower().replace(" ", "")
    if raw_compact in _STUDY_CONTEXT_DEFAULT_REPLIES:
        return True
    return bool(
        _SCOPE_HINT_RE.search(raw_notes)
        or _DAILY_LIMIT_RE.search(raw_notes)
        or _TARGET_SCORE_RE.search(raw_notes)
        or any(keyword in raw_notes for keyword in _STUDY_WEAK_AREA_KEYWORDS)
    )


def _study_context_from_reference_texts(reference_texts: list[str]) -> dict[str, Any]:
    for text in reversed(reference_texts):
        context = _extract_study_context_from_text(text)
        if _study_context_has_quality(context):
            return context
    return {}


def _has_complete_exam_info(exams: Any) -> bool:
    if not isinstance(exams, list) or not exams:
        return False
    for exam in exams:
        if not isinstance(exam, dict):
            return False
        if not str(exam.get("course_name") or "").strip():
            return False
        if not str(exam.get("exam_date") or "").strip():
            return False
    return True


def _wants_detailed_study_context(text: str) -> bool:
    return any(keyword in (text or "") for keyword in _STUDY_CONTEXT_DETAIL_KEYWORDS)


def _should_default_study_context(reference_texts: list[str], tool_args: dict[str, Any]) -> bool:
    if not _has_complete_exam_info(tool_args.get("exams")):
        return False
    combined = "\n".join(str(text or "") for text in reference_texts)
    return not _wants_detailed_study_context(combined)


def _has_real_available_slots(available_slots: Any) -> bool:
    if not isinstance(available_slots, dict):
        return False
    slots = available_slots.get("slots")
    if not isinstance(slots, list) or not slots:
        return False
    return all(
        isinstance(day, dict)
        and isinstance(day.get("free_periods"), list)
        and "date" in day
        for day in slots
    )


def _study_plan_intake_question(tool_args: dict[str, Any]) -> str:
    exams = tool_args.get("exams")
    course_names: list[str] = []
    if isinstance(exams, list):
        for exam in exams:
            if isinstance(exam, dict):
                course_name = str(exam.get("course_name") or "").strip()
                if course_name:
                    course_names.append(course_name)
    course_text = "、".join(course_names) if course_names else "这门考试"
    return (
        f"为了把「{course_text}」的复习任务拆得更准，请补充：复习范围/章节、薄弱点、"
        "目标成绩，以及每天最多能学多久。比如：范围 Unit1-6，听力和写作薄弱，"
        "目标 80 分，每天最多 2 小时。也可以回复“按默认”。"
    )


def _looks_like_study_plan_request(user_message: str) -> bool:
    text = (user_message or "").strip()
    if not text:
        return False
    if any(keyword in text for keyword in _SCHEDULE_IMPORT_KEYWORDS):
        return False
    return bool(
        ("考试" in text and any(keyword in text for keyword in ("复习计划", "学习计划", "安排", "拆")))
        or "备考计划" in text
        or "拆复习任务" in text
    )


def _should_collect_study_context_locally(user_message: str) -> bool:
    if not _looks_like_study_plan_request(user_message):
        return False
    if _ISO_DATE_RE.search(user_message or "") is None:
        return False
    if not _wants_detailed_study_context(user_message):
        return False
    return not _study_context_has_quality(_extract_study_context_from_text(user_message))


def _extract_total_study_duration_minutes(text: str) -> int | None:
    match = _TOTAL_STUDY_DURATION_RE.search(text or "")
    if match is None:
        return None
    number = _parse_study_number(match.group("value"))
    if number is None:
        return None
    unit = match.group("unit")
    if unit in {"小时", "钟头", "h", "H"}:
        return int(number * 60)
    return int(number)


def _extract_short_review_subjects(text: str) -> list[str]:
    match = re.search(
        r"复习(?:一下|下)?(?P<subjects>.+?)(?:，|,|。|；|;|你来|帮我|给我|做一下|规划|安排|吧|$)",
        text or "",
    )
    if match is None:
        return []
    raw_subjects = match.group("subjects")
    raw_subjects = re.sub(r"(?:一下|下|内容|任务|计划)$", "", raw_subjects).strip()
    parts = re.split(r"\s*(?:和|与|以及|、|/|，|,)\s*", raw_subjects)
    subjects: list[str] = []
    for part in parts:
        subject = part.strip(" ：:，,。.?？；;！!的")
        if not subject or subject in {"复习", "学习", "今晚", "今天晚上", "晚上"}:
            continue
        if subject not in subjects:
            subjects.append(subject)
    return subjects[:4]


def _extract_tonight_review_request(user_message: str) -> dict[str, Any] | None:
    text = (user_message or "").strip()
    if not text or "复习" not in text:
        return None
    if not any(keyword in text for keyword in ("今晚", "今天晚上", "晚上")):
        return None
    duration_minutes = _extract_total_study_duration_minutes(text)
    if duration_minutes is None or duration_minutes < 30:
        return None
    subjects = _extract_short_review_subjects(text)
    if not subjects:
        return None
    return {"subjects": subjects, "duration_minutes": duration_minutes}


def _should_handle_tonight_review_locally(user_message: str) -> bool:
    return _extract_tonight_review_request(user_message) is not None


def _extract_first_iso_date(text: str) -> str | None:
    match = _ISO_DATE_RE.search(text or "")
    if match is None:
        return None
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _extract_work_item_title(user_message: str) -> str:
    text = re.sub(_ISO_DATE_RE, "", user_message or "")
    for keyword in sorted(_WORK_PLAN_KEYWORDS, key=len, reverse=True):
        index = text.lower().find(keyword.lower())
        if index < 0:
            continue
        fragment = text[max(0, index - 14) : index + len(keyword)]
        fragment = re.sub(r".*(?:要交|提交|截止|完成|写|做|有|帮我|把|这个|那个)", "", fragment)
        fragment = fragment.strip(" ：:，,。.?？（）()“”\"'的")
        if fragment and keyword in fragment:
            return fragment
        return keyword
    return "作业任务"


def _extract_work_type(title: str) -> str:
    lowered = title.lower()
    if "实验报告" in title:
        return "lab report"
    if "报告" in title:
        return "report"
    if "论文" in title:
        return "essay"
    if "大作业" in title or "项目" in title or "project" in lowered:
        return "project"
    if "presentation" in lowered or "展示" in title:
        return "presentation"
    return "assignment"


def _extract_work_context_from_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    compact = raw.strip().lower().replace(" ", "")
    if compact in _WORK_CONTEXT_DEFAULT_REPLIES:
        return {"raw_notes": raw, "using_defaults": True}

    context: dict[str, Any] = {"raw_notes": raw}
    daily_limit = _extract_daily_study_limit_minutes(raw)
    if daily_limit is not None:
        context["daily_work_limit_minutes"] = daily_limit
    if _WORK_REQUIREMENT_HINT_RE.search(raw):
        context["requirements"] = raw
    if any(marker in raw for marker in ("已经", "做完", "写了", "完成了", "还没开始")):
        context["current_progress"] = raw
    if _work_context_has_quality(context):
        return context
    return {}


def _work_context_has_quality(work_context: Any) -> bool:
    if not isinstance(work_context, dict):
        return False
    if work_context.get("using_defaults") is True:
        return True
    for key in ("requirements", "current_progress", "daily_work_limit_minutes"):
        value = work_context.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, int) and value > 0:
            return True
    raw_notes = str(work_context.get("raw_notes") or "").strip()
    if not raw_notes:
        return False
    raw_compact = raw_notes.lower().replace(" ", "")
    if raw_compact in _WORK_CONTEXT_DEFAULT_REPLIES:
        return True
    return bool(_WORK_REQUIREMENT_HINT_RE.search(raw_notes) or _DAILY_LIMIT_RE.search(raw_notes))


def _work_context_from_reference_texts(reference_texts: list[str]) -> dict[str, Any]:
    for text in reversed(reference_texts):
        context = _extract_work_context_from_text(text)
        if _work_context_has_quality(context):
            return context
    return {}


def _work_plan_intake_question(title: str) -> str:
    return (
        f"为了把「{title}」拆得更准，请补充交付要求、格式/页数或评分点、当前进度，"
        "以及每天最多能投入多久。比如：需要 5 页 PDF，包括实验结果和参考文献，"
        "现在还没开始，每天最多 2 小时。也可以回复“按默认”。"
    )


def _looks_like_work_plan_request(user_message: str) -> bool:
    text = (user_message or "").strip()
    if not text:
        return False
    if any(keyword in text for keyword in _SCHEDULE_IMPORT_KEYWORDS):
        return False
    mentions_work = any(keyword.lower() in text.lower() for keyword in _WORK_PLAN_KEYWORDS)
    mentions_deadline = any(keyword.lower() in text.lower() for keyword in _WORK_PLAN_DEADLINE_KEYWORDS)
    asks_to_decompose = any(keyword in text for keyword in ("拆", "安排", "计划", "分解"))
    return mentions_work and (mentions_deadline or asks_to_decompose) and _extract_first_iso_date(text) is not None


def _should_handle_work_plan_locally(user_message: str) -> bool:
    return _looks_like_work_plan_request(user_message)


def _should_collect_work_context_locally(user_message: str) -> bool:
    if not _looks_like_work_plan_request(user_message):
        return False
    return not _work_context_has_quality(_extract_work_context_from_text(user_message))


def _normalize_study_plan_task(raw_task: dict[str, Any]) -> dict[str, Any] | None:
    title = str(raw_task.get("title") or "").strip()
    exam_name = str(raw_task.get("exam_name") or raw_task.get("course_name") or "").strip()
    scheduled_date = str(raw_task.get("scheduled_date") or raw_task.get("date") or "").strip()
    start_time = str(raw_task.get("start_time") or "").strip()
    end_time = str(raw_task.get("end_time") or "").strip()
    description = str(raw_task.get("description") or "").strip()

    if not title and exam_name:
        title = f"{exam_name} - 复习"
    elif exam_name and exam_name not in title:
        title = f"{exam_name} - {title}"

    if not title or not scheduled_date or not start_time or not end_time:
        return None

    task_args: dict[str, Any] = {
        "title": title,
        "scheduled_date": scheduled_date,
        "start_time": start_time,
        "end_time": end_time,
    }
    if description:
        task_args["description"] = description
    return task_args


def _normalize_study_plan_tasks(raw_tasks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tasks, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            continue
        task_args = _normalize_study_plan_task(raw_task)
        if task_args is not None:
            normalized.append(task_args)

    return normalized


def _normalize_work_plan_task(raw_task: dict[str, Any]) -> dict[str, Any] | None:
    title = str(raw_task.get("title") or "").strip()
    work_item_name = str(raw_task.get("work_item_name") or raw_task.get("work_item") or "").strip()
    scheduled_date = str(raw_task.get("scheduled_date") or raw_task.get("date") or "").strip()
    start_time = str(raw_task.get("start_time") or "").strip()
    end_time = str(raw_task.get("end_time") or "").strip()
    description = str(raw_task.get("description") or "").strip()

    if not title and work_item_name:
        title = f"{work_item_name} - 任务"
    elif work_item_name and work_item_name not in title:
        title = f"{work_item_name} - {title}"

    if not title or not scheduled_date or not start_time or not end_time:
        return None

    task_args: dict[str, Any] = {
        "title": title,
        "scheduled_date": scheduled_date,
        "start_time": start_time,
        "end_time": end_time,
    }
    if description:
        task_args["description"] = description
    return task_args


def _normalize_work_plan_tasks(raw_tasks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tasks, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            continue
        task_args = _normalize_work_plan_task(raw_task)
        if task_args is not None:
            normalized.append(task_args)

    return normalized


def _study_plan_review_data(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tasks": tasks,
        "count": len(tasks),
    }


def _plan_task_date_range(tasks: list[dict[str, Any]]) -> tuple[str, str] | None:
    dates: list[str] = []
    for task in tasks:
        scheduled_date = str(task.get("scheduled_date") or "")
        try:
            date.fromisoformat(scheduled_date)
        except ValueError:
            continue
        dates.append(scheduled_date)
    if not dates:
        return None
    return min(dates), max(dates)


def _time_to_minutes(value: str) -> int | None:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute


def _is_time_conflict_result(result: dict[str, Any]) -> bool:
    error = str(result.get("error") or "").lower()
    return "conflict" in error or "时间冲突" in error


def _reschedule_candidate_rank(
    original_date: str,
    original_start: str,
    candidate_date: str,
    candidate_start: str,
) -> tuple[int, str, int]:
    original_start_minutes = _time_to_minutes(original_start) or 0
    candidate_start_minutes = _time_to_minutes(candidate_start) or 0
    if candidate_date == original_date and candidate_start_minutes >= original_start_minutes:
        rank = 0
    elif candidate_date > original_date:
        rank = 1
    elif candidate_date == original_date:
        rank = 2
    else:
        rank = 3
    return rank, candidate_date, candidate_start_minutes


def _find_rescheduled_task_args(
    task_args: dict[str, Any],
    free_slots_result: dict[str, Any],
) -> dict[str, Any] | None:
    duration = _task_duration_minutes(task_args)
    if duration is None:
        return None

    original_date = str(task_args.get("scheduled_date") or "")
    original_start = str(task_args.get("start_time") or "")
    candidates: list[tuple[tuple[int, str, int], dict[str, Any]]] = []
    slots = free_slots_result.get("slots")
    if not isinstance(slots, list):
        return None

    for day in slots:
        if not isinstance(day, dict):
            continue
        candidate_date = str(day.get("date") or "")
        periods = day.get("free_periods")
        if not candidate_date or not isinstance(periods, list):
            continue
        for period in periods:
            if not isinstance(period, dict):
                continue
            start_time = str(period.get("start") or "")
            try:
                available_minutes = int(period.get("duration_minutes") or 0)
            except (TypeError, ValueError):
                continue
            if not start_time or available_minutes < duration:
                continue
            rescheduled = dict(task_args)
            rescheduled["scheduled_date"] = candidate_date
            rescheduled["start_time"] = start_time
            rescheduled["end_time"] = _time_after_minutes(start_time, duration)
            if (
                rescheduled.get("scheduled_date") == task_args.get("scheduled_date")
                and rescheduled.get("start_time") == task_args.get("start_time")
                and rescheduled.get("end_time") == task_args.get("end_time")
            ):
                continue
            candidates.append(
                (
                    _reschedule_candidate_rank(
                        original_date=original_date,
                        original_start=original_start,
                        candidate_date=candidate_date,
                        candidate_start=start_time,
                    ),
                    rescheduled,
                )
            )

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _clean_course_name_fragment(value: str) -> str:
    text = str(value or "").strip()
    text = text.strip(" \t\r\n，,。.?？:：；;！!\"'“”‘’`")
    prefixes = (
        "课表里的",
        "课表里",
        "课程里的",
        "课程里",
        "日历里的",
        "日历里",
        "那个",
        "这个",
        "这门课程",
        "这门课",
        "课程",
    )
    suffixes = (
        "这门课程",
        "这门课",
        "这个课程",
        "这个课",
        "这条记录",
        "这条",
        "记录",
        "课程",
        "一下",
        "吧",
        "啦",
        "了",
    )
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip(" \t\r\n，,。.?？:：；;！!\"'“”‘’`")
                changed = True
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip(" \t\r\n，,。.?？:：；;！!\"'“”‘’`")
                changed = True
    return text


def _parse_course_rename_request(user_text: str) -> dict[str, str] | None:
    text = str(user_text or "").strip()
    for pattern in _COURSE_RENAME_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        old_name = _clean_course_name_fragment(match.group("old"))
        new_name = _clean_course_name_fragment(match.group("new"))
        if len(old_name) >= 2 and len(new_name) >= 2 and old_name != new_name:
            return {"kind": "rename", "old_name": old_name, "new_name": new_name}
    return None


def _parse_course_delete_request(user_text: str) -> dict[str, str] | None:
    match = _COURSE_DELETE_RE.search(str(user_text or ""))
    if match is None:
        return None
    target_name = _clean_course_name_fragment(match.group("target"))
    if len(target_name) < 2:
        return None
    return {"kind": "delete", "target_name": target_name}


def _course_slot_key(course: dict[str, Any]) -> tuple[Any, ...]:
    return (
        course.get("weekday"),
        course.get("start_time"),
        course.get("end_time"),
        course.get("location") or "",
        course.get("week_start"),
        course.get("week_end"),
        course.get("week_pattern") or "all",
    )


def _should_handle_course_merge_locally(
    user_message: str,
    history_messages: list[ConversationMessage],
) -> bool:
    return _course_maintenance_intent(user_message, history_messages) is not None


def _course_maintenance_intent(
    user_message: str,
    history_messages: list[ConversationMessage],
) -> dict[str, str] | None:
    compact_message = (user_message or "").strip().lower().replace(" ", "")
    if not compact_message:
        return None
    if any(keyword in compact_message for keyword in _SCHEDULE_IMPORT_KEYWORDS):
        return None

    mentions_course_context = any(keyword in compact_message for keyword in _COURSE_CONTEXT_KEYWORDS)
    if any(keyword in compact_message for keyword in ("任务", "提醒")) and not mentions_course_context:
        return None

    rename_intent = _parse_course_rename_request(user_message)
    if rename_intent is not None:
        return rename_intent

    delete_intent = _parse_course_delete_request(user_message)
    if delete_intent is not None and (mentions_course_context or "课" in compact_message):
        return delete_intent

    merge_keywords = ("优化成一门", "合并成一门", "还是两门课", "重复课程", "重复的课")
    if any(keyword in compact_message for keyword in merge_keywords):
        return {"kind": "merge"}
    if _is_course_followup_message(user_message, history_messages):
        return {"kind": "merge"}
    return None


def _match_courses_from_text(user_text: str, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for course in courses:
        course_name = str(course.get("name") or "").strip()
        if course_name and course_name in user_text:
            matches.append(course)
    return matches


def _match_courses_by_name_fragment(fragment: str, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target = _clean_course_name_fragment(fragment)
    if len(target) < 2:
        return []

    exact_matches = [course for course in courses if str(course.get("name") or "").strip() == target]
    if exact_matches:
        return sorted(
            exact_matches,
            key=lambda course: (
                course.get("weekday") or 999,
                str(course.get("start_time") or ""),
                str(course.get("end_time") or ""),
                str(course.get("id") or ""),
            ),
        )

    fuzzy_matches = []
    for course in courses:
        course_name = str(course.get("name") or "").strip()
        if course_name and (course_name in target or target in course_name):
            fuzzy_matches.append(course)
    return sorted(
        fuzzy_matches,
        key=lambda course: (
            course.get("weekday") or 999,
            str(course.get("start_time") or ""),
            str(course.get("end_time") or ""),
            str(course.get("id") or ""),
        ),
    )


def _course_snapshot(course: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(course.get("id") or ""),
        "name": str(course.get("name") or ""),
        "teacher": course.get("teacher"),
        "location": course.get("location"),
        "weekday": course.get("weekday"),
        "start_time": course.get("start_time"),
        "end_time": course.get("end_time"),
        "week_start": course.get("week_start"),
        "week_end": course.get("week_end"),
        "week_pattern": course.get("week_pattern") or "all",
        "week_text": course.get("week_text"),
    }


def _build_course_rename_actions(
    old_name: str,
    new_name: str,
    courses: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    matches = _match_courses_by_name_fragment(old_name, courses)
    if not matches:
        return [], "not_found"

    actions: list[dict[str, Any]] = []
    for course in matches:
        same_slot_canonical = next(
            (
                candidate
                for candidate in courses
                if str(candidate.get("id") or "") != str(course.get("id") or "")
                and str(candidate.get("name") or "").strip() == new_name
                and _course_slot_key(candidate) == _course_slot_key(course)
            ),
            None,
        )
        if same_slot_canonical is not None:
            actions.append(
                {
                    "action": "delete",
                    "course": _course_snapshot(course),
                    "reason": f"同一时段已存在「{new_name}」，删除重复错名记录",
                    "canonical_course": _course_snapshot(same_slot_canonical),
                }
            )
            continue
        actions.append(
            {
                "action": "update",
                "course": _course_snapshot(course),
                "updates": {"name": new_name},
                "reason": f"把课程名改为「{new_name}」",
            }
        )
    return actions, None


def _build_course_delete_actions(
    target_name: str,
    courses: list[dict[str, Any]],
    user_text: str,
) -> tuple[list[dict[str, Any]], str | None]:
    matches = _match_courses_by_name_fragment(target_name, courses)
    if not matches:
        return [], "not_found"
    delete_all = any(keyword in user_text for keyword in ("全部", "所有", "都删", "全删"))
    if len(matches) > 1 and not delete_all:
        return [], "ambiguous"
    return [
        {
            "action": "delete",
            "course": _course_snapshot(course),
            "reason": "删除用户指定的错误课程记录",
        }
        for course in matches
    ], None


def _actions_from_course_merge_plan(
    merge_plan: list[dict[str, Any]],
    courses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    courses_by_id = {str(course.get("id") or ""): course for course in courses}
    actions: list[dict[str, Any]] = []
    for item in merge_plan:
        rename_to = item.get("rename_to")
        keep_course_id = str(item.get("keep_course_id") or "")
        if rename_to and keep_course_id:
            keep_course = courses_by_id.get(keep_course_id, {"id": keep_course_id, "name": item.get("keep_name")})
            actions.append(
                {
                    "action": "update",
                    "course": _course_snapshot(keep_course),
                    "updates": {"name": rename_to},
                    "reason": f"保留该时段并统一课程名为「{rename_to}」",
                }
            )

        for course_id in item.get("delete_ids", []):
            course = courses_by_id.get(str(course_id), {"id": str(course_id), "name": ""})
            actions.append(
                {
                    "action": "delete",
                    "course": _course_snapshot(course),
                    "reason": f"删除与「{item.get('keep_name')}」同一时段的重复记录",
                    "canonical_name": item.get("keep_name"),
                }
            )
    return actions


def _build_course_merge_plan(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for course in courses:
        key = (
            course.get("weekday"),
            course.get("start_time"),
            course.get("end_time"),
            course.get("location") or "",
            course.get("week_start"),
            course.get("week_end"),
            course.get("week_pattern") or "all",
        )
        grouped.setdefault(key, []).append(course)

    plans: list[dict[str, Any]] = []
    for (weekday, start_time, end_time, location, week_start, week_end, week_pattern), group in grouped.items():
        if len(group) < 2:
            continue

        distinct_names = sorted({str(course.get("name") or "").strip() for course in group if course.get("name")})
        if not distinct_names:
            continue
        canonical_name = max(distinct_names, key=lambda value: (len(value), value))
        keeper_candidates = sorted(
            group,
            key=lambda course: (
                str(course.get("name") or "").strip() != canonical_name,
                str(course.get("id") or ""),
            ),
        )
        keeper = keeper_candidates[0]
        delete_ids = [
            str(course.get("id") or "")
            for course in group
            if str(course.get("id") or "") != str(keeper.get("id") or "")
        ]
        rename_to = canonical_name if str(keeper.get("name") or "").strip() != canonical_name else None
        if not delete_ids and rename_to is None:
            continue

        plans.append(
            {
                "weekday": weekday,
                "start_time": start_time,
                "end_time": end_time,
                "location": location or None,
                "week_start": week_start,
                "week_end": week_end,
                "week_pattern": week_pattern,
                "current_names": distinct_names,
                "keep_course_id": str(keeper.get("id") or ""),
                "keep_name": canonical_name,
                "rename_to": rename_to,
                "delete_ids": delete_ids,
            }
        )

    return sorted(
        plans,
        key=lambda item: (
            item.get("weekday") or 999,
            str(item.get("start_time") or ""),
            str(item.get("end_time") or ""),
            str(item.get("week_pattern") or ""),
            str(item.get("keep_name") or ""),
        ),
    )


def _is_confirmed_answer(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    if not normalized:
        return False
    negative_prefixes = ("不", "先不", "取消", "等等", "no")
    if any(normalized.startswith(prefix) for prefix in negative_prefixes):
        return False
    positive_prefixes = ("确认", "好", "可以", "行", "是", "yes", "ok")
    return any(normalized.startswith(prefix) for prefix in positive_prefixes)


def _extract_review_override(answer: str) -> dict[str, Any] | None:
    marker = "review_override="
    marker_index = (answer or "").find(marker)
    if marker_index < 0:
        return None

    payload = answer[marker_index + len(marker) :].strip()
    if not payload:
        return None

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _build_plan_write_result_event(
    *,
    message_id: str,
    text: str,
    task_label: str,
    created_count: int,
    failed_count: int,
    rescheduled_count: int,
) -> dict[str, Any]:
    has_failure = failed_count > 0 or created_count == 0
    chips: list[str] = []
    if created_count > 0:
        chips.append(f"{created_count} 条记录")
    if rescheduled_count > 0:
        chips.append("含自动重排")
    if failed_count > 0:
        chips.append(f"{failed_count} 条待处理")

    return {
        "type": "result",
        "message_id": message_id,
        "content": text,
        "tone": "warning" if has_failure else "success",
        "eyebrow": "需要处理" if has_failure else "已完成",
        "title": text,
        "body": None,
        "chips": chips,
        "data": {
            "kind": "plan_write",
            "task_label": task_label,
            "created_count": created_count,
            "failed_count": failed_count,
            "rescheduled_count": rescheduled_count,
        },
    }


def _extract_schedule_file_id(user_message: str) -> str | None:
    match = _SCHEDULE_FILE_ID_RE.search(user_message or "")
    if match is None:
        return None
    return match.group(1)


def _should_handle_schedule_import_locally(user_message: str) -> bool:
    return _extract_schedule_file_id(user_message) is not None


def _schedule_parse_tool_name(user_message: str, user_id: str) -> str:
    file_id = _extract_schedule_file_id(user_message)
    if file_id:
        cached = get_schedule_upload(user_id, file_id)
        if cached is not None and cached.kind == "image":
            return "parse_schedule_image"

    compact_message = (user_message or "").strip().lower()
    if any(marker in compact_message for marker in ("图片", "截图", "照片", "image")):
        return "parse_schedule_image"
    return "parse_schedule"


def _build_schedule_missing_info_question(result: dict[str, Any], retry_hint: str | None = None) -> str:
    missing_periods = [str(period) for period in result.get("missing_periods") or [] if str(period).strip()]
    missing_semester_fields = {
        str(field)
        for field in result.get("missing_semester_fields") or []
        if str(field).strip()
    }

    lines: list[str] = []
    if retry_hint:
        lines.append(retry_hint)

    lines.append("请补充以下信息，我来帮你完成导入：")
    if missing_periods:
        joined_periods = "、".join(f"第{period}节" for period in missing_periods)
        lines.append(f"节次时间：请按“1-2节 08:00-09:40”的格式补充这些节次：{joined_periods}")

    if {"semester_start_date", "term_total_weeks"} <= missing_semester_fields:
        lines.append("学期信息：请告诉我学期开始日期（如 2026-03-02）和这学期总周数（如 18 周）。")
    elif "semester_start_date" in missing_semester_fields:
        lines.append("学期信息：请告诉我学期开始日期（如 2026-03-02）。")
    elif "term_total_weeks" in missing_semester_fields:
        lines.append("学期信息：请告诉我这学期总周数（如 18 周）。")

    return "\n".join(lines)


def _extract_period_entries_from_answer(answer: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen_periods: set[str] = set()
    for match in _SCHEDULE_PERIOD_ENTRY_RE.finditer(answer or ""):
        try:
            period = normalize_period(match.group("period"))
        except ValueError:
            continue
        if period in seen_periods:
            continue
        seen_periods.add(period)
        entries.append(
            {
                "period": period,
                "time": f"{match.group('start')}-{match.group('end')}",
            }
        )
    return entries


def _extract_semester_start_date_from_answer(answer: str) -> str | None:
    match = _SEMESTER_START_RE.search(answer or "")
    if match is None:
        return None
    return match.group(1)


def _extract_term_total_weeks_from_answer(answer: str) -> int | None:
    text = answer or ""
    match = _TERM_TOTAL_WEEKS_RE.search(text)
    if match is None:
        match = re.search(r"(\d{1,2})\s*周", text)
    if match is None:
        return None
    return int(match.group(1))


async def _run_schedule_import_shortcut(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
) -> AsyncGenerator[dict[str, Any], str | None]:
    file_id = _extract_schedule_file_id(user_message)
    if not file_id:
        message_id = str(uuid.uuid4())
        text = "我没有识别到这次课表上传的 file_id，请重新上传后再试。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    parse_tool_name = _schedule_parse_tool_name(user_message, user.id)
    parse_args = {"file_id": file_id}
    step = 1

    yield {"type": "tool_call", "name": parse_tool_name, "args": parse_args}
    parse_result = await execute_tool(parse_tool_name, parse_args, db, user.id)
    yield {"type": "tool_result", "name": parse_tool_name, "result": parse_result}
    await _persist_local_tool_step(db, session_id, user.id, step, parse_tool_name, parse_args, parse_result)

    if "error" in parse_result:
        message_id = str(uuid.uuid4())
        text = str(parse_result.get("error") or "课表解析失败，请重新上传后再试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    status = str(parse_result.get("status") or "")
    if status in {"processing", "failed"}:
        message_id = str(uuid.uuid4())
        text = str(parse_result.get("message") or parse_result.get("error") or "课表暂时还不能导入，请稍后重试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    current_result = parse_result
    retry_hint: str | None = None

    while str(current_result.get("status") or "") == "need_period_times":
        answer = yield {
            "type": "ask_user",
            "ask_type": "review",
            "question": _build_schedule_missing_info_question(current_result, retry_hint),
            "options": [],
            "data": None,
        }
        answer_text = str(answer or "").strip()
        entries = _extract_period_entries_from_answer(answer_text)
        semester_start_date = _extract_semester_start_date_from_answer(answer_text)
        term_total_weeks = _extract_term_total_weeks_from_answer(answer_text)

        if not entries and semester_start_date is None and term_total_weeks is None:
            retry_hint = "我还没识别到有效的节次时间或学期信息，请按示例格式再发一次。"
            continue

        step += 1
        save_args: dict[str, Any] = {"file_id": file_id}
        if entries:
            save_args["entries"] = entries
        if semester_start_date is not None:
            save_args["semester_start_date"] = semester_start_date
        if term_total_weeks is not None:
            save_args["term_total_weeks"] = term_total_weeks

        yield {"type": "tool_call", "name": "save_period_times", "args": save_args}
        save_result = await execute_tool("save_period_times", save_args, db, user.id)
        yield {"type": "tool_result", "name": "save_period_times", "result": save_result}
        await _persist_local_tool_step(db, session_id, user.id, step, "save_period_times", save_args, save_result)

        if "error" in save_result:
            retry_hint = str(save_result.get("error") or "补充信息保存失败，请按示例重新发送。")
            continue

        current_result = save_result
        retry_hint = None

    if str(current_result.get("status") or "") != "ready":
        message_id = str(uuid.uuid4())
        text = str(current_result.get("message") or "课表解析结果异常，请重新上传后再试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    courses = list(current_result.get("courses") or [])
    if not courses:
        message_id = str(uuid.uuid4())
        text = "我没有从这张图片里识别到课程信息。请确认上传的是清晰的课表截图，最好包含周一到周日、节次和课程格子。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    confirm_answer = yield {
        "type": "ask_user",
        "ask_type": "review",
        "question": f"以下是解析出的课表（共{len(courses)}条），请确认是否导入？",
        "options": ["确认", "取消"],
        "data": {"courses": courses, "count": len(courses)},
    }
    if not _is_confirmed_answer(str(confirm_answer or "")):
        message_id = str(uuid.uuid4())
        text = "好的，这次我先不导入。你后面想继续的话，重新确认一次就行。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    step += 1
    import_args = {"courses": courses}
    yield {"type": "tool_call", "name": "bulk_import_courses", "args": import_args}
    import_result = await execute_tool("bulk_import_courses", import_args, db, user.id)
    yield {"type": "tool_result", "name": "bulk_import_courses", "result": import_result}
    await _persist_local_tool_step(db, session_id, user.id, step, "bulk_import_courses", import_args, import_result)

    message_id = str(uuid.uuid4())
    if "error" in import_result:
        text = str(import_result.get("error") or "课表导入失败，请稍后重试。")
    else:
        imported_count = int(import_result.get("count") or len(courses))
        text = f"课表已导入完成，共 {imported_count} 条。"
    yield {"type": "text", "message_id": message_id, "content": text}
    await _save_message(db, session_id, "assistant", text)
    yield {"type": "done"}


async def _run_course_merge_shortcut(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
    history_messages: list[ConversationMessage],
) -> AsyncGenerator[dict[str, Any], str | None]:
    intent = _course_maintenance_intent(user_message, history_messages) or {"kind": "merge"}
    selected_names_text = user_message
    if intent.get("kind") == "merge" and not _is_course_followup_message(user_message, history_messages):
        selected_names_text = yield {
            "type": "ask_user",
            "ask_type": "review",
            "question": "你想合并的是哪两门课？请直接把课程名发给我，我来按当前课表里的记录帮你收口。",
            "options": [],
            "data": None,
        }
        selected_names_text = (selected_names_text or "").strip()
        if not selected_names_text:
            message_id = str(uuid.uuid4())
            text = "好的，等你把要合并的课程名发给我后，我再帮你处理。"
            yield {"type": "text", "message_id": message_id, "content": text}
            await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return

    yield {"type": "tool_call", "name": "list_courses", "args": {}}
    list_result = await execute_tool("list_courses", {}, db, user.id)
    yield {"type": "tool_result", "name": "list_courses", "result": list_result}
    await _persist_local_tool_step(db, session_id, user.id, 1, "list_courses", {}, list_result)

    if "error" in list_result:
        message_id = str(uuid.uuid4())
        text = str(list_result.get("error") or "课表查询失败，请稍后重试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    courses = list(list_result.get("courses") or [])
    actions: list[dict[str, Any]] = []
    issue: str | None = None
    kind = str(intent.get("kind") or "merge")
    if kind == "rename":
        actions, issue = _build_course_rename_actions(
            str(intent.get("old_name") or ""),
            str(intent.get("new_name") or ""),
            courses,
        )
    elif kind == "delete":
        actions, issue = _build_course_delete_actions(
            str(intent.get("target_name") or ""),
            courses,
            user_message,
        )
    else:
        matched_courses = _match_courses_from_text(selected_names_text, courses)
        merge_plan = _build_course_merge_plan(matched_courses)
        if not merge_plan:
            issue = "not_found"
        else:
            actions = _actions_from_course_merge_plan(merge_plan, matched_courses)

    if not actions:
        message_id = str(uuid.uuid4())
        if issue == "ambiguous":
            text = "我先查了当前课表，但匹配到多条同名课程。请补充周几、时间或地点后我再删除，避免误删。"
        elif kind == "rename":
            text = f"我先查了当前课表，但没有找到「{intent.get('old_name')}」。请确认课程名后再让我修改。"
        elif kind == "delete":
            text = f"我先查了当前课表，但没有找到「{intent.get('target_name')}」。请确认课程名后再让我删除。"
        else:
            text = "我先查了当前课表，但还没定位到可以直接合并的重复记录。你可以把要保留的课程名再明确发我一次。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    review_data = {
        "actions": [
            {
                "action": item["action"],
                "course": item["course"],
                "updates": item.get("updates"),
                "reason": item.get("reason"),
            }
            for item in actions
        ],
        "count": len(actions),
    }
    question = "我准备按下面方案维护课程记录。确认后我就直接处理。"
    if kind == "rename":
        question = "我准备按下面方案修改课程名。确认后我就直接处理。"
    elif kind == "delete":
        question = "我准备删除下面这些课程记录。确认后我就直接处理。"
    elif kind == "merge":
        question = "我准备把这些重复课程合并成每个时段 1 条记录。确认后我就直接处理。"

    confirm_answer = yield {
        "type": "ask_user",
        "ask_type": "review",
        "question": question,
        "options": ["确认", "取消"],
        "data": review_data,
    }
    if not _is_confirmed_answer(str(confirm_answer or "")):
        message_id = str(uuid.uuid4())
        text = "好的，我先不改。你后面想继续的话，直接告诉我保留哪个课程名就行。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    step = 1
    updated_results: list[dict[str, Any]] = []
    deleted_results: list[dict[str, Any]] = []
    failed_results: list[dict[str, Any]] = []
    for item in actions:
        action = str(item.get("action") or "")
        course = item.get("course") if isinstance(item.get("course"), dict) else {}
        course_id = str(course.get("id") or "")
        if action == "update" and course_id:
            update_args = {"course_id": course_id, **dict(item.get("updates") or {})}
            yield {"type": "tool_call", "name": "update_course", "args": update_args}
            update_result = await execute_tool("update_course", update_args, db, user.id)
            yield {"type": "tool_result", "name": "update_course", "result": update_result}
            step += 1
            await _persist_local_tool_step(db, session_id, user.id, step, "update_course", update_args, update_result)
            if "error" in update_result:
                failed_results.append(update_result)
            else:
                updated_results.append(update_result)
            continue

        if action == "delete" and course_id:
            delete_args = {"course_id": course_id}
            yield {"type": "tool_call", "name": "delete_course", "args": delete_args}
            delete_result = await execute_tool("delete_course", delete_args, db, user.id)
            yield {"type": "tool_result", "name": "delete_course", "result": delete_result}
            step += 1
            await _persist_local_tool_step(db, session_id, user.id, step, "delete_course", delete_args, delete_result)
            if "error" in delete_result:
                failed_results.append(delete_result)
            else:
                deleted_results.append(delete_result)
            continue

        failed_results.append({"error": "Invalid course maintenance action"})

    message_id = str(uuid.uuid4())
    if failed_results and (updated_results or deleted_results):
        text = (
            f"已完成 {len(updated_results)} 条课程修改、{len(deleted_results)} 条课程删除；"
            f"另有 {len(failed_results)} 条因为参数或记录不存在未处理。"
        )
    elif failed_results:
        text = "这些课程记录暂时没有处理成功，主要原因是参数不完整或记录不存在。请确认后再试。"
    elif kind == "rename" and deleted_results and not updated_results:
        text = f"已经帮你删除 {len(deleted_results)} 条重复错名课程记录，保留同一时段已有的正确课程。"
    elif kind == "rename":
        text = f"已经帮你修改 {len(updated_results)} 条课程记录。"
    elif kind == "delete":
        text = f"已经帮你删除 {len(deleted_results)} 条课程记录。"
    else:
        text = f"已经帮你把重复课程合并好了，删除 {len(deleted_results)} 条重复记录。"
    yield {"type": "text", "message_id": message_id, "content": text}
    await _save_message(db, session_id, "assistant", text)
    yield {"type": "done"}


async def _run_missing_task_create_shortcut(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
) -> AsyncGenerator[dict[str, Any], str | None]:
    title = _extract_task_title(user_message)
    details_answer = yield {
        "type": "ask_user",
        "ask_type": "review",
        "question": f"请补充「{title}」这个任务的日期、开始结束时间，以及是否需要提前提醒。",
        "options": [],
        "data": None,
    }

    details_text = str(details_answer or "").strip()
    schedule = _extract_task_schedule(details_text)
    if schedule is None:
        message_id = str(uuid.uuid4())
        text = "我还没识别到完整日期和时间，请按“2026年7月28日 19:00-20:00”这种格式再发一次。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    title = _extract_task_title(user_message, details_text)
    reminder_slot = extract_reminder_slot([details_text])
    create_args: dict[str, Any] = {"title": title, **schedule}
    if reminder_slot is not None:
        create_args["reminder_advance_minutes"] = reminder_slot.advance_minutes

    reminder_text = "不提醒"
    if reminder_slot is not None:
        if reminder_slot.advance_minutes is None:
            reminder_text = "不提醒"
        elif reminder_slot.advance_minutes == 0:
            reminder_text = "准点提醒"
        else:
            reminder_text = f"提前{reminder_slot.advance_minutes}分钟提醒"

    confirm_answer = yield {
        "type": "ask_user",
        "ask_type": "confirm",
        "question": "请确认是否创建这个任务。",
        "options": ["确认", "取消"],
        "data": {
            "title": title,
            "scheduled_date": schedule["scheduled_date"],
            "time": f"{schedule['start_time']}-{schedule['end_time']}",
            "reminder": reminder_text,
        },
    }
    if not _is_confirmed_answer(str(confirm_answer or "")):
        message_id = str(uuid.uuid4())
        text = "好的，我先不创建。你调整好时间后再告诉我。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    yield {"type": "tool_call", "name": "create_task", "args": create_args}
    create_result = await execute_tool("create_task", create_args, db, user.id)
    yield {"type": "tool_result", "name": "create_task", "result": create_result}
    await _persist_local_tool_step(db, session_id, user.id, 1, "create_task", create_args, create_result)

    message_id = str(uuid.uuid4())
    if "error" in create_result:
        text = str(create_result.get("error") or "任务创建失败，请稍后重试。")
    else:
        text = f"已创建「{title}」任务。"
    yield {"type": "text", "message_id": message_id, "content": text}
    await _save_message(db, session_id, "assistant", text)
    yield {"type": "done"}


def _build_tonight_review_tasks(
    subjects: list[str],
    total_minutes: int,
    free_slots_result: dict[str, Any],
) -> list[dict[str, Any]]:
    if not subjects or total_minutes <= 0:
        return []

    today = date.today().isoformat()
    durations: list[int] = []
    base_duration = total_minutes // len(subjects)
    remainder = total_minutes % len(subjects)
    for index in range(len(subjects)):
        durations.append(base_duration + (1 if index < remainder else 0))

    slots = free_slots_result.get("slots")
    if not isinstance(slots, list):
        return []

    free_periods: list[dict[str, Any]] = []
    for day in slots:
        if not isinstance(day, dict) or str(day.get("date") or "") != today:
            continue
        periods = day.get("free_periods")
        if isinstance(periods, list):
            free_periods = [period for period in periods if isinstance(period, dict)]
        break

    if not free_periods:
        return []

    evening_start = 18 * 60
    break_minutes = 15 if len(subjects) > 1 else 0
    period_index = 0
    cursor: int | None = None
    tasks: list[dict[str, Any]] = []

    for subject, duration in zip(subjects, durations):
        placed = False
        while period_index < len(free_periods):
            period = free_periods[period_index]
            period_start = _time_to_minutes(str(period.get("start") or ""))
            period_end = _time_to_minutes(str(period.get("end") or ""))
            if period_start is None or period_end is None:
                period_index += 1
                cursor = None
                continue

            candidate_start = max(period_start, evening_start)
            if cursor is not None:
                candidate_start = max(candidate_start, cursor)

            if candidate_start + duration <= period_end:
                start_time = _time_after_minutes("00:00", candidate_start)
                end_time = _time_after_minutes(start_time, duration)
                tasks.append(
                    {
                        "title": f"{subject}复习",
                        "scheduled_date": today,
                        "start_time": start_time,
                        "end_time": end_time,
                        "description": f"今晚集中复习：{subject}",
                    }
                )
                cursor = candidate_start + duration + break_minutes
                placed = True
                break

            period_index += 1
            cursor = None

        if not placed:
            return []

    return tasks


async def _run_tonight_review_shortcut(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
) -> AsyncGenerator[dict[str, Any], str | None]:
    request = _extract_tonight_review_request(user_message)
    if request is None:
        return

    total_minutes = int(request["duration_minutes"])
    subjects = list(request["subjects"])
    today = date.today().isoformat()
    free_args = {
        "start_date": today,
        "end_date": today,
        "min_duration_minutes": max(30, min(total_minutes // max(len(subjects), 1), total_minutes)),
    }
    step = 1
    yield {"type": "tool_call", "name": "get_free_slots", "args": free_args}
    free_result = await execute_tool("get_free_slots", free_args, db, user.id)
    yield {"type": "tool_result", "name": "get_free_slots", "result": free_result}
    await _persist_local_tool_step(db, session_id, user.id, step, "get_free_slots", free_args, free_result)

    if "error" in free_result:
        message_id = str(uuid.uuid4())
        text = str(free_result.get("error") or "查询今晚空闲时间失败，请稍后重试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    tasks = _build_tonight_review_tasks(subjects, total_minutes, free_result)
    if not tasks:
        message_id = str(uuid.uuid4())
        text = "今晚可用空闲时间不够完整排下这次复习。你可以减少总时长，或告诉我允许排到更晚一点。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    shortcut = _run_confirmed_plan_write(
        tasks,
        user,
        session_id,
        db,
        step,
        _normalize_study_plan_tasks,
        "复习任务",
        "今晚复习计划已经生成，但里面没有可写入日程的完整任务时间。请调整后再试。",
        "今晚 {count} 段复习已经排好。确认后我会写入你的日程。",
        "好的，我先不写入今晚的复习安排。你调整科目或时长后再告诉我。",
    )
    try:
        event = await shortcut.__anext__()
        while True:
            if event["type"] == "ask_user":
                user_response = yield event
                event = await shortcut.asend(user_response)
            else:
                yield event
                event = await shortcut.__anext__()
    except StopAsyncIteration:
        pass


async def _run_confirmed_plan_write(
    raw_tasks: Any,
    user: User,
    session_id: str,
    db: AsyncSession,
    start_step: int,
    normalize_tasks: Callable[[Any], list[dict[str, Any]]],
    task_label: str,
    empty_text: str,
    review_question: str,
    cancel_text: str,
) -> AsyncGenerator[dict[str, Any], str | None]:
    tasks = normalize_tasks(raw_tasks)
    if not tasks:
        message_id = str(uuid.uuid4())
        yield {"type": "text", "message_id": message_id, "content": empty_text}
        await _save_message(db, session_id, "assistant", empty_text)
        yield {"type": "done"}
        return

    confirm_answer = yield {
        "type": "ask_user",
        "ask_type": "review",
        "question": review_question.format(count=len(tasks)),
        "options": ["确认", "取消"],
        "data": _study_plan_review_data(tasks),
    }
    if confirm_answer is None:
        yield {"type": "done"}
        return
    if not _is_confirmed_answer(str(confirm_answer or "")):
        message_id = str(uuid.uuid4())
        yield {"type": "text", "message_id": message_id, "content": cancel_text}
        await _save_message(db, session_id, "assistant", cancel_text)
        yield {"type": "done"}
        return

    review_override = _extract_review_override(str(confirm_answer or ""))
    if review_override is not None:
        override_tasks = normalize_tasks(review_override.get("tasks"))
        tasks = override_tasks
        if not tasks:
            message_id = str(uuid.uuid4())
            text = f"你已经删除了全部{task_label}，这次没有写入日程。"
            yield _build_plan_write_result_event(
                message_id=message_id,
                text=text,
                task_label=task_label,
                created_count=0,
                failed_count=0,
                rescheduled_count=0,
            )
            yield {"type": "text", "message_id": message_id, "content": text}
            await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return

    step = start_step
    plan_date_range = _plan_task_date_range(tasks)
    created_results: list[dict[str, Any]] = []
    failed_results: list[dict[str, Any]] = []
    rescheduled_results: list[dict[str, Any]] = []
    for task_args in tasks:
        step += 1
        yield {"type": "tool_call", "name": "create_task", "args": task_args}
        create_result = await execute_tool("create_task", task_args, db, user.id)
        yield {"type": "tool_result", "name": "create_task", "result": create_result}
        await _persist_local_tool_step(
            db,
            session_id,
            user.id,
            step,
            "create_task",
            task_args,
            create_result,
        )
        if "error" not in create_result:
            created_results.append(create_result)
            continue

        duration = _task_duration_minutes(task_args)
        if not (_is_time_conflict_result(create_result) and plan_date_range is not None and duration is not None):
            failed_results.append(create_result)
            continue

        start_date, end_date = plan_date_range
        free_args = {
            "start_date": start_date,
            "end_date": end_date,
            "min_duration_minutes": duration,
        }
        step += 1
        yield {"type": "tool_call", "name": "get_free_slots", "args": free_args}
        free_result = await execute_tool("get_free_slots", free_args, db, user.id)
        yield {"type": "tool_result", "name": "get_free_slots", "result": free_result}
        await _persist_local_tool_step(
            db,
            session_id,
            user.id,
            step,
            "get_free_slots",
            free_args,
            free_result,
        )

        rescheduled_args = _find_rescheduled_task_args(task_args, free_result)
        if rescheduled_args is None:
            failed_results.append(create_result)
            continue

        step += 1
        yield {"type": "tool_call", "name": "create_task", "args": rescheduled_args}
        retry_result = await execute_tool("create_task", rescheduled_args, db, user.id)
        yield {"type": "tool_result", "name": "create_task", "result": retry_result}
        await _persist_local_tool_step(
            db,
            session_id,
            user.id,
            step,
            "create_task",
            rescheduled_args,
            retry_result,
        )
        if "error" in retry_result:
            failed_results.append(retry_result)
            continue
        created_results.append(retry_result)
        rescheduled_results.append(
            {
                "title": rescheduled_args.get("title") or task_args.get("title"),
                "from": f"{task_args.get('scheduled_date')} {task_args.get('start_time')}-{task_args.get('end_time')}",
                "to": f"{rescheduled_args.get('scheduled_date')} {rescheduled_args.get('start_time')}-{rescheduled_args.get('end_time')}",
            }
        )

    message_id = str(uuid.uuid4())
    reschedule_text = ""
    if rescheduled_results:
        reschedule_text = f"其中 {len(rescheduled_results)} 条因原时间冲突已自动重排；"
    if failed_results and created_results:
        text = f"已写入 {len(created_results)} 条{task_label}；{reschedule_text}另有 {len(failed_results)} 条因为时间冲突或参数问题未写入。"
    elif failed_results:
        text = f"这些{task_label}暂时没有写入成功，主要原因是时间冲突或参数不完整。请调整后再试。"
    elif rescheduled_results:
        text = f"已把 {len(created_results)} 条{task_label}写入日程，其中 {len(rescheduled_results)} 条因原时间冲突已自动重排。"
    else:
        text = f"已把 {len(created_results)} 条{task_label}写入日程。"

    yield _build_plan_write_result_event(
        message_id=message_id,
        text=text,
        task_label=task_label,
        created_count=len(created_results),
        failed_count=len(failed_results),
        rescheduled_count=len(rescheduled_results),
    )
    yield {"type": "text", "message_id": message_id, "content": text}
    await _save_message(db, session_id, "assistant", text)
    yield {"type": "done"}


def _run_confirmed_study_plan_write(
    raw_tasks: Any,
    user: User,
    session_id: str,
    db: AsyncSession,
    start_step: int,
) -> AsyncGenerator[dict[str, Any], str | None]:
    return _run_confirmed_plan_write(
        raw_tasks,
        user,
        session_id,
        db,
        start_step,
        _normalize_study_plan_tasks,
        "复习任务",
        "复习计划已经生成，但里面没有可写入日程的完整任务时间。请补充考试范围或每日可复习时间后再试。",
        "我已经拆出 {count} 条复习任务。确认后我会把它们写入你的日程。",
        "好的，我先不写入这些复习任务。你可以调整考试范围、复习强度或空闲时间后再让我重新拆。",
    )


def _run_confirmed_work_plan_write(
    raw_tasks: Any,
    user: User,
    session_id: str,
    db: AsyncSession,
    start_step: int,
) -> AsyncGenerator[dict[str, Any], str | None]:
    return _run_confirmed_plan_write(
        raw_tasks,
        user,
        session_id,
        db,
        start_step,
        _normalize_work_plan_tasks,
        "作业任务",
        "作业计划已经生成，但里面没有可写入日程的完整任务时间。请补充截止日期、交付要求或每日可投入时间后再试。",
        "我已经拆出 {count} 条作业任务。确认后我会把它们写入你的日程。",
        "好的，我先不写入这些作业任务。你可以调整要求、工作量或空闲时间后再让我重新拆。",
    )


async def run_review_override_plan_write(
    confirm_answer: str,
    user: User,
    session_id: str,
    db: AsyncSession,
    start_step: int = 0,
) -> AsyncGenerator[dict[str, Any], str | None]:
    """Write a submitted review payload when the live generator is gone."""

    review_override = _extract_review_override(confirm_answer)
    if review_override is None:
        yield {
            "type": "error",
            "message": "当前没有待确认的问题，请先发送消息或重新触发操作。",
        }
        yield {"type": "done"}
        return

    shortcut = _run_confirmed_plan_write(
        review_override.get("tasks"),
        user,
        session_id,
        db,
        start_step,
        _normalize_study_plan_tasks,
        "计划任务",
        "计划已经生成，但里面没有可写入日程的完整任务时间。请调整后再试。",
        "我已经拆出 {count} 条计划任务。确认后我会把它们写入你的日程。",
        "好的，我先不写入这些任务。你调整后再告诉我。",
    )
    try:
        event = await shortcut.__anext__()
        if event["type"] == "ask_user":
            event = await shortcut.asend(confirm_answer)
        while True:
            yield event
            event = await shortcut.__anext__()
    except StopAsyncIteration:
        pass


def _work_plan_date_range(due_date: str) -> tuple[str, str]:
    due = date.fromisoformat(due_date)
    start = date.today()
    if start >= due:
        start = due - timedelta(days=3)
    end = due - timedelta(days=1)
    if end < start:
        end = start
    return start.isoformat(), end.isoformat()


async def _run_work_plan_shortcut(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
) -> AsyncGenerator[dict[str, Any], str | None]:
    due_date = _extract_first_iso_date(user_message)
    title = _extract_work_item_title(user_message)
    if due_date is None:
        message_id = str(uuid.uuid4())
        text = "我还没识别到作业或报告的截止日期，请按“2026-06-12 要交机器学习报告”这种格式再发一次。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    context = _extract_work_context_from_text(user_message)
    if not _work_context_has_quality(context):
        context_answer = yield {
            "type": "ask_user",
            "ask_type": "review",
            "question": _work_plan_intake_question(title),
            "options": [],
            "data": None,
        }
        if _is_cancelled_answer(str(context_answer or "")):
            message_id = str(uuid.uuid4())
            text = "好的，我先不生成作业计划。你整理好要求后再告诉我。"
            yield {"type": "text", "message_id": message_id, "content": text}
            await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return
        context_text = str(context_answer or "按默认")
        context = _extract_work_context_from_text(context_text)
        if not _work_context_has_quality(context):
            context = {"raw_notes": context_text, "using_defaults": True}

    start_date, end_date = _work_plan_date_range(due_date)
    free_args = {"start_date": start_date, "end_date": end_date, "min_duration_minutes": 30}
    step = 1
    yield {"type": "tool_call", "name": "get_free_slots", "args": free_args}
    free_result = await execute_tool("get_free_slots", free_args, db, user.id)
    yield {"type": "tool_result", "name": "get_free_slots", "result": free_result}
    await _persist_local_tool_step(db, session_id, user.id, step, "get_free_slots", free_args, free_result)

    if "error" in free_result:
        message_id = str(uuid.uuid4())
        text = str(free_result.get("error") or "查询空闲时间失败，请稍后重试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    work_args = {
        "work_items": [
            {
                "title": title,
                "due_date": due_date,
                "work_type": _extract_work_type(title),
            }
        ],
        "available_slots": free_result,
        "work_context": context,
        "strategy": "staged",
    }
    step += 1
    yield {"type": "tool_call", "name": "create_work_plan", "args": work_args}
    work_result = await execute_tool("create_work_plan", work_args, db, user.id)
    yield {"type": "tool_result", "name": "create_work_plan", "result": work_result}
    await _persist_local_tool_step(db, session_id, user.id, step, "create_work_plan", work_args, work_result)

    if "error" in work_result:
        message_id = str(uuid.uuid4())
        text = str(work_result.get("error") or "作业计划生成失败，请补充要求或空闲时间后再试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    shortcut = _run_confirmed_work_plan_write(work_result.get("tasks"), user, session_id, db, step)
    try:
        event = await shortcut.__anext__()
        while True:
            if event["type"] == "ask_user":
                user_response = yield event
                event = await shortcut.asend(user_response)
            else:
                yield event
                event = await shortcut.__anext__()
    except StopAsyncIteration:
        pass


def _should_handle_plan_adjustment_locally(user_message: str) -> bool:
    text = (user_message or "").strip()
    if not text:
        return False
    if _extract_daily_study_limit_minutes(text) is None:
        return False
    if "计划" not in text and "任务" not in text:
        return False
    return any(keyword in text for keyword in _PLAN_ADJUSTMENT_KEYWORDS)


def _extract_plan_adjustment_query(user_message: str) -> str:
    work_title = _extract_work_item_title(user_message)
    if work_title != "作业任务":
        return work_title
    text = re.sub(_DAILY_LIMIT_RE, "", user_message or "")
    text = re.sub(r"(太满|太多|压缩|减少|调整|改成|每天最多|每日最多|计划|任务|这个|刚才|一下|帮我)", "", text)
    text = text.strip(" ：:，,。.?？")
    if len(text) >= 2:
        return text[:12]
    return ""


def _task_duration_minutes(task: dict[str, Any]) -> int | None:
    start_time = str(task.get("start_time") or "")
    end_time = str(task.get("end_time") or "")
    try:
        start = datetime.strptime(start_time, "%H:%M")
        end = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None
    minutes = int((end - start).total_seconds() // 60)
    return minutes if minutes > 0 else None


def _time_after_minutes(start_time: str, minutes: int) -> str:
    start = datetime.strptime(start_time, "%H:%M")
    return (start + timedelta(minutes=minutes)).strftime("%H:%M")


def _build_plan_adjustment_updates(
    tasks: list[dict[str, Any]],
    daily_limit_minutes: int,
) -> list[dict[str, Any]]:
    tasks_by_date: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_date.setdefault(str(task.get("scheduled_date") or ""), []).append(task)

    updates: list[dict[str, Any]] = []
    for date_key, day_tasks in tasks_by_date.items():
        if not date_key:
            continue
        per_task_limit = max(30, daily_limit_minutes // max(len(day_tasks), 1))
        for task in day_tasks:
            duration = _task_duration_minutes(task)
            if duration is None or duration <= per_task_limit:
                continue
            start_time = str(task.get("start_time") or "")
            new_end_time = _time_after_minutes(start_time, per_task_limit)
            updates.append(
                {
                    "task_id": str(task.get("id") or ""),
                    "title": str(task.get("title") or ""),
                    "scheduled_date": date_key,
                    "start_time": start_time,
                    "old_end_time": str(task.get("end_time") or ""),
                    "new_end_time": new_end_time,
                    "old_duration_minutes": duration,
                    "new_duration_minutes": per_task_limit,
                }
            )
    return [update for update in updates if update["task_id"]]


async def _run_plan_adjustment_shortcut(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
) -> AsyncGenerator[dict[str, Any], str | None]:
    daily_limit = _extract_daily_study_limit_minutes(user_message)
    query = _extract_plan_adjustment_query(user_message)
    if daily_limit is None or daily_limit < 30:
        message_id = str(uuid.uuid4())
        text = "我还没识别到有效的每日上限，请按“每天最多1小时”或“每天最多60分钟”这种格式再发一次。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return
    if not query:
        message_id = str(uuid.uuid4())
        text = "我还没识别到要调整哪个计划，请带上计划关键词，比如“机器学习报告计划太满，每天最多1小时”。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    list_args = {
        "date_from": date.today().isoformat(),
        "date_to": (date.today() + timedelta(days=30)).isoformat(),
    }
    step = 1
    yield {"type": "tool_call", "name": "list_tasks", "args": list_args}
    list_result = await execute_tool("list_tasks", list_args, db, user.id)
    yield {"type": "tool_result", "name": "list_tasks", "result": list_result}
    await _persist_local_tool_step(db, session_id, user.id, step, "list_tasks", list_args, list_result)

    if "error" in list_result:
        message_id = str(uuid.uuid4())
        text = str(list_result.get("error") or "查询任务失败，请稍后重试。")
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    tasks = [
        task
        for task in list_result.get("tasks", [])
        if isinstance(task, dict)
        and str(task.get("status") or "pending") == "pending"
        and query in f"{task.get('title') or ''}\n{task.get('description') or ''}"
    ]
    if not tasks:
        message_id = str(uuid.uuid4())
        text = f"我查了未来 30 天的任务，但没有找到包含「{query}」的待办任务，所以没有做调整。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    updates = _build_plan_adjustment_updates(tasks, daily_limit)
    if not updates:
        message_id = str(uuid.uuid4())
        text = f"我查到「{query}」相关任务，但它们当前单日安排已经不超过 {daily_limit} 分钟，暂时不需要压缩。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    confirm_answer = yield {
        "type": "ask_user",
        "ask_type": "review",
        "question": f"我找到 {len(updates)} 条需要压缩的「{query}」任务。确认后我会把它们调整到每天最多 {daily_limit} 分钟。",
        "options": ["确认", "取消"],
        "data": {"daily_limit_minutes": daily_limit, "tasks": updates, "count": len(updates)},
    }
    if not _is_confirmed_answer(str(confirm_answer or "")):
        message_id = str(uuid.uuid4())
        text = "好的，我先不调整这些任务。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    updated_results: list[dict[str, Any]] = []
    failed_results: list[dict[str, Any]] = []
    for update in updates:
        step += 1
        update_args = {
            "task_id": update["task_id"],
            "end_time": update["new_end_time"],
        }
        yield {"type": "tool_call", "name": "update_task", "args": update_args}
        update_result = await execute_tool("update_task", update_args, db, user.id)
        yield {"type": "tool_result", "name": "update_task", "result": update_result}
        await _persist_local_tool_step(db, session_id, user.id, step, "update_task", update_args, update_result)
        if "error" in update_result:
            failed_results.append(update_result)
        else:
            updated_results.append(update_result)

    message_id = str(uuid.uuid4())
    if failed_results and updated_results:
        text = f"已调整 {len(updated_results)} 条任务；另有 {len(failed_results)} 条因为冲突或参数问题未调整。"
    elif failed_results:
        text = "这些任务暂时没有调整成功，主要原因是时间冲突或参数不完整。"
    else:
        text = f"已把 {len(updated_results)} 条「{query}」相关任务压缩到每日上限内。"
    yield {"type": "text", "message_id": message_id, "content": text}
    await _save_message(db, session_id, "assistant", text)
    yield {"type": "done"}


async def run_agent_loop(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
    llm_client: AsyncOpenAI,
    runtime_hints: list[str] | None = None,
) -> AsyncGenerator[dict[str, Any], str | None]:
    """Run the agent loop and yield frontend events."""
    system_prompt = await build_system_prompt(user, db)

    history_result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.timestamp)
    )
    history_messages = history_result.scalars().all()

    messages = await _build_initial_messages(system_prompt, history_messages, llm_client)

    course_routing_hint = _build_course_routing_hint(user_message, history_messages)
    if course_routing_hint:
        messages.append({"role": "system", "content": course_routing_hint})
    task_routing_hint = _build_task_routing_hint(user_message)
    if task_routing_hint:
        messages.append({"role": "system", "content": task_routing_hint})
    for hint in runtime_hints or []:
        if hint.strip():
            messages.append({"role": "system", "content": hint})

    messages.append({"role": "user", "content": user_message})
    await _save_message(db, session_id, "user", user_message)

    initial_study_context_text: str | None = None
    if _should_collect_study_context_locally(user_message):
        context_answer = yield {
            "type": "ask_user",
            "ask_type": "review",
            "question": _study_plan_intake_question({"exams": []}),
            "options": [],
            "data": None,
        }
        if _is_cancelled_answer(str(context_answer or "")):
            message_id = str(uuid.uuid4())
            text = "好的，我先不生成复习计划。你整理好范围或目标后再告诉我。"
            yield {"type": "text", "message_id": message_id, "content": text}
            await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return
        initial_study_context_text = str(context_answer or "按默认")
        initial_study_context = _extract_study_context_from_text(initial_study_context_text)
        if not _study_context_has_quality(initial_study_context):
            initial_study_context = {"raw_notes": initial_study_context_text, "using_defaults": True}
        messages.append(
            {
                "role": "system",
                "content": (
                    "用户已补充学习计划上下文，后续调用 create_study_plan 时必须写入 study_context："
                    f"{json.dumps(initial_study_context, ensure_ascii=False)}"
                    "。不要再次追问复习范围、薄弱点、目标成绩或每日学习上限；"
                    "如果考试课程和日期已经明确，可以继续确认考试信息或直接查询空闲时间。"
                ),
            }
        )

    if _should_handle_schedule_import_locally(user_message):
        shortcut = _run_schedule_import_shortcut(user_message, user, session_id, db)
        try:
            event = await shortcut.__anext__()
            while True:
                if event["type"] == "ask_user":
                    user_response = yield event
                    event = await shortcut.asend(user_response)
                else:
                    yield event
                    event = await shortcut.__anext__()
        except StopAsyncIteration:
            pass
        return

    if _should_handle_tonight_review_locally(user_message):
        shortcut = _run_tonight_review_shortcut(user_message, user, session_id, db)
        try:
            event = await shortcut.__anext__()
            while True:
                if event["type"] == "ask_user":
                    user_response = yield event
                    event = await shortcut.asend(user_response)
                else:
                    yield event
                    event = await shortcut.__anext__()
        except StopAsyncIteration:
            pass
        return

    if _should_handle_work_plan_locally(user_message):
        shortcut = _run_work_plan_shortcut(user_message, user, session_id, db)
        try:
            event = await shortcut.__anext__()
            while True:
                if event["type"] == "ask_user":
                    user_response = yield event
                    event = await shortcut.asend(user_response)
                else:
                    yield event
                    event = await shortcut.__anext__()
        except StopAsyncIteration:
            pass
        return

    if _should_handle_plan_adjustment_locally(user_message):
        shortcut = _run_plan_adjustment_shortcut(user_message, user, session_id, db)
        try:
            event = await shortcut.__anext__()
            while True:
                if event["type"] == "ask_user":
                    user_response = yield event
                    event = await shortcut.asend(user_response)
                else:
                    yield event
                    event = await shortcut.__anext__()
        except StopAsyncIteration:
            pass
        return

    if _should_handle_missing_task_create_locally(user_message):
        shortcut = _run_missing_task_create_shortcut(user_message, user, session_id, db)
        try:
            event = await shortcut.__anext__()
            while True:
                if event["type"] == "ask_user":
                    user_response = yield event
                    event = await shortcut.asend(user_response)
                else:
                    yield event
                    event = await shortcut.__anext__()
        except StopAsyncIteration:
            pass
        return

    if _should_handle_course_merge_locally(user_message, history_messages):
        shortcut = _run_course_merge_shortcut(user_message, user, session_id, db, history_messages)
        try:
            event = await shortcut.__anext__()
            while True:
                if event["type"] == "ask_user":
                    user_response = yield event
                    event = await shortcut.asend(user_response)
                else:
                    yield event
                    event = await shortcut.__anext__()
        except StopAsyncIteration:
            pass
        return

    tool_history: list[str] = []
    preflight_reference_texts: list[str] = [user_message]
    preflight_user_texts: list[str] = [user_message]
    if initial_study_context_text:
        preflight_reference_texts.append(initial_study_context_text)
        preflight_user_texts.append(initial_study_context_text)
    error_count: dict[str, int] = {}
    last_free_slots_result: dict[str, Any] | None = None
    step = 0

    for iteration in range(MAX_ITERATIONS):
        check_max_loop_iterations(iteration, MAX_ITERATIONS)
        response: dict[str, Any] | None = None
        response_message_id = str(uuid.uuid4())
        streamed_deltas: list[str] = []
        streamed_deltas_emitted = False
        use_text_only_stream = _should_use_text_only_stream(preflight_user_texts, tool_history)
        completion_kwargs: dict[str, Any] = {}
        if not use_text_only_stream:
            tool_choice = "required" if _should_require_task_tool_response(preflight_user_texts, tool_history) else "auto"
            completion_kwargs = {"tools": TOOL_DEFINITIONS}
            if tool_choice != "auto":
                completion_kwargs["tool_choice"] = tool_choice
        try:
            async for stream_event in chat_completion_stream(
                llm_client,
                messages,
                **completion_kwargs,
            ):
                event_type = stream_event.get("type")
                if event_type == "content_delta":
                    delta = str(stream_event.get("delta") or "")
                    if not delta:
                        continue
                    streamed_deltas.append(delta)
                    if use_text_only_stream:
                        streamed_deltas_emitted = True
                        yield {
                            "type": "text_delta",
                            "message_id": response_message_id,
                            "delta": delta,
                        }
                    continue

                if event_type == "response":
                    response = stream_event.get("response")
        except Exception:
            if streamed_deltas:
                raise
            response = await chat_completion(
                llm_client,
                messages,
                **completion_kwargs,
            )
            response_message_id = str(uuid.uuid4())

        if response is None:
            raise RuntimeError("chat completion stream finished without a response payload")

        response_tool_calls = response.get("tool_calls") or []
        if not response_tool_calls:
            text = response.get("content", "") or "".join(streamed_deltas)
            if (
                text
                and _looks_like_task_write_context(preflight_user_texts)
                and _looks_like_plain_text_ask(text)
            ):
                tool_call_id = f"call_plain_{uuid.uuid4().hex[:24]}"
                tool_args = _plain_text_ask_tool_args(text)
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": "ask_user",
                                    "arguments": json.dumps(tool_args, ensure_ascii=False),
                                },
                            }
                        ],
                    }
                )
                yield {"type": "tool_call", "name": "ask_user", "args": tool_args}
                result = await execute_tool("ask_user", tool_args, db, user.id)
                ask_type = _normalize_ask_type(result)
                user_response = yield {**result, "type": "ask_user", "ask_type": ask_type}
                if user_response is None:
                    user_response = "确认"
                question = str(result.get("question") or "")
                if question and should_include_confirmed_question(user_response):
                    preflight_reference_texts.append(question)
                preflight_reference_texts.append(str(user_response))
                preflight_user_texts.append(str(user_response))
                tool_result_content = json.dumps({"user_response": user_response}, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result_content,
                    }
                )
                step += 1
                tool_history.append("ask_user")
                await _log_step(db, user.id, session_id, step, "ask_user", tool_args, result)
                continue

            if text:
                if not streamed_deltas_emitted:
                    for delta in streamed_deltas:
                        yield {
                            "type": "text_delta",
                            "message_id": response_message_id,
                            "delta": delta,
                        }
                yield {
                    "type": "text",
                    "message_id": response_message_id,
                    "content": text,
                }
                await _save_message(db, session_id, "assistant", text)
            yield {"type": "done"}
            return

        messages.append(response)

        for tool_call in response_tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args_str = tool_call["function"]["arguments"]
            tool_call_id = tool_call["id"]

            try:
                tool_args = json.loads(tool_args_str)
            except json.JSONDecodeError:
                tool_args = {}

            try:
                check_unknown_tool(tool_name, KNOWN_TOOLS)
                if tool_name == "ask_user":
                    check_consecutive_ask_user(tool_history + [tool_name])
                else:
                    check_consecutive_ask_user(tool_history)
                check_max_retries(tool_name, error_count)
            except GuardrailViolation as exc:
                tool_result = {"error": exc.message, "suggestion": exc.suggestion}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
                if exc.user_visible:
                    yield {"type": "error", "message": exc.message}
                continue

            preflight_error = task_tool_preflight_error(tool_name, preflight_user_texts)
            if preflight_error is not None:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(preflight_error, ensure_ascii=False),
                    }
                )
                continue

            if tool_name in {"create_study_plan", "create_work_plan"} and last_free_slots_result is not None:
                available_slots = tool_args.get("available_slots")
                if not _has_real_available_slots(available_slots):
                    tool_args["available_slots"] = last_free_slots_result
                    tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)

            if tool_name == "create_study_plan" and not _study_context_has_quality(tool_args.get("study_context")):
                inferred_context = _study_context_from_reference_texts(preflight_reference_texts)
                if _study_context_has_quality(inferred_context):
                    tool_args["study_context"] = inferred_context
                    tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)
                elif _should_default_study_context(preflight_reference_texts, tool_args):
                    tool_args["study_context"] = {"raw_notes": "按默认", "using_defaults": True}
                    tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)
                else:
                    context_answer = yield {
                        "type": "ask_user",
                        "ask_type": "review",
                        "question": _study_plan_intake_question(tool_args),
                        "options": [],
                        "data": None,
                    }
                    if _is_cancelled_answer(str(context_answer or "")):
                        message_id = str(uuid.uuid4())
                        text = "好的，我先不生成复习计划。你整理好范围或目标后再告诉我。"
                        yield {"type": "text", "message_id": message_id, "content": text}
                        await _save_message(db, session_id, "assistant", text)
                        yield {"type": "done"}
                        return
                    context_text = str(context_answer or "按默认")
                    context = _extract_study_context_from_text(context_text)
                    if not _study_context_has_quality(context):
                        context = {"raw_notes": context_text, "using_defaults": True}
                    tool_args["study_context"] = context
                    tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)
                    preflight_reference_texts.append(context_text)
                    preflight_user_texts.append(context_text)

            if tool_name == "create_work_plan" and not _work_context_has_quality(tool_args.get("work_context")):
                inferred_context = _work_context_from_reference_texts(preflight_reference_texts)
                if _work_context_has_quality(inferred_context):
                    tool_args["work_context"] = inferred_context
                    tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)
                else:
                    work_items = tool_args.get("work_items")
                    title = "作业任务"
                    if isinstance(work_items, list) and work_items and isinstance(work_items[0], dict):
                        title = str(work_items[0].get("title") or title)
                    context_answer = yield {
                        "type": "ask_user",
                        "ask_type": "review",
                        "question": _work_plan_intake_question(title),
                        "options": [],
                        "data": None,
                    }
                    if _is_cancelled_answer(str(context_answer or "")):
                        message_id = str(uuid.uuid4())
                        text = "好的，我先不生成作业计划。你整理好要求后再告诉我。"
                        yield {"type": "text", "message_id": message_id, "content": text}
                        await _save_message(db, session_id, "assistant", text)
                        yield {"type": "done"}
                        return
                    context_text = str(context_answer or "按默认")
                    context = _extract_work_context_from_text(context_text)
                    if not _work_context_has_quality(context):
                        context = {"raw_notes": context_text, "using_defaults": True}
                    tool_args["work_context"] = context
                    tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)
                    preflight_reference_texts.append(context_text)
                    preflight_user_texts.append(context_text)

            schema_preflight_error = tool_schema_preflight_error(
                tool_name,
                tool_args,
                TOOL_DEFINITIONS,
            )
            if schema_preflight_error is not None:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(schema_preflight_error, ensure_ascii=False),
                    }
                )
                continue

            tool_args, preflight_changed = apply_tool_preflight(
                tool_name,
                tool_args,
                preflight_reference_texts,
            )
            if preflight_changed:
                tool_call["function"]["arguments"] = json.dumps(tool_args, ensure_ascii=False)

            yield {"type": "tool_call", "name": tool_name, "args": tool_args}

            if tool_name == "ask_user":
                result = await execute_tool(tool_name, tool_args, db, user.id)
                ask_type = _normalize_ask_type(result)
                user_response = yield {**result, "type": "ask_user", "ask_type": ask_type}
                if user_response is None:
                    user_response = "确认"
                question = str(result.get("question") or "")
                if question and should_include_confirmed_question(user_response):
                    preflight_reference_texts.append(question)
                preflight_reference_texts.append(str(user_response))
                preflight_user_texts.append(str(user_response))
                tool_result_content = json.dumps({"user_response": user_response}, ensure_ascii=False)
            else:
                result = await execute_tool(tool_name, tool_args, db, user.id)
                tool_result_content = compress_tool_result(tool_name, result)
                if "error" in result:
                    error_count[tool_name] = error_count.get(tool_name, 0) + 1
                elif tool_name == "get_free_slots" and isinstance(result.get("slots"), list):
                    last_free_slots_result = result
                yield {"type": "tool_result", "name": tool_name, "result": result}
                await _save_message(
                    db,
                    session_id,
                    "assistant",
                    _to_persisted_tool_summary(tool_name, tool_result_content),
                    is_compressed=True,
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result_content,
                }
            )

            step += 1
            tool_history.append(tool_name)
            await _log_step(db, user.id, session_id, step, tool_name, tool_args, result)

            if tool_name == "create_study_plan" and "error" not in result:
                shortcut = _run_confirmed_study_plan_write(
                    result.get("tasks"),
                    user,
                    session_id,
                    db,
                    step,
                )
                try:
                    event = await shortcut.__anext__()
                    while True:
                        if event["type"] == "ask_user":
                            user_response = yield event
                            event = await shortcut.asend(user_response)
                        else:
                            yield event
                            event = await shortcut.__anext__()
                except StopAsyncIteration:
                    pass
                return

            if tool_name == "create_work_plan" and "error" not in result:
                shortcut = _run_confirmed_work_plan_write(
                    result.get("tasks"),
                    user,
                    session_id,
                    db,
                    step,
                )
                try:
                    event = await shortcut.__anext__()
                    while True:
                        if event["type"] == "ask_user":
                            user_response = yield event
                            event = await shortcut.asend(user_response)
                        else:
                            yield event
                            event = await shortcut.__anext__()
                except StopAsyncIteration:
                    pass
                return

    yield {"type": "error", "message": "Agent loop reached the maximum number of iterations."}
    yield {"type": "done"}


async def _save_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    *,
    is_compressed: bool = False,
) -> None:
    message = ConversationMessage(
        session_id=session_id,
        role=role,
        content=content,
        is_compressed=is_compressed,
    )
    db.add(message)
    await db.commit()


async def _log_step(
    db: AsyncSession,
    user_id: str,
    session_id: str,
    step: int,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_result: dict[str, Any],
) -> None:
    log = AgentLog(
        user_id=user_id,
        session_id=session_id,
        step=step,
        tool_called=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
    )
    db.add(log)
    await db.commit()
