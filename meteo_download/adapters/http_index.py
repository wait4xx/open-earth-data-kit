from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request

from meteo_download.models import DownloadPlan, DownloadRequest, PlannedFile
from .base import Adapter


class HttpIndexAdapter(Adapter):
    def plan(self, request: DownloadRequest) -> DownloadPlan:
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
