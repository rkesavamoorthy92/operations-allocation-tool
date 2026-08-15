"""Stable JSON serialization used for immutable evidence hashes."""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType
from typing import Any

CANONICAL_JSON_VERSION = "canonical-json-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_for(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def deep_freeze(value: Any) -> Any:
    """Return a recursively immutable representation of JSON-like data."""
    if isinstance(value, dict):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value


def deep_thaw(value: Any) -> Any:
    """Convert an immutable JSON-like representation back to plain containers."""
    if isinstance(value, MappingProxyType) or isinstance(value, dict):
        return {key: deep_thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [deep_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return [deep_thaw(item) for item in value]
    return value
