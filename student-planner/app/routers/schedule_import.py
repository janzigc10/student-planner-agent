from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.schedule_upload_cache import store_schedule_upload
from app.services.schedule_parser import RawCourse, parse_excel_schedule

router = APIRouter(prefix="/schedule", tags=["schedule-import"])

_EXCEL_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
_ALLOWED_TYPES = _EXCEL_TYPES | _IMAGE_TYPES
_MAX_IMAGE_FILES = 3
_MAX_SPREADSHEET_FILES = 1
_UPLOAD_ERROR = "不支持的文件格式: {content_type}。支持 xlsx、xls、png、jpg、jpeg、webp。"


@router.post("/upload")
async def upload_schedule(
    file: list[UploadFile] | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    del db

    uploads = file or []
    if not uploads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少上传一个课表文件。",
        )

    classified = [_classify_upload(upload) for upload in uploads]
    kinds = {kind for kind, _ in classified}
    if len(kinds) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不支持同时上传课表图片和表格文件，请选择一种格式。",
        )

    kind = classified[0][0]
    if kind == "image" and len(classified) > _MAX_IMAGE_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"课表图片最多支持 {_MAX_IMAGE_FILES} 张。",
        )
    if kind == "spreadsheet" and len(classified) > _MAX_SPREADSHEET_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="课表表格文件最多支持 1 个。",
        )

    course_dicts: list[dict[str, Any]] = []
    if kind == "spreadsheet":
        file_bytes = await uploads[0].read()
        courses = parse_excel_schedule(BytesIO(file_bytes))
        course_dicts.extend(_raw_course_to_dict(course) for course in courses)
    else:
        from app.agent.schedule_ocr import parse_schedule_image

        for upload in uploads:
            file_bytes = await upload.read()
            courses = await parse_schedule_image(file_bytes, upload.content_type or "")
            course_dicts.extend(_raw_course_to_dict(course) for course in courses)

    file_id = store_schedule_upload(user.id, kind, course_dicts)
    return {
        "file_id": file_id,
        "kind": kind,
        "courses": course_dicts,
        "count": len(course_dicts),
        "source_file_count": len(uploads),
    }


def _classify_upload(upload: UploadFile) -> tuple[str, UploadFile]:
    content_type = upload.content_type or ""
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_UPLOAD_ERROR.format(content_type=content_type),
        )
    if content_type in _IMAGE_TYPES:
        return "image", upload
    return "spreadsheet", upload


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
