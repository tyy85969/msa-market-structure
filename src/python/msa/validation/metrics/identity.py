"""Deterministic identity and Decimal helpers for C-008B."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .errors import MetricSerializationError


DECIMAL_PRECISION = 34


def _reject_float(value: object, path: str = "payload") -> None:
    if isinstance(value, float):
        raise MetricSerializationError(f"{path} must not contain float")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise MetricSerializationError(
                    f"{path} mapping keys must be strings"
                )
            _reject_float(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            _reject_float(item, f"{path}[{index}]")


def canonical_json(value: object) -> str:
    """Return compact, key-sorted JSON after rejecting floating point."""

    _reject_float(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise MetricSerializationError(
            "payload is not canonical-JSON serializable"
        ) from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def semantic_id(prefix: str, payload: Mapping[str, object]) -> str:
    if not isinstance(prefix, str) or not prefix:
        raise MetricSerializationError("identity prefix must be non-empty")
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
        raise error_type(f"{field_name} must be a non-empty string")
    if value != semantic_id(prefix, payload):
        raise error_type(f"{field_name} does not match its canonical payload")
    return value


def decimal_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Divide under the frozen C-008B Decimal context."""

    if (
        not isinstance(numerator, Decimal)
        or not isinstance(denominator, Decimal)
        or not numerator.is_finite()
        or not denominator.is_finite()
        or denominator == 0
    ):
        raise MetricSerializationError(
            "decimal division requires finite Decimal values and non-zero denominator"
        )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        return +(numerator / denominator)


def decimal_mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise MetricSerializationError("decimal mean requires at least one value")
    if any(
        not isinstance(item, Decimal) or not item.is_finite()
        for item in values
    ):
        raise MetricSerializationError(
            "decimal mean requires finite Decimal values"
        )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        total = sum(values, Decimal("0"))
        return +(total / Decimal(len(values)))


def decimal_wilder(
    previous_atr: Decimal, current_true_range: Decimal, period: int
) -> Decimal:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise MetricSerializationError("ATR period must be a positive integer")
    if (
        not isinstance(previous_atr, Decimal)
        or not isinstance(current_true_range, Decimal)
        or not previous_atr.is_finite()
        or not current_true_range.is_finite()
    ):
        raise MetricSerializationError(
            "Wilder ATR requires finite Decimal values"
        )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        return +(
            (
                previous_atr * Decimal(period - 1)
                + current_true_range
            )
            / Decimal(period)
        )
