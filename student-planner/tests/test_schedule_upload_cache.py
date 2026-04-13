from app.services.schedule_upload_cache import (
    get_schedule_upload,
    store_schedule_upload,
)


def test_schedule_upload_cache_is_user_scoped() -> None:
    file_id = store_schedule_upload(
        user_id="user-1",
        kind="spreadsheet",
        courses=[{"name": "高等数学", "weekday": 1, "period": "1-2"}],
    )

    assert get_schedule_upload("user-1", file_id) is not None
    assert get_schedule_upload("user-2", file_id) is None


def test_schedule_upload_cache_returns_copied_courses() -> None:
    file_id = store_schedule_upload(
        user_id="user-1",
        kind="spreadsheet",
        courses=[{"name": "线性代数", "weekday": 2, "period": "3-4"}],
    )

    cached = get_schedule_upload("user-1", file_id)
    assert cached is not None
    cached.courses[0]["name"] = "changed"

    fresh = get_schedule_upload("user-1", file_id)
    assert fresh is not None
    assert fresh.courses[0]["name"] == "线性代数"
