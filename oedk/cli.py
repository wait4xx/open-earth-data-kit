"""oedk 命令行入口 (CLI 层)。

基于 argparse 实现的子命令分发器，是用户与 oedk 交互的唯一入口
(console_script ``oedk`` 指向 :func:`main`)。职责：

1. 解析命令行参数，组装成 :class:`DownloadRequest`。
2. 通过 :func:`adapter_for` 拿到对应协议的 adapter，调 ``plan`` 得到
   :class:`DownloadPlan`。
3. 对普通物理文件，交给 :class:`PythonDownloadBackend` /
   :class:`ExternalToolBackend` 下载；对"虚拟文件"(``metadata["virtual"]``)，
   改调 adapter 的 ``execute`` 做导出。
4. 全程用 :class:`StateStore` 记录任务/文件状态。

子命令：``list`` / ``info`` / ``plan`` / ``download`` / ``tasks`` /
``catalog`` / ``doctor``。
"""

from __future__ import annotations

import argparse
import os
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import __version__
from .adapters import adapter_for
from .backends import ExternalToolBackend, PythonDownloadBackend
from .catalog import CATALOG_DIR, find_source, load_sources, validate_sources
from .models import DownloadRequest
from .state import StateStore


def _split_csv(value: str | None) -> list[str]:
    """把逗号分隔的字符串拆成去空白列表，空输入返回空列表。"""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_region(region: tuple[float, float, float, float] | None) -> None:
    """校验经纬度边界框 (lon [-180,360], lat [-90,90], min<=max)，不合法抛 ValueError。"""
    if not region:
        return
    lon_min, lon_max, lat_min, lat_max = region
    if not (-180 <= lon_min <= 360 and -180 <= lon_max <= 360):
        raise ValueError(f"region longitude out of range [-180, 360]: ({lon_min}, {lon_max})")
    if not (-90 <= lat_min <= 90 and -90 <= lat_max <= 90):
        raise ValueError(f"region latitude out of range [-90, 90]: ({lat_min}, {lat_max})")
    if lon_min > lon_max:
        raise ValueError(f"region lon_min > lon_max: ({lon_min} > {lon_max})")
    if lat_min > lat_max:
        raise ValueError(f"region lat_min > lat_max: ({lat_min} > {lat_max})")


def _validate_time_range(time_range: tuple[str, str] | None) -> None:
    """校验时间范围 (ISO 格式可解析 + start<=end)，不合法抛 ValueError。"""
    if not time_range:
        return
    from datetime import datetime

    start, end = time_range
    parsed: list[datetime] = []
    for label, value in [("start", start), ("end", end)]:
        try:
            parsed.append(datetime.fromisoformat(value))
        except ValueError:
            raise ValueError(f"invalid time {label} (not ISO format): {value!r}")
    if parsed[0] > parsed[1]:
        raise ValueError(f"time start after end: {start} > {end}")


def _build_request(args: argparse.Namespace) -> DownloadRequest:
    """把 argparse 解析出的 Namespace 组装成一个 :class:`DownloadRequest`。

    协议相关的零散参数 (prefix / endpoint_url / format / frequency / grid /
    workers) 统一塞进 ``extra`` 字典，避免给每种协议单独开命令行字段。
    在这里对 region / time_range 做基本校验，把格式错误拦截在下载阶段之前。
    """
    source = find_source(args.source)
    time_range = tuple(args.time_range) if args.time_range else None
    region = tuple(args.region) if args.region else None
    _validate_region(region)
    _validate_time_range(time_range)
    extra = {}
    if args.prefix:
        extra["prefix"] = args.prefix
    if args.endpoint_url:
        extra["endpoint_url"] = args.endpoint_url
    if args.format:
        extra["format"] = args.format
    if args.frequency:
        extra["frequency"] = args.frequency
    if args.grid:
        extra["grid"] = args.grid
    if args.workers:
        extra["workers"] = args.workers
    return DownloadRequest(
        source=source,
        variables=_split_csv(args.variables),
        time_range=time_range,
        region=region,
        output=Path(args.output),
        file_extensions=_split_csv(args.extensions),
        pattern=args.pattern,
        max_files=args.max_files,
        backend=args.backend,
        tool=args.tool,
        tool_path=args.tool_path,
        dry_run=getattr(args, "dry_run", False),
        extra=extra,
    )


