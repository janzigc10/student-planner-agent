from fastapi import FastAPI

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


app = create_app()