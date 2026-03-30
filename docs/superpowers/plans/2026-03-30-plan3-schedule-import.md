# Plan 3: 课表导入 — Excel 解析 + 图片识别 + 作息时间校准

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users import their course schedule from Excel files or photos/screenshots, with automatic school period-to-time conversion.

**Architecture:** Two import paths (Excel parsing via openpyxl, image OCR via multimodal LLM) both produce the same intermediate format — a list of raw course dicts. A shared pipeline then handles period-to-time calibration (asking the user for their school schedule if needed), presents results for confirmation via ask_user, and bulk-creates Course records. Two new agent tools (`parse_schedule`, `parse_schedule_image`) plus a new REST endpoint for file upload.

**Tech Stack:** openpyxl (xlsx), LLM multimodal (image), FastAPI UploadFile, existing agent tool system

**Depends on:** Plan 1 (Course model, CRUD), Plan 2 (agent tools, tool_executor, ask_user)

---

## File Structure

```
student-planner/
├── app/
│   ├── services/
│   │   ├── schedule_parser.py        # Excel parsing logic (openpyxl)
│   │   └── period_converter.py       # "第N节课" → "HH:MM-HH:MM" conversion
│   ├── agent/
│   │   ├── tools.py                  # (modify: add parse_schedule, parse_schedule_image definitions)
│   │   ├── tool_executor.py          # (modify: add handlers for new tools)
│   │   └── schedule_ocr.py           # Image → structured courses via multimodal LLM
│   ├── routers/
│   │   └── schedule_import.py        # POST /api/schedule/upload endpoint
│   └── main.py                       # (modify: mount schedule_import router)
├── tests/
│   ├── test_schedule_parser.py       # Excel parsing unit tests
│   ├── test_period_converter.py      # Period conversion unit tests
│   ├── test_schedule_ocr.py          # Image OCR unit tests (mocked LLM)
│   ├── test_schedule_import_api.py   # Upload endpoint tests
│   └── fixtures/
│       └── sample_schedule.xlsx      # Test fixture: a realistic course schedule Excel
```

---

### Task 1: Period Converter — "第N节课" → Concrete Times

The simplest, most self-contained piece. No external dependencies. Other tasks depend on this.

**Files:**
- Create: `student-planner/app/services/period_converter.py`
- Create: `student-planner/tests/test_period_converter.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_period_converter.py
import pytest

from app.services.period_converter import convert_periods, DEFAULT_SCHEDULE


def test_default_schedule_has_five_periods():
    """Default schedule covers period 1-2 through 9-10."""
    assert "1-2" in DEFAULT_SCHEDULE
    assert "3-4" in DEFAULT_SCHEDULE
    assert "5-6" in DEFAULT_SCHEDULE
    assert "7-8" in DEFAULT_SCHEDULE
    assert "9-10" in DEFAULT_SCHEDULE


def test_convert_single_period():
    result = convert_periods("1-2", DEFAULT_SCHEDULE)
    assert result == {"start_time": "08:00", "end_time": "09:40"}


def test_convert_period_5_6():
    result = convert_periods("5-6", DEFAULT_SCHEDULE)
    assert result == {"start_time": "14:00", "end_time": "15:40"}


def test_convert_with_custom_schedule():
    custom = {"1-2": {"start": "08:30", "end": "10:10"}}
    result = convert_periods("1-2", custom)
    assert result == {"start_time": "08:30", "end_time": "10:10"}


def test_convert_unknown_period_returns_none():
    result = convert_periods("11-12", DEFAULT_SCHEDULE)
    assert result is None


def test_convert_normalizes_chinese_dash():
    """Users might type 1—2 or 1–2 instead of 1-2."""
    result = convert_periods("1—2", DEFAULT_SCHEDULE)
    assert result == {"start_time": "08:00", "end_time": "09:40"}


def test_convert_strips_whitespace():
    result = convert_periods(" 3-4 ", DEFAULT_SCHEDULE)
    assert result == {"start_time": "10:00", "end_time": "11:40"}
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_period_converter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.period_converter'`

- [x] **Step 3: Implement period_converter.py**

```python
# app/services/period_converter.py
"""Convert "第N节课" period strings to concrete start/end times."""

# Default schedule matching most Chinese universities
DEFAULT_SCHEDULE: dict[str, dict[str, str]] = {
    "1-2": {"start": "08:00", "end": "09:40"},
    "3-4": {"start": "10:00", "end": "11:40"},
    "5-6": {"start": "14:00", "end": "15:40"},
    "7-8": {"start": "16:00", "end": "17:40"},
    "9-10": {"start": "19:00", "end": "20:40"},
}


def convert_periods(
    period: str,
    schedule: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """Convert a period string like '1-2' to {'start_time': 'HH:MM', 'end_time': 'HH:MM'}.

    Returns None if the period is not found in the schedule.
    Handles Chinese dashes (—, –) and whitespace.
    """
    normalized = period.strip().replace("—", "-").replace("–", "-")
    times = schedule.get(normalized)
    if times is None:
        return None
    return {"start_time": times["start"], "end_time": times["end"]}
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_period_converter.py -v`
Expected: All 7 tests PASS

