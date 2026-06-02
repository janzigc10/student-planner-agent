from datetime import date, datetime
from types import SimpleNamespace

from app.services.course_occurrence import course_occurs_on_date, next_course_occurrence


def test_course_occurs_on_date_respects_odd_teaching_weeks() -> None:
    course = SimpleNamespace(
        weekday=1,
        start_time="08:00",
        week_start=3,
        week_end=17,
        week_pattern="odd",
        week_text="3,5,7,9,11,13,15,17([周])",
    )
    semester_start = date(2026, 3, 2)

    assert course_occurs_on_date(course, date(2026, 5, 25), semester_start) is True
    assert course_occurs_on_date(course, date(2026, 6, 1), semester_start) is False
    assert course_occurs_on_date(course, date(2026, 6, 8), semester_start) is True


def test_next_course_occurrence_skips_inactive_weeks() -> None:
    course = SimpleNamespace(
        weekday=1,
        start_time="08:00",
        week_start=3,
        week_end=17,
        week_pattern="odd",
        week_text="3,5,7,9,11,13,15,17([周])",
    )
    semester_start = date(2026, 3, 2)

    occurrence = next_course_occurrence(
        course,
        semester_start,
        now=datetime(2026, 5, 31, 12, 0),
    )

    assert occurrence == datetime(2026, 6, 8, 8, 0)
