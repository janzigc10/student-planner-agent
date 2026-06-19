"""Real WebSocket smoke for LangGraph action golden paths.

The script starts a temporary local OpenAI-compatible stub and a real uvicorn
backend on 127.0.0.1:8001 with SP_AGENT_RUNTIME=langgraph. It uses a temporary
SQLite database under D:\tmp and verifies DB invariants after the WebSocket
turns complete.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv-native" / "Scripts" / "python.exe"
APP_PORT = 8001
BASE_URL = f"http://127.0.0.1:{APP_PORT}"
WS_URL = f"ws://127.0.0.1:{APP_PORT}/ws/chat"


def log(message: str) -> None:
    print(message, flush=True)


def wait_port(port: int, timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            try:
                sock.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.2)
    raise RuntimeError(f"port {port} did not open")


def request_json(
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    token: str | None = None,
    files: list[tuple[str, str, str, bytes]] | None = None,
) -> dict | list | None:
    import uuid

    headers: dict[str, str] = {}
    data: bytes | None = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if files:
        boundary = f"----smoke{uuid.uuid4().hex}"
        body = bytearray()
        for field, filename, content_type, content in files:
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
            )
            body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
            body.extend(content)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        data = bytes(body)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    with urlopen(
        Request(BASE_URL + path, data=data, method=method, headers=headers),
        timeout=25,
    ) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else None


def write_stub(stub_port: int) -> Path:
    stub_path = Path(tempfile.gettempdir()) / f"sp_langgraph_ws_stub_{stub_port}.py"
    stub_path.write_text(
        r'''
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COUNTER = {"n": 0}

def last_user(messages):
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""

def tool_messages(messages):
    return [str(message.get("content") or "") for message in messages if message.get("role") == "tool"]

def tool_call_names(messages):
    names = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if function.get("name"):
                names.append(str(function["name"]))
    return names

def first_id(text):
    match = re.search(r'"id"\s*:\s*"([^"]+)"', text)
    return match.group(1) if match else None

def tool_call(name, args):
    COUNTER["n"] += 1
    return {
        "id": f"call_{COUNTER['n']:04d}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }

def sse_response(message):
    if message.get("tool_calls"):
        delta = {
            "tool_calls": [
                {
                    "index": index,
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    },
                }
                for index, call in enumerate(message["tool_calls"])
            ]
        }
    else:
        delta = {"content": message.get("content") or ""}
    chunks = [
        {"id": "smoke", "object": "chat.completion.chunk", "created": int(time.time()), "model": "stub", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {"id": "smoke", "object": "chat.completion.chunk", "created": int(time.time()), "model": "stub", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    return ("".join("data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode("utf-8")

def normal_response(message):
    return json.dumps(
        {
            "id": "smoke",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "stub",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        },
        ensure_ascii=False,
    ).encode("utf-8")

def choose_message(payload):
    messages = payload.get("messages") or []
    user = last_user(messages)
    calls = tool_call_names(messages)
    tools = tool_messages(messages)

    if "PLAIN_CHAT_SMOKE" in user:
        return {"role": "assistant", "content": "plain chat done"}

    if "改革开放" in user:
        return {"role": "assistant", "content": "rag answer done"}

    if "TOOL_FAILURE_SMOKE" in user:
        if "create_task" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("create_task", {"title": "Recovered task"})]}
        if "ask_user" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("ask_user", {"question": "Confirm recovered task", "type": "review", "data": {"tasks": [{"title": "Recovered task", "scheduled_date": "2099-06-02", "start_time": "10:00", "end_time": "10:30"}]}})]}
        if calls.count("create_task") >= 2:
            return {"role": "assistant", "content": "tool failure recovered"}
        return {"role": "assistant", "content": None, "tool_calls": [tool_call("create_task", {"title": "Recovered task", "scheduled_date": "2099-06-02", "start_time": "10:00", "end_time": "10:30"})]}

    if "TASK_CANCEL_SMOKE" in user:
        if "ask_user" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("ask_user", {"question": "Confirm creating Cancelled task?", "type": "review", "data": {"tasks": [{"title": "Cancelled task", "scheduled_date": "2099-06-03", "start_time": "10:00", "end_time": "10:30"}]}})]}
        if "create_task" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("create_task", {"title": "Cancelled task", "scheduled_date": "2099-06-03", "start_time": "10:00", "end_time": "10:30"})]}
        return {"role": "assistant", "content": "task cancel done"}

    if "TASK_UPDATE_SMOKE" in user:
        if "list_tasks" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("list_tasks", {"date_from": "2099-06-01", "date_to": "2099-06-01"})]}
        if "ask_user" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("ask_user", {"question": "Confirm updating Smoke task", "type": "confirm"})]}
        if "update_task" not in calls:
            task_id = None
            for text in tools:
                if "Smoke task" in text:
                    task_id = first_id(text)
                    break
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("update_task", {"task_id": task_id, "scheduled_date": "2099-06-01", "start_time": "16:00", "end_time": "17:00", "reminder_advance_minutes": 15})]}
        return {"role": "assistant", "content": "task update done"}

    if "STUDY_PLAN_SMOKE" in user:
        if "get_free_slots" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("get_free_slots", {"start_date": "2099-06-01", "end_date": "2099-06-03", "min_duration_minutes": 30})]}
        if "create_study_plan" not in calls:
            return {"role": "assistant", "content": None, "tool_calls": [tool_call("create_study_plan", {"exams": [{"course_name": "English 3", "exam_date": "2099-06-04", "difficulty": "medium"}], "available_slots": {"slots": [{"date": "2099-06-01", "free_periods": [{"start": "09:00", "end": "10:00", "duration_minutes": 60}]}]}, "study_context": {"raw_notes": "unit 1-3", "using_defaults": True}, "strategy": "balanced"})]}
        return {"role": "assistant", "content": "study plan done"}

    # Used by planner fallback, compression, and session finalization.
    if not payload.get("stream"):
        return {"role": "assistant", "content": "{}"}

    return {"role": "assistant", "content": "stub fallback"}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        message = choose_message(payload)
        body = sse_response(message) if payload.get("stream") else normal_response(message)
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8" if payload.get("stream") else "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        return

ThreadingHTTPServer(("127.0.0.1", int(os.environ["STUB_PORT"])), Handler).serve_forever()
''',
        encoding="utf-8",
    )
    return stub_path


async def run_turn(ws, label: str, message: str, answers: list[str]) -> dict:
    log(f"TURN {label}")
    await ws.send(json.dumps({"message": message}, ensure_ascii=False))
    pending_answers = list(answers)
    sequence: list[str] = []
    graph_nodes: list[str] = []
    final_text: list[str] = []
    while True:
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=45))
        item = str(event.get("name") or event.get("type"))
        sequence.append(item)
        log(f"{label}:{item}")
        result = event.get("result")
        if isinstance(result, dict) and isinstance(result.get("graph_nodes"), list):
            graph_nodes.extend(str(node) for node in result["graph_nodes"])
        if event.get("type") in {"text", "result"} and event.get("content"):
            final_text.append(str(event["content"]))
        if event.get("type") == "ask_user":
            answer = pending_answers.pop(0) if pending_answers else "ok"
            await ws.send(json.dumps({"answer": answer}, ensure_ascii=False))
        if event.get("type") == "error":
            raise AssertionError(json.dumps(event, ensure_ascii=True))
        if event.get("type") == "done":
            if "delegate_legacy_loop" in graph_nodes:
                raise AssertionError(f"{label} graph_nodes used legacy delegate: {graph_nodes}")
            return {"sequence": sequence, "graph_nodes": graph_nodes, "final_text": final_text}


async def run_ws_smoke(token: str) -> dict[str, list[str]]:
    import websockets

    work_due = (date.today() + timedelta(days=21)).isoformat()
    async with websockets.connect(
        WS_URL,
        max_size=None,
        ping_interval=None,
        close_timeout=1,
    ) as ws:
        await ws.send(json.dumps({"token": token}))
        connected = json.loads(await ws.recv())
        assert connected["type"] == "connected", connected

        fixture = ROOT / "tests" / "fixtures" / "sample_schedule.xlsx"
        upload = request_json(
            "POST",
            "/api/schedule/upload",
            token=token,
            files=[
                (
                    "file",
                    "sample_schedule.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    fixture.read_bytes(),
                )
            ],
        )

        for payload in [
            {"name": "Course Alpha", "weekday": 1, "start_time": "12:00", "end_time": "13:00", "week_start": 1, "week_end": 16, "week_pattern": "all"},
            {"name": "Course Beta", "weekday": 2, "start_time": "12:00", "end_time": "13:00", "week_start": 1, "week_end": 16, "week_pattern": "all"},
            {"name": "Course Gamma", "weekday": 3, "start_time": "12:00", "end_time": "13:00", "week_start": 1, "week_end": 16, "week_pattern": "all"},
            {"name": "Course Gamma", "weekday": 3, "start_time": "12:00", "end_time": "13:00", "week_start": 1, "week_end": 16, "week_pattern": "all"},
        ]:
            request_json("POST", "/api/courses/", payload=payload, token=token)

        return {
            "no_web": await run_turn(
                ws,
                "no_web",
                "最新政策是什么",
                [],
            ),
            "rag_hit": await run_turn(
                ws,
                "rag_hit",
                "改革开放是什么时候开始的",
                [],
            ),
            "rag_insufficient": await run_turn(
                ws,
                "rag_insufficient",
                "量子计算的退相干错误怎么解释",
                [],
            ),
            "plain_chat": await run_turn(
                ws,
                "plain_chat",
                "PLAIN_CHAT_SMOKE hello",
                [],
            ),
            "tool_failure": await run_turn(
                ws,
                "tool_failure",
                "TOOL_FAILURE_SMOKE 创建一个 Recovered task 任务，时间是 2099-06-02 10:00-10:30",
                ["确认"],
            ),
            "task_cancel": await run_turn(
                ws,
                "task_cancel",
                "TASK_CANCEL_SMOKE 创建一个 Cancelled task 任务，时间是 2099-06-03 10:00-10:30",
                ["no"],
            ),
            "task_create": await run_turn(
                ws,
                "task_create",
                "创建一个 Smoke task 的任务",
                ["2099-06-01 15:00-16:00, 提前30分钟提醒", "ok"],
            ),
            "task_update": await run_turn(
                ws,
                "task_update",
                "TASK_UPDATE_SMOKE 把 Smoke task 改到2099-06-01 16:00-17:00，提前15分钟提醒",
                ["ok"],
            ),
            "study": await run_turn(
                ws,
                "study",
                "STUDY_PLAN_SMOKE 2099-06-04 有 English 3 考试，帮我做复习计划，范围 unit 1-3",
                ["ok"],
            ),
            "work": await run_turn(
                ws,
                "work",
                f"{work_due} 要交 ML report 作业，帮我做作业计划，要求 PDF",
                ["ok"],
            ),
            "schedule": await run_turn(
                ws,
                "schedule",
                f"please import this schedule file_id={upload['file_id']}",
                [
                    "1-2 08:00-09:40, 3-4 10:00-11:40, 5-6 14:00-15:40, 7-8 16:00-17:40, 2099-03-01, 16周",
                    "ok",
                ],
            ),
            "course_rename": await run_turn(
                ws,
                "course_rename",
                "把课程 Course Alpha 改名为 Course Alpha Renamed",
                ["ok"],
            ),
            "course_delete": await run_turn(
                ws,
                "course_delete",
                "删除课程 Course Beta",
                ["ok"],
            ),
            "course_merge": await run_turn(
                ws,
                "course_merge",
                "合并重复课程 Course Gamma",
                ["Course Gamma", "ok"],
            ),
        }


def query_db(env: dict[str, str]) -> dict:
    code = r'''
import asyncio
import json
from sqlalchemy import select
from app.database import async_session
from app.models.course import Course
from app.models.reminder import Reminder
from app.models.task import Task

async def main():
    async with async_session() as db:
        tasks = list((await db.execute(select(Task))).scalars().all())
        reminders = list((await db.execute(select(Reminder))).scalars().all())
        courses = list((await db.execute(select(Course))).scalars().all())
        print(json.dumps({
            "tasks": [{"title": t.title, "date": t.scheduled_date, "start": t.start_time, "end": t.end_time} for t in tasks],
            "reminders": [{"advance": r.advance_minutes, "at": r.remind_at} for r in reminders],
            "courses": [c.name for c in courses],
        }, ensure_ascii=True))

asyncio.run(main())
'''
    raw = subprocess.run(
        [str(PYTHON), "-c", code],
        cwd=str(ROOT),
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return json.loads(raw)


def assert_invariants(db_state: dict) -> None:
    tasks = db_state["tasks"]
    reminders = db_state["reminders"]
    courses = db_state["courses"]

    assert any(
        task["title"] == "Smoke task"
        and task["date"] == "2099-06-01"
        and task["start"] == "16:00"
        and task["end"] == "17:00"
        for task in tasks
    ), json.dumps(db_state, ensure_ascii=True)
    assert any(
        reminder["advance"] == 15 and "15:45" in reminder["at"]
        for reminder in reminders
    ), json.dumps(db_state, ensure_ascii=True)
    assert any("English 3" in task["title"] for task in tasks), json.dumps(db_state, ensure_ascii=True)
    assert any("ML report" in task["title"] for task in tasks), json.dumps(db_state, ensure_ascii=True)
    assert "Course Alpha Renamed" in courses, json.dumps(db_state, ensure_ascii=True)
    assert "Course Beta" not in courses, json.dumps(db_state, ensure_ascii=True)
    assert courses.count("Course Gamma") == 1, json.dumps(db_state, ensure_ascii=True)
    assert any(
        task["title"] == "Recovered task"
        and task["date"] == "2099-06-02"
        and task["start"] == "10:00"
        and task["end"] == "10:30"
        for task in tasks
    ), json.dumps(db_state, ensure_ascii=True)
    assert not any(task["title"] == "Cancelled task" for task in tasks), json.dumps(
        db_state,
        ensure_ascii=True,
    )
    assert any(
        name in courses
        for name in ["高等数学", "线性代数", "大学英语", "大学物理", "概率论", "体育"]
    ), json.dumps(db_state, ensure_ascii=True)


def assert_smoke_evidence(sequences: dict) -> None:
    assert sequences["no_web"]["sequence"] == ["text", "done"], json.dumps(sequences, ensure_ascii=True)
    assert "rag_qa" in sequences["rag_hit"]["graph_nodes"], json.dumps(sequences["rag_hit"], ensure_ascii=True)
    assert "rag_insufficient" in sequences["rag_insufficient"]["graph_nodes"], json.dumps(
        sequences["rag_insufficient"], ensure_ascii=True
    )
    assert sequences["plain_chat"]["sequence"][0] == "text_delta", json.dumps(
        sequences["plain_chat"], ensure_ascii=True
    )
    assert "create_task" in sequences["tool_failure"]["sequence"], json.dumps(
        sequences["tool_failure"], ensure_ascii=True
    )
    assert "ask_user" in sequences["task_cancel"]["sequence"], json.dumps(
        sequences["task_cancel"], ensure_ascii=True
    )
    assert "create_task" in sequences["task_cancel"]["sequence"], json.dumps(
        sequences["task_cancel"], ensure_ascii=True
    )
    for label, evidence in sequences.items():
        assert "delegate_legacy_loop" not in evidence["graph_nodes"], json.dumps(
            {label: evidence}, ensure_ascii=True
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=r"D:\tmp\student-planner-langgraph-ws-smoke-full.db")
    parser.add_argument("--stub-port", type=int, default=18095)
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()

    stub_path = write_stub(args.stub_port)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "SP_DATABASE_URL": f"sqlite+aiosqlite:///{db_path.as_posix()}",
            "SP_AGENT_RUNTIME": "langgraph",
            "SP_LLM_API_KEY": "sk-smoke",
            "SP_LLM_BASE_URL": f"http://127.0.0.1:{args.stub_port}/v1",
            "SP_LLM_MODEL": "stub",
            "SP_RAG_EMBEDDING_PROVIDER": "fallback",
            "SP_RAG_EMBEDDING_API_KEY": "",
            "TMP": r"D:\tmp\pytest-tmp-native",
            "TEMP": r"D:\tmp\pytest-tmp-native",
        }
    )
    stub_env = os.environ.copy()
    stub_env["STUB_PORT"] = str(args.stub_port)
    stub_env["PYTHONIOENCODING"] = "utf-8"
    stub = subprocess.Popen(
        [str(PYTHON), str(stub_path)],
        cwd=str(ROOT),
        env=stub_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    app = None
    try:
        wait_port(args.stub_port, 10)
        subprocess.run(
            [str(PYTHON), "-m", "alembic", "upgrade", "head"],
            cwd=str(ROOT),
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        app = subprocess.Popen(
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(APP_PORT),
                "--log-level",
                "warning",
            ],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        wait_port(APP_PORT, 30)

        username = f"lg-smoke-{int(time.time())}"
        request_json("POST", "/api/auth/register", payload={"username": username, "password": "pass123"})
        token_payload = request_json("POST", "/api/auth/login", payload={"username": username, "password": "pass123"})
        token = token_payload["access_token"]

        sequences = asyncio.run(run_ws_smoke(token))
        db_state = query_db(env)
        assert_smoke_evidence(sequences)
        assert_invariants(db_state)
        log("SMOKE_EVENTS=" + json.dumps(sequences, ensure_ascii=True))
        log("SMOKE_DB=" + json.dumps(db_state, ensure_ascii=True))
        return 0
    finally:
        for proc in (app, stub):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
