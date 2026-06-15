from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DataSource


CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog"


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(f"YAML catalog requires PyYAML: {path}") from exc
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_file(path: Path) -> Any:
    if path.suffix == ".json":
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    if path.suffix in {".yaml", ".yml"}:
        return _load_yaml(path)
    raise ValueError(f"unsupported catalog file: {path}")


def load_sources(catalog_dir: Path = CATALOG_DIR) -> list[DataSource]:
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
    errors: list[str] = []
    seen: set[str] = set()
    for src in sources:
        if src.id in seen:
            errors.append(f"duplicate source id: {src.id}")
        seen.add(src.id)
        if src.required_credentials and src.support_level.value == "downloadable":
            errors.append(f"{src.id}: downloadable source should not require credentials")
        if src.adapter != src.protocol.value and not src.adapter:
            errors.append(f"{src.id}: adapter is empty")
    return errors


def find_source(source_id: str, catalog_dir: Path = CATALOG_DIR) -> DataSource:
    for source in load_sources(catalog_dir):
        if source.id == source_id:
            return source
    raise KeyError(f"unknown source id: {source_id}")