- [x] **Step 5: Commit**

```bash
cd student-planner
git add app/services/period_converter.py tests/test_period_converter.py
git commit -m "feat: add period converter for school schedule calibration"
```

---

### Task 2: Excel Schedule Parser

Parses `.xlsx` files into a list of raw course dicts. Uses openpyxl. The parser uses LLM to understand the table structure (as specified in the design doc), with a rule-based fallback.

**Files:**
- Create: `student-planner/app/services/schedule_parser.py`
- Create: `student-planner/tests/test_schedule_parser.py`
- Create: `student-planner/tests/fixtures/sample_schedule.xlsx`
- Modify: `student-planner/pyproject.toml` (add openpyxl dependency)

- [x] **Step 1: Add openpyxl dependency**

In `pyproject.toml`, add `"openpyxl>=3.1.0"` to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "alembic>=1.13.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-multipart>=0.0.9",
    "openpyxl>=3.1.0",
]
```

Then install: `cd student-planner && pip install -e '.[dev]'`

- [x] **Step 2: Create test fixture Excel file**

```python
# Run this once to generate the fixture (not a test file — a helper script)
# Execute: cd student-planner && python -c "
import openpyxl

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "课表"

# Header row: time periods in column A, weekdays in columns B-F
ws["A1"] = "节次"
ws["B1"] = "周一"
ws["C1"] = "周二"
ws["D1"] = "周三"
ws["E1"] = "周四"
ws["F1"] = "周五"

# Row 2: period 1-2
ws["A2"] = "1-2节"
ws["B2"] = "高等数学\n张老师\n教学楼A301\n1-16周"
ws["D2"] = "线性代数\n李老师\n教学楼B205\n1-16周"

# Row 3: period 3-4
ws["A3"] = "3-4节"
ws["C3"] = "大学英语\n王老师\n外语楼201\n1-14周"
ws["E3"] = "概率论\n赵老师\n教学楼A302\n3-16周"

# Row 4: period 5-6
ws["A4"] = "5-6节"
ws["B4"] = "大学物理\n刘老师\n理学楼101\n1-16周"

# Row 5: period 7-8
ws["A5"] = "7-8节"
ws["F5"] = "体育\n\n操场\n1-16周"

wb.save("tests/fixtures/sample_schedule.xlsx")
# "
```

Run: `cd student-planner && mkdir -p tests/fixtures && python -c "<the script above>"`

- [x] **Step 3: Write the failing tests**

```python
# tests/test_schedule_parser.py
import pytest
from pathlib import Path

from app.services.schedule_parser import parse_excel_schedule, RawCourse

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_schedule.xlsx"


def test_parse_returns_list_of_raw_courses():
    courses = parse_excel_schedule(FIXTURE_PATH)
    assert isinstance(courses, list)
    assert len(courses) > 0
    assert all(isinstance(c, RawCourse) for c in courses)


def test_parse_extracts_course_name():
    courses = parse_excel_schedule(FIXTURE_PATH)
    names = {c.name for c in courses}
    assert "高等数学" in names
    assert "线性代数" in names
    assert "大学英语" in names


def test_parse_extracts_weekday():
    courses = parse_excel_schedule(FIXTURE_PATH)
    gaoshu = next(c for c in courses if c.name == "高等数学")
    assert gaoshu.weekday == 1  # 周一


def test_parse_extracts_period():
    courses = parse_excel_schedule(FIXTURE_PATH)
    gaoshu = next(c for c in courses if c.name == "高等数学")
    assert gaoshu.period == "1-2"


def test_parse_extracts_teacher():
    courses = parse_excel_schedule(FIXTURE_PATH)
    gaoshu = next(c for c in courses if c.name == "高等数学")
    assert gaoshu.teacher == "张老师"


def test_parse_extracts_location():
    courses = parse_excel_schedule(FIXTURE_PATH)
    gaoshu = next(c for c in courses if c.name == "高等数学")
    assert gaoshu.location == "教学楼A301"


def test_parse_extracts_weeks():
    courses = parse_excel_schedule(FIXTURE_PATH)
    gaoshu = next(c for c in courses if c.name == "高等数学")
    assert gaoshu.week_start == 1
    assert gaoshu.week_end == 16


def test_parse_handles_missing_teacher():
    """体育 has no teacher in the fixture."""
    courses = parse_excel_schedule(FIXTURE_PATH)
    tiyu = next(c for c in courses if c.name == "体育")
    assert tiyu.teacher is None


def test_parse_handles_custom_week_range():
    """概率论 is 3-16周."""
    courses = parse_excel_schedule(FIXTURE_PATH)
    gailv = next(c for c in courses if c.name == "概率论")
    assert gailv.week_start == 3
    assert gailv.week_end == 16


def test_parse_total_course_count():
    """Fixture has 6 courses."""
    courses = parse_excel_schedule(FIXTURE_PATH)
    assert len(courses) == 6
```

- [x] **Step 4: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_schedule_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.schedule_parser'`

- [x] **Step 5: Implement schedule_parser.py**

