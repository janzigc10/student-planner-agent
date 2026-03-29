# Plan 1: 后端基础 — 数据模型 + API + 认证

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend foundation with all data models, CRUD APIs, JWT auth, and project scaffolding.

**Architecture:** FastAPI app with SQLAlchemy ORM, SQLite for development, Alembic for migrations, JWT-based auth. All models from the spec (User, Course, Exam, Task, Reminder, AgentLog, Memory, SessionSummary, ConversationMessage) are created with full CRUD endpoints for the core entities.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, python-jose (JWT), passlib (bcrypt), uvicorn, pytest, httpx

---

## File Structure

```
student-planner/
├── pyproject.toml                    # Project config, dependencies
├── alembic.ini                       # Alembic config
├── alembic/
│   ├── env.py
│   └── versions/                     # Migration files
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app factory, router mounting
│   ├── config.py                     # Settings (DB URL, JWT secret, etc.)
│   ├── database.py                   # Engine, session factory
│   ├── models/
│   │   ├── __init__.py               # Re-export all models
│   │   ├── user.py                   # User model
│   │   ├── course.py                 # Course model
│   │   ├── exam.py                   # Exam model
│   │   ├── task.py                   # Task model
│   │   ├── reminder.py               # Reminder model
│   │   ├── agent_log.py              # AgentLog model
│   │   ├── memory.py                 # Memory model
│   │   ├── session_summary.py        # SessionSummary model
│   │   └── conversation_message.py   # ConversationMessage model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py                   # User Pydantic schemas
│   │   ├── course.py                 # Course schemas
│   │   ├── exam.py                   # Exam schemas
│   │   ├── task.py                   # Task schemas
│   │   └── reminder.py               # Reminder schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py                   # Register, login, token refresh
│   │   ├── courses.py                # Course CRUD
│   │   ├── exams.py                  # Exam CRUD
│   │   ├── tasks.py                  # Task CRUD
│   │   └── reminders.py              # Reminder CRUD
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt.py                    # JWT create/verify
│   │   └── dependencies.py           # get_current_user dependency
│   └── services/
│       ├── __init__.py
│       └── calendar.py               # get_free_slots logic
├── tests/
│   ├── conftest.py                   # Fixtures: test DB, test client, auth helpers
│   ├── test_auth.py                  # Auth endpoint tests
│   ├── test_courses.py               # Course CRUD tests
│   ├── test_exams.py                 # Exam CRUD tests
│   ├── test_tasks.py                 # Task CRUD tests
│   ├── test_reminders.py             # Reminder CRUD tests
│   └── test_calendar.py              # get_free_slots tests
└── Agent.md                          # Agent behavior rules (placeholder for Plan 2)
```

---

### Task 1: Project Scaffolding + Database Setup

**Files:**
- Create: `student-planner/pyproject.toml`
- Create: `student-planner/app/__init__.py`
- Create: `student-planner/app/config.py`
- Create: `student-planner/app/database.py`
- Create: `student-planner/app/main.py`

- [x] **Step 1: Create project directory and pyproject.toml**

```bash
mkdir -p student-planner
cd student-planner
```

```toml
# pyproject.toml
[project]
name = "student-planner"
version = "0.1.0"
requires-python = ">=3.11"
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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [x] **Step 2: Create config.py**

```python
# app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./student_planner.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    model_config = {"env_prefix": "SP_"}


settings = Settings()
```

- [x] **Step 3: Create database.py**

```python
# app/database.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session
```

- [x] **Step 4: Create main.py**

```python
# app/main.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Student Planner", version="0.1.0")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [x] **Step 5: Create empty __init__.py files**

```bash
touch app/__init__.py
mkdir -p app/models app/schemas app/routers app/auth app/services tests
touch app/models/__init__.py app/schemas/__init__.py app/routers/__init__.py
touch app/auth/__init__.py app/services/__init__.py tests/__init__.py
```

- [x] **Step 6: Install dependencies and verify server starts**

Run: `cd student-planner && pip install -e ".[dev]" && python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with FastAPI, SQLAlchemy, config"
```

---

### Task 2: User Model + Auth (Register/Login)

