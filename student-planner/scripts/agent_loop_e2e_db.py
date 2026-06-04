from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_URL = "sqlite+aiosqlite:///./agent_loop_e2e.db"


def resolve_sqlite_path(database_url: str) -> Path:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if database_url.startswith(prefix):
            raw_path = database_url[len(prefix) :]
            path = Path(raw_path)
            return path if path.is_absolute() else Path.cwd() / path
    raise SystemExit(f"Unsupported E2E database URL: {database_url}")


def connect() -> sqlite3.Connection:
    database_url = os.environ.get("SP_DATABASE_URL", DEFAULT_DB_URL)
    path = resolve_sqlite_path(database_url)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def rows(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def find_user(connection: sqlite3.Connection, username: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def cleanup(username: str) -> None:
    with connect() as connection:
        user = find_user(connection, username)
        if not user:
            return
        user_id = user["id"]
        session_rows = rows(
            connection,
            """
            SELECT session_id FROM agent_logs WHERE user_id = ?
            UNION
            SELECT session_id FROM session_summaries WHERE user_id = ?
            UNION
            SELECT source_session_id AS session_id FROM memories WHERE user_id = ? AND source_session_id IS NOT NULL
            """,
            (user_id, user_id, user_id),
        )
        session_ids = [row["session_id"] for row in session_rows if row.get("session_id")]
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            connection.execute(f"DELETE FROM conversation_messages WHERE session_id IN ({placeholders})", session_ids)

        for table in (
            "agent_logs",
            "session_summaries",
            "memories",
            "reminders",
            "tasks",
            "exams",
            "courses",
        ):
            connection.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        connection.commit()


def snapshot(username: str) -> dict[str, Any]:
    with connect() as connection:
        user = find_user(connection, username)
        if not user:
            return {
                "username": username,
                "user": None,
                "courses": [],
                "tasks": [],
                "reminders": [],
                "agent_logs": [],
                "messages": [],
            }

        user_id = user["id"]
        agent_logs = rows(
            connection,
            "SELECT step, tool_called, tool_args, tool_result, timestamp, session_id FROM agent_logs WHERE user_id = ? ORDER BY timestamp, step",
            (user_id,),
        )
        session_ids = sorted({row["session_id"] for row in agent_logs if row.get("session_id")})
        messages: list[dict[str, Any]] = []
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            messages = rows(
                connection,
                f"""
                SELECT session_id, role, substr(content, 1, 1200) AS content, is_compressed, timestamp
                FROM conversation_messages
                WHERE session_id IN ({placeholders})
                ORDER BY timestamp
                """,
                tuple(session_ids),
            )

        return {
            "username": username,
            "user": user,
            "courses": rows(
                connection,
                """
                SELECT id, name, teacher, location, weekday, start_time, end_time,
                       week_start, week_end, week_pattern, week_text
                FROM courses
                WHERE user_id = ?
                ORDER BY weekday, start_time, name
                """,
                (user_id,),
            ),
            "tasks": rows(
                connection,
                """
                SELECT id, title, description, scheduled_date, start_time, end_time, status
                FROM tasks
                WHERE user_id = ?
                ORDER BY scheduled_date, start_time, title
                """,
                (user_id,),
            ),
            "reminders": rows(
                connection,
                """
                SELECT id, target_type, target_id, remind_at, advance_minutes, status
                FROM reminders
                WHERE user_id = ?
                ORDER BY remind_at, id
                """,
                (user_id,),
            ),
            "agent_logs": agent_logs,
            "messages": messages,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Loop E2E database helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("username")

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("username")

    args = parser.parse_args()
    if args.command == "cleanup":
        cleanup(args.username)
        return
    if args.command == "snapshot":
        print(json.dumps(snapshot(args.username), ensure_ascii=False))
        return
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
