from __future__ import annotations

from pathlib import Path

from meteo_download.models import DownloadPlan, DownloadRequest, PlannedFile
from .base import Adapter


class OpendapXarrayAdapter(Adapter):
    def plan(self, request: DownloadRequest) -> DownloadPlan:
        output_name = request.extra.get("filename") or f"{request.source.id}.nc"
        return DownloadPlan(
            request=request,
            files=[PlannedFile(url=request.source.endpoint, filename=output_name, metadata={"virtual": True})],
            message="OPeNDAP plans are exported through xarray during download implementation.",
        )

    def execute(self, plan: DownloadPlan, store, task_id: int) -> int:
        try:
            import xarray as xr
        except ImportError as exc:
            store.update_task_status(task_id, "failed")
            print("xarray is required for OPeNDAP export. Install with: pip install -e '.[opendap]'")
            return 2

        request = plan.request
        dataset_url = request.extra.get("endpoint_url") or request.source.endpoint
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
            ds = _subset_region(ds, request.region)
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
    if output.suffix:
        return output
    return output / filename


def _subset_region(ds, region):
    if not region:
        return ds
    lon_min, lon_max, lat_min, lat_max = region
    lon_name = "lon" if "lon" in ds.coords else "longitude" if "longitude" in ds.coords else None
    lat_name = "lat" if "lat" in ds.coords else "latitude" if "latitude" in ds.coords else None
    if lon_name:
        ds = ds.sel({lon_name: slice(lon_min, lon_max)})
    if lat_name:
        values = ds[lat_name].values
        if len(values) >= 2 and values[0] > values[-1]:
            ds = ds.sel({lat_name: slice(lat_max, lat_min)})
        else:
            ds = ds.sel({lat_name: slice(lat_min, lat_max)})
    return ds
