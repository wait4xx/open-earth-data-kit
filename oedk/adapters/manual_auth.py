"""人工 / 需凭据 (manual_auth) 协议适配器。

这类数据源 (如 CDS、Earthdata) 需要账号 / API Key，且下载流程各异、
暂未抽象成统一自动化路径。本适配器不真正下载，只做两件事：

1. ``validate_config`` : 检查所需的环境变量凭据是否已设置。
2. ``plan``            : 产出一个空计划 + 提示信息，告诉用户这是人工源、
   还缺哪些凭据。

它起到"登记 + 提示"的作用，保证这类源在 ``oedk list`` / ``oedk info``
里可见、可被 ``doctor`` 检查，而不需要为每个源写独立脚本。
"""

from __future__ import annotations

import os

from oedk.models import DownloadPlan, DownloadRequest
from .base import Adapter


class ManualAuthAdapter(Adapter):
    """不执行下载、只登记凭据要求的占位适配器。"""

    def validate_config(self, request: DownloadRequest) -> list[str]:
        """检查数据源声明的凭据环境变量是否都已设置，返回缺失项列表。"""
        missing = [name for name in request.source.required_credentials if not os.getenv(name)]
        return [f"missing environment variable: {name}" for name in missing]

    def plan(self, request: DownloadRequest) -> DownloadPlan:
        """返回空文件清单的计划，message 里附带凭据检查结果。"""
        errors = self.validate_config(request)
        message = "manual or authenticated source"
        if errors:
            message += "; " + "; ".join(errors)
        return DownloadPlan(request=request, files=[], message=message)
