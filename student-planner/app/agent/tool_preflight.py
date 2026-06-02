import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ReminderSlot:
    advance_minutes: int | None


_ADVANCE_RE = re.compile(
    r"提前\s*(?P<num>\d+|[零〇一二两三四五六七八九十百半]+)\s*"
    r"(?P<unit>个?小时|小时|h|H|分钟|分)"
)
_AT_TIME_RE = re.compile(
    r"(?:准点|到点|开始时|开始的时候)\s*提醒|"
    r"提醒\s*(?:准点|到点)|"
    r"提前\s*(?:0|零|〇)\s*(?:分钟|分)?\s*提醒?"
)
_CANCEL_RE = re.compile(
    r"(?:不|不用|不要|无需|别)\s*(?:再)?\s*(?:提醒|设置提醒|加提醒)|"
    r"(?:取消|关掉|关闭|去掉|删除)\s*(?:这个|该|任务)?\s*提醒|"
    r"提醒\s*(?:取消|关掉|关闭|去掉|删除)"
)
_AFFIRMATIVE_RE = re.compile(r"^(?:确认|可以|好|好的|对|是|嗯|行|没问题|按这个|就这样)[。.!！\s]*$")
_TASK_UPDATE_RE = re.compile(r"(?:改到|改成|改为|修改|调整|换到|挪到|改一下)")
_TASK_CREATE_RE = re.compile(r"(?:创建|新建|新增|生成|加一个|加一条|安排一个新的|拆成)")
_TASK_REFERENCE_RE = re.compile(r"(?:任务|刚才|已有|原来|之前|复习|作业|提醒|20\d{2}-\d{2}-\d{2})")


def apply_tool_preflight(
    tool_name: str,
    tool_args: dict[str, Any],
    reference_texts: Iterable[str],
) -> tuple[dict[str, Any], bool]:
    """Align low-ambiguity reminder slots from user-confirmed text into tool args."""
    slot = extract_reminder_slot(reference_texts)
    if slot is None:
        return tool_args, False

    updated = dict(tool_args)
    if tool_name in {"create_task", "update_task"}:
        has_reminder_arg = "reminder_advance_minutes" in updated
        current_minutes = _coerce_optional_int(updated.get("reminder_advance_minutes"))
        if has_reminder_arg and current_minutes == slot.advance_minutes:
            return tool_args, False
        updated["reminder_advance_minutes"] = slot.advance_minutes
        return updated, True

    if tool_name == "set_reminder" and slot.advance_minutes is not None:
        if _coerce_optional_int(updated.get("advance_minutes")) == slot.advance_minutes:
            return tool_args, False
        updated["advance_minutes"] = slot.advance_minutes
        return updated, True

    return tool_args, False


def task_tool_preflight_error(tool_name: str, user_texts: Iterable[str]) -> dict[str, str] | None:
    if tool_name != "create_task" or not looks_like_task_update_intent(user_texts):
        return None
    return {
        "error": "This user request is to update an existing task, not create a new task.",
        "suggestion": (
            "Use list_tasks to identify the target task, then ask_user to confirm, "
            "then call update_task with scheduled_date/start_time/end_time and "
            "reminder_advance_minutes if present, or null when the user cancels the reminder."
        ),
    }


def tool_schema_preflight_error(
    tool_name: str,
    tool_args: dict[str, Any],
    tool_definitions: Iterable[dict[str, Any]],
) -> dict[str, str] | None:
    tool_definition = _find_tool_definition(tool_name, tool_definitions)
    if tool_definition is None:
        return None

    parameters = tool_definition.get("function", {}).get("parameters", {})
    required = list(parameters.get("required") or [])
    missing = [name for name in required if _is_missing_required_arg(tool_args, name)]
    if missing:
        return {
            "error": (
                f"Tool {tool_name} is missing required argument(s): "
                f"{', '.join(missing)}."
            ),
            "suggestion": (
                "Ask the user for the missing information or retry the same tool "
                "with complete arguments before executing it."
            ),
        }

    properties = parameters.get("properties") or {}
    invalid_enums: list[str] = []
    for name, value in tool_args.items():
        if value is None:
            continue
        schema = properties.get(name)
        if not isinstance(schema, dict):
            continue
        enum_values = schema.get("enum")
        if isinstance(enum_values, list) and value not in enum_values:
            invalid_enums.append(f"{name}={value!r}")

    if invalid_enums:
        return {
            "error": (
                f"Tool {tool_name} has invalid enum argument(s): "
                f"{', '.join(invalid_enums)}."
            ),
            "suggestion": "Retry with values from the tool schema enum, or ask the user to choose.",
        }

    return None


def looks_like_task_update_intent(user_texts: Iterable[str]) -> bool:
    compact_text = "\n".join(str(text or "") for text in user_texts)
    if not compact_text:
        return False
    if _TASK_CREATE_RE.search(compact_text):
        return False
    return bool(_TASK_UPDATE_RE.search(compact_text) and _TASK_REFERENCE_RE.search(compact_text))


def extract_reminder_slot(reference_texts: Iterable[str]) -> ReminderSlot | None:
    slot: ReminderSlot | None = None
    for text in reference_texts:
        text_slot = _extract_last_reminder_slot(str(text or ""))
        if text_slot is not None:
            slot = text_slot
    return slot


def should_include_confirmed_question(user_response: str | None) -> bool:
    return bool(_AFFIRMATIVE_RE.match(str(user_response or "").strip()))


def _extract_last_reminder_slot(text: str) -> ReminderSlot | None:
    matches: list[tuple[int, ReminderSlot]] = []

    for match in _CANCEL_RE.finditer(text):
        matches.append((match.start(), ReminderSlot(advance_minutes=None)))

    for match in _AT_TIME_RE.finditer(text):
        matches.append((match.start(), ReminderSlot(advance_minutes=0)))

    for match in _ADVANCE_RE.finditer(text):
        minutes = _parse_advance_minutes(match.group("num"), match.group("unit"))
        if minutes is not None:
            matches.append((match.start(), ReminderSlot(advance_minutes=minutes)))

    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def _parse_advance_minutes(raw_number: str, unit: str) -> int | None:
    number = _parse_number(raw_number)
    if number is None:
        return None
    if "小时" in unit or unit.lower() == "h":
        return int(number * 60)
    return int(number)


def _parse_number(value: str) -> float | None:
    value = str(value or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(int(value))
    if value == "半":
        return 0.5

    digits = {
        "零": 0,
        "〇": 0,
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
    if "百" in value:
        left, _, right = value.partition("百")
        hundreds = digits.get(left, 1 if left == "" else None)
        if hundreds is None:
            return None
        tail = _parse_number(right) if right else 0
        return hundreds * 100 + tail
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1 if left == "" else None)
        ones = digits.get(right, 0 if right == "" else None)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    if all(char in digits for char in value):
        total = 0
        for char in value:
            total = total * 10 + digits[char]
        return float(total)
    return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_tool_definition(
    tool_name: str,
    tool_definitions: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    for definition in tool_definitions:
        function = definition.get("function")
        if isinstance(function, dict) and function.get("name") == tool_name:
            return definition
    return None


def _is_missing_required_arg(tool_args: dict[str, Any], name: str) -> bool:
    if name not in tool_args:
        return True
    value = tool_args.get(name)
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False
