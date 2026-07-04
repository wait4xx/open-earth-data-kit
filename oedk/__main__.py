"""``python -m oedk`` 的入口。

直接转发到 :func:`oedk.cli.main`，方便不通过 console_script ``oedk``
而用模块方式运行 (例如开发期 ``python -m oedk ...``)。
"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
