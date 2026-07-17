"""Stable enumerations used by the C-002 domain model contract."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Self

from .errors import DomainSerializationError


SCHEMA_VERSION = 1


class DomainEnum(str, Enum):
    """String enum with a strict, versioned standalone representation."""

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        if not isinstance(payload, Mapping):
            raise DomainSerializationError(
                f"{cls.__name__} payload must be a mapping"
            )
        expected = {"schema_version", "value"}
        keys = set(payload)
        missing = expected - keys
        unknown = keys - expected
        if missing:
            raise DomainSerializationError(
                f"{cls.__name__} payload missing fields: {sorted(missing)}"
            )
        if unknown:
            raise DomainSerializationError(
                f"{cls.__name__} payload has unknown fields: {sorted(unknown)}"
            )
        version = payload["schema_version"]
        if isinstance(version, bool) or version != SCHEMA_VERSION:
            raise DomainSerializationError(
                f"{cls.__name__}.schema_version must be {SCHEMA_VERSION}"
            )
        try:
            return cls(payload["value"])
        except (TypeError, ValueError) as exc:
            raise DomainSerializationError(
                f"{cls.__name__}.value is unknown: {payload['value']!r}"
            ) from exc


class StructureSourceType(DomainEnum):
    """Approved structural evidence source categories."""

    SWING = "SWING"
    PERIODIC_EXTREME = "PERIODIC_EXTREME"
    HISTORICAL_REACTION = "HISTORICAL_REACTION"


class BoundarySide(DomainEnum):
    """Whether a boundary is above or below the represented price context."""

    UPPER = "UPPER"
    LOWER = "LOWER"


class MarketRole(DomainEnum):
    """Observed structural role, independent of boundary side or trade bias."""

    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    NEUTRAL = "NEUTRAL"


class ConfirmationStatus(DomainEnum):
    """Whether a candidate has reached its causal confirmation event."""

    FORMING = "FORMING"
    CONFIRMED = "CONFIRMED"


class LifecycleState(DomainEnum):
    """Stored lifecycle labels; C-002 defines no transition algorithm."""

    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    FRESH = "FRESH"
    TESTED = "TESTED"
    WEAKENED = "WEAKENED"
    BROKEN = "BROKEN"
    FLIPPED = "FLIPPED"
    RETIRED = "RETIRED"


class StructureObjectKind(DomainEnum):
    """Concrete domain object represented by a boundary snapshot."""

    LEVEL_CANDIDATE = "LEVEL_CANDIDATE"
    STRUCTURE_CLUSTER = "STRUCTURE_CLUSTER"


class ActiveBoxStatus(DomainEnum):
    """Stored Active Box status; C-002 defines no status transitions."""

    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    INVALIDATED = "INVALIDATED"
    RETIRED = "RETIRED"
