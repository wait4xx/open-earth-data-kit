import sqlite3

import pytest
from pathlib import Path

from oedk.catalog import find_source
from oedk.models import DownloadRequest, PlannedFile
from oedk.state import StateStore


def test_state_store_creates_task(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    source = find_source("ecmwf_open_ifs")
    request = DownloadRequest(source=source, output=tmp_path)
    task_id = store.create_task(request, [PlannedFile(url="https://example.com/a.grib2", filename="a.grib2")])

    tasks = store.list_tasks()
    files = store.task_files(task_id)

    assert tasks[0]["id"] == task_id
    assert files[0]["filename"] == "a.grib2"


def test_state_store_context_manager_closes_connection(tmp_path: Path):
    with StateStore(tmp_path / "state.db") as store:
        # 可在 with 块内正常使用
        store.list_tasks()

    # 退出 with 后连接已关闭，再操作应抛 ProgrammingError
    with pytest.raises(sqlite3.ProgrammingError):
        store.list_tasks()
