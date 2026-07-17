"""Immutable primitive values and strict serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, TypeVar

from .errors import DomainSerializationError, DomainValidationError


SCHEMA_VERSION = 1
EnumT = TypeVar("EnumT", bound=Enum)


def _field(object_name: str, field_name: str) -> str:
    return f"{object_name}.{field_name}"


def _require_non_empty_text(
    object_name: str, field_name: str, value: object
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be a non-empty string"
        )
    return value


def _require_optional_text(
    object_name: str, field_name: str, value: object
) -> str | None:
    if value is None:
        return None
    return _require_non_empty_text(object_name, field_name, value)


def _require_int(
    object_name: str,
    field_name: str,
    value: object,
    *,
    minimum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be >= {minimum}"
        )
    return value


def _require_decimal(
    object_name: str, field_name: str, value: object
) -> Decimal:
    if not isinstance(value, Decimal):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be a Decimal"
        )
    if not value.is_finite():
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be finite"
        )
    return value


def _normalize_utc_datetime(
    object_name: str, field_name: str, value: object
) -> datetime:
    if not isinstance(value, datetime):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be a datetime"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _normalize_optional_utc_datetime(
    object_name: str, field_name: str, value: object
) -> datetime | None:
    if value is None:
        return None
    return _normalize_utc_datetime(object_name, field_name, value)


def _require_instance(
    object_name: str, field_name: str, value: object, expected_type: type[Any]
) -> Any:
    if not isinstance(value, expected_type):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be a "
            f"{expected_type.__name__}"
        )
    return value


def _require_tuple(
    object_name: str, field_name: str, value: object
) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must be a tuple"
        )
    return value


def _canonical_text_tuple(
    object_name: str,
    field_name: str,
    value: object,
    *,
    non_empty: bool,
    unique: bool,
    sort_values: bool,
) -> tuple[str, ...]:
    raw = _require_tuple(object_name, field_name, value)
    if non_empty and not raw:
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must not be empty"
        )
    normalized = tuple(
        _require_non_empty_text(object_name, f"{field_name}[{index}]", item)
        for index, item in enumerate(raw)
    )
    if unique and len(set(normalized)) != len(normalized):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must contain unique values"
        )
    return tuple(sorted(normalized)) if sort_values else normalized


def _canonical_enum_tuple(
    object_name: str,
    field_name: str,
    value: object,
    enum_type: type[EnumT],
    *,
    non_empty: bool,
) -> tuple[EnumT, ...]:
    raw = _require_tuple(object_name, field_name, value)
    if non_empty and not raw:
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must not be empty"
        )
    for index, item in enumerate(raw):
        if not isinstance(item, enum_type):
            raise DomainValidationError(
                f"{_field(object_name, f'{field_name}[{index}]')} must be a "
                f"{enum_type.__name__}"
            )
    if len(set(raw)) != len(raw):
        raise DomainValidationError(
            f"{_field(object_name, field_name)} must contain unique values"
        )
    return tuple(sorted(raw, key=lambda item: str(item.value)))


def _strict_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise DomainSerializationError(f"{object_name} payload must be a mapping")
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise DomainSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise DomainSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    version = payload["schema_version"]
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise DomainSerializationError(
            f"{object_name}.schema_version must be {SCHEMA_VERSION}"
        )
    return payload


def _deserialize_datetime(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> datetime:
    raw = payload[field_name]
    if not isinstance(raw, str):
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be an ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(raw)
        return _normalize_utc_datetime(object_name, field_name, parsed)
    except (DomainValidationError, ValueError) as exc:
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be an aware ISO-8601 datetime"
        ) from exc


def _deserialize_optional_datetime(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> datetime | None:
    if payload[field_name] is None:
        return None
    return _deserialize_datetime(payload, object_name, field_name)


def _deserialize_decimal(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> Decimal:
    raw = payload[field_name]
    if not isinstance(raw, str):
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be a Decimal string"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be a Decimal string"
        ) from exc
    if not value.is_finite():
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be finite"
        )
    return value


def _deserialize_enum(
    payload: Mapping[str, Any],
    object_name: str,
    field_name: str,
    enum_type: type[EnumT],
) -> EnumT:
    raw = payload[field_name]
    if not isinstance(raw, str):
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be a string"
        )
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} has unknown "
            f"{enum_type.__name__} value: {raw!r}"
        ) from exc


def _deserialize_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    raw = payload[field_name]
    if not isinstance(raw, list):
        raise DomainSerializationError(
            f"{_field(object_name, field_name)} must be an ordered list"
        )
    return raw


def _wrap_validation(object_name: str, exc: DomainValidationError) -> None:
    raise DomainSerializationError(
        f"invalid serialized {object_name}: {exc}"
    ) from exc


@dataclass(frozen=True, slots=True)
class PriceRange:
    """A finite inclusive Decimal price interval."""

    low: Decimal
    high: Decimal

    def __post_init__(self) -> None:
        low = _require_decimal("PriceRange", "low", self.low)
        high = _require_decimal("PriceRange", "high", self.high)
        if low > high:
            raise DomainValidationError(
                "PriceRange.low must be less than or equal to PriceRange.high"
            )

    @property
    def width(self) -> Decimal:
        return self.high - self.low

    @property
    def midpoint(self) -> Decimal:
        return (self.low + self.high) / Decimal(2)

    def contains(self, price: Decimal) -> bool:
        value = _require_decimal("PriceRange", "price", price)
        return self.low <= value <= self.high

    def overlaps(self, other: PriceRange) -> bool:
        if not isinstance(other, PriceRange):
            raise DomainValidationError("PriceRange.other must be a PriceRange")
        return self.low <= other.high and other.low <= self.high

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "low": str(self.low),
            "high": str(self.high),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PriceRange:
        object_name = cls.__name__
        data = _strict_payload(payload, object_name, {"low", "high"})
        try:
            return cls(
                low=_deserialize_decimal(data, object_name, "low"),
                high=_deserialize_decimal(data, object_name, "high"),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)


@dataclass(frozen=True, slots=True)
class ScaleDescriptor:
    """Caller-supplied scale identity with optional configured ordering rank."""

    scale_id: str
    rank: int | None

    def __post_init__(self) -> None:
        _require_non_empty_text("ScaleDescriptor", "scale_id", self.scale_id)
        if self.rank is not None:
            _require_int("ScaleDescriptor", "rank", self.rank, minimum=0)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "scale_id": self.scale_id,
            "rank": self.rank,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScaleDescriptor:
        object_name = cls.__name__
        data = _strict_payload(payload, object_name, {"scale_id", "rank"})
        try:
            return cls(scale_id=data["scale_id"], rank=data["rank"])
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)
