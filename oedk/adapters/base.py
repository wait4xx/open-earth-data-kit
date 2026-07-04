"""Adapter (适配器) 抽象基类与注册表。

Adapter 是整个 oedk 的核心扩展点：每种数据访问协议对应一个 adapter，
它知道如何"发现文件" (``plan``) 以及 (对导出型协议) "生成文件"
(``execute``)。新增一种数据源时，只要已有协议能表达，就只改目录 JSON；
只有遇到现有协议都覆盖不了的情况，才需要在这里注册一个新 adapter。

``adapter_for(name)`` 是唯一的 adapter 工厂入口，按名字惰性 import 对应
实现类 —— 这样可选依赖 (xarray / icechunk 等) 只在真正用到时才被加载，
保住"零核心运行时依赖"这一设计约束。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from oedk.models import DownloadPlan, DownloadRequest


class Adapter(ABC):
    """所有协议适配器的抽象基类。

    子类必须实现 :meth:`plan`；:meth:`validate_config` 和 :meth:`execute`
    有默认空实现，子类按需覆盖。
    """

    @abstractmethod
    def plan(self, request: DownloadRequest) -> DownloadPlan:
        """根据请求发现/规划要下载的文件，返回一个 :class:`DownloadPlan`。"""
        raise NotImplementedError

    def validate_config(self, request: DownloadRequest) -> list[str]:
        """返回配置/凭据方面的问题列表 (空列表表示没有问题)。

        默认实现总是返回空。需要凭据检查的 adapter (如 manual_auth) 覆盖它。
        """
        return []

    def execute(self, plan: DownloadPlan, store, task_id: int) -> int | None:
        """对"虚拟文件"做实际的导出/生成，返回退出码或 None。

        默认返回 None 表示"本 adapter 不提供导出实现"。导出型 adapter
        (opendap_xarray / icechunk_zarr) 覆盖它。CLI 在下载阶段检测到
        ``metadata["virtual"]`` 时会调用此方法。
        """
        return None


def adapter_for(name: str) -> Adapter:
    """按名字构造对应的 adapter 实例 (惰性导入实现类)。

    ``name`` 通常等于数据源的协议值或其 ``adapter`` 字段。找不到时抛
    ``KeyError``。每个分支里的 import 都是局部的，确保可选依赖只在
    真正选择该协议时才被加载。
    """
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
