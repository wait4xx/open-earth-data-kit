"""OPeNDAP + xarray (opendap_xarray) 协议适配器。

OPeNDAP 是一种"远程数据子集化"协议：客户端可以只请求感兴趣的时间段 /
变量 / 区域，服务端只返回这一片数据。因此它不是"下载现成文件"，而是
"按需导出"。

本适配器遵循 oedk 的"虚拟文件"约定：``plan`` 阶段产出一个带
``metadata["virtual"]`` 的占位文件，真正的导出在 ``execute`` 里完成。
``execute`` 用 xarray 打开远程 OPeNDAP 数据集，做变量 / 时间 / 区域切片
后 ``load().to_netcdf()`` 落盘。

依赖：xarray + netCDF4 (可选 extra ``pip install -e ".[opendap]"``)，
惰性导入。
"""

from __future__ import annotations

from pathlib import Path

from oedk.models import DownloadPlan, DownloadRequest, PlannedFile
from oedk.geo import subset_region
from .base import Adapter


class OpendapXarrayAdapter(Adapter):
    """通过 xarray 从 OPeNDAP 端点导出子集的适配器。"""

    def plan(self, request: DownloadRequest) -> DownloadPlan:
        """产出一个"虚拟"输出文件 (真正导出在 :meth:`execute` 完成)。"""
        output_name = request.extra.get("filename") or f"{request.source.id}.nc"
        return DownloadPlan(
            request=request,
            files=[PlannedFile(url=request.source.endpoint, filename=output_name, metadata={"virtual": True})],
            message="OPeNDAP plans are exported through xarray during download implementation.",
        )

    def execute(self, plan: DownloadPlan, store, task_id: int) -> int:
        """真正执行 OPeNDAP 子集导出。

        流程：惰性导入 xarray → 校验 endpoint 是具体数据集而非目录 → 按
        变量 / 时间 / 区域切片 → 加载并写 NetCDF → 更新状态库。
        任一步抛异常则记为失败并返回 1。
        """
        try:
            import xarray as xr
        except ImportError as exc:
            store.update_task_status(task_id, "failed")
            print("xarray is required for OPeNDAP export. Install with: pip install -e '.[opendap]'")
            return 2

        request = plan.request
        dataset_url = request.extra.get("endpoint_url") or request.source.endpoint
        # GFS NOMADS 的这些 endpoint 是"目录"而非具体数据集，无法直接
        # open_dataset，需要用户用 --endpoint-url 指到具体某条数据集。
        if dataset_url.rstrip("/").endswith(("gfs_0p25", "gfs_0p25_1hr", "gfs_0p50", "gfs_1p00")):
            store.update_task_status(task_id, "blocked")
            print("OPeNDAP export requires a concrete dataset URL. Pass it with --endpoint-url.")
            return 2

        output = _output_path(request.output, plan.files[0].filename)
        output.parent.mkdir(parents=True, exist_ok=True)
        item = plan.files[0]
        try:
            ds = xr.open_dataset(dataset_url)
            if request.variables:
                ds = ds[request.variables]
            if request.time_range and "time" in ds.coords:
                ds = ds.sel(time=slice(request.time_range[0], request.time_range[1]))
            ds = subset_region(ds, request.region)
            # load() 把切片后的数据真正拉到本地内存，再一次性写盘。
            ds.load().to_netcdf(output)
            ds.close()
            store.update_file_status(task_id, item.url, "completed")
            store.update_task_status(task_id, "completed")
            print(f"completed task {task_id}: {output}")
            return 0
        except Exception as exc:
            store.update_file_status(task_id, item.url, "failed", str(exc))
            store.update_task_status(task_id, "failed")
            print(f"OPeNDAP export failed: {exc}")
            return 1


def _output_path(output: Path, filename: str) -> Path:
    """若 output 自带后缀就直接当作目标文件名，否则视为目录拼上 filename。"""
    if output.suffix:
        return output
    return output / filename
