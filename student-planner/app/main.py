from contextlib import asynccontextmanager, suppress
import asyncio

from fastapi import FastAPI

from app.routers import auth, chat, courses, exams, push, reminders, schedule_import, tasks
from app.services.reminder_scheduler import get_scheduler, reload_pending_reminders, reminder_watch_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    await reload_pending_reminders()
    stop_event = asyncio.Event()
    watch_task = asyncio.create_task(reminder_watch_loop(stop_event))
    yield
    stop_event.set()
    watch_task.cancel()
    with suppress(asyncio.CancelledError):
        await watch_task
    if scheduler.running:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Student Planner", version="0.1.0", lifespan=lifespan)
    app.include_router(auth.router, prefix="/api")
    app.include_router(courses.router, prefix="/api")
    app.include_router(exams.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(reminders.router, prefix="/api")
    app.include_router(schedule_import.router, prefix="/api")
    app.include_router(push.router, prefix="/api")
    app.include_router(chat.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
