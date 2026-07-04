"""本地任务状态持久化 (State 层)。

每次执行 ``oedk download`` 都会在一个 SQLite 库里建一条 task 记录及其
属下的 file 记录，用于事后查询"下载了什么 / 成功没有 / 失败原因"。
默认库文件位于 ``.oedk/state.db``，可用 ``--state-db`` 覆盖。

两张表：
- ``tasks`` : 一次下载任务 (谁、用什么后端、输出到哪、何时创建/更新)
- ``files`` : 任务下的每个目标文件及其状态 (pending/completed/failed/...)
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import DownloadRequest, PlannedFile


# 默认状态库目录；整个 .oedk/ 已在 .gitignore 中。
DEFAULT_STATE_DIR = Path(".oedk")


class StateStore:
    """SQLite 状态存储的轻量封装。"""

    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_STATE_DIR / "state.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        # 让查回来的行可以按列名取值 (row["status"])，而不只是按下标。
        self.conn.row_factory = sqlite3.Row
        self._init()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _init(self) -> None:
        """建表 (若已存在则跳过)。在构造时自动调用。"""
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
        """新建一条 task 记录并插入其全部 file 记录，返回新 task id。

        整个请求参数序列化成 JSON 存进 ``parameters_json``，便于事后复现。
        """
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
        """更新任务状态并刷新 updated_at 时间戳。"""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now, task_id))
        self.conn.commit()

    def update_file_status(self, task_id: int, url: str, status: str, error: str = "") -> None:
        """更新某任务下某个 URL 对应文件的状态 (及可选的错误信息)。"""
        self.conn.execute(
            "UPDATE files SET status = ?, error = ? WHERE task_id = ? AND url = ?",
            (status, error, task_id, url),
        )
        self.conn.commit()

    def list_tasks(self) -> list[sqlite3.Row]:
        """列出所有任务，附带各自的文件数，按 id 倒序 (最新的在前)。"""
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
        """返回某任务下的全部文件记录，按插入顺序排列。"""
        return list(self.conn.execute("SELECT * FROM files WHERE task_id = ? ORDER BY id", (task_id,)))

