"""Canonical JSON and SHA-256 identities for C-008C authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from .errors import ExperimentSerializationError


def _reject_float(value: object, path: str = "payload") -> None:
    if isinstance(value, float):
        raise ExperimentSerializationError(f"{path} must not contain float")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ExperimentSerializationError(
                    f"{path} mapping keys must be strings"
                )
            _reject_float(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            _reject_float(item, f"{path}[{index}]")


def canonical_json(value: object) -> str:
    _reject_float(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentSerializationError(
            "payload is not canonical-JSON serializable"
        ) from exc


def canonical_json_bytes(value: object) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def semantic_id(prefix: str, payload: Mapping[str, object]) -> str:
    if not isinstance(prefix, str) or not prefix:
        raise ExperimentSerializationError(
            "identity prefix must be non-empty"
        )
    return f"{prefix}{digest(payload)}"


def require_semantic_id(
    value: object,
    *,
    prefix: str,
    payload: Mapping[str, object],
    field_name: str,
    error_type: type[ValueError],
) -> str:
    if not isinstance(value, str) or not value:
        raise error_type(f"{field_name} must be non-empty text")
    if value != semantic_id(prefix, payload):
        raise error_type(f"{field_name} does not match canonical payload")
    return value
