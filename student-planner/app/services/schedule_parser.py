"""Parse Excel course schedules into structured raw course records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import openpyxl


@dataclass
class RawCourse:
    name: str
    teacher: str | None
    location: str | None
    weekday: int
    period: str
    week_start: int
    week_end: int


_WEEKDAY_MAP: dict[str, int] = {
    "周一": 1,
    "星期一": 1,
    "Monday": 1,
    "Mon": 1,
    "周二": 2,
    "星期二": 2,
    "Tuesday": 2,
    "Tue": 2,
    "周三": 3,
    "星期三": 3,
    "Wednesday": 3,
    "Wed": 3,
    "周四": 4,
    "星期四": 4,
    "Thursday": 4,
    "Thu": 4,
    "周五": 5,
    "星期五": 5,
    "Friday": 5,
    "Fri": 5,
    "周六": 6,
    "星期六": 6,
    "Saturday": 6,
    "Sat": 6,
    "周日": 7,
    "星期日": 7,
    "Sunday": 7,
    "Sun": 7,
}

_WEEK_RANGE_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s*周")
_PERIOD_RE = re.compile(r"(\d+)\s*-\s*(\d+)")
_TEACHER_RE = re.compile(r"老师|教授|讲师")


def parse_excel_schedule(file_path: Path | str | BinaryIO) -> list[RawCourse]:
    workbook = openpyxl.load_workbook(file_path, data_only=True)
    worksheet = workbook.active

    col_weekday: dict[int, int] = {}
    for col_idx in range(2, worksheet.max_column + 1):
        header = str(worksheet.cell(row=1, column=col_idx).value or "").strip()
        for label, weekday in _WEEKDAY_MAP.items():
            if label in header:
                col_weekday[col_idx] = weekday
                break

    courses: list[RawCourse] = []
    for row_idx in range(2, worksheet.max_row + 1):
        period_text = str(worksheet.cell(row=row_idx, column=1).value or "")
        period = _extract_period(period_text)
        if period is None:
            continue

        for col_idx, weekday in col_weekday.items():
            cell_value = worksheet.cell(row=row_idx, column=col_idx).value
            if not cell_value:
                continue
            courses.extend(_parse_cell(str(cell_value), weekday, period))

    workbook.close()
    return courses


def _extract_period(text: str) -> str | None:
    normalized = text.replace("—", "-").replace("–", "-")
    match = _PERIOD_RE.search(normalized)
    if match is None:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def _parse_cell(text: str, weekday: int, period: str) -> list[RawCourse]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    name = lines[0]
    teacher: str | None = None
    location: str | None = None
    week_start = 1
    week_end = 16
    extra_lines: list[str] = []

    for line in lines[1:]:
        week_match = _WEEK_RANGE_RE.search(line)
        if week_match:
            week_start = int(week_match.group(1))
            week_end = int(week_match.group(2))
            continue
        if _TEACHER_RE.search(line):
            teacher = line
            continue
        extra_lines.append(line)

    if extra_lines:
        location = extra_lines[0]

    return [
        RawCourse(
            name=name,
            teacher=teacher,
            location=location,
            weekday=weekday,
            period=period,
            week_start=week_start,
            week_end=week_end,
        )
    ]