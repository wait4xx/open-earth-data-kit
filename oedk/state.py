from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import DownloadRequest, PlannedFile


DEFAULT_STATE_DIR = Path(".oedk")


class StateStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_STATE_DIR / "state.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def close(self) -> None:
        self.conn.close()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                status TEXT NOT NULL,
                backend TEXT NOT NULL,
                output TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                filename TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );
            """
        )
        self.conn.commit()

    def create_task(self, request: DownloadRequest, files: list[PlannedFile]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        params = asdict(request)
        params["source"] = request.source.id
        params["output"] = str(request.output)
        cur = self.conn.execute(
            """
            INSERT INTO tasks (source_id, status, backend, output, parameters_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.source.id,
                "planned",
                request.backend,
                str(request.output),
                json.dumps(params, ensure_ascii=False, default=str),
                now,
                now,
            ),
        )
        task_id = int(cur.lastrowid)
        self.conn.executemany(
            """
            INSERT INTO files (task_id, url, filename, size_bytes, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(task_id, item.url, item.filename, item.size_bytes, "pending") for item in files],
        )
        self.conn.commit()
        return task_id

    def update_task_status(self, task_id: int, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now, task_id))
        self.conn.commit()

    def update_file_status(self, task_id: int, url: str, status: str, error: str = "") -> None:
        self.conn.execute(
            "UPDATE files SET status = ?, error = ? WHERE task_id = ? AND url = ?",
            (status, error, task_id, url),
        )
        self.conn.commit()

    def list_tasks(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT t.*, COUNT(f.id) AS file_count
                FROM tasks t LEFT JOIN files f ON f.task_id = t.id
                GROUP BY t.id
                ORDER BY t.id DESC
                """
            )
        )

    def task_files(self, task_id: int) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM files WHERE task_id = ? ORDER BY id", (task_id,)))

