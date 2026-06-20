"""
Config-driven catalog loader.

To onboard a new client dataset:
1. Drop their JSON export into data/
2. Copy config.yaml → config.client.yaml and update source_path + field mapping
3. Set DATA_CONFIG=config.client.yaml — no changes to server.py or tool handlers
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CatalogError(Exception):
    """Raised when catalog config or source data is invalid."""


@dataclass(frozen=True)
class CatalogRecord:
    """Normalized record used by all MCP tools."""

    id: str
    category: str
    tags: list[str]
    metadata: dict[str, Any]


@dataclass
class Catalog:
    record_type: str
    records: list[CatalogRecord]
    records_by_id: dict[str, CatalogRecord] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.records_by_id = {record.id: record for record in self.records}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        raise CatalogError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict) or "catalog" not in config:
        raise CatalogError("Config must contain a top-level 'catalog' section")

    return config["catalog"]


def _normalize_record(raw: dict[str, Any], catalog_cfg: dict[str, Any]) -> CatalogRecord:
    fields = catalog_cfg.get("fields")
    if not isinstance(fields, dict):
        raise CatalogError("catalog.fields must be a mapping")

    id_field = fields.get("id")
    category_field = fields.get("category")
    tags_field = fields.get("tags")

    if not id_field or not category_field or not tags_field:
        raise CatalogError("catalog.fields must define id, category, and tags")

    record_id = raw.get(id_field)
    if not record_id or not isinstance(record_id, str):
        raise CatalogError(f"Record missing string '{id_field}': {raw!r}")

    category = raw.get(category_field, "")
    if not isinstance(category, str):
        category = str(category)

    tags_raw = raw.get(tags_field, [])
    if isinstance(tags_raw, str):
        tags = [tags_raw]
    elif isinstance(tags_raw, list):
        tags = [str(tag) for tag in tags_raw]
    else:
        tags = []

    include_fields = fields.get("include", [])
    metadata: dict[str, Any] = dict(raw)
    if isinstance(include_fields, list):
        for key in include_fields:
            if key in raw:
                metadata[key] = raw[key]

    metadata.setdefault(id_field, record_id)
    metadata.setdefault(category_field, category)
    metadata.setdefault(tags_field, tags)

    return CatalogRecord(
        id=record_id.strip().lower(),
        category=category,
        tags=tags,
        metadata=metadata,
    )


def load_catalog(config_path: Path | None = None) -> Catalog:
    root = _project_root()
    config_file = config_path or Path(
        os.environ.get("DATA_CONFIG", root / "config.yaml")
    )
    if not config_file.is_absolute():
        config_file = root / config_file

    catalog_cfg = _load_yaml_config(config_file)

    source_path = catalog_cfg.get("source_path")
    if not source_path or not isinstance(source_path, str):
        raise CatalogError("catalog.source_path must be a non-empty string")

    data_file = Path(source_path)
    if not data_file.is_absolute():
        data_file = root / data_file

    if not data_file.is_file():
        raise CatalogError(f"Catalog source file not found: {data_file}")

    with data_file.open(encoding="utf-8") as handle:
        raw_records = json.load(handle)

    if not isinstance(raw_records, list):
        raise CatalogError("Catalog source must be a JSON array of records")

    record_type = str(catalog_cfg.get("record_type", "item"))
    records = [_normalize_record(item, catalog_cfg) for item in raw_records]

    return Catalog(record_type=record_type, records=records)