**Files:**
- Create: `student-planner/app/models/user.py`
- Create: `student-planner/app/schemas/user.py`
- Create: `student-planner/app/auth/jwt.py`
- Create: `student-planner/app/auth/dependencies.py`
- Create: `student-planner/app/routers/auth.py`
- Modify: `student-planner/app/main.py`
- Create: `student-planner/tests/conftest.py`
- Create: `student-planner/tests/test_auth.py`

- [x] **Step 1: Write User model**

```python
# app/models/user.py
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import Date, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    push_subscription: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    current_semester_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
```

- [x] **Step 2: Write User schemas**

```python
# app/schemas/user.py
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    username: str
    preferences: Optional[dict[str, Any]] = None
    current_semester_start: Optional[date] = None

    model_config = {"from_attributes": True}
```

- [x] **Step 3: Write JWT utilities**

```python
# app/auth/jwt.py
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> str | None:
    """Returns user_id if valid, None otherwise."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None
```

- [x] **Step 4: Write auth dependency**

```python
# app/auth/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import verify_token
from app.database import get_db
from app.models.user import User

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = verify_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [x] **Step 5: Write auth router**

```python
# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.user import TokenResponse, UserLogin, UserOut, UserRegister

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=body.username, hashed_password=pwd_context.hash(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
```

- [x] **Step 6: Mount auth router in main.py**

```python
# app/main.py
from fastapi import FastAPI

from app.routers import auth


def create_app() -> FastAPI:
    app = FastAPI(title="Student Planner", version="0.1.0")
    app.include_router(auth.router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [x] **Step 7: Write test fixtures**

```python
# tests/conftest.py
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import create_app

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"
engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Client with a registered and logged-in user."""
    await client.post("/api/auth/register", json={"username": "testuser", "password": "testpass"})
    resp = await client.post("/api/auth/login", json={"username": "testuser", "password": "testpass"})
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
```

- [x] **Step 8: Write auth tests**

```python
# tests/test_auth.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={"username": "alice", "password": "pass123"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate(client: AsyncClient):
    await client.post("/api/auth/register", json={"username": "bob", "password": "pass123"})
    resp = await client.post("/api/auth/register", json={"username": "bob", "password": "pass123"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/auth/register", json={"username": "carol", "password": "pass123"})
    resp = await client.post("/api/auth/login", json={"username": "carol", "password": "pass123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={"username": "dave", "password": "pass123"})
    resp = await client.post("/api/auth/login", json={"username": "dave", "password": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me(auth_client: AsyncClient):
    resp = await auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_me_no_token(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 403
```

- [x] **Step 9: Run tests**

Run: `cd student-planner && pytest tests/test_auth.py -v`
Expected: All 6 tests PASS

- [x] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: user model, JWT auth, register/login endpoints with tests"
```

---

### Task 3: Course Model + CRUD API

**Files:**
- Create: `student-planner/app/models/course.py`
- Create: `student-planner/app/schemas/course.py`
- Create: `student-planner/app/routers/courses.py`
- Modify: `student-planner/app/models/__init__.py`
- Modify: `student-planner/app/main.py`
- Create: `student-planner/tests/test_courses.py`

- [x] **Step 1: Write Course model**

```python
# app/models/course.py
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    teacher: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 1=Monday, 7=Sunday
    start_time: Mapped[str] = mapped_column(String(5))  # "08:00"
    end_time: Mapped[str] = mapped_column(String(5))  # "09:40"
    week_start: Mapped[int] = mapped_column(Integer, default=1)
    week_end: Mapped[int] = mapped_column(Integer, default=16)
```

- [x] **Step 2: Write Course schemas**

```python
# app/schemas/course.py
from typing import Optional

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    name: str
    teacher: Optional[str] = None
    location: Optional[str] = None
    weekday: int = Field(ge=1, le=7)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    week_start: int = Field(default=1, ge=1)
    week_end: int = Field(default=16, ge=1)


class CourseUpdate(BaseModel):
    name: Optional[str] = None
    teacher: Optional[str] = None
    location: Optional[str] = None
    weekday: Optional[int] = Field(default=None, ge=1, le=7)
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    week_start: Optional[int] = Field(default=None, ge=1)
    week_end: Optional[int] = Field(default=None, ge=1)


class CourseOut(BaseModel):
    id: str
    user_id: str
    name: str
    teacher: Optional[str] = None
    location: Optional[str] = None
    weekday: int
    start_time: str
    end_time: str
    week_start: int
    week_end: int

    model_config = {"from_attributes": True}
```

- [x] **Step 3: Write courses router**

```python
# app/routers/courses.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.course import Course
from app.models.user import User
from app.schemas.course import CourseCreate, CourseOut, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("/", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = Course(user_id=user.id, **body.model_dump())
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


@router.get("/", response_model=list[CourseOut])
async def list_courses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Course).where(Course.user_id == user.id))
    return result.scalars().all()


@router.get("/{course_id}", response_model=CourseOut)
async def get_course(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.patch("/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: str,
    body: CourseUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(course, key, value)
    await db.commit()
    await db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Course).where(Course.id == course_id, Course.user_id == user.id)
    )
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    await db.delete(course)
    await db.commit()
```

- [x] **Step 4: Update models/__init__.py and main.py**

```python
# app/models/__init__.py
from app.models.user import User
from app.models.course import Course

__all__ = ["User", "Course"]
```

Add to `app/main.py` `create_app()`:
```python
from app.routers import auth, courses

app.include_router(courses.router, prefix="/api")
```

- [x] **Step 5: Write course tests**

```python
# tests/test_courses.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_course(auth_client: AsyncClient):
    resp = await auth_client.post("/api/courses/", json={
        "name": "高等数学",
        "teacher": "张老师",
        "location": "教学楼A301",
        "weekday": 1,
        "start_time": "08:00",
        "end_time": "09:40",
        "week_start": 1,
        "week_end": 16,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "高等数学"
    assert data["weekday"] == 1


@pytest.mark.asyncio
async def test_list_courses(auth_client: AsyncClient):
    await auth_client.post("/api/courses/", json={
        "name": "线性代数", "weekday": 2, "start_time": "10:00", "end_time": "11:40",
    })
    resp = await auth_client.get("/api/courses/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_update_course(auth_client: AsyncClient):
    create = await auth_client.post("/api/courses/", json={
        "name": "概率论", "weekday": 3, "start_time": "14:00", "end_time": "15:40",
    })
    course_id = create.json()["id"]
    resp = await auth_client.patch(f"/api/courses/{course_id}", json={"location": "教学楼B205"})
    assert resp.status_code == 200
    assert resp.json()["location"] == "教学楼B205"


@pytest.mark.asyncio
async def test_delete_course(auth_client: AsyncClient):
    create = await auth_client.post("/api/courses/", json={
        "name": "英语", "weekday": 4, "start_time": "08:00", "end_time": "09:40",
    })
    course_id = create.json()["id"]
    resp = await auth_client.delete(f"/api/courses/{course_id}")
    assert resp.status_code == 204
    resp = await auth_client.get(f"/api/courses/{course_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_course_not_found(auth_client: AsyncClient):
    resp = await auth_client.get("/api/courses/nonexistent")
    assert resp.status_code == 404
```

- [x] **Step 6: Run tests**

Run: `cd student-planner && pytest tests/test_courses.py -v`
Expected: All 5 tests PASS

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: course model and CRUD endpoints with tests"
```

---

### Task 4: Exam Model + CRUD API

**Files:**
- Create: `student-planner/app/models/exam.py`
- Create: `student-planner/app/schemas/exam.py`
- Create: `student-planner/app/routers/exams.py`
- Modify: `student-planner/app/models/__init__.py`
- Modify: `student-planner/app/main.py`
- Create: `student-planner/tests/test_exams.py`

- [x] **Step 1: Write Exam model**

```python
# app/models/exam.py
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    course_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("courses.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="exam")  # exam / assignment / other
    date: Mapped[str] = mapped_column(String(10))  # "2026-04-05"
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
```

- [x] **Step 2: Write Exam schemas**

```python
# app/schemas/exam.py
from typing import Optional

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    course_id: Optional[str] = None
    type: str = Field(default="exam", pattern=r"^(exam|assignment|other)$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: Optional[str] = None


class ExamUpdate(BaseModel):
    course_id: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern=r"^(exam|assignment|other)$")
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    description: Optional[str] = None


class ExamOut(BaseModel):
    id: str
    user_id: str
    course_id: Optional[str] = None
    type: str
    date: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}
```

- [x] **Step 3: Write exams router**

```python
# app/routers/exams.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.exam import Exam
from app.models.user import User
from app.schemas.exam import ExamCreate, ExamOut, ExamUpdate

router = APIRouter(prefix="/exams", tags=["exams"])


@router.post("/", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: ExamCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exam = Exam(user_id=user.id, **body.model_dump())
    db.add(exam)
    await db.commit()
    await db.refresh(exam)
    return exam


@router.get("/", response_model=list[ExamOut])
async def list_exams(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Exam).where(Exam.user_id == user.id))
    return result.scalars().all()


@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Exam).where(Exam.id == exam_id, Exam.user_id == user.id)
    )
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    await db.delete(exam)
    await db.commit()
```

- [x] **Step 4: Update models/__init__.py and main.py**

```python
# app/models/__init__.py
from app.models.user import User
from app.models.course import Course
from app.models.exam import Exam

__all__ = ["User", "Course", "Exam"]
```

Add to `app/main.py` `create_app()`:
```python
from app.routers import auth, courses, exams

app.include_router(exams.router, prefix="/api")
```

- [x] **Step 5: Write exam tests**

```python
# tests/test_exams.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_exam(auth_client: AsyncClient):
    resp = await auth_client.post("/api/exams/", json={
        "type": "exam",
        "date": "2026-04-05",
        "description": "高等数学期中考试",
    })
    assert resp.status_code == 201
    assert resp.json()["date"] == "2026-04-05"


@pytest.mark.asyncio
async def test_list_exams(auth_client: AsyncClient):
    await auth_client.post("/api/exams/", json={"date": "2026-04-10", "type": "assignment"})
    resp = await auth_client.get("/api/exams/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_exam(auth_client: AsyncClient):
    create = await auth_client.post("/api/exams/", json={"date": "2026-05-01", "type": "exam"})
    exam_id = create.json()["id"]
    resp = await auth_client.delete(f"/api/exams/{exam_id}")
    assert resp.status_code == 204
```

- [x] **Step 6: Run tests**

Run: `cd student-planner && pytest tests/test_exams.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: exam model and CRUD endpoints with tests"
```

---

### Task 5: Task Model + CRUD API (with conflict detection)

**Files:**
- Create: `student-planner/app/models/task.py`
- Create: `student-planner/app/schemas/task.py`
- Create: `student-planner/app/routers/tasks.py`
- Modify: `student-planner/app/models/__init__.py`
- Modify: `student-planner/app/main.py`
- Create: `student-planner/tests/test_tasks.py`

- [x] **Step 1: Write Task model**

```python
# app/models/task.py
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    exam_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("exams.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    scheduled_date: Mapped[str] = mapped_column(String(10))  # "2026-03-30"
    start_time: Mapped[str] = mapped_column(String(5))  # "10:00"
    end_time: Mapped[str] = mapped_column(String(5))  # "12:00"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / completed / skipped
```

- [x] **Step 2: Write Task schemas**

```python
# app/schemas/task.py
from typing import Optional

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    exam_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    scheduled_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    status: Optional[str] = Field(default=None, pattern=r"^(pending|completed|skipped)$")


class TaskOut(BaseModel):
    id: str
    user_id: str
    exam_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    scheduled_date: str
    start_time: str
    end_time: str
    status: str

    model_config = {"from_attributes": True}
```

- [x] **Step 3: Write tasks router with conflict detection**

```python
# app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def check_time_conflict(
    db: AsyncSession, user_id: str, date: str, start: str, end: str, exclude_id: str | None = None,
) -> Task | None:
    """Return the first conflicting task, or None."""
    query = select(Task).where(
        Task.user_id == user_id,
        Task.scheduled_date == date,
        Task.start_time < end,
        Task.end_time > start,
        Task.status != "skipped",
    )
    if exclude_id:
        query = query.where(Task.id != exclude_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.post("/", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conflict = await check_time_conflict(db, user.id, body.scheduled_date, body.start_time, body.end_time)
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Time conflict with '{conflict.title}' ({conflict.start_time}-{conflict.end_time})",
        )
    task = Task(user_id=user.id, **body.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/", response_model=list[TaskOut])
async def list_tasks(
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Task).where(Task.user_id == user.id)
    if date_from:
        query = query.where(Task.scheduled_date >= date_from)
    if date_to:
        query = query.where(Task.scheduled_date <= date_to)
    query = query.order_by(Task.scheduled_date, Task.start_time)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = body.model_dump(exclude_unset=True)
    new_date = updates.get("scheduled_date", task.scheduled_date)
    new_start = updates.get("start_time", task.start_time)
    new_end = updates.get("end_time", task.end_time)

    if any(k in updates for k in ("scheduled_date", "start_time", "end_time")):
        conflict = await check_time_conflict(db, user.id, new_date, new_start, new_end, exclude_id=task_id)
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Time conflict with '{conflict.title}' ({conflict.start_time}-{conflict.end_time})",
            )

    for key, value in updates.items():
        setattr(task, key, value)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await db.commit()
```

- [x] **Step 4: Update models/__init__.py and main.py**

```python
# app/models/__init__.py
from app.models.user import User
from app.models.course import Course
from app.models.exam import Exam
from app.models.task import Task

__all__ = ["User", "Course", "Exam", "Task"]
```

Add to `app/main.py`:
```python
from app.routers import auth, courses, exams, tasks

app.include_router(tasks.router, prefix="/api")
```

- [x] **Step 5: Write task tests (including conflict detection)**

```python
# tests/test_tasks.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_task(auth_client: AsyncClient):
    resp = await auth_client.post("/api/tasks/", json={
        "title": "高数 - 极限复习",
        "scheduled_date": "2026-03-30",
        "start_time": "10:00",
        "end_time": "12:00",
    })
    assert resp.status_code == 201
    assert resp.json()["title"] == "高数 - 极限复习"
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_time_conflict(auth_client: AsyncClient):
    await auth_client.post("/api/tasks/", json={
        "title": "线代复习",
        "scheduled_date": "2026-03-31",
        "start_time": "14:00",
        "end_time": "16:00",
    })
    resp = await auth_client.post("/api/tasks/", json={
        "title": "概率论复习",
        "scheduled_date": "2026-03-31",
        "start_time": "15:00",
        "end_time": "17:00",
    })
    assert resp.status_code == 409
    assert "conflict" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_conflict_different_day(auth_client: AsyncClient):
    await auth_client.post("/api/tasks/", json={
        "title": "Task A",
        "scheduled_date": "2026-04-01",
        "start_time": "10:00",
        "end_time": "12:00",
    })
    resp = await auth_client.post("/api/tasks/", json={
        "title": "Task B",
        "scheduled_date": "2026-04-02",
        "start_time": "10:00",
        "end_time": "12:00",
    })
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_list_tasks_date_filter(auth_client: AsyncClient):
    await auth_client.post("/api/tasks/", json={
        "title": "Early", "scheduled_date": "2026-03-28", "start_time": "09:00", "end_time": "10:00",
    })
    await auth_client.post("/api/tasks/", json={
        "title": "Late", "scheduled_date": "2026-04-10", "start_time": "09:00", "end_time": "10:00",
    })
    resp = await auth_client.get("/api/tasks/?date_from=2026-04-01&date_to=2026-04-30")
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "Late" in titles
    assert "Early" not in titles


@pytest.mark.asyncio
async def test_update_task_status(auth_client: AsyncClient):
    create = await auth_client.post("/api/tasks/", json={
        "title": "Complete me", "scheduled_date": "2026-04-03", "start_time": "08:00", "end_time": "09:00",
    })
    task_id = create.json()["id"]
    resp = await auth_client.patch(f"/api/tasks/{task_id}", json={"status": "completed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_update_task_conflict(auth_client: AsyncClient):
    await auth_client.post("/api/tasks/", json={
        "title": "Blocker", "scheduled_date": "2026-04-04", "start_time": "14:00", "end_time": "16:00",
    })
    create = await auth_client.post("/api/tasks/", json={
        "title": "Mover", "scheduled_date": "2026-04-04", "start_time": "10:00", "end_time": "12:00",
    })
    task_id = create.json()["id"]
    resp = await auth_client.patch(f"/api/tasks/{task_id}", json={"start_time": "15:00", "end_time": "17:00"})
    assert resp.status_code == 409
```

- [x] **Step 6: Run tests**

Run: `cd student-planner && pytest tests/test_tasks.py -v`
Expected: All 6 tests PASS

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: task model and CRUD with time conflict detection"
```

---

### Task 6: Reminder Model + CRUD API

**Files:**
- Create: `student-planner/app/models/reminder.py`
- Create: `student-planner/app/schemas/reminder.py`
- Create: `student-planner/app/routers/reminders.py`
- Modify: `student-planner/app/models/__init__.py`
- Modify: `student-planner/app/main.py`
- Create: `student-planner/tests/test_reminders.py`

- [x] **Step 1: Write Reminder model**

```python
# app/models/reminder.py
import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(20))  # course / task
    target_id: Mapped[str] = mapped_column(String(36))
    remind_at: Mapped[str] = mapped_column(String(19))  # "2026-03-30T09:45:00"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / sent / failed
```

- [x] **Step 2: Write Reminder schemas**

```python
# app/schemas/reminder.py
from typing import Optional

from pydantic import BaseModel, Field


class ReminderCreate(BaseModel):
    target_type: str = Field(pattern=r"^(course|task)$")
    target_id: str
    remind_at: str  # ISO datetime string


class ReminderOut(BaseModel):
    id: str
    user_id: str
    target_type: str
    target_id: str
    remind_at: str
    status: str

    model_config = {"from_attributes": True}
```

- [x] **Step 3: Write reminders router**

```python
# app/routers/reminders.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.reminder import Reminder
from app.models.user import User
from app.schemas.reminder import ReminderCreate, ReminderOut

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("/", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reminder = Reminder(user_id=user.id, **body.model_dump())
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.get("/", response_model=list[ReminderOut])
async def list_reminders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.remind_at)
    )
    return result.scalars().all()


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user.id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await db.delete(reminder)
    await db.commit()
```

- [x] **Step 4: Update models/__init__.py and main.py**

```python
# app/models/__init__.py
from app.models.user import User
from app.models.course import Course
from app.models.exam import Exam
from app.models.task import Task
from app.models.reminder import Reminder

__all__ = ["User", "Course", "Exam", "Task", "Reminder"]
```

Add to `app/main.py`:
```python
from app.routers import auth, courses, exams, tasks, reminders

app.include_router(reminders.router, prefix="/api")
```

- [x] **Step 5: Write reminder tests**

```python
# tests/test_reminders.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_reminder(auth_client: AsyncClient):
    course = await auth_client.post("/api/courses/", json={
        "name": "高等数学", "weekday": 1, "start_time": "08:00", "end_time": "09:40",
    })
    resp = await auth_client.post("/api/reminders/", json={
        "target_type": "course",
        "target_id": course.json()["id"],
        "remind_at": "2026-03-30T07:45:00",
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_list_reminders(auth_client: AsyncClient):
    await auth_client.post("/api/reminders/", json={
        "target_type": "task",
        "target_id": "fake-task-id",
        "remind_at": "2026-04-01T09:00:00",
    })
    resp = await auth_client.get("/api/reminders/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_reminder(auth_client: AsyncClient):
    create = await auth_client.post("/api/reminders/", json={
        "target_type": "task",
        "target_id": "fake-id",
        "remind_at": "2026-04-02T10:00:00",
    })
    reminder_id = create.json()["id"]
    resp = await auth_client.delete(f"/api/reminders/{reminder_id}")
    assert resp.status_code == 204
```

- [x] **Step 6: Run tests**

Run: `cd student-planner && pytest tests/test_reminders.py -v`
Expected: All 3 tests PASS

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: reminder model and CRUD endpoints with tests"
```

---

### Task 7: Calendar Service — get_free_slots

This is the most critical service for the Agent. It computes free time slots by subtracting courses and tasks from the user's available hours.

**Files:**
- Create: `student-planner/app/services/calendar.py`
- Create: `student-planner/tests/test_calendar.py`

- [x] **Step 1: Write failing tests for get_free_slots**

```python
# tests/test_calendar.py
from datetime import date

import pytest

from app.services.calendar import compute_free_slots, DaySchedule, TimeSlot


def test_empty_day():
    """No courses or tasks = full day is free (within user preferences)."""
    result = compute_free_slots(
        occupied=[],
        day_start="08:00",
        day_end="22:00",
        min_duration_minutes=30,
    )
    assert len(result) == 1
    assert result[0].start == "08:00"
    assert result[0].end == "22:00"
    assert result[0].duration_minutes == 840


def test_one_course_splits_day():
    """A course in the middle creates two free slots."""
    result = compute_free_slots(
        occupied=[TimeSlot(start="10:00", end="12:00", type="course", name="高等数学")],
        day_start="08:00",
        day_end="22:00",
        min_duration_minutes=30,
    )
    assert len(result) == 2
    assert result[0].start == "08:00"
    assert result[0].end == "10:00"
    assert result[1].start == "12:00"
    assert result[1].end == "22:00"


def test_adjacent_courses():
    """Back-to-back courses leave no gap between them."""
    result = compute_free_slots(
        occupied=[
            TimeSlot(start="08:00", end="10:00", type="course", name="高数"),
            TimeSlot(start="10:00", end="12:00", type="course", name="线代"),
        ],
        day_start="08:00",
        day_end="22:00",
        min_duration_minutes=30,
    )
    assert len(result) == 1
    assert result[0].start == "12:00"


def test_min_duration_filter():
    """Slots shorter than min_duration_minutes are excluded."""
    result = compute_free_slots(
        occupied=[
            TimeSlot(start="08:00", end="08:20", type="task", name="Quick task"),
        ],
        day_start="08:00",
        day_end="08:30",
        min_duration_minutes=30,
    )
    # 08:20-08:30 is only 10 minutes, should be filtered out
    assert len(result) == 0


def test_overlapping_events():
    """Overlapping events are merged correctly."""
    result = compute_free_slots(
        occupied=[
            TimeSlot(start="09:00", end="11:00", type="course", name="A"),
            TimeSlot(start="10:00", end="12:00", type="task", name="B"),
        ],
        day_start="08:00",
        day_end="22:00",
        min_duration_minutes=30,
    )
    assert result[0].start == "08:00"
    assert result[0].end == "09:00"
    assert result[1].start == "12:00"
    assert result[1].end == "22:00"


def test_lunch_break_excluded():
    """Lunch break is treated as occupied time."""
    result = compute_free_slots(
        occupied=[
            TimeSlot(start="12:00", end="13:30", type="break", name="午休"),
        ],
        day_start="08:00",
        day_end="22:00",
        min_duration_minutes=30,
    )
    starts = [s.start for s in result]
    assert "08:00" in starts
    assert "13:30" in starts
    # No slot should overlap with 12:00-13:30
    for slot in result:
        assert not (slot.start < "13:30" and slot.end > "12:00")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd student-planner && pytest tests/test_calendar.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_free_slots'`

- [x] **Step 3: Implement calendar service**

```python
# app/services/calendar.py
from dataclasses import dataclass


@dataclass
class TimeSlot:
    start: str  # "HH:MM"
    end: str  # "HH:MM"
    type: str = ""  # "course" / "task" / "break"
    name: str = ""
    duration_minutes: int = 0

    def __post_init__(self):
        if not self.duration_minutes:
            self.duration_minutes = _minutes(self.end) - _minutes(self.start)


@dataclass
class DaySchedule:
    date: str
    weekday: str
    free_periods: list[TimeSlot]
    occupied: list[TimeSlot]
    summary: str = ""


def _minutes(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _time_str(minutes: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def compute_free_slots(
    occupied: list[TimeSlot],
    day_start: str = "08:00",
    day_end: str = "22:00",
    min_duration_minutes: int = 30,
) -> list[TimeSlot]:
    """Compute free time slots by subtracting occupied periods from the day range."""
    start_min = _minutes(day_start)
    end_min = _minutes(day_end)

    # Convert occupied to minute intervals and sort
    intervals = sorted(
        [(_minutes(o.start), _minutes(o.end)) for o in occupied],
        key=lambda x: x[0],
    )

    # Merge overlapping intervals
    merged: list[tuple[int, int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Compute free slots as gaps between merged occupied intervals
    free: list[TimeSlot] = []
    cursor = start_min

    for occ_start, occ_end in merged:
        # Clamp to day boundaries
        occ_start = max(occ_start, start_min)
        occ_end = min(occ_end, end_min)

        if cursor < occ_start:
            duration = occ_start - cursor
            if duration >= min_duration_minutes:
                free.append(TimeSlot(
                    start=_time_str(cursor),
                    end=_time_str(occ_start),
                    duration_minutes=duration,
                ))
        cursor = max(cursor, occ_end)

    # Remaining time after last occupied slot
    if cursor < end_min:
        duration = end_min - cursor
        if duration >= min_duration_minutes:
            free.append(TimeSlot(
                start=_time_str(cursor),
                end=_time_str(end_min),
                duration_minutes=duration,
            ))

    return free
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd student-planner && pytest tests/test_calendar.py -v`
Expected: All 6 tests PASS

- [x] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: calendar service with get_free_slots computation"
```

---

### Task 8: Remaining Models (AgentLog, Memory, SessionSummary, ConversationMessage)

These models are needed by Plan 2 (Agent core) and Plan 4 (Memory system). We create them now so the database schema is complete.

**Files:**
- Create: `student-planner/app/models/agent_log.py`
- Create: `student-planner/app/models/memory.py`
- Create: `student-planner/app/models/session_summary.py`
- Create: `student-planner/app/models/conversation_message.py`
- Modify: `student-planner/app/models/__init__.py`

- [x] **Step 1: Write AgentLog model**

```python
# app/models/agent_log.py
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    step: Mapped[int] = mapped_column(Integer)
    tool_called: Mapped[str] = mapped_column(String(50))
    tool_args: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

- [x] **Step 2: Write Memory model**

```python
# app/models/memory.py
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))  # preference / habit / decision / knowledge
    content: Mapped[str] = mapped_column(Text)
    source_session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_accessed: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)
```

- [x] **Step 3: Write SessionSummary and ConversationMessage models**

```python
# app/models/session_summary.py
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    summary: Mapped[str] = mapped_column(Text)
    actions_taken: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

```python
# app/models/conversation_message.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user / assistant / tool_call / tool_result
    content: Mapped[str] = mapped_column(Text)
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

- [x] **Step 4: Update models/__init__.py**

```python
# app/models/__init__.py
from app.models.user import User
from app.models.course import Course
from app.models.exam import Exam
from app.models.task import Task
from app.models.reminder import Reminder
from app.models.agent_log import AgentLog
from app.models.memory import Memory
from app.models.session_summary import SessionSummary
from app.models.conversation_message import ConversationMessage

__all__ = [
    "User", "Course", "Exam", "Task", "Reminder",
    "AgentLog", "Memory", "SessionSummary", "ConversationMessage",
]
```

- [x] **Step 5: Verify all models can be imported and tables created**

Run: `cd student-planner && python -c "from app.models import *; print('All models OK')"`
Expected: `All models OK`

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add AgentLog, Memory, SessionSummary, ConversationMessage models"
```

---

### Task 9: Alembic Setup + Initial Migration

**Files:**
- Create: `student-planner/alembic.ini`
- Create: `student-planner/alembic/env.py`
- Create: `student-planner/alembic/versions/` (auto-generated)

- [x] **Step 1: Initialize Alembic**

Run: `cd student-planner && alembic init alembic`

- [x] **Step 2: Configure alembic/env.py to use our models and async engine**

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base
from app.models import *  # noqa: F401, F403 — ensure all models are registered

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [x] **Step 3: Update alembic.ini sqlalchemy.url**

Set `sqlalchemy.url` to empty string (we use `settings.database_url` in env.py):
```ini
sqlalchemy.url =
```

- [x] **Step 4: Generate initial migration**

Run: `cd student-planner && alembic revision --autogenerate -m "initial schema"`
Expected: Migration file created in `alembic/versions/`

- [x] **Step 5: Apply migration**

Run: `cd student-planner && alembic upgrade head`
Expected: All tables created

- [x] **Step 6: Run full test suite**

Run: `cd student-planner && pytest -v`
Expected: All tests PASS (auth + courses + exams + tasks + reminders + calendar)

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: alembic setup with initial migration for all models"
```

