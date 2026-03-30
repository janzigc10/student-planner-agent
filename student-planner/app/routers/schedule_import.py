from io import BytesIO

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
    del user, db

    content_type = file.content_type or ""
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {content_type}。支持 xlsx、xls、png、jpg、jpeg、webp。",
        )

    file_bytes = await file.read()
    if content_type in _EXCEL_TYPES:
        courses = parse_excel_schedule(BytesIO(file_bytes))
    else:
        from app.agent.schedule_ocr import parse_schedule_image

        courses = await parse_schedule_image(file_bytes, content_type)

    return {
        "courses": [_raw_course_to_dict(course) for course in courses],
        "count": len(courses),
    }


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