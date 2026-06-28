from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .models import PlannedFile


TEMP_SUFFIX = ".part"


class PythonDownloadBackend:
    def download(self, item: PlannedFile, output_dir: Path, timeout: int = 60) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / item.filename
        temp = target.with_suffix(target.suffix + TEMP_SUFFIX)
        if target.exists() and item.size_bytes and target.stat().st_size >= item.size_bytes:
            return target

        headers: dict[str, str] = {}
        mode = "wb"
        if temp.exists():
            downloaded = temp.stat().st_size
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"
                mode = "ab"

        request = urllib.request.Request(item.url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response, temp.open(mode + "") as fh:
                if mode == "ab" and response.status == 200:
                    fh.close()
                    temp.unlink(missing_ok=True)
                    return self.download(item, output_dir, timeout)
                shutil.copyfileobj(response, fh, length=1024 * 1024)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"download failed: {item.url}: {exc}") from exc

        os.replace(temp, target)
        return target


class ExternalToolBackend:
    def __init__(self, tool: str, tool_path: str | None = None):
        self.tool = tool.lower()
        self.tool_path = tool_path or self._default_tool_path()

    def _default_tool_path(self) -> str:
        if self.tool == "idm":
            return r"D:\Program Files (x86)\Internet Download Manager\IDMan.exe"
        if self.tool == "xdm":
            return "xdman" if os.name != "nt" else r"C:\Program Files\XDM\xdman.exe"
        raise ValueError(f"unsupported external tool: {self.tool}")

    def submit(self, item: PlannedFile, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.tool == "idm":
            cmd = [self.tool_path, "/n", "/d", item.url, "/p", str(output_dir.resolve()), "/f", item.filename]
        else:
            cmd = [
                self.tool_path,
                "--add-url",
                item.url,
                "--save-path",
                str((output_dir / item.filename).resolve()),
                "--quiet",
            ]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

