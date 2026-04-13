"""Short-lived in-process cache for parsed schedule uploads."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


_TTL = timedelta(minutes=30)
_CACHE: dict[tuple[str, str], "CachedScheduleUpload"] = {}


@dataclass(frozen=True)
class CachedScheduleUpload:
    user_id: str
    file_id: str
    kind: str
    courses: list[dict[str, Any]]
    created_at: datetime


def store_schedule_upload(user_id: str, kind: str, courses: list[dict[str, Any]]) -> str:
    file_id = str(uuid4())
    _CACHE[(user_id, file_id)] = CachedScheduleUpload(
        user_id=user_id,
        file_id=file_id,
        kind=kind,
        courses=deepcopy(courses),
        created_at=datetime.now(UTC),
    )
    _prune_expired()
    return file_id


def get_schedule_upload(user_id: str, file_id: str) -> CachedScheduleUpload | None:
    _prune_expired()
    cached = _CACHE.get((user_id, file_id))
    if cached is None:
        return None
    return CachedScheduleUpload(
        user_id=cached.user_id,
        file_id=cached.file_id,
        kind=cached.kind,
        courses=deepcopy(cached.courses),
        created_at=cached.created_at,
    )


def _prune_expired() -> None:
    cutoff = datetime.now(UTC) - _TTL
    expired = [key for key, cached in _CACHE.items() if cached.created_at < cutoff]
    for key in expired:
        _CACHE.pop(key, None)