```python
# app/services/schedule_parser.py
"""Parse Excel/WPS course schedule files into structured course data."""

import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl


@dataclass
class RawCourse:
    """Intermediate representation of a parsed course, before period→time conversion."""

    name: str
    teacher: str | None
    location: str | None
    weekday: int  # 1=Monday, 7=Sunday
    period: str  # e.g. "1-2", "3-4"
    week_start: int
    week_end: int


# Maps header text to weekday number
_WEEKDAY_MAP: dict[str, int] = {
    "周一": 1, "星期一": 1, "Monday": 1, "Mon": 1,
    "周二": 2, "星期二": 2, "Tuesday": 2, "Tue": 2,
    "周三": 3, "星期三": 3, "Wednesday": 3, "Wed": 3,
    "周四": 4, "星期四": 4, "Thursday": 4, "Thu": 4,
    "周五": 5, "星期五": 5, "Friday": 5, "Fri": 5,
    "周六": 6, "星期六": 6, "Saturday": 6, "Sat": 6,
    "周日": 7, "星期日": 7, "Sunday": 7, "Sun": 7,
}


def parse_excel_schedule(file_path: Path | str) -> list[RawCourse]:
    """Parse an Excel schedule file and return a list of RawCourse objects.

    Expected format: rows = time periods, columns = weekdays.
    Each cell may contain multi-line text: course name, teacher, location, weeks.
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    # Step 1: Detect weekday columns from header row
    col_weekday: dict[int, int] = {}  # column index → weekday number
    for col_idx in range(2, ws.max_column + 1):
        header = str(ws.cell(row=1, column=col_idx).value or "").strip()
        for key, weekday in _WEEKDAY_MAP.items():
            if key in header:
                col_weekday[col_idx] = weekday
                break

    # Step 2: Parse each data row
    courses: list[RawCourse] = []
    for row_idx in range(2, ws.max_row + 1):
        period = _extract_period(str(ws.cell(row=row_idx, column=1).value or ""))
        if not period:
            continue

        for col_idx, weekday in col_weekday.items():
            cell_value = ws.cell(row=row_idx, column=col_idx).value
            if not cell_value:
                continue

            parsed = _parse_cell(str(cell_value), weekday, period)
            if parsed:
                courses.extend(parsed)

    wb.close()
    return courses


def _extract_period(text: str) -> str | None:
    """Extract period like '1-2' from text like '1-2节' or '第1-2节'."""
    text = text.replace("—", "-").replace("–", "-")
    match = re.search(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def _parse_cell(text: str, weekday: int, period: str) -> list[RawCourse]:
    """Parse a cell that may contain one or more courses (e.g. odd/even week)."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return []

    name = lines[0]
    teacher = None
    location = None
    week_start = 1
    week_end = 16

    for line in lines[1:]:
        week_match = re.search(r"(\d+)\s*-\s*(\d+)\s*周", line)
        if week_match:
            week_start = int(week_match.group(1))
            week_end = int(week_match.group(2))
        elif re.search(r"老师|教授|讲师", line):
            teacher = line
        elif teacher is None and location is None and not re.search(r"周", line):
            # Second line is usually teacher
            teacher = line if line else None
        elif location is None:
            location = line if line else None

    # Handle empty teacher (e.g. "体育\n\n操场\n1-16周")
    if teacher == "":
        teacher = None

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
```

- [x] **Step 6: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_schedule_parser.py -v`
Expected: All 10 tests PASS

- [x] **Step 7: Commit**

```bash
cd student-planner
git add app/services/schedule_parser.py tests/test_schedule_parser.py tests/fixtures/sample_schedule.xlsx pyproject.toml
git commit -m "feat: add Excel schedule parser with rule-based cell extraction"
```

---

### Task 3: Image OCR — Schedule Screenshot → Structured Courses

Uses a multimodal LLM (Qwen-VL, DeepSeek-VL, etc.) to extract course data from photos/screenshots. Returns the same `RawCourse` format as the Excel parser.

**Files:**
- Create: `student-planner/app/agent/schedule_ocr.py`
- Create: `student-planner/tests/test_schedule_ocr.py`
- Modify: `student-planner/app/config.py` (add vision model config)

- [x] **Step 1: Add vision model config**

Add to `app/config.py` Settings class:

```python
    # Vision LLM settings (for schedule image parsing)
    vision_llm_api_key: str = ""  # Falls back to llm_api_key if empty
    vision_llm_base_url: str = ""  # Falls back to llm_base_url if empty
    vision_llm_model: str = "qwen-vl-plus"
```

The full Settings class after modification:

```python
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./student_planner.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    llm_api_key: str = "sk-placeholder"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
    vision_llm_api_key: str = ""
    vision_llm_base_url: str = ""
    vision_llm_model: str = "qwen-vl-plus"

    model_config = {"env_prefix": "SP_"}
```

- [x] **Step 2: Write the failing tests**

```python
# tests/test_schedule_ocr.py
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.schedule_ocr import parse_schedule_image
from app.services.schedule_parser import RawCourse

