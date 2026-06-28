from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

from oedk.models import DownloadPlan, DownloadRequest, PlannedFile
from .base import Adapter


class IcechunkZarrAdapter(Adapter):
    def plan(self, request: DownloadRequest) -> DownloadPlan:
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
                zarr_path = f"era5/{variable}/{frequency}/{grid}/era5_{variable}_{frequency}_{grid}.zarr"
                storage = ic.s3_storage(
                    bucket="planette-era5",
                    prefix=zarr_path,
                    region="us-east-2",
                    anonymous=True,
                )
                repo = ic.Repository.open(storage=storage, config=config)
                session = repo.readonly_session(branch="main")
                ds = xr.open_dataset(session.store, engine="zarr", consolidated=False, chunks={})
                print(f"[{variable}] remote dims: {dict(ds.sizes)}", flush=True)
                _print_chunk_hint(ds, variable)
                if request.time_range:
                    print(f"[{variable}] selecting time {request.time_range[0]} to {request.time_range[1]}", flush=True)
                    ds = ds.sel(time=slice(request.time_range[0], request.time_range[1]))
                ds = _subset_region(ds, request.region)
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
    if output.suffix and not force_dir:
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


def _progress_context():
    try:
        from dask.diagnostics import ProgressBar

        return ProgressBar()
    except Exception:
        return nullcontext()


def _clear_remote_encoding(ds) -> None:
    # Zarr/Icechunk encodings include codecs/chunk metadata that are not valid
    # NetCDF encodings and can corrupt coordinate serialization.
    for name in ds.variables:
        ds[name].encoding = {}


def _print_chunk_hint(ds, variable: str) -> None:
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