def cmd_list(args: argparse.Namespace) -> int:
    """``oedk list`` —— 列出目录中的数据源，支持按 category/provider/support 过滤。"""
    sources = load_sources()
    for src in sources:
        if args.category and src.category != args.category:
            continue
        if args.provider and args.provider.lower() not in src.provider.lower():
            continue
        if args.support and src.support_level.value != args.support:
            continue
        print(f"{src.id:<32} {src.support_level.value:<13} {src.protocol.value:<15} {src.provider:<18} {src.name}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """``oedk info <source>`` —— 打印单条数据源的详细元数据。"""
    src = find_source(args.source)
    print(f"id: {src.id}")
    print(f"name: {src.name}")
    print(f"category: {src.category}")
    print(f"provider: {src.provider}")
    print(f"protocol: {src.protocol.value}")
    print(f"support_level: {src.support_level.value}")
    print(f"endpoint: {src.endpoint}")
    if src.coverage:
        print(f"coverage: {src.coverage}")
    if src.update_frequency:
        print(f"update_frequency: {src.update_frequency}")
    if src.formats:
        print(f"formats: {', '.join(src.formats)}")
    if src.required_credentials:
        print(f"required_credentials: {', '.join(src.required_credentials)}")
    if src.notes:
        print(f"notes: {src.notes}")
    return 0


def _create_plan(args: argparse.Namespace):
    """公共流程：构建请求 → 选 adapter → 校验配置 → 规划下载。

    被 ``cmd_plan`` 和 ``cmd_download`` 共用。
    """
    request = _build_request(args)
    adapter = adapter_for(request.source.adapter)
    errors = adapter.validate_config(request)
    plan = adapter.plan(request)
    return request, plan, errors


def cmd_plan(args: argparse.Namespace) -> int:
    """``oedk plan`` —— 只规划不下载，打印将要拉取的文件清单 (含校验告警)。"""
    try:
        _, plan, errors = _create_plan(args)
    except (urllib.error.URLError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    if errors:
        for error in errors:
            print(f"WARN: {error}")
    print(plan.message)
    for item in plan.files:
        size = f" ({item.size_bytes} bytes)" if item.size_bytes else ""
        print(f"{item.filename}{size}\n  {item.url}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """``oedk download`` —— 规划并真正执行下载/导出。

    三条执行路径，按优先级判定：
    1. **虚拟文件** (``metadata["virtual"]``) → 调 ``adapter.execute`` 导出
       (OPeNDAP / Icechunk 走这条)。
    2. **外部下载器** (``--backend external``) → 逐个 submit 给 IDM/XDM。
    3. **默认** → 用 :class:`PythonDownloadBackend` 逐个下载。

    每个文件的成功/失败都写回状态库；全部完成后按是否有失败决定退出码。
    整个执行过程包在 ``with StateStore`` 里，确保 SQLite 连接无论哪条路径
    返回都会被关闭。
    """
    try:
        request, plan, errors = _create_plan(args)
    except (urllib.error.URLError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    with StateStore(Path(args.state_db) if args.state_db else None) as store:
        task_id = store.create_task(request, plan.files)
        if args.dry_run:
            print(f"created dry-run task {task_id}: {len(plan.files)} files")
            return 0
        # 虚拟文件分支：交由 adapter 自己导出。
        virtual = [item for item in plan.files if item.metadata.get("virtual")]
        if virtual:
            result = adapter_for(request.source.adapter).execute(plan, store, task_id)
            if result is not None:
                return result
            # adapter 没有实现 execute (返回 None)，说明这种协议尚不支持导出。
            store.update_task_status(task_id, "blocked")
            print(f"task {task_id} is blocked: {request.source.protocol.value} has no exporter implementation")
            return 2
        # 外部下载器分支：只提交 URL，不等完成。
        if request.backend == "external":
            backend = ExternalToolBackend(request.tool or "xdm", request.tool_path)
            for item in plan.files:
                try:
                    backend.submit(item, request.output)
                    store.update_file_status(task_id, item.url, "submitted")
                except Exception as exc:
                    store.update_file_status(task_id, item.url, "failed", str(exc))
            store.update_task_status(task_id, "submitted")
            print(f"submitted task {task_id}: {len(plan.files)} files")
            return 0
        # 默认分支：Python 后端并发下载。下载在 worker 线程跑；
        # 状态写回 (store.update_file_status) 在主线程的 as_completed 循环里做，
        # 因为 SQLite 连接绑定创建它的线程、不能跨线程使用。
        backend = PythonDownloadBackend()
        max_workers = max(1, int(request.extra.get("workers") or 4))
        failed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_item = {
                pool.submit(backend.download, item, request.output): item for item in plan.files
            }
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    future.result()
                    store.update_file_status(task_id, item.url, "completed")
                except Exception as exc:
                    failed += 1
                    store.update_file_status(task_id, item.url, "failed", str(exc))
                    print(f"failed: {item.filename}: {exc}")
        store.update_task_status(task_id, "failed" if failed else "completed")
        print(f"completed task {task_id}: {len(plan.files) - failed}/{len(plan.files)} files")
        return 1 if failed else 0


def cmd_tasks(args: argparse.Namespace) -> int:
    """``oedk tasks list / show <id>`` —— 查询本地任务状态库。"""
    with StateStore(Path(args.state_db) if args.state_db else None) as store:
        if args.task_command == "list":
            for row in store.list_tasks():
                print(f"{row['id']:<5} {row['status']:<10} {row['source_id']:<32} files={row['file_count']} output={row['output']}")
            return 0
        if args.task_command == "show":
            for row in store.task_files(args.task_id):
                print(f"{row['status']:<10} {row['filename']}\n  {row['url']}")
            return 0
        raise SystemExit("tasks command required")


def cmd_catalog_validate(_: argparse.Namespace) -> int:
    """``oedk catalog validate`` —— 校验目录文件的一致性。"""
    sources = load_sources()
    errors = validate_sources(sources)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"catalog ok: {len(sources)} sources in {CATALOG_DIR}")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    """``oedk doctor`` —— 检查本地环境与所有数据源声明的凭据是否就绪。

    汇总目录中每条数据源的 ``required_credentials``，去重后逐一检查对应
    环境变量是否已设置，避免硬编码只覆盖少数几个源。
    """
    print(f"open-earth-data-kit {__version__}")
    print(f"catalog: {CATALOG_DIR}")
    sources = load_sources()
    all_vars = sorted({var for src in sources for var in src.required_credentials})
    for var in all_vars:
        status = "set" if os.getenv(var) else "missing"
        print(f"{var}: {status}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构建顶层 argparse 解析器及全部子命令。

    每个子命令通过 ``set_defaults(func=...)`` 绑定处理函数，:func:`main`
    据此直接调用对应的 ``cmd_*``。
    """
    parser = argparse.ArgumentParser(prog="oedk", description="Unified public Earth data download CLI")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List catalog sources")
    p_list.add_argument("--category")
    p_list.add_argument("--provider")
    p_list.add_argument("--support", choices=["downloadable", "auth_required", "manual"])
    p_list.set_defaults(func=cmd_list)

    p_info = sub.add_parser("info", help="Show source details")
    p_info.add_argument("source")
    p_info.set_defaults(func=cmd_info)

    def add_plan_args(p: argparse.ArgumentParser) -> None:
        """给 plan / download 子命令添加共享的参数集合。"""
        p.add_argument("source")
        p.add_argument("-v", "--variables", help="Comma-separated variable list")
        p.add_argument("-t", "--time-range", nargs=2, metavar=("START", "END"))
        p.add_argument("-r", "--region", nargs=4, type=float, metavar=("LON_MIN", "LON_MAX", "LAT_MIN", "LAT_MAX"))
        p.add_argument("-o", "--output", default="./downloads")
        p.add_argument("--extensions", help="Comma-separated file extensions")
        p.add_argument("--pattern")
        p.add_argument("--prefix")
        p.add_argument("--endpoint-url", help="Override catalog endpoint for this run")
        p.add_argument("--format", choices=["netcdf4", "zarr"])
        p.add_argument("--frequency", help="Dataset frequency for sources that need it")
        p.add_argument("--grid", help="Grid identifier for sources that need it")
        p.add_argument("--workers", type=int, default=4, help="Concurrent workers for parallel download and export")
        p.add_argument("--max-files", type=int)
        p.add_argument("--backend", choices=["python", "external"], default="python")
        p.add_argument("--tool", choices=["idm", "xdm"])
        p.add_argument("--tool-path")

    p_plan = sub.add_parser("plan", help="Create a download plan")
    add_plan_args(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_download = sub.add_parser("download", help="Download a source")
    add_plan_args(p_download)
    p_download.add_argument("--dry-run", action="store_true")
    p_download.add_argument("--state-db")
    p_download.set_defaults(func=cmd_download)

    p_tasks = sub.add_parser("tasks", help="Manage local task state")
    p_tasks.add_argument("--state-db")
    task_sub = p_tasks.add_subparsers(dest="task_command", required=True)
    task_list = task_sub.add_parser("list")
    task_list.set_defaults(func=cmd_tasks)
    task_show = task_sub.add_parser("show")
    task_show.add_argument("task_id", type=int)
    task_show.set_defaults(func=cmd_tasks)

    p_catalog = sub.add_parser("catalog", help="Catalog operations")
    catalog_sub = p_catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_validate = catalog_sub.add_parser("validate")
    catalog_validate.set_defaults(func=cmd_catalog_validate)

    p_doctor = sub.add_parser("doctor", help="Check local environment")
    p_doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口：解析参数并分派到对应子命令处理函数，返回退出码。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