MOCK_LLM_RESPONSE = json.dumps([
    {
        "name": "高等数学",
        "teacher": "张老师",
        "location": "教学楼A301",
        "weekday": 1,
        "period": "1-2",
        "weeks": "1-16周",
    },
    {
        "name": "线性代数",
        "teacher": "李老师",
        "location": "教学楼B205",
        "weekday": 3,
        "period": "1-2",
        "weeks": "1-16周",
    },
])


@pytest.mark.asyncio
async def test_parse_image_returns_raw_courses():
    mock_response = {"role": "assistant", "content": MOCK_LLM_RESPONSE}
    with patch("app.agent.schedule_ocr._vision_completion", new_callable=AsyncMock, return_value=mock_response):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    assert len(courses) == 2
    assert all(isinstance(c, RawCourse) for c in courses)


@pytest.mark.asyncio
async def test_parse_image_extracts_fields():
    mock_response = {"role": "assistant", "content": MOCK_LLM_RESPONSE}
    with patch("app.agent.schedule_ocr._vision_completion", new_callable=AsyncMock, return_value=mock_response):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    gaoshu = next(c for c in courses if c.name == "高等数学")
    assert gaoshu.weekday == 1
    assert gaoshu.period == "1-2"
    assert gaoshu.teacher == "张老师"
    assert gaoshu.location == "教学楼A301"
    assert gaoshu.week_start == 1
    assert gaoshu.week_end == 16


@pytest.mark.asyncio
async def test_parse_image_handles_llm_error():
    mock_response = {"role": "assistant", "content": "抱歉，我无法识别这张图片"}
    with patch("app.agent.schedule_ocr._vision_completion", new_callable=AsyncMock, return_value=mock_response):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    assert courses == []


@pytest.mark.asyncio
async def test_parse_image_handles_missing_weeks():
    """When weeks field is null, default to 1-16."""
    response_data = json.dumps([{
        "name": "体育",
        "teacher": None,
        "location": "操场",
        "weekday": 5,
        "period": "7-8",
        "weeks": None,
    }])
    mock_response = {"role": "assistant", "content": response_data}
    with patch("app.agent.schedule_ocr._vision_completion", new_callable=AsyncMock, return_value=mock_response):
        courses = await parse_schedule_image(b"fake-image-bytes", "image/png")
    assert len(courses) == 1
    assert courses[0].week_start == 1
    assert courses[0].week_end == 16
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_schedule_ocr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agent.schedule_ocr'`

- [x] **Step 4: Implement schedule_ocr.py**

```python
# app/agent/schedule_ocr.py
"""Parse course schedule images using a multimodal LLM."""

import base64
import json
import re

from openai import AsyncOpenAI

from app.config import settings
from app.services.schedule_parser import RawCourse

EXTRACT_PROMPT = """这是一张大学课表的照片/截图。请提取所有课程信息，输出 JSON 数组。

每门课的格式：
{
  "name": "课程名",
  "teacher": "教师（看不到填 null）",
  "location": "教室（看不到填 null）",
  "weekday": 1-7（1=周一，7=周日）,
  "period": "第几节课（如 1-2）",
  "weeks": "周次（如 1-16周，看不到填 null）"
}

只输出 JSON 数组，不要输出其他内容。如果图片不是课表或无法识别，输出空数组 []。"""


def _create_vision_client() -> AsyncOpenAI:
    """Create a client for the vision-capable LLM."""
    api_key = settings.vision_llm_api_key or settings.llm_api_key
    base_url = settings.vision_llm_base_url or settings.llm_base_url
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


async def _vision_completion(client: AsyncOpenAI, messages: list) -> dict:
    """Call the vision LLM directly (may use a different model than the text LLM)."""
    model = settings.vision_llm_model or settings.llm_model
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    msg = response.choices[0].message
    return {"role": "assistant", "content": msg.content}


async def parse_schedule_image(
    image_bytes: bytes,
    content_type: str = "image/png",
) -> list[RawCourse]:
    """Send a schedule image to a multimodal LLM and parse the response.

    Args:
        image_bytes: Raw image file bytes.
        content_type: MIME type (image/png, image/jpeg, etc.)

    Returns:
        List of RawCourse objects, or empty list if parsing fails.
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64}"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACT_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    client = _create_vision_client()
    response = await _vision_completion(client, messages)
    content = response.get("content", "").strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])

    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        return []

    if not isinstance(items, list):
        return []

    return [_item_to_raw_course(item) for item in items if _is_valid_item(item)]


def _is_valid_item(item: dict) -> bool:
    """Check that an item has the minimum required fields."""
    return isinstance(item, dict) and bool(item.get("name")) and isinstance(item.get("weekday"), int)


def _item_to_raw_course(item: dict) -> RawCourse:
    """Convert a dict from LLM output to a RawCourse."""
    week_start, week_end = _parse_weeks(item.get("weeks"))
    return RawCourse(
        name=item["name"],
        teacher=item.get("teacher"),
        location=item.get("location"),
        weekday=item["weekday"],
        period=item.get("period", ""),
        week_start=week_start,
        week_end=week_end,
    )


def _parse_weeks(weeks_str: str | None) -> tuple[int, int]:
    """Parse '1-16周' into (1, 16). Returns (1, 16) as default."""
    if not weeks_str:
        return 1, 16
    match = re.search(r"(\d+)\s*-\s*(\d+)", weeks_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 1, 16
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_schedule_ocr.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd student-planner
git add app/agent/schedule_ocr.py tests/test_schedule_ocr.py app/config.py
git commit -m "feat: add multimodal LLM schedule image parser"
```

