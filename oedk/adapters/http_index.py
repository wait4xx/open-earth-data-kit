"""HTTP 目录索引 (http_index) 协议适配器。

很多气象 / 气候数据源就是一个简单的 HTML 目录页 (Apache / Nginx 的
``autoindex``)，里面用 ``<a href="...">`` 列出可下载文件。本适配器抓取
这种页面，用正则提取链接，按扩展名 / 模式 / 数量过滤后产出下载计划。

依赖：仅标准库，无第三方包。
"""

from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request

from oedk.models import DownloadPlan, DownloadRequest, PlannedFile
from .base import Adapter


class HttpIndexAdapter(Adapter):
    """从 HTTP 目录索引页发现文件的适配器。"""

    def plan(self, request: DownloadRequest) -> DownloadPlan:
        """抓取目录页 HTML，提取并过滤 ``<a href>`` 链接，返回下载计划。

        过滤参数优先取命令行 (``request``)，缺省时回退到数据源的 ``defaults``：
        文件扩展名、正则模式、最大文件数。
        """
        extensions = request.file_extensions or request.source.defaults.get("file_extensions", [])
        pattern = request.pattern or request.source.defaults.get("pattern")
        max_files = request.max_files or request.source.defaults.get("max_files")

        endpoint = request.extra.get("endpoint_url") or request.source.endpoint
        html = urllib.request.urlopen(endpoint, timeout=30).read().decode("utf-8", "ignore")
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
        files: list[PlannedFile] = []
        for href in hrefs:
            url = urllib.parse.urljoin(endpoint, href)
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            # 跳过目录链接 (以 / 结尾) 和无意义的当前/上级目录项。
            if not filename or filename in {".", ".."} or url.endswith("/"):
                continue
            if extensions and not any(filename.lower().endswith(ext.lower()) for ext in extensions):
                continue
            if pattern and not re.search(pattern, filename, flags=re.I):
                continue
            files.append(PlannedFile(url=url, filename=filename))
            if max_files and len(files) >= int(max_files):
                break
        return DownloadPlan(request=request, files=files, message=f"discovered {len(files)} files")
