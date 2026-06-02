from datetime import datetime
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.models.reminder import Reminder
from app.models.user import User


@pytest_asyncio.fixture
async def setup_pending_reminders(setup_db):
    from tests.conftest import TestSession

    async with TestSession() as db:
        user = User(
            id="user-reload-1",
            username="reloaduser",
            hashed_password="x",
        )
        db.add(user)

        r1 = Reminder(
            id="rem-reload-1",
            user_id="user-reload-1",
            target_type="task",
            target_id="task-fake-1",
            remind_at="2099-04-05T09:30:00",
            advance_minutes=30,
            status="pending",
        )
        r2 = Reminder(
            id="rem-reload-2",
            user_id="user-reload-1",
            target_type="course",
            target_id="course-fake-1",
            remind_at="2099-04-05T13:45:00",
            advance_minutes=15,
            status="pending",
        )
        r3 = Reminder(
            id="rem-reload-3",
            user_id="user-reload-1",
            target_type="task",
            target_id="task-fake-2",
            remind_at="2099-04-05T16:00:00",
            advance_minutes=15,
            status="sent",
        )
        db.add_all([r1, r2, r3])
        await db.commit()

    yield


@pytest.mark.asyncio
@patch("app.services.reminder_scheduler.schedule_reminder_job")
async def test_reload_pending_reminders_uses_stored_trigger_time(mock_schedule, setup_pending_reminders):
    from tests.conftest import TestSession
    from app.services.reminder_scheduler import reload_pending_reminders

    with patch("app.services.reminder_scheduler.async_session", TestSession):
        count = await reload_pending_reminders()

    assert count == 2
    assert mock_schedule.call_count == 2
    first_call = mock_schedule.call_args_list[0].kwargs
    second_call = mock_schedule.call_args_list[1].kwargs
    assert {first_call["reminder_id"], second_call["reminder_id"]} == {"rem-reload-1", "rem-reload-2"}
    scheduled_times = {first_call["fire_time"].isoformat(), second_call["fire_time"].isoformat()}
    assert scheduled_times == {"2099-04-05T09:30:00", "2099-04-05T13:45:00"}


@pytest.mark.asyncio
@patch("app.services.reminder_scheduler.fire_reminder")
async def test_deliver_due_reminders_only_dispatches_overdue_pending(mock_fire, setup_pending_reminders):
    from tests.conftest import TestSession
    from app.services.reminder_scheduler import deliver_due_reminders

    with patch("app.services.reminder_scheduler.async_session", TestSession):
        count = await deliver_due_reminders(now=datetime.fromisoformat("2099-04-05T12:00:00"))

    assert count == 1
    mock_fire.assert_called_once_with(reminder_id="rem-reload-1", user_id="user-reload-1")
