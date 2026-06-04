"""Persistence for column mappings.

A mapping is ``{canonical_key: source_header}``.  We auto-derive one from the
incoming headers (``schema.auto_map``) and let the user override + save named
mappings to ``column_mappings.json`` in the user-data directory so future files
with the same schema load with zero clicks.
"""
from __future__ import annotations

import json
from typing import Optional

from .. import config
from . import schema


def load_saved_mappings() -> dict[str, dict]:
    if config.MAPPINGS_FILE.exists():
        try:
            return json.loads(config.MAPPINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_mapping(name: str, mapping: dict[str, Optional[str]]) -> None:
    config.ensure_user_dirs()
    data = load_saved_mappings()
    data[name] = {k: v for k, v in mapping.items() if v}
    config.MAPPINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def delete_mapping(name: str) -> None:
    data = load_saved_mappings()
    if name in data:
        del data[name]
        config.MAPPINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve_mapping(headers: list[str], saved: Optional[dict] = None) -> dict[str, Optional[str]]:
    """Pick the best mapping for a set of headers.

    If a saved mapping's source columns are all present, use it; otherwise fall
    back to auto-mapping.  Auto-map fills any gaps a partial saved mapping leaves.
    """
    auto = schema.auto_map(headers)
    if saved:
        header_set = set(headers)
        merged = dict(auto)
        for key, src in saved.items():
            if src in header_set:
                merged[key] = src
        return merged
    return auto


def mapping_coverage(mapping: dict[str, Optional[str]]) -> dict:
    """Summarise how complete a mapping is."""
    mapped = {k: v for k, v in mapping.items() if v}
    missing_required = [k for k in schema.REQUIRED_KEYS if not mapping.get(k)]
    return {
        "mapped": len(mapped),
        "total": len(schema.CANONICAL_FIELDS),
        "missing_required": missing_required,
        "ok": not missing_required,
    }
