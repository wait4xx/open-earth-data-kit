import urllib.error

from oedk.cli import main


def test_list_command_runs(capsys):
    assert main(["list", "--support", "downloadable"]) == 0

    out = capsys.readouterr().out
    assert "era5_planette" in out


def test_info_command_runs(capsys):
    assert main(["info", "era5_planette"]) == 0

    out = capsys.readouterr().out
    assert "Planette ERA5" in out


def test_catalog_validate_runs(capsys):
    assert main(["catalog", "validate"]) == 0

    out = capsys.readouterr().out
    assert "catalog ok" in out


def test_plan_handles_network_error(capsys, monkeypatch):
    """plan 阶段网络失败时应给友好错误 + 非零退出码，而非 traceback。"""
    from oedk.adapters.http_index import HttpIndexAdapter

    def fake_plan(self, request):
        raise urllib.error.URLError("[Errno -2] Name or service not known")

    monkeypatch.setattr(HttpIndexAdapter, "plan", fake_plan)

    ret = main(["plan", "ecmwf_open_ifs"])
    assert ret == 1

    out = capsys.readouterr().out
    assert "ERROR" in out


def test_doctor_lists_all_catalog_credentials(capsys):
    """doctor 应检查目录中所有数据源声明的凭据，而非硬编码列表。"""
    from oedk.catalog import load_sources

    expected = {v for s in load_sources() for v in s.required_credentials}

    main(["doctor"])
    out = capsys.readouterr().out

    for var in expected:
        assert var in out, f"doctor 未检查 catalog 中声明的凭据: {var}"


def test_download_runs_concurrently(capsys, monkeypatch, tmp_path):
    """download 默认分支应真正并发下载 (用并发计数器验证 peak > 1)。"""
    import threading
    import time
    from oedk.adapters.http_index import HttpIndexAdapter
    from oedk.backends import PythonDownloadBackend
    from oedk.models import DownloadPlan, PlannedFile

    files = [
        PlannedFile(url=f"https://example.com/file{i}.grib2", filename=f"file{i}.grib2")
        for i in range(4)
    ]
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_plan(self, request):
        return DownloadPlan(request=request, files=files, message="test plan")

    def fake_download(self, item, output_dir, timeout=60):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)  # 模拟慢 I/O，让并发可见
        with lock:
            active -= 1
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / item.filename).write_bytes(b"data")
        return output_dir / item.filename

    monkeypatch.setattr(HttpIndexAdapter, "plan", fake_plan)
    monkeypatch.setattr(PythonDownloadBackend, "download", fake_download)

    ret = main([
        "download", "ecmwf_open_ifs",
        "-o", str(tmp_path),
        "--state-db", str(tmp_path / "state.db"),
    ])
    assert ret == 0

    out = capsys.readouterr().out
    assert "4/4 files" in out
    assert peak > 1, f"下载未并发执行, peak={peak}"


def test_plan_rejects_invalid_region(capsys):
    """region 越界或 min>max 时应给清晰错误，而非到下载阶段才报错。"""
    ret = main(["plan", "ecmwf_open_ifs", "-r", "100", "120", "50", "40"])
    assert ret == 1

    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "lat" in out.lower()


def test_plan_rejects_invalid_time_range(capsys):
    """时间字符串不可解析或 start>end 时应给清晰错误。"""
    ret = main(["plan", "ecmwf_open_ifs", "-t", "2024-01-01", "not-a-date"])
    assert ret == 1

    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "time" in out.lower()
