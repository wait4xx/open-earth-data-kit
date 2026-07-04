"""下载后端 (Backend)。

Backend 负责"把一个 :class:`PlannedFile` 真正落盘"这一最底层动作。
本模块提供两种实现：

- :class:`PythonDownloadBackend` : 纯标准库 ``urllib`` 实现，支持断点续传，
  适合绝大多数可直接 HTTP 拉取的公开数据源。
- :class:`ExternalToolBackend`   : 调用外部下载器 (IDM / XDM) 做下载，
  交给用户本机上更强的多线程下载工具处理。

两者都只处理"物理文件" —— ``metadata["virtual"]`` 的导出型文件由 adapter
自己的 ``execute()`` 方法负责，不经过这里。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .models import PlannedFile


# 下载过程中使用的临时后缀；下载完整后原子重命名为正式文件名。
TEMP_SUFFIX = ".part"


class PythonDownloadBackend:
    """基于标准库 urllib 的下载后端，支持断点续传。"""

    def download(self, item: PlannedFile, output_dir: Path, timeout: int = 60) -> Path:
        """下载单个文件到 ``output_dir``，返回最终落盘路径。

        流程：
        1. 若目标文件已存在且大小达标，视为已完成，直接跳过。
        2. 否则写到 ``<name>.part`` 临时文件；若 ``.part`` 已存在，带上
           ``Range`` 头从断点继续 (``ab`` 追加模式)。
        3. 若服务器无视 Range、回了一个完整的 200 响应，说明续传无意义，
           删掉临时文件从头重来一次 (递归调用自身)。
        4. 成功后用 ``os.replace`` 原子地把 ``.part`` 改名为正式文件名。
        """
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
                # 带上 Range 头请求剩余字节，并以追加模式写入临时文件。
                headers["Range"] = f"bytes={downloaded}-"
                mode = "ab"

        request = urllib.request.Request(item.url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response, temp.open(mode) as fh:
                if mode == "ab" and response.status == 200:
                    # 服务器忽略了 Range，返回的是完整内容 —— 追加会损坏文件，
                    # 因此丢弃已有片段，从头重新下载。
                    fh.close()
                    temp.unlink(missing_ok=True)
                    return self.download(item, output_dir, timeout)
                shutil.copyfileobj(response, fh, length=1024 * 1024)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"download failed: {item.url}: {exc}") from exc

        os.replace(temp, target)
        return target


class ExternalToolBackend:
    """把下载委托给外部下载器 (IDM / XDM) 的后端。

    只做"提交 URL"的动作 (``submit``)，不跟踪下载进度 —— 进度由外部工具
    自己的界面管理。适合 Windows 用户借助 IDM/XDM 获得更好的多线程体验。
    """

    def __init__(self, tool: str, tool_path: str | None = None):
        self.tool = tool.lower()
        self.tool_path = tool_path or self._default_tool_path()

    def _default_tool_path(self) -> str:
        """按工具名和操作系统给出默认可执行路径。"""
        if self.tool == "idm":
            return r"D:\Program Files (x86)\Internet Download Manager\IDMan.exe"
        if self.tool == "xdm":
            return "xdman" if os.name != "nt" else r"C:\Program Files\XDM\xdman.exe"
        raise ValueError(f"unsupported external tool: {self.tool}")

    def submit(self, item: PlannedFile, output_dir: Path) -> None:
        """向外部下载器提交一个 URL，立即返回 (不等待完成)。"""
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

