"""下载后端测试。"""

import pytest

from oedk.backends import ExternalToolBackend
from oedk.models import PlannedFile


def test_external_tool_submit_fails_clearly_when_tool_missing(tmp_path):
    """工具可执行文件不存在时应抛带清晰提示的 FileNotFoundError。

    不做检查时 Popen 会抛晦涩的 ``[Errno 2] No such file or directory``；
    P5 在 submit 前用 shutil.which 探测，给出带工具名和安装提示的可操作错误。
    """
    backend = ExternalToolBackend("xdm", tool_path="/nonexistent/xdman")
    item = PlannedFile(url="https://example.com/f.bin", filename="f.bin")

    with pytest.raises(FileNotFoundError, match="external tool"):
        backend.submit(item, tmp_path)
