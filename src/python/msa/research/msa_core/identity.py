"""Deterministic identities for C-007D integration objects."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def canonical_json(value: object) -> str:
    """Return compact, stable JSON for already-serialized contract payloads."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def semantic_id(prefix: str, payload: Mapping[str, object]) -> str:
    return f"{prefix}{digest(payload)}"


def require_semantic_id(
    value: object,
    *,
    prefix: str,
    payload: Mapping[str, object],
    field_name: str,
    error_type: type[Exception],
) -> str:
    expected = semantic_id(prefix, payload)
    if not isinstance(value, str) or value != expected:
        raise error_type(f"{field_name} must equal its deterministic identity")
    return value
