from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from oedk.models import DownloadPlan, DownloadRequest, PlannedFile
from .base import Adapter


class S3XmlAdapter(Adapter):
    def plan(self, request: DownloadRequest) -> DownloadPlan:
        endpoint = request.extra.get("endpoint_url") or request.source.endpoint
        parsed = urllib.parse.urlparse(endpoint)
        bucket_base = f"{parsed.scheme}://{parsed.netloc}"
        prefix = request.extra.get("prefix") or request.source.defaults.get("prefix") or parsed.path.lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix, "max-keys": request.max_files or 1000})
        api_url = f"{bucket_base}/?{query}"
        root = ET.fromstring(urllib.request.urlopen(api_url, timeout=30).read())
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        files: list[PlannedFile] = []
        extensions = request.file_extensions or request.source.defaults.get("file_extensions", [])
        pattern = request.pattern or request.source.defaults.get("pattern")
        contents = root.findall(".//s3:Contents", ns) or root.findall(".//Contents")
        for item in contents:
            key = item.findtext("s3:Key", default="", namespaces=ns) or item.findtext("Key", default="")
            size_text = item.findtext("s3:Size", default="0", namespaces=ns) or item.findtext("Size", default="0")
            filename = os.path.basename(key)
            if not filename or filename.endswith("/"):
                continue
            if extensions and not any(filename.lower().endswith(ext.lower()) for ext in extensions):
                continue
            if pattern and not re.search(pattern, filename, flags=re.I):
                continue
            files.append(PlannedFile(url=f"{bucket_base}/{key}", filename=filename, size_bytes=int(size_text or 0)))
        return DownloadPlan(request=request, files=files, message=f"discovered {len(files)} files")
