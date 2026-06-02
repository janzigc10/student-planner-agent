import json
import re
import uuid
from typing import Any, AsyncGenerator

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
    "复习",
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


def _looks_like_task_write_context(user_texts: list[str]) -> bool:
    compact_text = "\n".join(str(text or "") for text in user_texts).lower().replace(" ", "")
    return any(keyword in compact_text for keyword in _TASK_WRITE_CONTEXT_KEYWORDS)


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


def _should_handle_course_merge_locally(
    user_message: str,
    history_messages: list[ConversationMessage],
) -> bool:
    compact_message = (user_message or "").strip().lower().replace(" ", "")
    if not compact_message:
        return False
    if any(keyword in compact_message for keyword in _SCHEDULE_IMPORT_KEYWORDS):
        return False

    merge_keywords = ("优化成一门", "合并成一门", "还是两门课", "重复课程", "重复的课")
    if any(keyword in compact_message for keyword in merge_keywords):
        return True
    return _is_course_followup_message(user_message, history_messages)


def _match_courses_from_text(user_text: str, courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for course in courses:
        course_name = str(course.get("name") or "").strip()
        if course_name and course_name in user_text:
            matches.append(course)
    return matches


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
    selected_names_text = user_message
    if not _is_course_followup_message(user_message, history_messages):
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
    await _save_message(
        db,
        session_id,
        "assistant",
        _to_persisted_tool_summary("list_courses", compress_tool_result("list_courses", list_result)),
        is_compressed=True,
    )
    await _log_step(db, user.id, session_id, 1, "list_courses", {}, list_result)

    matched_courses = _match_courses_from_text(selected_names_text, list_result.get("courses", []))
    merge_plan = _build_course_merge_plan(matched_courses)
    if not merge_plan:
        message_id = str(uuid.uuid4())
        text = "我先查了当前课表，但还没定位到可以直接合并的重复记录。你可以把要保留的课程名再明确发我一次。"
        yield {"type": "text", "message_id": message_id, "content": text}
        await _save_message(db, session_id, "assistant", text)
        yield {"type": "done"}
        return

    review_data = {
        "plans": [
            {
                "weekday": item["weekday"],
                "start_time": item["start_time"],
                "end_time": item["end_time"],
                "location": item["location"],
                "week_start": item["week_start"],
                "week_end": item["week_end"],
                "week_pattern": item["week_pattern"],
                "current_names": item["current_names"],
                "keep_name": item["keep_name"],
                "delete_count": len(item["delete_ids"]),
            }
            for item in merge_plan
        ],
        "count": len(merge_plan),
    }
    confirm_answer = yield {
        "type": "ask_user",
        "ask_type": "review",
        "question": "我准备把这些重复课程合并成每个时段 1 条记录。确认后我就直接处理。",
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
    for item in merge_plan:
        rename_to = item.get("rename_to")
        keep_course_id = str(item.get("keep_course_id") or "")
        if rename_to and keep_course_id:
            update_args = {"course_id": keep_course_id, "name": rename_to}
            yield {"type": "tool_call", "name": "update_course", "args": update_args}
            update_result = await execute_tool("update_course", update_args, db, user.id)
            yield {"type": "tool_result", "name": "update_course", "result": update_result}
            step += 1
            await _save_message(
                db,
                session_id,
                "assistant",
                _to_persisted_tool_summary("update_course", compress_tool_result("update_course", update_result)),
                is_compressed=True,
            )
            await _log_step(db, user.id, session_id, step, "update_course", update_args, update_result)

        for course_id in item.get("delete_ids", []):
            delete_args = {"course_id": course_id}
            yield {"type": "tool_call", "name": "delete_course", "args": delete_args}
            delete_result = await execute_tool("delete_course", delete_args, db, user.id)
            yield {"type": "tool_result", "name": "delete_course", "result": delete_result}
            step += 1
            await _save_message(
                db,
                session_id,
                "assistant",
                _to_persisted_tool_summary("delete_course", compress_tool_result("delete_course", delete_result)),
                is_compressed=True,
            )
            await _log_step(db, user.id, session_id, step, "delete_course", delete_args, delete_result)

    merged_names = "、".join(dict.fromkeys(item["keep_name"] for item in merge_plan))
    message_id = str(uuid.uuid4())
    text = f"已经帮你把重复课程合并好了，当前保留的是：{merged_names}。"
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


async def run_agent_loop(
    user_message: str,
    user: User,
    session_id: str,
    db: AsyncSession,
    llm_client: AsyncOpenAI,
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

    messages.append({"role": "user", "content": user_message})
    await _save_message(db, session_id, "user", user_message)

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
    error_count: dict[str, int] = {}
    step = 0

    for iteration in range(MAX_ITERATIONS):
        check_max_loop_iterations(iteration, MAX_ITERATIONS)
        response: dict[str, Any] | None = None
        response_message_id = str(uuid.uuid4())
        streamed_deltas: list[str] = []
        tool_choice = "required" if _should_require_task_tool_response(preflight_user_texts, tool_history) else "auto"
        completion_kwargs: dict[str, Any] = {"tools": TOOL_DEFINITIONS}
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
