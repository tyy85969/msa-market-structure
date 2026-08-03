"""Bounded deterministic recursive payload comparison."""

from __future__ import annotations

import json

from ...identity import canonical_json_bytes, digest, semantic_id
from .contracts import DifferenceKind, PayloadDifference


_MISSING = object()


def _pointer(path: str, token: object) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped}"


def _typename(value: object) -> str:
    return "missing" if value is _MISSING else type(value).__name__


def _safe(value: object) -> object:
    return "<missing>" if value is _MISSING else value


def _representation(value: object) -> str:
    if value is _MISSING:
        return "<missing>"
    try:
        text = canonical_json_bytes(value).decode("utf-8").rstrip("\n")
    except (TypeError, ValueError):
        text = json.dumps(str(value), ensure_ascii=False)
    return text if len(text) <= 256 else text[:253] + "..."


def _difference(path: str, kind: DifferenceKind, left: object, right: object) -> PayloadDifference:
    kwargs = {
        "path": path or "/",
        "difference_kind": kind,
        "left_type": _typename(left),
        "right_type": _typename(right),
        "left_value": _representation(left),
        "right_value": _representation(right),
        "left_subtree_digest": digest(_safe(left)),
        "right_subtree_digest": digest(_safe(right)),
        "schema_version": 1,
    }
    payload = {
        **kwargs,
        "difference_kind": kind.value,
    }
    return PayloadDifference(
        payload_difference_id=semantic_id(PayloadDifference._PREFIX, payload), **kwargs
    )


def payload_differences(
    left: object, right: object, *, max_stored: int = 20
) -> tuple[int, tuple[PayloadDifference, ...]]:
    """Return total count and the first bounded differences in stable order."""

    found: list[PayloadDifference] = []
    total = 0

    def add(path: str, kind: DifferenceKind, a: object, b: object) -> None:
        nonlocal total
        total += 1
        if len(found) < max_stored:
            found.append(_difference(path, kind, a, b))

    def walk(a: object, b: object, path: str) -> None:
        if type(a) is not type(b):
            add(path, DifferenceKind.TYPE, a, b)
            return
        if isinstance(a, dict):
            for key in a:
                if key not in b:
                    add(_pointer(path, key), DifferenceKind.MISSING, a[key], _MISSING)
                else:
                    walk(a[key], b[key], _pointer(path, key))
            for key in b:
                if key not in a:
                    add(_pointer(path, key), DifferenceKind.EXTRA, _MISSING, b[key])
            return
        if isinstance(a, list):
            if len(a) == len(b) and a != b:
                try:
                    if sorted(canonical_json_bytes(item) for item in a) == sorted(
                        canonical_json_bytes(item) for item in b
                    ):
                        add(path, DifferenceKind.ORDER, a, b)
                except TypeError:
                    pass
            for index in range(max(len(a), len(b))):
                if index >= len(a):
                    add(_pointer(path, index), DifferenceKind.EXTRA, _MISSING, b[index])
                elif index >= len(b):
                    add(_pointer(path, index), DifferenceKind.MISSING, a[index], _MISSING)
                else:
                    walk(a[index], b[index], _pointer(path, index))
            return
        if a != b:
            add(path, DifferenceKind.VALUE, a, b)

    walk(left, right, "")
    return total, tuple(found)


__all__ = ["payload_differences"]
