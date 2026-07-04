"""S3 兼容存储 (s3_xml) 协议适配器。

面向公开的 S3 / S3 兼容桶 (如 NOAA Open Data、Planette 等)。通过
ListObjectsV2 REST 接口列出对象，解析返回的 XML，按前缀 / 扩展名 / 模式
过滤后产出下载计划。

注意：本适配器只做"匿名列举 + 下载"，不处理签名鉴权 —— 需要凭据的桶
应走 manual_auth 或专用脚本。

依赖：仅标准库 (urllib + xml.etree)，无第三方包。
"""

from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from oedk.models import DownloadPlan, DownloadRequest, PlannedFile
from .base import Adapter


class S3XmlAdapter(Adapter):
    """通过 ListObjectsV2 XML 列举 S3 / 兼容存储对象的适配器。"""

    def plan(self, request: DownloadRequest) -> DownloadPlan:
        """向桶发送 ListObjectsV2 请求，解析 XML 结果并过滤。"""
        endpoint = request.extra.get("endpoint_url") or request.source.endpoint
        parsed = urllib.parse.urlparse(endpoint)
        bucket_base = f"{parsed.scheme}://{parsed.netloc}"
        # 前缀优先级：命令行 > 数据源 defaults > endpoint 路径部分。
        prefix = request.extra.get("prefix") or request.source.defaults.get("prefix") or parsed.path.lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix, "max-keys": request.max_files or 1000})
        api_url = f"{bucket_base}/?{query}"
        root = ET.fromstring(urllib.request.urlopen(api_url, timeout=30).read())
        # S3 列举 XML 带命名空间；同时兼容不带命名空间的实现。
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        files: list[PlannedFile] = []
        extensions = request.file_extensions or request.source.defaults.get("file_extensions", [])
        pattern = request.pattern or request.source.defaults.get("pattern")
        contents = root.findall(".//s3:Contents", ns) or root.findall(".//Contents")
        for item in contents:
            key = item.findtext("s3:Key", default="", namespaces=ns) or item.findtext("Key", default="")
            size_text = item.findtext("s3:Size", default="0", namespaces=ns) or item.findtext("Size", default="0")
            filename = os.path.basename(key)
            # 以 / 结尾的 key 是"目录占位符"，不是真实文件。
            if not filename or filename.endswith("/"):
                continue
            if extensions and not any(filename.lower().endswith(ext.lower()) for ext in extensions):
                continue
            if pattern and not re.search(pattern, filename, flags=re.I):
                continue
            files.append(PlannedFile(url=f"{bucket_base}/{key}", filename=filename, size_bytes=int(size_text or 0)))
        return DownloadPlan(request=request, files=files, message=f"discovered {len(files)} files")
