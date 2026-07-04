"""目录 (catalog) 加载与校验。

"目录" 是 ``catalog/`` 下的一组 JSON / YAML 文件，每个文件描述若干条
数据源。本模块负责把它们读进来、转成 :class:`DataSource`，并对外提供
按 id 查找、整体校验两个能力。

校验规则见 :func:`validate_sources`，CLI 的 ``oedk catalog validate``
和测试套件都依赖它。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DataSource


# 目录目录默认在仓库根的 catalog/ 下（与本模块同级再上一级）。
CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"


def _load_yaml(path: Path) -> Any:
    """惰性加载 PyYAML 来读 YAML 目录文件。

    PyYAML 是可选依赖 (``pip install -e ".[yaml]"``)，没有安装时这里会
    抛出带安装提示的 RuntimeError，而不是在 import 期就崩掉。
    """
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(f"YAML catalog requires PyYAML: {path}") from exc
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_file(path: Path) -> Any:
    """按扩展名分派到 JSON 或 YAML 解析器。"""
    if path.suffix == ".json":
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    if path.suffix in {".yaml", ".yml"}:
        return _load_yaml(path)
    raise ValueError(f"unsupported catalog file: {path}")


def load_sources(catalog_dir: Path = CATALOG_DIR) -> list[DataSource]:
    """加载目录目录下所有 ``.json`` / ``.yaml`` / ``.yml`` 文件中的数据源。

    文件按文件名排序加载，保证结果稳定。每个文件既可以是 ``{"sources": [...]}``
    形式，也可以直接是一个列表，两种都兼容。
    """
    sources: list[DataSource] = []
    for path in sorted(catalog_dir.glob("*")):
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        raw = _load_file(path)
        entries = raw.get("sources", raw) if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            raise ValueError(f"catalog file must contain a list or sources list: {path}")
        sources.extend(DataSource.from_dict(item) for item in entries)
    return sources


def validate_sources(sources: list[DataSource]) -> list[str]:
    """对已加载的数据源做一致性校验，返回错误信息列表 (空表示通过)。

    校验三条规则：
    1. id 必须唯一 —— 重复 id 会让 ``find_source`` 产生歧义。
    2. ``downloadable`` 数据源不应要求凭据 —— 既然能自动下载，就不该再
       依赖人工凭据，二者同时出现说明目录配置自相矛盾。
    3. adapter 必须是已注册的名字 —— 否则下载时 ``adapter_for()`` 会抛
       KeyError，不如在校验阶段就发现。惰性 import 避免模块级耦合。
    """
    from .adapters import adapter_for  # 惰性 import，避免 catalog ↔ adapters 循环依赖

    errors: list[str] = []
    seen: set[str] = set()
    for src in sources:
        if src.id in seen:
            errors.append(f"duplicate source id: {src.id}")
        seen.add(src.id)
        if src.required_credentials and src.support_level.value == "downloadable":
            errors.append(f"{src.id}: downloadable source should not require credentials")
        try:
            adapter_for(src.adapter)
        except KeyError:
            errors.append(f"{src.id}: unknown adapter '{src.adapter}'")
    return errors


def find_source(source_id: str, catalog_dir: Path = CATALOG_DIR) -> DataSource:
    """按 id 查找单条数据源，找不到则抛 ``KeyError``。"""
    for source in load_sources(catalog_dir):
        if source.id == source_id:
            return source
    raise KeyError(f"unknown source id: {source_id}")