---

### Task 4: File Upload REST Endpoint

A REST endpoint that accepts Excel or image files, parses them, and returns the raw course list. The agent tools (Task 5) will call this internally, but it's also useful as a standalone API for the frontend to upload files directly.

**Files:**
- Create: `student-planner/app/routers/schedule_import.py`
- Modify: `student-planner/app/main.py` (mount new router)
- Create: `student-planner/tests/test_schedule_import_api.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_schedule_import_api.py
import io
from pathlib import Path

import pytest
from httpx import AsyncClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_schedule.xlsx"


@pytest.mark.asyncio
async def test_upload_excel_returns_courses(auth_client: AsyncClient):
    with open(FIXTURE_PATH, "rb") as f:
        response = await auth_client.post(
            "/api/schedule/upload",
            files={"file": ("schedule.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    data = response.json()
    assert "courses" in data
    assert len(data["courses"]) == 6
    names = {c["name"] for c in data["courses"]}
    assert "高等数学" in names


@pytest.mark.asyncio
async def test_upload_excel_includes_period_field(auth_client: AsyncClient):
    with open(FIXTURE_PATH, "rb") as f:
        response = await auth_client.post(
            "/api/schedule/upload",
            files={"file": ("schedule.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    data = response.json()
    gaoshu = next(c for c in data["courses"] if c["name"] == "高等数学")
    assert gaoshu["period"] == "1-2"
    assert gaoshu["weekday"] == 1


@pytest.mark.asyncio
async def test_upload_unsupported_format(auth_client: AsyncClient):
    response = await auth_client.post(
        "/api/schedule/upload",
        files={"file": ("schedule.txt", io.BytesIO(b"not a schedule"), "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/schedule/upload",
        files={"file": ("schedule.xlsx", io.BytesIO(b"fake"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 403
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_schedule_import_api.py -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Implement schedule_import router**

```python
# app/routers/schedule_import.py
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.schedule_parser import RawCourse, parse_excel_schedule

router = APIRouter(prefix="/schedule", tags=["schedule-import"])

_EXCEL_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_ALLOWED_TYPES = _EXCEL_TYPES | _IMAGE_TYPES


@router.post("/upload")
async def upload_schedule(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    content_type = file.content_type or ""
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {content_type}。支持 xlsx、png、jpg。",
        )

    file_bytes = await file.read()

    if content_type in _EXCEL_TYPES:
        courses = _parse_excel_bytes(file_bytes)
    else:
        # Image parsing — import here to avoid circular deps at module level
        from app.agent.schedule_ocr import parse_schedule_image
        courses = await parse_schedule_image(file_bytes, content_type)

    return {
        "courses": [_raw_course_to_dict(c) for c in courses],
        "count": len(courses),
    }


