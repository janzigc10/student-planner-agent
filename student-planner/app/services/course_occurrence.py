"""Course occurrence helpers shared by calendar, availability, and reminders."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any


def teaching_week_for_date(target_date: date, semester_start: date | None) -> int | None:
    if semester_start is None:
        return None
    diff_days = (target_date - semester_start).days
    if diff_days < 0:
        return None
    return diff_days // 7 + 1


def active_weeks_from_course(course: Any) -> set[int]:
    start = _as_int(getattr(course, "week_start", None), 1)
    end = _as_int(getattr(course, "week_end", None), start)
    if end < start:
        end = start

    explicit_weeks = _weeks_from_text(getattr(course, "week_text", None))
    if explicit_weeks:
        return {week for week in explicit_weeks if start <= week <= end}

    pattern = str(getattr(course, "week_pattern", None) or "all").lower()
    weeks = set(range(start, end + 1))
    if pattern == "odd":
        return {week for week in weeks if week % 2 == 1}
    if pattern == "even":
        return {week for week in weeks if week % 2 == 0}
    return weeks


def course_occurs_on_date(
    course: Any,
    target_date: date,
    semester_start: date | None,
) -> bool:
    if int(getattr(course, "weekday", 0) or 0) != target_date.isoweekday():
        return False

    teaching_week = teaching_week_for_date(target_date, semester_start)
    if teaching_week is None:
        return semester_start is None

    return teaching_week in active_weeks_from_course(course)


def next_course_occurrence(
    course: Any,
    semester_start: date | None,
    now: datetime | None = None,
    *,
    search_days: int = 370,
) -> datetime | None:
    current = now or datetime.now()
    start_time = time.fromisoformat(str(getattr(course, "start_time")))
    for offset in range(search_days + 1):
        candidate_date = current.date() + timedelta(days=offset)
        candidate = datetime.combine(candidate_date, start_time)
        if candidate <= current:
            continue
        if course_occurs_on_date(course, candidate_date, semester_start):
            return candidate
    return None


def _weeks_from_text(text: str | None) -> set[int]:
    if not text:
        return set()
    source = str(text).replace("\uff0c", ",")
    if "," not in source:
        return set()

    weeks: set[int] = set()
    for token in [part.strip() for part in source.split(",") if part.strip()]:
        range_match = re.match(r"^(\d{1,2})\s*[-~\uff5e\u2014\u2013]\s*(\d{1,2})", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if end < start:
                start, end = end, start
            weeks.update(range(start, end + 1))
            continue
        number_match = re.search(r"\d{1,2}", token)
        if number_match:
            weeks.add(int(number_match.group(0)))
    return weeks


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
