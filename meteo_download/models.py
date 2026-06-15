from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SupportLevel(StrEnum):
    DOWNLOADABLE = "downloadable"
    AUTH_REQUIRED = "auth_required"
    MANUAL = "manual"


class Protocol(StrEnum):
    HTTP_INDEX = "http_index"
    S3_XML = "s3_xml"
    OPENDAP_XARRAY = "opendap_xarray"
    ICECHUNK_ZARR = "icechunk_zarr"
    MANUAL_AUTH = "manual_auth"


@dataclass(frozen=True)
class DataSource:
    id: str
    name: str
    category: str
    provider: str
    protocol: Protocol
    support_level: SupportLevel
    endpoint: str
    formats: list[str] = field(default_factory=list)
    required_credentials: list[str] = field(default_factory=list)
    adapter: str = ""
    update_frequency: str = ""
    coverage: str = ""
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DataSource":
        required = ["id", "name", "category", "provider", "protocol", "support_level", "endpoint"]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise ValueError(f"missing required fields {missing}: {raw!r}")
        protocol = Protocol(raw["protocol"])
        adapter = raw.get("adapter") or protocol.value
        return cls(
            id=str(raw["id"]),
            name=str(raw["name"]),
            category=str(raw["category"]),
            provider=str(raw["provider"]),
            protocol=protocol,
            support_level=SupportLevel(raw["support_level"]),
            endpoint=str(raw["endpoint"]),
            formats=list(raw.get("formats") or []),
            required_credentials=list(raw.get("required_credentials") or []),
            adapter=str(adapter),
            update_frequency=str(raw.get("update_frequency") or ""),
            coverage=str(raw.get("coverage") or ""),
            notes=str(raw.get("notes") or ""),
            tags=list(raw.get("tags") or []),
            defaults=dict(raw.get("defaults") or {}),
        )


@dataclass(frozen=True)
class DownloadRequest:
    source: DataSource
    variables: list[str] = field(default_factory=list)
    time_range: tuple[str, str] | None = None
    region: tuple[float, float, float, float] | None = None
    output: Path = Path(".")
    file_extensions: list[str] = field(default_factory=list)
    pattern: str | None = None
    max_files: int | None = None
    backend: str = "python"
    tool: str | None = None
    tool_path: str | None = None
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannedFile:
    url: str
    filename: str
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DownloadPlan:
    request: DownloadRequest
    files: list[PlannedFile]
    message: str = ""