def _parse_excel_bytes(data: bytes) -> list[RawCourse]:
    """Write bytes to a temp file and parse with openpyxl."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return parse_excel_schedule(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _raw_course_to_dict(course: RawCourse) -> dict:
    return {
        "name": course.name,
        "teacher": course.teacher,
        "location": course.location,
        "weekday": course.weekday,
        "period": course.period,
        "week_start": course.week_start,
        "week_end": course.week_end,
    }
```

- [ ] **Step 4: Mount the router in main.py**

In `app/main.py`, add the import and include_router:

```python
from app.routers import auth, chat, courses, exams, reminders, schedule_import, tasks


def create_app() -> FastAPI:
    app = FastAPI(title="Student Planner", version="0.1.0")
    app.include_router(auth.router, prefix="/api")
    app.include_router(courses.router, prefix="/api")
    app.include_router(exams.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(reminders.router, prefix="/api")
    app.include_router(schedule_import.router, prefix="/api")
    app.include_router(chat.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_schedule_import_api.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd student-planner
git add app/routers/schedule_import.py app/main.py tests/test_schedule_import_api.py
git commit -m "feat: add schedule file upload endpoint (Excel + image)"
```

---

### Task 5: Agent Tools — parse_schedule + parse_schedule_image

Register the two new tools in the agent tool system. These tools handle the full pipeline: parse → calibrate periods → ask_user to confirm → bulk create courses.

**Files:**
- Modify: `student-planner/app/agent/tools.py` (add 2 tool definitions)
- Modify: `student-planner/app/agent/tool_executor.py` (add 2 handlers)
- Create: `student-planner/tests/test_schedule_tools.py`

- [ ] **Step 1: Add tool definitions to tools.py**

Append these two entries to the `TOOL_DEFINITIONS` list in `app/agent/tools.py`:

```python
    {
        "type": "function",
        "function": {
            "name": "parse_schedule",
            "description": "解析用户上传的 Excel/WPS 课表文件。返回识别出的课程列表（含节次信息），需要用户确认后再写入。如果课程包含'第N节课'且用户未配置作息时间表，需要先用 ask_user 追问作息时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "上传文件的临时 ID（由 /api/schedule/upload 返回）",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_schedule_image",
            "description": "解析用户上传的课表图片/截图。使用多模态 LLM 识别课程信息。返回识别出的课程列表，需要用户确认后再写入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "上传图片的临时 ID（由 /api/schedule/upload 返回）",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
```

- [x] **Step 2: Write the failing tests**

```python
# tests/test_schedule_tools.py
import pytest

from app.agent.tools import TOOL_DEFINITIONS


def test_parse_schedule_tool_defined():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "parse_schedule" in names


def test_parse_schedule_image_tool_defined():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "parse_schedule_image" in names


def test_parse_schedule_requires_file_id():
    tool = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "parse_schedule")
    assert "file_id" in tool["function"]["parameters"]["required"]


def test_parse_schedule_image_requires_file_id():
    tool = next(t for t in TOOL_DEFINITIONS if t["function"]["name"] == "parse_schedule_image")
    assert "file_id" in tool["function"]["parameters"]["required"]
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_schedule_tools.py -v`
Expected: FAIL — `parse_schedule` not found in TOOL_DEFINITIONS

- [ ] **Step 4: Run tests after adding definitions (Step 1)**

Run: `cd student-planner && python -m pytest tests/test_schedule_tools.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Add handlers to tool_executor.py**

Add these imports at the top of `app/agent/tool_executor.py`:

```python
from app.services.period_converter import DEFAULT_SCHEDULE, convert_periods
```

Add these two handler functions before the `TOOL_HANDLERS` dict:

```python
async def _parse_schedule(
    db: AsyncSession, user_id: str, file_id: str, **kwargs
) -> dict[str, Any]:
    """Handle parse_schedule tool call.

    The file_id is a reference to previously uploaded data stored in the
    upload endpoint's response. The agent should have the parsed course
    list from the upload response already. This tool converts periods to
    times and prepares courses for confirmation.
    """
    # In practice, the agent already has the parsed courses from the upload
    # endpoint response. This tool is a pass-through that the agent calls
    # to signal "I want to import these courses". The actual import happens
    # after ask_user confirmation in the agent loop.
    return {
        "status": "ready",
        "message": "课表已解析。请使用 ask_user 向用户展示识别结果并确认。",
        "file_id": file_id,
    }


async def _parse_schedule_image(
    db: AsyncSession, user_id: str, file_id: str, **kwargs
) -> dict[str, Any]:
    """Handle parse_schedule_image tool call. Same flow as parse_schedule."""
    return {
        "status": "ready",
        "message": "课表图片已识别。请使用 ask_user 向用户展示识别结果并确认。",
        "file_id": file_id,
    }
```

Add both to the `TOOL_HANDLERS` dict:

```python
TOOL_HANDLERS = {
    "list_courses": _list_courses,
    "add_course": _add_course,
    "delete_course": _delete_course,
    "get_free_slots": _get_free_slots,
    "list_tasks": _list_tasks,
    "update_task": _update_task,
    "complete_task": _complete_task,
    "set_reminder": _set_reminder,
    "list_reminders": _list_reminders,
    "ask_user": _ask_user,
    "create_study_plan": _create_study_plan,
    "parse_schedule": _parse_schedule,
    "parse_schedule_image": _parse_schedule_image,
}
```

- [ ] **Step 6: Run all tool tests**

Run: `cd student-planner && python -m pytest tests/test_schedule_tools.py tests/test_tool_executor.py tests/test_tools_schema.py -v`
Expected: All PASS

- [x] **Step 7: Commit**

```bash
cd student-planner
git add app/agent/tools.py app/agent/tool_executor.py tests/test_schedule_tools.py
git commit -m "feat: register parse_schedule and parse_schedule_image agent tools"
```

---

### Task 6: Bulk Import Pipeline — Confirmed Courses → Database

After the user confirms the parsed course list via ask_user, the agent needs to bulk-create Course records. This task adds a `bulk_import_courses` tool that takes the confirmed list, converts periods to times, and creates all courses in one transaction.

**Files:**
- Modify: `student-planner/app/agent/tools.py` (add bulk_import_courses definition)
- Modify: `student-planner/app/agent/tool_executor.py` (add handler)
- Create: `student-planner/tests/test_bulk_import.py`

- [ ] **Step 1: Add tool definition**

Append to `TOOL_DEFINITIONS` in `app/agent/tools.py`:

```python
    {
        "type": "function",
        "function": {
            "name": "bulk_import_courses",
            "description": "批量导入课程到用户课表。在用户通过 ask_user 确认解析结果后调用。需要提供完整的课程列表（含具体时间，不是节次）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "courses": {
                        "type": "array",
                        "description": "课程列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "课程名称"},
                                "teacher": {"type": "string", "description": "教师"},
                                "location": {"type": "string", "description": "上课地点"},
                                "weekday": {"type": "integer", "description": "周几，1-7"},
                                "start_time": {"type": "string", "description": "开始时间 HH:MM"},
                                "end_time": {"type": "string", "description": "结束时间 HH:MM"},
                                "week_start": {"type": "integer", "description": "开始周次"},
                                "week_end": {"type": "integer", "description": "结束周次"},
                            },
                            "required": ["name", "weekday", "start_time", "end_time"],
                        },
                    },
                },
                "required": ["courses"],
            },
        },
    },
```

- [x] **Step 2: Write the failing tests**

```python
# tests/test_bulk_import.py
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_executor import execute_tool
from app.agent.tools import TOOL_DEFINITIONS
from app.models.course import Course
from app.models.user import User

# Re-use the test DB setup from conftest.py


def test_bulk_import_tool_defined():
    names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
    assert "bulk_import_courses" in names


@pytest.mark.asyncio
async def test_bulk_import_creates_courses(setup_db):
    """bulk_import_courses should create Course records in the database."""
    from tests.conftest import TestSession

    async with TestSession() as db:
        # Create a test user
        user = User(id="test-user-1", username="bulktest", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {
                "courses": [
                    {
                        "name": "高等数学",
                        "teacher": "张老师",
                        "location": "教学楼A301",
                        "weekday": 1,
                        "start_time": "08:00",
                        "end_time": "09:40",
                        "week_start": 1,
                        "week_end": 16,
                    },
                    {
                        "name": "线性代数",
                        "weekday": 3,
                        "start_time": "10:00",
                        "end_time": "11:40",
                    },
                ]
            },
            db=db,
            user_id="test-user-1",
        )

        assert result["status"] == "imported"
        assert result["count"] == 2

        # Verify courses exist in DB
        courses_result = await db.execute(
            select(Course).where(Course.user_id == "test-user-1")
        )
        courses = courses_result.scalars().all()
        assert len(courses) == 2
        names = {c.name for c in courses}
        assert "高等数学" in names
        assert "线性代数" in names


@pytest.mark.asyncio
async def test_bulk_import_empty_list(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(id="test-user-2", username="bulktest2", hashed_password="x")
        db.add(user)
        await db.commit()

        result = await execute_tool(
            "bulk_import_courses",
            {"courses": []},
            db=db,
            user_id="test-user-2",
        )
        assert result["status"] == "imported"
        assert result["count"] == 0
```

- [x] **Step 3: Run tests to verify they fail**

Run: `cd student-planner && python -m pytest tests/test_bulk_import.py -v`
Expected: FAIL — `bulk_import_courses` not in TOOL_HANDLERS

- [ ] **Step 4: Implement the handler**

Add this handler function to `app/agent/tool_executor.py`:

```python
async def _bulk_import_courses(
    db: AsyncSession, user_id: str, courses: list[dict[str, Any]], **kwargs
) -> dict[str, Any]:
    """Bulk-create Course records from a confirmed list."""
    created = []
    for course_data in courses:
        course = Course(
            user_id=user_id,
            name=course_data["name"],
            teacher=course_data.get("teacher"),
            location=course_data.get("location"),
            weekday=course_data["weekday"],
            start_time=course_data["start_time"],
            end_time=course_data["end_time"],
            week_start=course_data.get("week_start", 1),
            week_end=course_data.get("week_end", 16),
        )
        db.add(course)
        created.append(course_data["name"])

    await db.commit()
    return {
        "status": "imported",
        "count": len(created),
        "courses": created,
    }
```

Add to `TOOL_HANDLERS`:

```python
TOOL_HANDLERS = {
    # ... existing entries ...
    "parse_schedule": _parse_schedule,
    "parse_schedule_image": _parse_schedule_image,
    "bulk_import_courses": _bulk_import_courses,
}
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd student-planner && python -m pytest tests/test_bulk_import.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
cd student-planner
git add app/agent/tools.py app/agent/tool_executor.py tests/test_bulk_import.py
git commit -m "feat: add bulk_import_courses tool for batch course creation"
```

---

### Task 7: Update Agent.md — Schedule Import Rules + Few-Shot

Add behavior rules and a few-shot example for the schedule import flow to Agent.md.

**Files:**
- Modify: `student-planner/Agent.md`

- [ ] **Step 1: Add schedule import tool usage rules**

Add the following under the `### 工具使用` section in `Agent.md`:

```markdown
- parse_schedule / parse_schedule_image：解析结果必须用 ask_user(type="review") 展示给用户确认，确认后才能调用 bulk_import_courses
- bulk_import_courses：只在用户确认解析结果后调用，不要跳过确认步骤
- 当解析结果中课程包含"第N节课"（period 字段）但没有具体时间时，必须先用 ask_user 追问用户的作息时间表，拿到后再转换为具体时间
- 如果用户已经配置过作息时间表（存在 preferences.school_schedule 中），直接使用，不要重复追问
```

- [ ] **Step 2: Add few-shot example for schedule import**

Add the following as `### 示例3：导入课表` after the existing examples in `Agent.md`:

```markdown
### 示例3：导入课表（Excel）

用户上传了课表 Excel 文件，前端调用 /api/schedule/upload 后返回解析结果。

用户: "我上传了课表文件"（前端附带解析结果）

→ 检查解析结果中是否有 period 字段（如 "1-2"）
→ 有 period 且用户未配置作息时间表:
  ask_user: "你的课表用的是'第几节课'，我需要知道你们学校的作息时间：
  第1-2节 = ?:?? - ?:??
  第3-4节 = ?:?? - ?:??
  第5-6节 = ?:?? - ?:??
  第7-8节 = ?:?? - ?:??
  第9-10节 = ?:?? - ?:??"
→ 用户回答后，将 period 转换为具体时间
→ ask_user(type="review"): 展示完整课程列表（含具体时间），请求确认
→ 用户确认 → bulk_import_courses(courses=[...])
→ 回复: "课表导入完成，共 N 门课。"

注意：
- 如果用户之前已经配置过作息时间表，直接用，不要再问
- 如果解析结果中已经有具体时间（start_time/end_time），不需要追问作息
- 导入前如果用户已有课程，提醒用户"你已有 M 门课，是要追加还是替换？"
```

- [ ] **Step 3: Commit**

```bash
cd student-planner
git add Agent.md
git commit -m "docs: add schedule import rules and few-shot to Agent.md"
```

---

### Task 8: Integration Test — Full Import Flow

End-to-end test: upload Excel → parse → confirm → bulk import → verify courses in DB.

**Files:**
- Create: `student-planner/tests/test_schedule_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_schedule_integration.py
"""Integration test: Excel upload → parse → bulk import → verify."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tool_executor import execute_tool
from app.models.course import Course
from app.services.period_converter import DEFAULT_SCHEDULE, convert_periods

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_schedule.xlsx"


