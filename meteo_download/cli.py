from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import __version__
from .adapters import adapter_for
from .backends import ExternalToolBackend, PythonDownloadBackend
from .catalog import CATALOG_DIR, find_source, load_sources, validate_sources
from .models import DownloadRequest
from .state import StateStore


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _build_request(args: argparse.Namespace) -> DownloadRequest:
    source = find_source(args.source)
    time_range = tuple(args.time_range) if args.time_range else None
    region = tuple(args.region) if args.region else None
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
    request = _build_request(args)
    adapter = adapter_for(request.source.adapter)
    errors = adapter.validate_config(request)
    plan = adapter.plan(request)
    return request, plan, errors


def cmd_plan(args: argparse.Namespace) -> int:
    _, plan, errors = _create_plan(args)
    if errors:
        for error in errors:
            print(f"WARN: {error}")
    print(plan.message)
    for item in plan.files:
        size = f" ({item.size_bytes} bytes)" if item.size_bytes else ""
        print(f"{item.filename}{size}\n  {item.url}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    request, plan, errors = _create_plan(args)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    store = StateStore(Path(args.state_db) if args.state_db else None)
    task_id = store.create_task(request, plan.files)
    if args.dry_run:
        print(f"created dry-run task {task_id}: {len(plan.files)} files")
        return 0
    virtual = [item for item in plan.files if item.metadata.get("virtual")]
    if virtual:
        result = adapter_for(request.source.adapter).execute(plan, store, task_id)
        if result is not None:
            return result
        store.update_task_status(task_id, "blocked")
        print(f"task {task_id} is blocked: {request.source.protocol.value} has no exporter implementation")
        return 2
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
    backend = PythonDownloadBackend()
    failed = 0
    for item in plan.files:
        try:
            backend.download(item, request.output)
            store.update_file_status(task_id, item.url, "completed")
        except Exception as exc:
            failed += 1
            store.update_file_status(task_id, item.url, "failed", str(exc))
            print(f"failed: {item.filename}: {exc}")
    store.update_task_status(task_id, "failed" if failed else "completed")
    print(f"completed task {task_id}: {len(plan.files) - failed}/{len(plan.files)} files")
    return 1 if failed else 0


def cmd_tasks(args: argparse.Namespace) -> int:
    store = StateStore(Path(args.state_db) if args.state_db else None)
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
    sources = load_sources()
    errors = validate_sources(sources)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"catalog ok: {len(sources)} sources in {CATALOG_DIR}")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    print(f"open-earth-data-kit {__version__}")
    print(f"catalog: {CATALOG_DIR}")
    for var in ["CDSAPI_URL", "CDSAPI_KEY", "EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"]:
        status = "set" if os.getenv(var) else "missing"
        print(f"{var}: {status}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meteo", description="Unified public Earth data download CLI")
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
        p.add_argument("--workers", type=int, default=4, help="Concurrent workers/requests for export-oriented sources")
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
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
