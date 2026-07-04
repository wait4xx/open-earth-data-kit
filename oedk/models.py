"""核心数据模型。

本模块定义了贯穿整个 oedk 数据流的几个不可变值对象。所有层
(CLI → Catalog → Adapter → Backend → State) 都围绕这些类型交互：

- ``DataSource``        : 目录中的一条数据源元数据
- ``DownloadRequest``   : 用户发起的一次下载意图 (命令行参数解析后产出)
- ``PlannedFile``       : 计划中要下载/导出的一个目标文件
- ``DownloadPlan``      : Adapter 对一次请求规划出的文件清单

这些 dataclass 全部 ``frozen=True``，保证一旦构造完成就不会被无意修改，
适合在多层之间安全传递。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SupportLevel(StrEnum):
    """数据源的支持等级，决定 oedk 能做到哪一步。

    - ``DOWNLOADABLE`` : 可直接由后端自动下载
    - ``AUTH_REQUIRED``: 需要凭据/账号，oedk 只做规划与提示
    - ``MANUAL``       : 结构未标准化，仅做登记，需人工处理
    """

    DOWNLOADABLE = "downloadable"
    AUTH_REQUIRED = "auth_required"
    MANUAL = "manual"


class Protocol(StrEnum):
    """数据源的访问协议 / 适配器映射键。

    ``Protocol`` 的值同时也是默认的 adapter 名字 —— 当目录条目没有显式
    指定 ``adapter`` 字段时，``DataSource.from_dict`` 会用协议值充当
    adapter 名字去 ``adapter_for()`` 里查找。
    """

    HTTP_INDEX = "http_index"
    S3_XML = "s3_xml"
    OPENDAP_XARRAY = "opendap_xarray"
    ICECHUNK_ZARR = "icechunk_zarr"
    MANUAL_AUTH = "manual_auth"


@dataclass(frozen=True)
class DataSource:
    """目录中的一条数据源描述。

    与 ``catalog/sources.json`` 中的条目一一对应。``defaults`` 字段允许
    数据源为 adapter 预置默认参数 (如默认文件扩展名、前缀、最大文件数)，
    用户未在命令行覆盖时由 adapter 自行读取。
    """

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
        """从目录 JSON 的一条原始字典构造实例。

        会校验必填字段，并把字符串协议/支持等级转成对应的枚举。
        ``adapter`` 缺省时取协议值，保证后续 ``adapter_for()`` 总能拿到
        一个非空名字。
        """
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
    """一次下载请求的所有参数。

    由 CLI 层根据用户命令行参数组装。``extra`` 字典承载协议相关的可选
    参数 (prefix / endpoint_url / format / frequency / grid / workers)，
    避免在 dataclass 里为每种协议都开一堆字段。
    """

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
    """计划中的一个目标文件。

    ``metadata["virtual"]`` 为真时，表示这不是一个可以直接 HTTP/S3 拉取
    的物理文件，而是需要由 adapter 的 ``execute()`` 方法现场导出 (例如
    OPeNDAP 子集导出 NetCDF、Icechunk/Zarr 切片)。CLI 层据此分流。
    """

    url: str
    filename: str
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DownloadPlan:
    """Adapter 对一次请求给出的规划结果。

    ``message`` 是给用户看的简短说明，``files`` 是具体要下载/导出的清单。
    """

    request: DownloadRequest
    files: list[PlannedFile]
    message: str = ""