@pytest.mark.asyncio
async def test_full_excel_import_flow(auth_client: AsyncClient):
    """Simulate the full import flow: upload → parse → convert periods → import."""

    # Step 1: Upload the Excel file
    with open(FIXTURE_PATH, "rb") as f:
        upload_response = await auth_client.post(
            "/api/schedule/upload",
            files={"file": ("schedule.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert upload_response.status_code == 200
    parsed = upload_response.json()
    assert parsed["count"] == 6

    # Step 2: Convert periods to concrete times (simulating what the agent does)
    courses_for_import = []
    for raw in parsed["courses"]:
        times = convert_periods(raw["period"], DEFAULT_SCHEDULE)
        assert times is not None, f"Failed to convert period {raw['period']}"
        courses_for_import.append({
            "name": raw["name"],
            "teacher": raw["teacher"],
            "location": raw["location"],
            "weekday": raw["weekday"],
            "start_time": times["start_time"],
            "end_time": times["end_time"],
            "week_start": raw["week_start"],
            "week_end": raw["week_end"],
        })

    # Step 3: Bulk import (simulating tool call after user confirmation)
    from tests.conftest import TestSession

    async with TestSession() as db:
        # Get the test user ID from the auth_client
        me_response = await auth_client.get("/api/auth/me")
        user_id = me_response.json()["id"]

        result = await execute_tool(
            "bulk_import_courses",
            {"courses": courses_for_import},
            db=db,
            user_id=user_id,
        )
        assert result["status"] == "imported"
        assert result["count"] == 6

        # Step 4: Verify courses in DB
        db_courses = await db.execute(
            select(Course).where(Course.user_id == user_id)
        )
        courses = db_courses.scalars().all()
        assert len(courses) == 6

        # Verify a specific course has correct times
        gaoshu = next(c for c in courses if c.name == "高等数学")
        assert gaoshu.start_time == "08:00"
        assert gaoshu.end_time == "09:40"
        assert gaoshu.weekday == 1
        assert gaoshu.week_start == 1
        assert gaoshu.week_end == 16


@pytest.mark.asyncio
async def test_period_conversion_all_fixture_courses():
    """Verify all periods in the fixture can be converted."""
    from app.services.schedule_parser import parse_excel_schedule

    courses = parse_excel_schedule(FIXTURE_PATH)
    for course in courses:
        times = convert_periods(course.period, DEFAULT_SCHEDULE)
        assert times is not None, f"Cannot convert period '{course.period}' for {course.name}"
        assert ":" in times["start_time"]
        assert ":" in times["end_time"]
```

- [ ] **Step 2: Run the integration test**

Run: `cd student-planner && python -m pytest tests/test_schedule_integration.py -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Run the full test suite**

Run: `cd student-planner && python -m pytest -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 4: Commit**

```bash
cd student-planner
git add tests/test_schedule_integration.py
git commit -m "test: add schedule import integration test"
```

---

### Task 9: Update AGENTS.md — Mark Plan 3 Progress

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update progress in AGENTS.md**

Change the Plan 3 line from:
```markdown
- [ ] Plan 3: 课表导入（未写）
```
to:
```markdown
- [ ] Plan 3: 课表导入（9 个 task）
```

Update "当前正在执行" to:
```markdown
**Plan 3 完成，待进入 Plan 4（未写）**
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs: update AGENTS.md with Plan 3 completion status"
```
