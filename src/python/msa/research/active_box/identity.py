"""Canonical JSON and SHA-256 identities for C-007C contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def semantic_id(prefix: str, payload: Mapping[str, object]) -> str:
    return f"{prefix}{digest(payload)}"


def require_semantic_id(
    value: object,
    prefix: str,
    payload: Mapping[str, object],
    field_name: str,
    error_type: type[Exception],
) -> str:
    if not isinstance(value, str):
        raise error_type(f"{field_name} must be a string")
    expected = semantic_id(prefix, payload)
    if value != expected:
        raise error_type(f"{field_name} does not match exact semantic payload")
    return value
