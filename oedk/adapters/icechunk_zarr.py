"""Icechunk / Zarr (icechunk_zarr) 协议适配器。

专门面向 Planette ERA5 —— 一套托管在 S3 上、用 Icechunk (Zarr 兼容的
事务型存储) 组织的 ERA5 再分析数据。和 OPeNDAP 类似，它是"按需子集导出"
而非"下载现成文件"，因此同样走"虚拟文件"约定。

``plan`` 为每个请求的变量生成一个虚拟输出文件 (NetCDF 或 Zarr)，``execute``
则用 icechunk 打开远端仓库的只读会话、经 xarray 切片后写盘。

依赖：xarray + icechunk + zarr + netCDF4 + dask (可选 extra
``pip install -e ".[icechunk]"``)，惰性导入。
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

from oedk.models import DownloadPlan, DownloadRequest, PlannedFile
from oedk.geo import subset_region
from .base import Adapter


class IcechunkZarrAdapter(Adapter):
    """通过 icechunk + xarray 从 Planette ERA5 导出子集的适配器。"""

    def plan(self, request: DownloadRequest) -> DownloadPlan:
        """为每个变量生成一个虚拟输出文件 (NetCDF 或 Zarr)。

        ``metadata`` 里携带 variable / frequency，``execute`` 阶段会读出来
        定位远端数据集路径。
        """
        variables = request.variables or request.source.defaults.get("variables", [])
        frequency = request.extra.get("frequency") or request.source.defaults.get("frequency", "month")
        files = []
        for var in variables:
            suffix = request.extra.get("format", "netcdf4")
            ext = ".zarr" if suffix == "zarr" else ".nc"
            files.append(
                PlannedFile(
                    url=request.source.endpoint,
                    filename=f"{request.source.id}_{var}_{frequency}{ext}",
                    metadata={"virtual": True, "variable": var, "frequency": frequency},
                )
            )
        message = "Icechunk/Zarr export is planned; execution requires optional icechunk dependencies."
        return DownloadPlan(request=request, files=files, message=message)

    def execute(self, plan: DownloadPlan, store, task_id: int) -> int:
        """逐变量打开远端 Icechunk 仓库、做时间/区域切片、写 NetCDF/Zarr。"""
        try:
            import icechunk as ic
            import icechunk.config as ic_config
            import xarray as xr
        except ImportError:
            store.update_task_status(task_id, "failed")
            print("icechunk and xarray are required. Install with: pip install -e '.[icechunk]'")
            return 2

        request = plan.request
        output_format = request.extra.get("format", "netcdf4")
        grid = request.extra.get("grid") or request.source.defaults.get("grid", "0p25latx0p25lon")
        workers = int(request.extra.get("workers") or 4)
        # 并发度按 workers 等比放大，并设一个下限 (64 / 8)，保证即使
        # workers 很小也有足够的并发来高效读取 Zarr 分块。
        config = ic_config.RepositoryConfig(
            max_concurrent_requests=max(64, workers * 64),
            get_partial_values_concurrency=max(8, workers * 8),
        )
        failed = 0

        for item in plan.files:
            variable = item.metadata["variable"]
            frequency = item.metadata["frequency"]
            output = _output_path(request.output, item.filename, len(plan.files) > 1)
            try:
                print(f"[{variable}] opening Planette ERA5 {frequency}/{grid}", flush=True)
                # 远端 Zarr 数据集在桶里的固定路径模式：era5/<变量>/<频率>/<网格>/era5_*.zarr
                zarr_path = f"era5/{variable}/{frequency}/{grid}/era5_{variable}_{frequency}_{grid}.zarr"
                storage = ic.s3_storage(
                    bucket="planette-era5",
                    prefix=zarr_path,
                    region="us-east-2",
                    anonymous=True,
                )
                repo = ic.Repository.open(storage=storage, config=config)
                session = repo.readonly_session(branch="main")
                # chunks={} 让 xarray 用最优分块策略，而不是沿用远端的大分块。
                ds = xr.open_dataset(session.store, engine="zarr", consolidated=False, chunks={})
                print(f"[{variable}] remote dims: {dict(ds.sizes)}", flush=True)
                _print_chunk_hint(ds, variable)
                if request.time_range:
                    print(f"[{variable}] selecting time {request.time_range[0]} to {request.time_range[1]}", flush=True)
                    ds = ds.sel(time=slice(request.time_range[0], request.time_range[1]))
                ds = subset_region(ds, request.region)
                _clear_remote_encoding(ds)
                print(f"[{variable}] selected dims: {dict(ds.sizes)}", flush=True)
                output.parent.mkdir(parents=True, exist_ok=True)
                progress = _progress_context()
                if output_format == "zarr":
                    print(f"[{variable}] writing Zarr: {output}", flush=True)
                    with progress:
                        ds.to_zarr(output, mode="w")
                else:
                    print(f"[{variable}] writing NetCDF: {output}", flush=True)
                    # 对每个数据变量统一启用 zlib 压缩 (complevel 4) + shuffle，
                    # 显著减小 NetCDF 体积，坐标变量保持不压缩以免精度问题。
                    encoding = {
                        name: {"zlib": True, "complevel": 4, "shuffle": True}
                        for name in ds.data_vars
                    }
                    with progress:
                        ds.to_netcdf(output, encoding=encoding if encoding else None)
                ds.close()
                store.update_file_status(task_id, item.url, "completed")
                print(f"exported {variable}: {output}")
            except Exception as exc:
                failed += 1
                store.update_file_status(task_id, item.url, "failed", str(exc))
                print(f"Icechunk/Zarr export failed for {variable}: {exc}")

        store.update_task_status(task_id, "failed" if failed else "completed")
        return 1 if failed else 0


def _output_path(output: Path, filename: str, force_dir: bool) -> Path:
    """决定输出路径：output 带后缀且只有一个文件时当文件名，否则当目录。

    ``force_dir`` 在多文件导出时强制走"目录 + filename"分支，避免多个
    变量挤进同一个文件名。
    """
    if output.suffix and not force_dir:
        return output
    return output / filename


def _progress_context():
    """如果装了 dask，返回一个 ProgressBar 上下文；否则返回空上下文。"""
    try:
        from dask.diagnostics import ProgressBar

        return ProgressBar()
    except Exception:
        return nullcontext()


def _clear_remote_encoding(ds) -> None:
    # Zarr/Icechunk 的 encoding 里含编解码器 / 分块元数据，这些不是合法的
    # NetCDF encoding，保留它们会导致坐标序列化出错，所以写盘前先清空。
    for name in ds.variables:
        ds[name].encoding = {}


def _print_chunk_hint(ds, variable: str) -> None:
    """打印远端分块信息；若空间分块覆盖整张网格，提示小子集仍会读大块。

    这对用户调整 --region 大小有参考意义：Zarr 按块读取，块比子集大时
    会拉入大量无用数据。
    """
    data = ds[variable].data if variable in ds else None
    chunks = getattr(data, "chunks", None)
    if not chunks:
        return
    dims = ds[variable].dims
    chunk_map = {dim: chunks[idx][0] for idx, dim in enumerate(dims) if idx < len(chunks) and chunks[idx]}
    print(f"[{variable}] remote chunks: {chunk_map}", flush=True)
    lat_chunk = chunk_map.get("lat") or chunk_map.get("latitude")
    lon_chunk = chunk_map.get("lon") or chunk_map.get("longitude")
    if lat_chunk == ds.sizes.get("lat") and lon_chunk == ds.sizes.get("lon"):
        print(
            f"[{variable}] note: spatial chunks cover the full grid; small region subsets may still read large remote chunks",
            flush=True,
        )
