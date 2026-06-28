from __future__ import annotations

from abc import ABC, abstractmethod

from oedk.models import DownloadPlan, DownloadRequest


class Adapter(ABC):
    @abstractmethod
    def plan(self, request: DownloadRequest) -> DownloadPlan:
        raise NotImplementedError

    def validate_config(self, request: DownloadRequest) -> list[str]:
        return []

    def execute(self, plan: DownloadPlan, store, task_id: int) -> int | None:
        return None


def adapter_for(name: str) -> Adapter:
    if name == "http_index":
        from .http_index import HttpIndexAdapter

        return HttpIndexAdapter()
    if name == "s3_xml":
        from .s3_xml import S3XmlAdapter

        return S3XmlAdapter()
    if name == "opendap_xarray":
        from .opendap_xarray import OpendapXarrayAdapter

        return OpendapXarrayAdapter()
    if name == "icechunk_zarr":
        from .icechunk_zarr import IcechunkZarrAdapter

        return IcechunkZarrAdapter()
    if name == "manual_auth":
        from .manual_auth import ManualAuthAdapter

        return ManualAuthAdapter()
    raise KeyError(f"unknown adapter: {name}")
