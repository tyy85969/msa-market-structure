"""Immutable contracts for dependency-aware C-007B resonance scoring."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from itertools import combinations
from typing import Any, Mapping, Self

from msa.domain import (
    BoundarySide,
    Direction,
    LifecycleState,
    PriceRange,
    ProvenanceRef,
    StructureSourceType,
)

from .contracts import (
    ResonanceContext,
    ResonanceEvidence,
    ResonanceEvidenceTier,
    ResonanceFrame,
    ResonanceFrameHistory,
)
from .errors import (
    ResonanceScoringConfigurationError,
    ResonanceScoringEngineError,
    ResonanceScoringInputError,
    ResonanceScoringSerializationError,
)
from .scoring_identity import (
    _component_id,
    _contribution_id,
    _score_frame_id,
    _zone_key_id,
    _zone_snapshot_id,
)


SCHEMA_VERSION = 1
_SCORING_MODULE = "msa.research.resonance.scoring"
_ASSUMPTIONS = (
    "ResonanceFrame.evidence is the complete scoring evidence universe",
    "UPPER and LOWER evidence are clustered separately by range-gap SINGLE_LINK",
    "structure families are explicit dependency evidence, not statistical proof",
    "all weights and thresholds are caller-supplied unoptimized research parameters",
    "Selection Score is a deterministic C-007C input, not a trading edge",
    "C-007B performs no ActiveBox selection",
)


def _exact_payload(
    payload: Mapping[str, Any], object_name: str, field_names: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ResonanceScoringSerializationError(
            f"{object_name} payload must be a mapping"
        )
    expected = field_names | {"schema_version"}
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise ResonanceScoringSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise ResonanceScoringSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    _schema(payload["schema_version"], object_name, ResonanceScoringSerializationError)
    return payload


def _schema(value: object, object_name: str, error_type: type[Exception]) -> None:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error_type(f"{object_name}.schema_version must be {SCHEMA_VERSION}")


def _text(field_name: str, value: object, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def _integer(
    field_name: str,
    value: object,
    error_type: type[Exception],
    *,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise error_type(f"{field_name} must be an integer >= {minimum}")
    return value


def _boolean(field_name: str, value: object, error_type: type[Exception]) -> bool:
    if not isinstance(value, bool):
        raise error_type(f"{field_name} must be a bool")
    return value


def _decimal(
    field_name: str,
    value: object,
    error_type: type[Exception],
    *,
    minimum: Decimal | None = Decimal("0"),
    maximum: Decimal | None = None,
    exclusive_minimum: bool = False,
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise error_type(f"{field_name} must be a finite Decimal")
    if minimum is not None and (
        value < minimum or (exclusive_minimum and value == minimum)
    ):
        relation = ">" if exclusive_minimum else ">="
        raise error_type(f"{field_name} must be {relation} {minimum}")
    if maximum is not None and value > maximum:
        raise error_type(f"{field_name} must be <= {maximum}")
    return value


def _parse_decimal(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise ResonanceScoringSerializationError(
            f"{field_name} must be a Decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ResonanceScoringSerializationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise ResonanceScoringSerializationError(f"{field_name} must be finite")
    return parsed


def _time(field_name: str, value: object, error_type: type[Exception]) -> datetime:
    if not isinstance(value, datetime):
        raise error_type(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error_type(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_time(
    field_name: str, value: object, error_type: type[Exception]
) -> datetime | None:
    return None if value is None else _time(field_name, value, error_type)


def _parse_time(field_name: str, value: object) -> datetime:
    if not isinstance(value, str):
        raise ResonanceScoringSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResonanceScoringSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    return _time(field_name, parsed, ResonanceScoringSerializationError)


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    return None if value is None else _parse_time(field_name, value)


def _ordered_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise ResonanceScoringSerializationError(
            f"{object_name}.{field_name} must be an ordered list"
        )
    return value


def _text_tuple(
    object_name: str,
    field_name: str,
    values: object,
    error_type: type[Exception],
    *,
    non_empty: bool = False,
    unique: bool = False,
    sort_values: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise error_type(f"{object_name}.{field_name} must be a tuple")
    if non_empty and not values:
        raise error_type(f"{object_name}.{field_name} must not be empty")
    normalized = tuple(
        _text(f"{object_name}.{field_name}[{index}]", item, error_type)
        for index, item in enumerate(values)
    )
    if unique and len(set(normalized)) != len(normalized):
        raise error_type(f"{object_name}.{field_name} must contain unique values")
    return tuple(sorted(normalized)) if sort_values else normalized


def _context_key(context: ResonanceContext) -> tuple[str, str, int, int]:
    return (
        context.timeframe.value,
        context.scale.scale_id,
        0 if context.scale.rank is None else 1,
        -1 if context.scale.rank is None else context.scale.rank,
    )


def _elapsed_seconds(delta: timedelta) -> Decimal:
    microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    return Decimal(microseconds) / Decimal("1000000")


def _range_gap(left: PriceRange, right: PriceRange) -> Decimal:
    if left.high < right.low:
        return right.low - left.high
    if right.high < left.low:
        return left.low - right.high
    return Decimal("0")


def _identity(value: str, prefix: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise ResonanceScoringEngineError(
            f"{field_name} must be a canonical SHA-256 identity"
        )
    digest = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ResonanceScoringEngineError(
            f"{field_name} must be a canonical SHA-256 identity"
        )


class _ScoringEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact_payload(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise ResonanceScoringSerializationError(
                f"{cls.__name__}.value is unknown: {data['value']!r}"
            ) from exc


class ResonanceToleranceMode(_ScoringEnum):
    ABSOLUTE = "ABSOLUTE"
    REFERENCE_FRACTION = "REFERENCE_FRACTION"


class ResonanceClusteringPolicy(_ScoringEnum):
    SIDE_SEPARATED_SINGLE_LINK = "SIDE_SEPARATED_SINGLE_LINK"


class ResonanceDirectionRelation(_ScoringEnum):
    ALIGNED = "ALIGNED"
    NEUTRAL = "NEUTRAL"
    TURNING = "TURNING"
    OPPOSED = "OPPOSED"
    UNKNOWN = "UNKNOWN"


class ResonancePriceRelation(_ScoringEnum):
    EXPECTED_SIDE = "EXPECTED_SIDE"
    CONTAINS_PRICE = "CONTAINS_PRICE"
    OPPOSITE_SIDE = "OPPOSITE_SIDE"


class ResonanceClass(_ScoringEnum):
    SINGLE = "SINGLE"
    LOCAL_CLUSTER = "LOCAL_CLUSTER"
    MULTI_CONTEXT_RESONANCE = "MULTI_CONTEXT_RESONANCE"


@dataclass(frozen=True, slots=True)
class ResonanceContextWeight:
    context: ResonanceContext
    weight: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringConfigurationError)
        if not isinstance(self.context, ResonanceContext):
            raise ResonanceScoringConfigurationError(
                "ResonanceContextWeight.context must be a ResonanceContext"
            )
        _decimal(
            f"{name}.weight",
            self.weight,
            ResonanceScoringConfigurationError,
            exclusive_minimum=True,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "context": self.context.to_dict(),
            "weight": str(self.weight),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceContextWeight:
        data = _exact_payload(payload, cls.__name__, {"context", "weight"})
        try:
            return cls(
                context=ResonanceContext.from_dict(data["context"]),
                weight=_parse_decimal("weight", data["weight"]),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


_FACTOR_FIELDS = (
    "candidate_tier_weight",
    "confirmed_tier_weight",
    "fresh_lifecycle_weight",
    "tested_lifecycle_weight",
    "weakened_lifecycle_weight",
    "flipped_lifecycle_weight",
    "freshness_horizon_seconds",
    "freshness_floor",
    "touch_penalty_per_extra",
    "touch_floor",
    "aligned_direction_factor",
    "neutral_direction_factor",
    "turning_direction_factor",
    "opposed_direction_factor",
    "unknown_direction_factor",
    "dependency_repeat_credit",
    "source_diversity_bonus_per_extra",
    "source_diversity_bonus_cap",
    "context_diversity_bonus_per_extra",
    "context_diversity_bonus_cap",
    "expected_side_factor",
    "contains_price_factor",
    "opposite_side_factor",
)


@dataclass(frozen=True, slots=True)
class ResonanceFactorTable:
    candidate_tier_weight: Decimal
    confirmed_tier_weight: Decimal
    fresh_lifecycle_weight: Decimal
    tested_lifecycle_weight: Decimal
    weakened_lifecycle_weight: Decimal
    flipped_lifecycle_weight: Decimal
    freshness_horizon_seconds: Decimal
    freshness_floor: Decimal
    touch_penalty_per_extra: Decimal
    touch_floor: Decimal
    aligned_direction_factor: Decimal
    neutral_direction_factor: Decimal
    turning_direction_factor: Decimal
    opposed_direction_factor: Decimal
    unknown_direction_factor: Decimal
    dependency_repeat_credit: Decimal
    source_diversity_bonus_per_extra: Decimal
    source_diversity_bonus_cap: Decimal
    context_diversity_bonus_per_extra: Decimal
    context_diversity_bonus_cap: Decimal
    expected_side_factor: Decimal
    contains_price_factor: Decimal
    opposite_side_factor: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringConfigurationError)
        bounded = {
            "freshness_floor",
            "touch_floor",
            "aligned_direction_factor",
            "neutral_direction_factor",
            "turning_direction_factor",
            "opposed_direction_factor",
            "unknown_direction_factor",
            "dependency_repeat_credit",
            "expected_side_factor",
            "contains_price_factor",
            "opposite_side_factor",
        }
        for field_name in _FACTOR_FIELDS:
            _decimal(
                f"{name}.{field_name}",
                getattr(self, field_name),
                ResonanceScoringConfigurationError,
                maximum=Decimal("1") if field_name in bounded else None,
                exclusive_minimum=field_name == "freshness_horizon_seconds",
            )

    def to_dict(self) -> dict[str, object]:
        result = {"schema_version": self.schema_version}
        result.update({name: str(getattr(self, name)) for name in _FACTOR_FIELDS})
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFactorTable:
        data = _exact_payload(payload, cls.__name__, set(_FACTOR_FIELDS))
        try:
            return cls(
                **{name: _parse_decimal(name, data[name]) for name in _FACTOR_FIELDS},
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceScoringConfig:
    engine_id: str
    engine_version: str
    policy_id: str
    clustering_policy: ResonanceClusteringPolicy
    tolerance_mode: ResonanceToleranceMode
    absolute_tolerance: Decimal | None
    reference_tolerance_fraction: Decimal | None
    context_weights: tuple[ResonanceContextWeight, ...]
    candidate_tier_weight: Decimal
    confirmed_tier_weight: Decimal
    fresh_lifecycle_weight: Decimal
    tested_lifecycle_weight: Decimal
    weakened_lifecycle_weight: Decimal
    flipped_lifecycle_weight: Decimal
    freshness_horizon_seconds: Decimal
    freshness_floor: Decimal
    touch_penalty_per_extra: Decimal
    touch_floor: Decimal
    aligned_direction_factor: Decimal
    neutral_direction_factor: Decimal
    turning_direction_factor: Decimal
    opposed_direction_factor: Decimal
    unknown_direction_factor: Decimal
    dependency_repeat_credit: Decimal
    source_diversity_bonus_per_extra: Decimal
    source_diversity_bonus_cap: Decimal
    context_diversity_bonus_per_extra: Decimal
    context_diversity_bonus_cap: Decimal
    distance_horizon_mode: ResonanceToleranceMode
    absolute_distance_horizon: Decimal | None
    reference_distance_fraction: Decimal | None
    expected_side_factor: Decimal
    contains_price_factor: Decimal
    opposite_side_factor: Decimal
    minimum_resonant_evidence_count: int
    minimum_resonant_context_count: int
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringConfigurationError)
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                ResonanceScoringConfigurationError,
            )
        if self.clustering_policy is not ResonanceClusteringPolicy.SIDE_SEPARATED_SINGLE_LINK:
            raise ResonanceScoringConfigurationError(
                "clustering_policy must be SIDE_SEPARATED_SINGLE_LINK"
            )
        self._validate_mode(
            "tolerance",
            self.tolerance_mode,
            self.absolute_tolerance,
            self.reference_tolerance_fraction,
        )
        self._validate_mode(
            "distance_horizon",
            self.distance_horizon_mode,
            self.absolute_distance_horizon,
            self.reference_distance_fraction,
        )
        if not isinstance(self.context_weights, tuple) or not self.context_weights:
            raise ResonanceScoringConfigurationError(
                "context_weights must be a non-empty tuple"
            )
        if any(not isinstance(item, ResonanceContextWeight) for item in self.context_weights):
            raise ResonanceScoringConfigurationError(
                "context_weights must contain ResonanceContextWeight"
            )
        ordered = tuple(sorted(self.context_weights, key=lambda item: _context_key(item.context)))
        if len({item.context for item in ordered}) != len(ordered):
            raise ResonanceScoringConfigurationError(
                "context_weights must contain each context exactly once"
            )
        factor_table = ResonanceFactorTable(
            **{field_name: getattr(self, field_name) for field_name in _FACTOR_FIELDS}
        )
        if factor_table.freshness_horizon_seconds <= 0:
            raise ResonanceScoringConfigurationError(
                "freshness_horizon_seconds must be > 0"
            )
        _integer(
            f"{name}.minimum_resonant_evidence_count",
            self.minimum_resonant_evidence_count,
            ResonanceScoringConfigurationError,
            minimum=1,
        )
        _integer(
            f"{name}.minimum_resonant_context_count",
            self.minimum_resonant_context_count,
            ResonanceScoringConfigurationError,
            minimum=1,
        )
        _boolean(f"{name}.strict", self.strict, ResonanceScoringConfigurationError)
        if self.strict is not True:
            raise ResonanceScoringConfigurationError(
                "ResonanceScoringConfig.strict must be True; C-007B supports strict mode only"
            )
        object.__setattr__(self, "context_weights", ordered)

    @staticmethod
    def _validate_mode(
        field_name: str,
        mode: ResonanceToleranceMode,
        absolute: Decimal | None,
        fraction: Decimal | None,
    ) -> None:
        if not isinstance(mode, ResonanceToleranceMode):
            raise ResonanceScoringConfigurationError(
                f"{field_name}_mode must be a ResonanceToleranceMode"
            )
        if mode is ResonanceToleranceMode.ABSOLUTE:
            if fraction is not None or absolute is None:
                raise ResonanceScoringConfigurationError(
                    f"{field_name} ABSOLUTE mode requires absolute value and no reference fraction"
                )
            _decimal(
                f"absolute_{field_name}",
                absolute,
                ResonanceScoringConfigurationError,
                exclusive_minimum=True,
            )
        else:
            if absolute is not None or fraction is None:
                raise ResonanceScoringConfigurationError(
                    f"{field_name} REFERENCE_FRACTION mode requires reference fraction and no absolute value"
                )
            _decimal(
                f"reference_{field_name}_fraction",
                fraction,
                ResonanceScoringConfigurationError,
                exclusive_minimum=True,
            )

    @property
    def factor_table(self) -> ResonanceFactorTable:
        return ResonanceFactorTable(
            **{field_name: getattr(self, field_name) for field_name in _FACTOR_FIELDS}
        )

    def context_weight(self, context: ResonanceContext) -> Decimal:
        for item in self.context_weights:
            if item.context == context:
                return item.weight
        raise ResonanceScoringInputError(
            "evidence context is missing from scoring context_weights"
        )

    def effective_tolerance(self, reference_price: Decimal) -> Decimal:
        if self.tolerance_mode is ResonanceToleranceMode.ABSOLUTE:
            if self.absolute_tolerance is None:
                raise ResonanceScoringConfigurationError(
                    "tolerance mode and absolute_tolerance are inconsistent"
                )
            return self.absolute_tolerance
        if self.reference_tolerance_fraction is None:
            raise ResonanceScoringConfigurationError(
                "tolerance mode and reference_tolerance_fraction are inconsistent"
            )
        return reference_price * self.reference_tolerance_fraction

    def distance_horizon(self, reference_price: Decimal) -> Decimal:
        if self.distance_horizon_mode is ResonanceToleranceMode.ABSOLUTE:
            if self.absolute_distance_horizon is None:
                raise ResonanceScoringConfigurationError(
                    "distance horizon mode and absolute_distance_horizon are inconsistent"
                )
            return self.absolute_distance_horizon
        if self.reference_distance_fraction is None:
            raise ResonanceScoringConfigurationError(
                "distance horizon mode and reference_distance_fraction are inconsistent"
            )
        return reference_price * self.reference_distance_fraction

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "policy_id": self.policy_id,
            "clustering_policy": self.clustering_policy.value,
            "tolerance_mode": self.tolerance_mode.value,
            "absolute_tolerance": None if self.absolute_tolerance is None else str(self.absolute_tolerance),
            "reference_tolerance_fraction": None if self.reference_tolerance_fraction is None else str(self.reference_tolerance_fraction),
            "context_weights": [item.to_dict() for item in self.context_weights],
            "distance_horizon_mode": self.distance_horizon_mode.value,
            "absolute_distance_horizon": None if self.absolute_distance_horizon is None else str(self.absolute_distance_horizon),
            "reference_distance_fraction": None if self.reference_distance_fraction is None else str(self.reference_distance_fraction),
            "minimum_resonant_evidence_count": self.minimum_resonant_evidence_count,
            "minimum_resonant_context_count": self.minimum_resonant_context_count,
            "strict": self.strict,
        }
        result.update({name: str(getattr(self, name)) for name in _FACTOR_FIELDS})
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceScoringConfig:
        special = {
            "engine_id", "engine_version", "policy_id", "clustering_policy",
            "tolerance_mode", "absolute_tolerance", "reference_tolerance_fraction",
            "context_weights", "distance_horizon_mode", "absolute_distance_horizon",
            "reference_distance_fraction", "minimum_resonant_evidence_count",
            "minimum_resonant_context_count", "strict",
        }
        data = _exact_payload(payload, cls.__name__, special | set(_FACTOR_FIELDS))

        def optional_decimal(field_name: str) -> Decimal | None:
            value = data[field_name]
            return None if value is None else _parse_decimal(field_name, value)

        try:
            return cls(
                engine_id=data["engine_id"],
                engine_version=data["engine_version"],
                policy_id=data["policy_id"],
                clustering_policy=ResonanceClusteringPolicy(data["clustering_policy"]),
                tolerance_mode=ResonanceToleranceMode(data["tolerance_mode"]),
                absolute_tolerance=optional_decimal("absolute_tolerance"),
                reference_tolerance_fraction=optional_decimal("reference_tolerance_fraction"),
                context_weights=tuple(
                    ResonanceContextWeight.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "context_weights")
                ),
                **{name: _parse_decimal(name, data[name]) for name in _FACTOR_FIELDS},
                distance_horizon_mode=ResonanceToleranceMode(data["distance_horizon_mode"]),
                absolute_distance_horizon=optional_decimal("absolute_distance_horizon"),
                reference_distance_fraction=optional_decimal("reference_distance_fraction"),
                minimum_resonant_evidence_count=data["minimum_resonant_evidence_count"],
                minimum_resonant_context_count=data["minimum_resonant_context_count"],
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceRangeGap:
    left_evidence_id: str
    right_evidence_id: str
    gap: Decimal
    directly_connected: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        left = _text(f"{name}.left_evidence_id", self.left_evidence_id, ResonanceScoringEngineError)
        right = _text(f"{name}.right_evidence_id", self.right_evidence_id, ResonanceScoringEngineError)
        if left >= right:
            raise ResonanceScoringEngineError(
                "ResonanceRangeGap evidence IDs must be canonical and distinct"
            )
        _decimal(f"{name}.gap", self.gap, ResonanceScoringEngineError)
        _boolean(f"{name}.directly_connected", self.directly_connected, ResonanceScoringEngineError)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_evidence_id": self.left_evidence_id,
            "right_evidence_id": self.right_evidence_id,
            "gap": str(self.gap),
            "directly_connected": self.directly_connected,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceRangeGap:
        data = _exact_payload(
            payload, cls.__name__,
            {"left_evidence_id", "right_evidence_id", "gap", "directly_connected"},
        )
        try:
            return cls(
                left_evidence_id=data["left_evidence_id"],
                right_evidence_id=data["right_evidence_id"],
                gap=_parse_decimal("gap", data["gap"]),
                directly_connected=data["directly_connected"],
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceDependencyEdge:
    left_evidence_id: str
    right_evidence_id: str
    shared_family_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        left = _text(f"{name}.left_evidence_id", self.left_evidence_id, ResonanceScoringEngineError)
        right = _text(f"{name}.right_evidence_id", self.right_evidence_id, ResonanceScoringEngineError)
        if left >= right:
            raise ResonanceScoringEngineError(
                "ResonanceDependencyEdge evidence IDs must be canonical and distinct"
            )
        families = _text_tuple(
            name, "shared_family_ids", self.shared_family_ids,
            ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True,
        )
        object.__setattr__(self, "shared_family_ids", families)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "left_evidence_id": self.left_evidence_id,
            "right_evidence_id": self.right_evidence_id,
            "shared_family_ids": list(self.shared_family_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceDependencyEdge:
        data = _exact_payload(
            payload, cls.__name__,
            {"left_evidence_id", "right_evidence_id", "shared_family_ids"},
        )
        try:
            return cls(
                left_evidence_id=data["left_evidence_id"],
                right_evidence_id=data["right_evidence_id"],
                shared_family_ids=tuple(_ordered_list(data, cls.__name__, "shared_family_ids")),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceEvidenceContribution:
    contribution_id: str
    evidence_id: str
    subject_id: str
    lifecycle_state_id: str
    context: ResonanceContext
    side: BoundarySide
    tier: ResonanceEvidenceTier
    lifecycle_state: LifecycleState
    direction: Direction
    direction_relation: ResonanceDirectionRelation
    context_weight: Decimal
    tier_weight: Decimal
    lifecycle_weight: Decimal
    age_seconds: Decimal
    freshness_factor: Decimal
    touch_count: int
    extra_touches: int
    touch_factor: Decimal
    direction_factor: Decimal
    raw_contribution: Decimal
    dependency_component_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        _identity(self.contribution_id, "resonance-contribution-v1-", f"{name}.contribution_id")
        _identity(
            self.dependency_component_id,
            "resonance-dependency-component-v1-",
            f"{name}.dependency_component_id",
        )
        for field_name in ("evidence_id", "subject_id", "lifecycle_state_id"):
            _text(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        if not isinstance(self.context, ResonanceContext):
            raise ResonanceScoringEngineError("contribution context type is invalid")
        enum_fields = (
            ("side", BoundarySide),
            ("tier", ResonanceEvidenceTier),
            ("lifecycle_state", LifecycleState),
            ("direction", Direction),
            ("direction_relation", ResonanceDirectionRelation),
        )
        for field_name, enum_type in enum_fields:
            if not isinstance(getattr(self, field_name), enum_type):
                raise ResonanceScoringEngineError(
                    f"{name}.{field_name} must be a {enum_type.__name__}"
                )
        for field_name in (
            "context_weight", "tier_weight", "lifecycle_weight", "age_seconds",
            "freshness_factor", "touch_factor", "direction_factor", "raw_contribution",
        ):
            _decimal(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        _integer(f"{name}.touch_count", self.touch_count, ResonanceScoringEngineError)
        _integer(f"{name}.extra_touches", self.extra_touches, ResonanceScoringEngineError)
        if self.extra_touches != max(0, self.touch_count - 1):
            raise ResonanceScoringEngineError("contribution extra_touches is inconsistent")
        expected = (
            self.context_weight
            * self.tier_weight
            * self.lifecycle_weight
            * self.freshness_factor
            * self.touch_factor
            * self.direction_factor
        )
        if self.raw_contribution != expected:
            raise ResonanceScoringEngineError(
                "raw_contribution does not equal the exact factor product"
            )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": self.schema_version,
            "contribution_id": self.contribution_id,
            "evidence_id": self.evidence_id,
            "subject_id": self.subject_id,
            "lifecycle_state_id": self.lifecycle_state_id,
            "context": self.context.to_dict(),
            "side": self.side.value,
            "tier": self.tier.value,
            "lifecycle_state": self.lifecycle_state.value,
            "direction": self.direction.value,
            "direction_relation": self.direction_relation.value,
            "touch_count": self.touch_count,
            "extra_touches": self.extra_touches,
            "dependency_component_id": self.dependency_component_id,
        }
        for field_name in (
            "context_weight", "tier_weight", "lifecycle_weight", "age_seconds",
            "freshness_factor", "touch_factor", "direction_factor", "raw_contribution",
        ):
            result[field_name] = str(getattr(self, field_name))
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceEvidenceContribution:
        field_names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, field_names)
        decimal_fields = {
            "context_weight", "tier_weight", "lifecycle_weight", "age_seconds",
            "freshness_factor", "touch_factor", "direction_factor", "raw_contribution",
        }
        try:
            return cls(
                contribution_id=data["contribution_id"],
                evidence_id=data["evidence_id"],
                subject_id=data["subject_id"],
                lifecycle_state_id=data["lifecycle_state_id"],
                context=ResonanceContext.from_dict(data["context"]),
                side=BoundarySide(data["side"]),
                tier=ResonanceEvidenceTier(data["tier"]),
                lifecycle_state=LifecycleState(data["lifecycle_state"]),
                direction=Direction(data["direction"]),
                direction_relation=ResonanceDirectionRelation(data["direction_relation"]),
                **{field_name: _parse_decimal(field_name, data[field_name]) for field_name in decimal_fields},
                touch_count=data["touch_count"],
                extra_touches=data["extra_touches"],
                dependency_component_id=data["dependency_component_id"],
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceDependencyComponent:
    component_id: str
    member_evidence_ids: tuple[str, ...]
    shared_family_ids: tuple[str, ...]
    primary_evidence_id: str
    primary_raw_contribution: Decimal
    repeated_raw_contribution: Decimal
    repeat_credit: Decimal
    adjusted_component_score: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        _identity(self.component_id, "resonance-dependency-component-v1-", f"{name}.component_id")
        members = _text_tuple(
            name, "member_evidence_ids", self.member_evidence_ids,
            ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True,
        )
        families = _text_tuple(
            name, "shared_family_ids", self.shared_family_ids,
            ResonanceScoringEngineError, unique=True, sort_values=True,
        )
        _text(f"{name}.primary_evidence_id", self.primary_evidence_id, ResonanceScoringEngineError)
        if self.primary_evidence_id not in members:
            raise ResonanceScoringEngineError("component primary evidence must be a member")
        for field_name in (
            "primary_raw_contribution", "repeated_raw_contribution", "repeat_credit",
            "adjusted_component_score",
        ):
            _decimal(
                f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError,
                maximum=Decimal("1") if field_name == "repeat_credit" else None,
            )
        expected = self.primary_raw_contribution + self.repeat_credit * self.repeated_raw_contribution
        if self.adjusted_component_score != expected:
            raise ResonanceScoringEngineError("component adjusted score is inconsistent")
        if len(members) == 1 and (families or self.repeated_raw_contribution != 0):
            raise ResonanceScoringEngineError("singleton dependency component facts are invalid")
        object.__setattr__(self, "member_evidence_ids", members)
        object.__setattr__(self, "shared_family_ids", families)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "component_id": self.component_id,
            "member_evidence_ids": list(self.member_evidence_ids),
            "shared_family_ids": list(self.shared_family_ids),
            "primary_evidence_id": self.primary_evidence_id,
            "primary_raw_contribution": str(self.primary_raw_contribution),
            "repeated_raw_contribution": str(self.repeated_raw_contribution),
            "repeat_credit": str(self.repeat_credit),
            "adjusted_component_score": str(self.adjusted_component_score),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceDependencyComponent:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                component_id=data["component_id"],
                member_evidence_ids=tuple(_ordered_list(data, cls.__name__, "member_evidence_ids")),
                shared_family_ids=tuple(_ordered_list(data, cls.__name__, "shared_family_ids")),
                primary_evidence_id=data["primary_evidence_id"],
                primary_raw_contribution=_parse_decimal("primary_raw_contribution", data["primary_raw_contribution"]),
                repeated_raw_contribution=_parse_decimal("repeated_raw_contribution", data["repeated_raw_contribution"]),
                repeat_credit=_parse_decimal("repeat_credit", data["repeat_credit"]),
                adjusted_component_score=_parse_decimal("adjusted_component_score", data["adjusted_component_score"]),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceClassRationale:
    evidence_count: int
    distinct_context_count: int
    minimum_resonant_evidence_count: int
    minimum_resonant_context_count: int
    assigned_class: ResonanceClass
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        _integer(f"{name}.evidence_count", self.evidence_count, ResonanceScoringEngineError, minimum=1)
        _integer(f"{name}.distinct_context_count", self.distinct_context_count, ResonanceScoringEngineError, minimum=1)
        _integer(f"{name}.minimum_resonant_evidence_count", self.minimum_resonant_evidence_count, ResonanceScoringEngineError, minimum=1)
        _integer(f"{name}.minimum_resonant_context_count", self.minimum_resonant_context_count, ResonanceScoringEngineError, minimum=1)
        if not isinstance(self.assigned_class, ResonanceClass):
            raise ResonanceScoringEngineError("assigned_class must be a ResonanceClass")
        expected = (
            ResonanceClass.SINGLE
            if self.evidence_count == 1
            else ResonanceClass.MULTI_CONTEXT_RESONANCE
            if self.evidence_count >= self.minimum_resonant_evidence_count
            and self.distinct_context_count >= self.minimum_resonant_context_count
            else ResonanceClass.LOCAL_CLUSTER
        )
        if self.assigned_class is not expected:
            raise ResonanceScoringEngineError("resonance class rationale is inconsistent")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evidence_count": self.evidence_count,
            "distinct_context_count": self.distinct_context_count,
            "minimum_resonant_evidence_count": self.minimum_resonant_evidence_count,
            "minimum_resonant_context_count": self.minimum_resonant_context_count,
            "assigned_class": self.assigned_class.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceClassRationale:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                evidence_count=data["evidence_count"],
                distinct_context_count=data["distinct_context_count"],
                minimum_resonant_evidence_count=data["minimum_resonant_evidence_count"],
                minimum_resonant_context_count=data["minimum_resonant_context_count"],
                assigned_class=ResonanceClass(data["assigned_class"]),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceRankKey:
    selection_score: Decimal
    quality_score: Decimal
    distinct_context_count: int
    distinct_source_type_count: int
    distance: Decimal
    latest_evidence_confirm_time: datetime
    zone_key_id: str
    zone_snapshot_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        for field_name in ("selection_score", "quality_score", "distance"):
            _decimal(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        _integer(f"{name}.distinct_context_count", self.distinct_context_count, ResonanceScoringEngineError, minimum=1)
        _integer(f"{name}.distinct_source_type_count", self.distinct_source_type_count, ResonanceScoringEngineError, minimum=1)
        normalized = _time(
            f"{name}.latest_evidence_confirm_time",
            self.latest_evidence_confirm_time,
            ResonanceScoringEngineError,
        )
        _identity(self.zone_key_id, "resonance-zone-key-v1-", f"{name}.zone_key_id")
        _identity(self.zone_snapshot_id, "resonance-zone-snapshot-v1-", f"{name}.zone_snapshot_id")
        object.__setattr__(self, "latest_evidence_confirm_time", normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "selection_score": str(self.selection_score),
            "quality_score": str(self.quality_score),
            "distinct_context_count": self.distinct_context_count,
            "distinct_source_type_count": self.distinct_source_type_count,
            "distance": str(self.distance),
            "latest_evidence_confirm_time": self.latest_evidence_confirm_time.isoformat(),
            "zone_key_id": self.zone_key_id,
            "zone_snapshot_id": self.zone_snapshot_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceRankKey:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                selection_score=_parse_decimal("selection_score", data["selection_score"]),
                quality_score=_parse_decimal("quality_score", data["quality_score"]),
                distinct_context_count=data["distinct_context_count"],
                distinct_source_type_count=data["distinct_source_type_count"],
                distance=_parse_decimal("distance", data["distance"]),
                latest_evidence_confirm_time=_parse_time("latest_evidence_confirm_time", data["latest_evidence_confirm_time"]),
                zone_key_id=data["zone_key_id"],
                zone_snapshot_id=data["zone_snapshot_id"],
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceZoneExplanation:
    effective_clustering_tolerance: Decimal
    direct_member_gaps: tuple[ResonanceRangeGap, ...]
    single_link_member_evidence_ids: tuple[str, ...]
    chain_bridged: bool
    member_evidence_ids: tuple[str, ...]
    member_subject_ids: tuple[str, ...]
    member_contexts: tuple[ResonanceContext, ...]
    context_weights: tuple[ResonanceContextWeight, ...]
    contributions: tuple[ResonanceEvidenceContribution, ...]
    dependency_family_edges: tuple[ResonanceDependencyEdge, ...]
    dependency_components: tuple[ResonanceDependencyComponent, ...]
    dependency_repeat_credit: Decimal
    dependency_adjusted_base_score: Decimal
    source_diversity_bonus: Decimal
    context_diversity_bonus: Decimal
    quality_score: Decimal
    reference_price: Decimal
    price_relation: ResonancePriceRelation
    distance: Decimal
    distance_horizon: Decimal
    distance_factor: Decimal
    placement_factor: Decimal
    selection_score: Decimal
    resonance_class_rationale: ResonanceClassRationale
    side_rank_key: ResonanceRankKey
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        for field_name in (
            "effective_clustering_tolerance", "dependency_repeat_credit",
            "dependency_adjusted_base_score", "source_diversity_bonus",
            "context_diversity_bonus", "quality_score", "reference_price",
            "distance", "distance_horizon", "distance_factor", "placement_factor",
            "selection_score",
        ):
            _decimal(
                f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError,
                exclusive_minimum=field_name == "distance_horizon",
            )
        _boolean(f"{name}.chain_bridged", self.chain_bridged, ResonanceScoringEngineError)
        members = _text_tuple(
            name, "member_evidence_ids", self.member_evidence_ids,
            ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True,
        )
        single_link = _text_tuple(
            name, "single_link_member_evidence_ids", self.single_link_member_evidence_ids,
            ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True,
        )
        subjects = _text_tuple(
            name, "member_subject_ids", self.member_subject_ids,
            ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True,
        )
        if single_link != members:
            raise ResonanceScoringEngineError("single-link membership must equal member evidence IDs")
        tuple_types = (
            ("direct_member_gaps", ResonanceRangeGap),
            ("member_contexts", ResonanceContext),
            ("context_weights", ResonanceContextWeight),
            ("contributions", ResonanceEvidenceContribution),
            ("dependency_family_edges", ResonanceDependencyEdge),
            ("dependency_components", ResonanceDependencyComponent),
        )
        for field_name, item_type in tuple_types:
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
                raise ResonanceScoringEngineError(
                    f"{name}.{field_name} must be a {item_type.__name__} tuple"
                )
        if len(set(self.member_contexts)) != len(self.member_contexts):
            raise ResonanceScoringEngineError("explanation member contexts must be unique")
        contexts = tuple(sorted(self.member_contexts, key=_context_key))
        weights = tuple(sorted(self.context_weights, key=lambda item: _context_key(item.context)))
        if tuple(item.context for item in weights) != contexts:
            raise ResonanceScoringEngineError("explanation context weights must cover member contexts")
        if tuple(item.evidence_id for item in self.contributions) != members:
            raise ResonanceScoringEngineError("explanation contributions must cover member evidence")
        expected_gap_pairs = tuple(combinations(members, 2))
        actual_gap_pairs = tuple(
            (item.left_evidence_id, item.right_evidence_id)
            for item in self.direct_member_gaps
        )
        if actual_gap_pairs != expected_gap_pairs:
            raise ResonanceScoringEngineError(
                "explanation direct gaps must exactly cover canonical member pairs"
            )
        expected_chain = len(members) > 2 and any(
            not item.directly_connected for item in self.direct_member_gaps
        )
        if self.chain_bridged != expected_chain:
            raise ResonanceScoringEngineError("explanation chain-bridging fact is inconsistent")
        component_members = tuple(
            sorted(
                member
                for component in self.dependency_components
                for member in component.member_evidence_ids
            )
        )
        if component_members != members:
            raise ResonanceScoringEngineError(
                "explanation dependency components must partition members"
            )
        if any(
            item.left_evidence_id not in members or item.right_evidence_id not in members
            for item in self.dependency_family_edges
        ):
            raise ResonanceScoringEngineError(
                "explanation dependency edge references a non-member"
            )
        if self.quality_score != (
            self.dependency_adjusted_base_score
            + self.source_diversity_bonus
            + self.context_diversity_bonus
        ):
            raise ResonanceScoringEngineError("explanation quality score is inconsistent")
        if self.selection_score != self.quality_score * self.distance_factor * self.placement_factor:
            raise ResonanceScoringEngineError("explanation selection score is inconsistent")
        if not isinstance(self.price_relation, ResonancePriceRelation):
            raise ResonanceScoringEngineError("explanation price_relation type is invalid")
        if not isinstance(self.resonance_class_rationale, ResonanceClassRationale):
            raise ResonanceScoringEngineError("explanation class rationale type is invalid")
        if not isinstance(self.side_rank_key, ResonanceRankKey):
            raise ResonanceScoringEngineError("explanation side rank key type is invalid")
        assumptions = _text_tuple(name, "assumptions", self.assumptions, ResonanceScoringEngineError)
        if assumptions != _ASSUMPTIONS:
            raise ResonanceScoringEngineError("explanation assumptions must equal C-007B assumptions")
        object.__setattr__(self, "single_link_member_evidence_ids", single_link)
        object.__setattr__(self, "member_evidence_ids", members)
        object.__setattr__(self, "member_subject_ids", subjects)
        object.__setattr__(self, "member_contexts", contexts)
        object.__setattr__(self, "context_weights", weights)
        object.__setattr__(self, "assumptions", assumptions)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "effective_clustering_tolerance": str(self.effective_clustering_tolerance),
            "direct_member_gaps": [item.to_dict() for item in self.direct_member_gaps],
            "single_link_member_evidence_ids": list(self.single_link_member_evidence_ids),
            "chain_bridged": self.chain_bridged,
            "member_evidence_ids": list(self.member_evidence_ids),
            "member_subject_ids": list(self.member_subject_ids),
            "member_contexts": [item.to_dict() for item in self.member_contexts],
            "context_weights": [item.to_dict() for item in self.context_weights],
            "contributions": [item.to_dict() for item in self.contributions],
            "dependency_family_edges": [item.to_dict() for item in self.dependency_family_edges],
            "dependency_components": [item.to_dict() for item in self.dependency_components],
            "dependency_repeat_credit": str(self.dependency_repeat_credit),
            "dependency_adjusted_base_score": str(self.dependency_adjusted_base_score),
            "source_diversity_bonus": str(self.source_diversity_bonus),
            "context_diversity_bonus": str(self.context_diversity_bonus),
            "quality_score": str(self.quality_score),
            "reference_price": str(self.reference_price),
            "price_relation": self.price_relation.value,
            "distance": str(self.distance),
            "distance_horizon": str(self.distance_horizon),
            "distance_factor": str(self.distance_factor),
            "placement_factor": str(self.placement_factor),
            "selection_score": str(self.selection_score),
            "resonance_class_rationale": self.resonance_class_rationale.to_dict(),
            "side_rank_key": self.side_rank_key.to_dict(),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceZoneExplanation:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        decimal_fields = {
            "effective_clustering_tolerance", "dependency_repeat_credit",
            "dependency_adjusted_base_score", "source_diversity_bonus",
            "context_diversity_bonus", "quality_score", "reference_price",
            "distance", "distance_horizon", "distance_factor", "placement_factor",
            "selection_score",
        }
        try:
            return cls(
                **{field_name: _parse_decimal(field_name, data[field_name]) for field_name in decimal_fields},
                direct_member_gaps=tuple(
                    ResonanceRangeGap.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "direct_member_gaps")
                ),
                single_link_member_evidence_ids=tuple(_ordered_list(data, cls.__name__, "single_link_member_evidence_ids")),
                chain_bridged=data["chain_bridged"],
                member_evidence_ids=tuple(_ordered_list(data, cls.__name__, "member_evidence_ids")),
                member_subject_ids=tuple(_ordered_list(data, cls.__name__, "member_subject_ids")),
                member_contexts=tuple(
                    ResonanceContext.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "member_contexts")
                ),
                context_weights=tuple(
                    ResonanceContextWeight.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "context_weights")
                ),
                contributions=tuple(
                    ResonanceEvidenceContribution.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "contributions")
                ),
                dependency_family_edges=tuple(
                    ResonanceDependencyEdge.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "dependency_family_edges")
                ),
                dependency_components=tuple(
                    ResonanceDependencyComponent.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "dependency_components")
                ),
                price_relation=ResonancePriceRelation(data["price_relation"]),
                resonance_class_rationale=ResonanceClassRationale.from_dict(data["resonance_class_rationale"]),
                side_rank_key=ResonanceRankKey.from_dict(data["side_rank_key"]),
                assumptions=tuple(_ordered_list(data, cls.__name__, "assumptions")),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceZone:
    zone_key_id: str
    zone_snapshot_id: str
    source_frame_id: str
    side: BoundarySide
    price_range: PriceRange
    resonance_class: ResonanceClass
    side_rank: int
    member_evidence_ids: tuple[str, ...]
    member_subject_ids: tuple[str, ...]
    contexts: tuple[ResonanceContext, ...]
    source_types: tuple[StructureSourceType, ...]
    structure_families: tuple[str, ...]
    candidate_count: int
    confirmed_count: int
    fresh_count: int
    tested_count: int
    weakened_count: int
    flipped_count: int
    distinct_context_count: int
    distinct_source_type_count: int
    distinct_structure_family_count: int
    earliest_evidence_confirm_time: datetime
    latest_evidence_confirm_time: datetime
    dependency_components: tuple[ResonanceDependencyComponent, ...]
    contributions: tuple[ResonanceEvidenceContribution, ...]
    dependency_adjusted_base_score: Decimal
    source_diversity_bonus: Decimal
    context_diversity_bonus: Decimal
    quality_score: Decimal
    reference_price: Decimal
    price_relation: ResonancePriceRelation
    distance: Decimal
    distance_factor: Decimal
    placement_factor: Decimal
    selection_score: Decimal
    explanation: ResonanceZoneExplanation
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        _identity(self.zone_key_id, "resonance-zone-key-v1-", f"{name}.zone_key_id")
        _identity(self.zone_snapshot_id, "resonance-zone-snapshot-v1-", f"{name}.zone_snapshot_id")
        _text(f"{name}.source_frame_id", self.source_frame_id, ResonanceScoringEngineError)
        if not isinstance(self.side, BoundarySide):
            raise ResonanceScoringEngineError("zone side must be a BoundarySide")
        if not isinstance(self.price_range, PriceRange):
            raise ResonanceScoringEngineError("zone price_range must be a PriceRange")
        if not isinstance(self.resonance_class, ResonanceClass):
            raise ResonanceScoringEngineError("zone resonance_class type is invalid")
        _integer(f"{name}.side_rank", self.side_rank, ResonanceScoringEngineError, minimum=1)
        members = _text_tuple(name, "member_evidence_ids", self.member_evidence_ids, ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True)
        subjects = _text_tuple(name, "member_subject_ids", self.member_subject_ids, ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True)
        if len(members) != len(subjects):
            raise ResonanceScoringEngineError("zone evidence and subject counts must match")
        if not isinstance(self.contexts, tuple) or any(not isinstance(item, ResonanceContext) for item in self.contexts):
            raise ResonanceScoringEngineError("zone contexts must be a ResonanceContext tuple")
        if len(set(self.contexts)) != len(self.contexts):
            raise ResonanceScoringEngineError("zone contexts must be unique")
        contexts = tuple(sorted(self.contexts, key=_context_key))
        if not contexts:
            raise ResonanceScoringEngineError("zone contexts must not be empty")
        if not isinstance(self.source_types, tuple) or any(not isinstance(item, StructureSourceType) for item in self.source_types):
            raise ResonanceScoringEngineError("zone source_types must be a StructureSourceType tuple")
        if len(set(self.source_types)) != len(self.source_types):
            raise ResonanceScoringEngineError("zone source_types must be unique")
        source_types = tuple(sorted(self.source_types, key=lambda item: item.value))
        if not source_types:
            raise ResonanceScoringEngineError("zone source_types must not be empty")
        families = _text_tuple(name, "structure_families", self.structure_families, ResonanceScoringEngineError, non_empty=True, unique=True, sort_values=True)
        count_fields = (
            "candidate_count", "confirmed_count", "fresh_count", "tested_count",
            "weakened_count", "flipped_count", "distinct_context_count",
            "distinct_source_type_count", "distinct_structure_family_count",
        )
        for field_name in count_fields:
            _integer(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        if self.candidate_count + self.confirmed_count != len(members):
            raise ResonanceScoringEngineError("zone tier counts are inconsistent")
        if self.fresh_count + self.tested_count + self.weakened_count + self.flipped_count != len(members):
            raise ResonanceScoringEngineError("zone lifecycle counts are inconsistent")
        if (
            self.distinct_context_count != len(contexts)
            or self.distinct_source_type_count != len(source_types)
            or self.distinct_structure_family_count != len(families)
        ):
            raise ResonanceScoringEngineError("zone distinct counts are inconsistent")
        earliest = _time(f"{name}.earliest_evidence_confirm_time", self.earliest_evidence_confirm_time, ResonanceScoringEngineError)
        latest = _time(f"{name}.latest_evidence_confirm_time", self.latest_evidence_confirm_time, ResonanceScoringEngineError)
        if earliest > latest:
            raise ResonanceScoringEngineError("zone evidence confirm-time bounds are invalid")
        if not isinstance(self.dependency_components, tuple) or not self.dependency_components or any(not isinstance(item, ResonanceDependencyComponent) for item in self.dependency_components):
            raise ResonanceScoringEngineError("zone dependency_components are invalid")
        components = tuple(sorted(self.dependency_components, key=lambda item: item.component_id))
        if not isinstance(self.contributions, tuple) or any(not isinstance(item, ResonanceEvidenceContribution) for item in self.contributions):
            raise ResonanceScoringEngineError("zone contributions are invalid")
        contributions = tuple(sorted(self.contributions, key=lambda item: item.evidence_id))
        if tuple(item.evidence_id for item in contributions) != members:
            raise ResonanceScoringEngineError("zone contributions must exactly cover members")
        component_members = tuple(sorted(item for component in components for item in component.member_evidence_ids))
        if component_members != members:
            raise ResonanceScoringEngineError("dependency components must partition zone members")
        component_ids = {item.component_id for item in components}
        if any(item.dependency_component_id not in component_ids for item in contributions):
            raise ResonanceScoringEngineError("contribution references an unknown dependency component")
        decimal_fields = (
            "dependency_adjusted_base_score", "source_diversity_bonus",
            "context_diversity_bonus", "quality_score", "reference_price", "distance",
            "distance_factor", "placement_factor", "selection_score",
        )
        for field_name in decimal_fields:
            _decimal(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        if self.dependency_adjusted_base_score != sum(
            (item.adjusted_component_score for item in components), Decimal("0")
        ):
            raise ResonanceScoringEngineError("dependency-adjusted base score is inconsistent")
        if self.quality_score != self.dependency_adjusted_base_score + self.source_diversity_bonus + self.context_diversity_bonus:
            raise ResonanceScoringEngineError("zone quality score is inconsistent")
        if self.selection_score != self.quality_score * self.distance_factor * self.placement_factor:
            raise ResonanceScoringEngineError("zone selection score is inconsistent")
        if not isinstance(self.price_relation, ResonancePriceRelation):
            raise ResonanceScoringEngineError("zone price_relation type is invalid")
        if not isinstance(self.explanation, ResonanceZoneExplanation):
            raise ResonanceScoringEngineError("zone explanation type is invalid")
        rank_key = self.explanation.side_rank_key
        expected_rank_values = (
            self.selection_score, self.quality_score, self.distinct_context_count,
            self.distinct_source_type_count, self.distance, latest,
            self.zone_key_id, self.zone_snapshot_id,
        )
        actual_rank_values = (
            rank_key.selection_score, rank_key.quality_score,
            rank_key.distinct_context_count, rank_key.distinct_source_type_count,
            rank_key.distance, rank_key.latest_evidence_confirm_time,
            rank_key.zone_key_id, rank_key.zone_snapshot_id,
        )
        if actual_rank_values != expected_rank_values:
            raise ResonanceScoringEngineError("zone side-rank key contradicts zone facts")
        explanation_values = (
            self.explanation.member_evidence_ids,
            self.explanation.member_subject_ids,
            self.explanation.contributions,
            self.explanation.dependency_components,
            self.explanation.dependency_adjusted_base_score,
            self.explanation.source_diversity_bonus,
            self.explanation.context_diversity_bonus,
            self.explanation.quality_score,
            self.explanation.reference_price,
            self.explanation.price_relation,
            self.explanation.distance,
            self.explanation.distance_factor,
            self.explanation.placement_factor,
            self.explanation.selection_score,
            self.explanation.resonance_class_rationale.assigned_class,
        )
        zone_values = (
            members, subjects, contributions, components,
            self.dependency_adjusted_base_score, self.source_diversity_bonus,
            self.context_diversity_bonus, self.quality_score, self.reference_price,
            self.price_relation, self.distance, self.distance_factor,
            self.placement_factor, self.selection_score, self.resonance_class,
        )
        if explanation_values != zone_values:
            raise ResonanceScoringEngineError("zone explanation contradicts zone facts")
        if not isinstance(self.provenance, ProvenanceRef):
            raise ResonanceScoringEngineError("zone provenance type is invalid")
        object.__setattr__(self, "member_evidence_ids", members)
        object.__setattr__(self, "member_subject_ids", subjects)
        object.__setattr__(self, "contexts", contexts)
        object.__setattr__(self, "source_types", source_types)
        object.__setattr__(self, "structure_families", families)
        object.__setattr__(self, "earliest_evidence_confirm_time", earliest)
        object.__setattr__(self, "latest_evidence_confirm_time", latest)
        object.__setattr__(self, "dependency_components", components)
        object.__setattr__(self, "contributions", contributions)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "zone_key_id": self.zone_key_id,
            "zone_snapshot_id": self.zone_snapshot_id,
            "source_frame_id": self.source_frame_id,
            "side": self.side.value,
            "price_range": self.price_range.to_dict(),
            "resonance_class": self.resonance_class.value,
            "side_rank": self.side_rank,
            "member_evidence_ids": list(self.member_evidence_ids),
            "member_subject_ids": list(self.member_subject_ids),
            "contexts": [item.to_dict() for item in self.contexts],
            "source_types": [item.value for item in self.source_types],
            "structure_families": list(self.structure_families),
            "candidate_count": self.candidate_count,
            "confirmed_count": self.confirmed_count,
            "fresh_count": self.fresh_count,
            "tested_count": self.tested_count,
            "weakened_count": self.weakened_count,
            "flipped_count": self.flipped_count,
            "distinct_context_count": self.distinct_context_count,
            "distinct_source_type_count": self.distinct_source_type_count,
            "distinct_structure_family_count": self.distinct_structure_family_count,
            "earliest_evidence_confirm_time": self.earliest_evidence_confirm_time.isoformat(),
            "latest_evidence_confirm_time": self.latest_evidence_confirm_time.isoformat(),
            "dependency_components": [item.to_dict() for item in self.dependency_components],
            "contributions": [item.to_dict() for item in self.contributions],
            "dependency_adjusted_base_score": str(self.dependency_adjusted_base_score),
            "source_diversity_bonus": str(self.source_diversity_bonus),
            "context_diversity_bonus": str(self.context_diversity_bonus),
            "quality_score": str(self.quality_score),
            "reference_price": str(self.reference_price),
            "price_relation": self.price_relation.value,
            "distance": str(self.distance),
            "distance_factor": str(self.distance_factor),
            "placement_factor": str(self.placement_factor),
            "selection_score": str(self.selection_score),
            "explanation": self.explanation.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceZone:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        decimal_fields = {
            "dependency_adjusted_base_score", "source_diversity_bonus",
            "context_diversity_bonus", "quality_score", "reference_price", "distance",
            "distance_factor", "placement_factor", "selection_score",
        }
        raw_fields = names - decimal_fields - {
            "side", "price_range", "resonance_class", "member_evidence_ids",
            "member_subject_ids", "contexts", "source_types", "structure_families",
            "earliest_evidence_confirm_time", "latest_evidence_confirm_time",
            "dependency_components", "contributions", "price_relation", "explanation",
            "provenance",
        }
        try:
            return cls(
                **{name: data[name] for name in raw_fields},
                **{name: _parse_decimal(name, data[name]) for name in decimal_fields},
                side=BoundarySide(data["side"]),
                price_range=PriceRange.from_dict(data["price_range"]),
                resonance_class=ResonanceClass(data["resonance_class"]),
                member_evidence_ids=tuple(_ordered_list(data, cls.__name__, "member_evidence_ids")),
                member_subject_ids=tuple(_ordered_list(data, cls.__name__, "member_subject_ids")),
                contexts=tuple(ResonanceContext.from_dict(item) for item in _ordered_list(data, cls.__name__, "contexts")),
                source_types=tuple(StructureSourceType(item) for item in _ordered_list(data, cls.__name__, "source_types")),
                structure_families=tuple(_ordered_list(data, cls.__name__, "structure_families")),
                earliest_evidence_confirm_time=_parse_time("earliest_evidence_confirm_time", data["earliest_evidence_confirm_time"]),
                latest_evidence_confirm_time=_parse_time("latest_evidence_confirm_time", data["latest_evidence_confirm_time"]),
                dependency_components=tuple(ResonanceDependencyComponent.from_dict(item) for item in _ordered_list(data, cls.__name__, "dependency_components")),
                contributions=tuple(ResonanceEvidenceContribution.from_dict(item) for item in _ordered_list(data, cls.__name__, "contributions")),
                price_relation=ResonancePriceRelation(data["price_relation"]),
                explanation=ResonanceZoneExplanation.from_dict(data["explanation"]),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceScoreReport:
    as_of_time: datetime
    source_frame_id: str
    evidence_count: int
    zone_count: int
    upper_zone_count: int
    lower_zone_count: int
    singleton_zone_count: int
    local_cluster_count: int
    multi_context_resonance_count: int
    candidate_evidence_count: int
    confirmed_evidence_count: int
    dependency_component_count: int
    dependent_evidence_count: int
    chain_bridged_zone_count: int
    highest_upper_selection_score: Decimal | None
    highest_lower_selection_score: Decimal | None
    highest_upper_quality_score: Decimal | None
    highest_lower_quality_score: Decimal | None
    engine_id: str
    engine_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        as_of = _time(f"{name}.as_of_time", self.as_of_time, ResonanceScoringEngineError)
        _text(f"{name}.source_frame_id", self.source_frame_id, ResonanceScoringEngineError)
        for field_name in (
            "evidence_count", "zone_count", "upper_zone_count", "lower_zone_count",
            "singleton_zone_count", "local_cluster_count", "multi_context_resonance_count",
            "candidate_evidence_count", "confirmed_evidence_count",
            "dependency_component_count", "dependent_evidence_count",
            "chain_bridged_zone_count",
        ):
            _integer(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        for field_name in (
            "highest_upper_selection_score", "highest_lower_selection_score",
            "highest_upper_quality_score", "highest_lower_quality_score",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _decimal(f"{name}.{field_name}", value, ResonanceScoringEngineError)
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(f"{name}.{field_name}", getattr(self, field_name), ResonanceScoringEngineError)
        assumptions = _text_tuple(name, "assumptions", self.assumptions, ResonanceScoringEngineError)
        warnings = _text_tuple(name, "warnings", self.warnings, ResonanceScoringEngineError)
        errors = _text_tuple(name, "errors", self.errors, ResonanceScoringEngineError)
        if assumptions != _ASSUMPTIONS or warnings or errors:
            raise ResonanceScoringEngineError("successful score report metadata is invalid")
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "errors", errors)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        optional_decimals = {
            "highest_upper_selection_score", "highest_lower_selection_score",
            "highest_upper_quality_score", "highest_lower_quality_score",
        }
        for field in fields(self):
            if field.name == "schema_version":
                continue
            value = getattr(self, field.name)
            if isinstance(value, datetime):
                result[field.name] = value.isoformat()
            elif field.name in optional_decimals:
                result[field.name] = None if value is None else str(value)
            elif isinstance(value, tuple):
                result[field.name] = list(value)
            else:
                result[field.name] = value
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceScoreReport:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        optional_decimals = {
            "highest_upper_selection_score", "highest_lower_selection_score",
            "highest_upper_quality_score", "highest_lower_quality_score",
        }
        tuples = {"assumptions", "warnings", "errors"}
        raw = names - optional_decimals - tuples - {"as_of_time"}

        def optional_decimal(name: str) -> Decimal | None:
            return None if data[name] is None else _parse_decimal(name, data[name])

        try:
            return cls(
                **{name: data[name] for name in raw},
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                **{name: optional_decimal(name) for name in optional_decimals},
                assumptions=tuple(_ordered_list(data, cls.__name__, "assumptions")),
                warnings=tuple(_ordered_list(data, cls.__name__, "warnings")),
                errors=tuple(_ordered_list(data, cls.__name__, "errors")),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def _rank_sort_key(zone: ResonanceZone) -> tuple[object, ...]:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = zone.latest_evidence_confirm_time - epoch
    confirm_microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    return (
        -zone.selection_score,
        -zone.quality_score,
        -zone.distinct_context_count,
        -zone.distinct_source_type_count,
        zone.distance,
        -confirm_microseconds,
        zone.zone_key_id,
        zone.zone_snapshot_id,
    )


def _report_for(
    frame: ResonanceFrame,
    zones: tuple[ResonanceZone, ...],
    config: ResonanceScoringConfig,
) -> ResonanceScoreReport:
    upper = tuple(item for item in zones if item.side is BoundarySide.UPPER)
    lower = tuple(item for item in zones if item.side is BoundarySide.LOWER)
    return ResonanceScoreReport(
        as_of_time=frame.as_of_time,
        source_frame_id=frame.frame_id,
        evidence_count=len(frame.evidence),
        zone_count=len(zones),
        upper_zone_count=len(upper),
        lower_zone_count=len(lower),
        singleton_zone_count=sum(item.resonance_class is ResonanceClass.SINGLE for item in zones),
        local_cluster_count=sum(item.resonance_class is ResonanceClass.LOCAL_CLUSTER for item in zones),
        multi_context_resonance_count=sum(item.resonance_class is ResonanceClass.MULTI_CONTEXT_RESONANCE for item in zones),
        candidate_evidence_count=sum(item.tier is ResonanceEvidenceTier.CANDIDATE for item in frame.evidence),
        confirmed_evidence_count=sum(item.tier is ResonanceEvidenceTier.CONFIRMED for item in frame.evidence),
        dependency_component_count=sum(len(item.dependency_components) for item in zones),
        dependent_evidence_count=sum(
            len(component.member_evidence_ids)
            for item in zones
            for component in item.dependency_components
            if len(component.member_evidence_ids) > 1
        ),
        chain_bridged_zone_count=sum(item.explanation.chain_bridged for item in zones),
        highest_upper_selection_score=max((item.selection_score for item in upper), default=None),
        highest_lower_selection_score=max((item.selection_score for item in lower), default=None),
        highest_upper_quality_score=max((item.quality_score for item in upper), default=None),
        highest_lower_quality_score=max((item.quality_score for item in lower), default=None),
        engine_id=config.engine_id,
        engine_version=config.engine_version,
        policy_id=config.policy_id,
        assumptions=_ASSUMPTIONS,
        warnings=(),
        errors=(),
    )


@dataclass(frozen=True, slots=True)
class ResonanceScoreFrame:
    score_frame_id: str
    as_of_time: datetime
    source_frame_id: str
    source_frame: ResonanceFrame
    zones: tuple[ResonanceZone, ...]
    report: ResonanceScoreReport
    config_snapshot: ResonanceScoringConfig
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        _identity(self.score_frame_id, "resonance-score-frame-v1-", f"{name}.score_frame_id")
        as_of = _time(f"{name}.as_of_time", self.as_of_time, ResonanceScoringEngineError)
        _text(f"{name}.source_frame_id", self.source_frame_id, ResonanceScoringEngineError)
        if not isinstance(self.source_frame, ResonanceFrame):
            raise ResonanceScoringEngineError("source_frame must be a ResonanceFrame")
        if self.source_frame_id != self.source_frame.frame_id or as_of != self.source_frame.as_of_time:
            raise ResonanceScoringEngineError("score frame must align exactly to source ResonanceFrame")
        if not isinstance(self.config_snapshot, ResonanceScoringConfig):
            raise ResonanceScoringEngineError("score frame config_snapshot type is invalid")
        config_contexts = tuple(item.context for item in self.config_snapshot.context_weights)
        if config_contexts != self.source_frame.config_snapshot.contexts:
            raise ResonanceScoringEngineError(
                "scoring context_weights must exactly cover source Frame contexts"
            )
        if not isinstance(self.zones, tuple) or any(not isinstance(item, ResonanceZone) for item in self.zones):
            raise ResonanceScoringEngineError("score frame zones must be a ResonanceZone tuple")
        upper = tuple(item for item in self.zones if item.side is BoundarySide.UPPER)
        lower = tuple(item for item in self.zones if item.side is BoundarySide.LOWER)
        canonical = upper + lower
        if self.zones != canonical:
            raise ResonanceScoringEngineError("score frame zones must store UPPER then LOWER")
        for side_zones, side in ((upper, BoundarySide.UPPER), (lower, BoundarySide.LOWER)):
            if tuple(item.side_rank for item in side_zones) != tuple(range(1, len(side_zones) + 1)):
                raise ResonanceScoringEngineError(f"{side.value} side_rank values must be contiguous from 1")
            if side_zones != tuple(sorted(side_zones, key=_rank_sort_key)):
                raise ResonanceScoringEngineError(f"{side.value} zones violate deterministic ranking")
        frame_ids = tuple(sorted(item.evidence_id for item in self.source_frame.evidence))
        zone_ids = tuple(sorted(item_id for zone in self.zones for item_id in zone.member_evidence_ids))
        if zone_ids != frame_ids:
            raise ResonanceScoringEngineError(
                "score frame zones must exactly partition source Frame evidence"
            )
        evidence_by_id = {item.evidence_id: item for item in self.source_frame.evidence}
        for zone in self.zones:
            _validate_zone_against_frame(zone, evidence_by_id, self.source_frame, self.config_snapshot)
        tolerance = self.config_snapshot.effective_tolerance(self.source_frame.reference_price.price)
        for left, right in combinations(self.source_frame.evidence, 2):
            if left.boundary.boundary_side is not right.boundary.boundary_side:
                continue
            if _range_gap(left.boundary.price_range, right.boundary.price_range) <= tolerance:
                containing = [
                    zone for zone in self.zones
                    if left.evidence_id in zone.member_evidence_ids
                    or right.evidence_id in zone.member_evidence_ids
                ]
                if len(containing) != 1:
                    raise ResonanceScoringEngineError(
                        "directly connected same-side evidence cannot span zones"
                    )
        if not isinstance(self.report, ResonanceScoreReport):
            raise ResonanceScoringEngineError("score frame report type is invalid")
        expected_report = _report_for(self.source_frame, self.zones, self.config_snapshot)
        if self.report != expected_report:
            raise ResonanceScoringEngineError("score frame report contradicts frame facts")
        if not isinstance(self.provenance, ProvenanceRef):
            raise ResonanceScoringEngineError("score frame provenance type is invalid")
        expected_parents = tuple(sorted({
            self.source_frame_id,
            *(item.zone_snapshot_id for item in self.zones),
        }))
        if (
            self.provenance.source_module != _SCORING_MODULE
            or self.provenance.source_version != self.config_snapshot.engine_version
            or self.provenance.source_object_id != self.score_frame_id
            or self.provenance.policy_id != self.config_snapshot.policy_id
            or self.provenance.parent_object_ids != expected_parents
            or self.provenance.notes != (f"engine_id={self.config_snapshot.engine_id}",)
        ):
            raise ResonanceScoringEngineError("score frame provenance is inconsistent")
        expected_id = _score_frame_id(
            source_frame_id=self.source_frame_id,
            as_of_time=as_of.isoformat(),
            config=self.config_snapshot.to_dict(),
            zone_snapshot_ids=tuple(item.zone_snapshot_id for item in self.zones),
            report=self.report.to_dict(),
            schema_version=self.schema_version,
        )
        if self.score_frame_id != expected_id:
            raise ResonanceScoringEngineError("score_frame_id does not match exact payload")
        object.__setattr__(self, "as_of_time", as_of)

    @property
    def upper_zones(self) -> tuple[ResonanceZone, ...]:
        return tuple(item for item in self.zones if item.side is BoundarySide.UPPER)

    @property
    def lower_zones(self) -> tuple[ResonanceZone, ...]:
        return tuple(item for item in self.zones if item.side is BoundarySide.LOWER)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "score_frame_id": self.score_frame_id,
            "as_of_time": self.as_of_time.isoformat(),
            "source_frame_id": self.source_frame_id,
            "source_frame": self.source_frame.to_dict(),
            "zones": [item.to_dict() for item in self.zones],
            "report": self.report.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceScoreFrame:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                score_frame_id=data["score_frame_id"],
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                source_frame_id=data["source_frame_id"],
                source_frame=ResonanceFrame.from_dict(data["source_frame"]),
                zones=tuple(ResonanceZone.from_dict(item) for item in _ordered_list(data, cls.__name__, "zones")),
                report=ResonanceScoreReport.from_dict(data["report"]),
                config_snapshot=ResonanceScoringConfig.from_dict(data["config_snapshot"]),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceScoreHistory:
    frames: tuple[ResonanceScoreFrame, ...]
    final_frame: ResonanceScoreFrame
    source_history: ResonanceFrameHistory
    config_snapshot: ResonanceScoringConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceScoringEngineError)
        if not isinstance(self.frames, tuple) or not self.frames or any(not isinstance(item, ResonanceScoreFrame) for item in self.frames):
            raise ResonanceScoringEngineError("score history frames must be a non-empty tuple")
        if any(current.as_of_time <= previous.as_of_time for previous, current in zip(self.frames, self.frames[1:])):
            raise ResonanceScoringEngineError("score history times must be strictly increasing")
        if len({item.score_frame_id for item in self.frames}) != len(self.frames):
            raise ResonanceScoringEngineError("score history frame IDs must be unique")
        if not isinstance(self.final_frame, ResonanceScoreFrame) or self.final_frame != self.frames[-1]:
            raise ResonanceScoringEngineError("score history final_frame must equal the last frame")
        if not isinstance(self.source_history, ResonanceFrameHistory):
            raise ResonanceScoringEngineError("source_history must be a ResonanceFrameHistory")
        if not isinstance(self.config_snapshot, ResonanceScoringConfig):
            raise ResonanceScoringEngineError("score history config type is invalid")
        if any(item.config_snapshot != self.config_snapshot for item in self.frames):
            raise ResonanceScoringEngineError("score history configurations must be identical")
        source_ids = {item.frame_id for item in self.source_history.frames}
        scored_by_source = {item.source_frame_id: item for item in self.frames}
        if not source_ids.issubset(scored_by_source):
            raise ResonanceScoringEngineError("score history is missing an original source Frame")
        for source in self.source_history.frames:
            if scored_by_source[source.frame_id].source_frame != source:
                raise ResonanceScoringEngineError("score history source Frame mapping is inconsistent")
        if any(item.source_frame.config_snapshot != self.source_history.config_snapshot for item in self.frames):
            raise ResonanceScoringEngineError("score history contains incompatible source Frame config")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "frames": [item.to_dict() for item in self.frames],
            "final_frame": self.final_frame.to_dict(),
            "source_history": self.source_history.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceScoreHistory:
        data = _exact_payload(
            payload, cls.__name__,
            {"frames", "final_frame", "source_history", "config_snapshot"},
        )
        try:
            return cls(
                frames=tuple(ResonanceScoreFrame.from_dict(item) for item in _ordered_list(data, cls.__name__, "frames")),
                final_frame=ResonanceScoreFrame.from_dict(data["final_frame"]),
                source_history=ResonanceFrameHistory.from_dict(data["source_history"]),
                config_snapshot=ResonanceScoringConfig.from_dict(data["config_snapshot"]),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def _direction_relation(side: BoundarySide, direction: Direction) -> ResonanceDirectionRelation:
    if direction is Direction.RANGE:
        return ResonanceDirectionRelation.NEUTRAL
    if direction is Direction.TURNING:
        return ResonanceDirectionRelation.TURNING
    if direction is Direction.UNKNOWN:
        return ResonanceDirectionRelation.UNKNOWN
    aligned = (
        direction is Direction.DOWN
        if side is BoundarySide.UPPER
        else direction is Direction.UP
    )
    return (
        ResonanceDirectionRelation.ALIGNED
        if aligned
        else ResonanceDirectionRelation.OPPOSED
    )


def _direction_factor(
    relation: ResonanceDirectionRelation, config: ResonanceScoringConfig
) -> Decimal:
    return {
        ResonanceDirectionRelation.ALIGNED: config.aligned_direction_factor,
        ResonanceDirectionRelation.NEUTRAL: config.neutral_direction_factor,
        ResonanceDirectionRelation.TURNING: config.turning_direction_factor,
        ResonanceDirectionRelation.OPPOSED: config.opposed_direction_factor,
        ResonanceDirectionRelation.UNKNOWN: config.unknown_direction_factor,
    }[relation]


def _lifecycle_weight(state: LifecycleState, config: ResonanceScoringConfig) -> Decimal:
    return {
        LifecycleState.FRESH: config.fresh_lifecycle_weight,
        LifecycleState.TESTED: config.tested_lifecycle_weight,
        LifecycleState.WEAKENED: config.weakened_lifecycle_weight,
        LifecycleState.FLIPPED: config.flipped_lifecycle_weight,
    }[state]


def _dependency_partition(
    evidence: tuple[ResonanceEvidence, ...],
) -> tuple[tuple[ResonanceEvidence, ...], ...]:
    ordered = tuple(sorted(evidence, key=lambda item: item.evidence_id))
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        parent[max(left_root, right_root)] = min(left_root, right_root)

    for left, right in combinations(range(len(ordered)), 2):
        if set(ordered[left].structure_families) & set(ordered[right].structure_families):
            union(left, right)
    grouped: dict[int, list[ResonanceEvidence]] = {}
    for index, item in enumerate(ordered):
        grouped.setdefault(find(index), []).append(item)
    return tuple(
        sorted(
            (tuple(sorted(items, key=lambda item: item.evidence_id)) for items in grouped.values()),
            key=lambda items: tuple(item.evidence_id for item in items),
        )
    )


def _dependency_edges(
    evidence: tuple[ResonanceEvidence, ...],
) -> tuple[ResonanceDependencyEdge, ...]:
    result: list[ResonanceDependencyEdge] = []
    for left, right in combinations(sorted(evidence, key=lambda item: item.evidence_id), 2):
        shared = tuple(sorted(set(left.structure_families) & set(right.structure_families)))
        if shared:
            result.append(
                ResonanceDependencyEdge(
                    left_evidence_id=left.evidence_id,
                    right_evidence_id=right.evidence_id,
                    shared_family_ids=shared,
                )
            )
    return tuple(result)


def _shared_component_families(
    evidence: tuple[ResonanceEvidence, ...],
) -> tuple[str, ...]:
    shared: set[str] = set()
    for left, right in combinations(evidence, 2):
        shared.update(set(left.structure_families) & set(right.structure_families))
    return tuple(sorted(shared))


def _price_relation_and_distance(
    side: BoundarySide, price_range: PriceRange, price: Decimal
) -> tuple[ResonancePriceRelation, Decimal]:
    if price_range.low <= price <= price_range.high:
        return ResonancePriceRelation.CONTAINS_PRICE, Decimal("0")
    distance = price_range.low - price if price < price_range.low else price - price_range.high
    expected = (
        price_range.low > price
        if side is BoundarySide.UPPER
        else price_range.high < price
    )
    return (
        ResonancePriceRelation.EXPECTED_SIDE
        if expected
        else ResonancePriceRelation.OPPOSITE_SIDE,
        distance,
    )


def _validate_zone_against_frame(
    zone: ResonanceZone,
    evidence_by_id: Mapping[str, ResonanceEvidence],
    frame: ResonanceFrame,
    config: ResonanceScoringConfig,
) -> None:
    if zone.source_frame_id != frame.frame_id:
        raise ResonanceScoringEngineError(
            "zone source_frame_id must equal the authoritative source Frame"
        )
    try:
        members = tuple(evidence_by_id[item] for item in zone.member_evidence_ids)
    except KeyError as exc:
        raise ResonanceScoringEngineError(
            "zone references evidence absent from source Frame"
        ) from exc
    if any(item.boundary.boundary_side is not zone.side for item in members):
        raise ResonanceScoringEngineError("zone cannot mix BoundarySide values")
    expected_range = PriceRange(
        min(item.boundary.price_range.low for item in members),
        max(item.boundary.price_range.high for item in members),
    )
    if zone.price_range != expected_range:
        raise ResonanceScoringEngineError("zone price range is not the member envelope")
    expected_subjects = tuple(sorted(item.subject_id for item in members))
    expected_contexts = tuple(sorted({item.context for item in members}, key=_context_key))
    expected_context_weights = tuple(
        item for item in config.context_weights if item.context in expected_contexts
    )
    expected_sources = tuple(sorted({source for item in members for source in item.source_types}, key=lambda item: item.value))
    expected_families = tuple(sorted({family for item in members for family in item.structure_families}))
    if (
        zone.member_subject_ids != expected_subjects
        or zone.contexts != expected_contexts
        or zone.source_types != expected_sources
        or zone.structure_families != expected_families
    ):
        raise ResonanceScoringEngineError("zone member-derived facts are inconsistent")
    if (
        zone.explanation.member_contexts != expected_contexts
        or zone.explanation.context_weights != expected_context_weights
    ):
        raise ResonanceScoringEngineError(
            "zone explanation contexts or configured context weights are inconsistent"
        )
    if zone.explanation.dependency_repeat_credit != config.dependency_repeat_credit:
        raise ResonanceScoringEngineError(
            "zone explanation dependency repeat credit is inconsistent"
        )
    expected_counts = (
        sum(item.tier is ResonanceEvidenceTier.CANDIDATE for item in members),
        sum(item.tier is ResonanceEvidenceTier.CONFIRMED for item in members),
        sum(item.lifecycle_state is LifecycleState.FRESH for item in members),
        sum(item.lifecycle_state is LifecycleState.TESTED for item in members),
        sum(item.lifecycle_state is LifecycleState.WEAKENED for item in members),
        sum(item.lifecycle_state is LifecycleState.FLIPPED for item in members),
    )
    if expected_counts != (
        zone.candidate_count, zone.confirmed_count, zone.fresh_count,
        zone.tested_count, zone.weakened_count, zone.flipped_count,
    ):
        raise ResonanceScoringEngineError("zone Evidence counts are inconsistent")
    times = tuple(item.state_confirm_time for item in members)
    if zone.earliest_evidence_confirm_time != min(times) or zone.latest_evidence_confirm_time != max(times):
        raise ResonanceScoringEngineError("zone confirm-time bounds are inconsistent")
    effective_tolerance = config.effective_tolerance(frame.reference_price.price)
    if zone.explanation.effective_clustering_tolerance != effective_tolerance:
        raise ResonanceScoringEngineError("zone clustering tolerance is inconsistent")
    direct_gaps = tuple(
        ResonanceRangeGap(
            left_evidence_id=min(left.evidence_id, right.evidence_id),
            right_evidence_id=max(left.evidence_id, right.evidence_id),
            gap=_range_gap(left.boundary.price_range, right.boundary.price_range),
            directly_connected=_range_gap(left.boundary.price_range, right.boundary.price_range) <= effective_tolerance,
        )
        for left, right in combinations(sorted(members, key=lambda item: item.evidence_id), 2)
    )
    if zone.explanation.direct_member_gaps != direct_gaps:
        raise ResonanceScoringEngineError("zone direct member gaps are inconsistent")
    parent = {item.evidence_id: item.evidence_id for item in members}

    def find(item_id: str) -> str:
        while parent[item_id] != item_id:
            parent[item_id] = parent[parent[item_id]]
            item_id = parent[item_id]
        return item_id

    for gap in direct_gaps:
        if not gap.directly_connected:
            continue
        left_root, right_root = find(gap.left_evidence_id), find(gap.right_evidence_id)
        parent[max(left_root, right_root)] = min(left_root, right_root)
    if len({find(item.evidence_id) for item in members}) != 1:
        raise ResonanceScoringEngineError("zone members are not one SINGLE_LINK component")
    chain_bridged = len(members) > 2 and any(not item.directly_connected for item in direct_gaps)
    if zone.explanation.chain_bridged != chain_bridged:
        raise ResonanceScoringEngineError("zone chain-bridging fact is inconsistent")
    component_members = _dependency_partition(members)
    components_by_members = {item.member_evidence_ids: item for item in zone.dependency_components}
    contributions = {item.evidence_id: item for item in zone.contributions}
    for component_evidence in component_members:
        member_ids = tuple(item.evidence_id for item in component_evidence)
        shared_families = _shared_component_families(component_evidence)
        expected_component_id = _component_id(
            engine_id=config.engine_id,
            engine_version=config.engine_version,
            policy_id=config.policy_id,
            member_evidence_ids=member_ids,
            shared_family_ids=shared_families,
            schema_version=SCHEMA_VERSION,
        )
        component = components_by_members.get(member_ids)
        if component is None or component.component_id != expected_component_id or component.shared_family_ids != shared_families:
            raise ResonanceScoringEngineError("dependency component identity or families are inconsistent")
        component_contributions = tuple(contributions[item_id] for item_id in member_ids)
        ordered_contributions = tuple(sorted(component_contributions, key=lambda item: (-item.raw_contribution, item.evidence_id)))
        primary = ordered_contributions[0]
        repeated = sum((item.raw_contribution for item in ordered_contributions[1:]), Decimal("0"))
        if (
            component.primary_evidence_id != primary.evidence_id
            or component.primary_raw_contribution != primary.raw_contribution
            or component.repeated_raw_contribution != repeated
            or component.repeat_credit != config.dependency_repeat_credit
        ):
            raise ResonanceScoringEngineError("dependency component score facts are inconsistent")
        for evidence in component_evidence:
            contribution = contributions[evidence.evidence_id]
            relation = _direction_relation(zone.side, evidence.direction)
            age = _elapsed_seconds(frame.as_of_time - evidence.state_confirm_time)
            freshness = max(
                config.freshness_floor,
                Decimal("1") - age / config.freshness_horizon_seconds,
            )
            extra_touches = max(0, evidence.touch_count - 1)
            touch = max(
                config.touch_floor,
                Decimal("1") - Decimal(extra_touches) * config.touch_penalty_per_extra,
            )
            tier_weight = (
                config.candidate_tier_weight
                if evidence.tier is ResonanceEvidenceTier.CANDIDATE
                else config.confirmed_tier_weight
            )
            expected_values = (
                evidence.subject_id, evidence.lifecycle_state_id, evidence.context,
                zone.side, evidence.tier, evidence.lifecycle_state, evidence.direction,
                relation, config.context_weight(evidence.context), tier_weight,
                _lifecycle_weight(evidence.lifecycle_state, config), age, freshness,
                evidence.touch_count, extra_touches, touch,
                _direction_factor(relation, config), expected_component_id,
            )
            actual_values = (
                contribution.subject_id, contribution.lifecycle_state_id,
                contribution.context, contribution.side, contribution.tier,
                contribution.lifecycle_state, contribution.direction,
                contribution.direction_relation, contribution.context_weight,
                contribution.tier_weight, contribution.lifecycle_weight,
                contribution.age_seconds, contribution.freshness_factor,
                contribution.touch_count, contribution.extra_touches,
                contribution.touch_factor, contribution.direction_factor,
                contribution.dependency_component_id,
            )
            if actual_values != expected_values:
                raise ResonanceScoringEngineError("Evidence contribution facts are inconsistent")
            expected_contribution_id = _contribution_id(
                config=config.to_dict(),
                evidence_id=evidence.evidence_id,
                subject_id=evidence.subject_id,
                lifecycle_state_id=evidence.lifecycle_state_id,
                context=evidence.context.to_dict(),
                side=zone.side.value,
                tier=evidence.tier.value,
                lifecycle_state=evidence.lifecycle_state.value,
                direction=evidence.direction.value,
                direction_relation=relation.value,
                context_weight=str(contribution.context_weight),
                tier_weight=str(contribution.tier_weight),
                lifecycle_weight=str(contribution.lifecycle_weight),
                age_seconds=str(contribution.age_seconds),
                freshness_factor=str(contribution.freshness_factor),
                touch_count=contribution.touch_count,
                extra_touches=contribution.extra_touches,
                touch_factor=str(contribution.touch_factor),
                direction_factor=str(contribution.direction_factor),
                raw_contribution=str(contribution.raw_contribution),
                dependency_component_id=expected_component_id,
                schema_version=SCHEMA_VERSION,
            )
            if contribution.contribution_id != expected_contribution_id:
                raise ResonanceScoringEngineError("contribution_id does not match exact inputs")
    expected_dependency_edges = _dependency_edges(members)
    if zone.explanation.dependency_family_edges != expected_dependency_edges:
        raise ResonanceScoringEngineError("dependency family graph is inconsistent")
    expected_source_bonus = min(
        config.source_diversity_bonus_cap,
        Decimal(max(0, len(expected_sources) - 1)) * config.source_diversity_bonus_per_extra,
    )
    expected_context_bonus = min(
        config.context_diversity_bonus_cap,
        Decimal(max(0, len(expected_contexts) - 1)) * config.context_diversity_bonus_per_extra,
    )
    if zone.source_diversity_bonus != expected_source_bonus or zone.context_diversity_bonus != expected_context_bonus:
        raise ResonanceScoringEngineError("zone diversity bonus is inconsistent")
    price = frame.reference_price.price
    relation, distance = _price_relation_and_distance(zone.side, zone.price_range, price)
    horizon = config.distance_horizon(price)
    distance_factor = max(Decimal("0"), Decimal("1") - distance / horizon)
    placement = {
        ResonancePriceRelation.EXPECTED_SIDE: config.expected_side_factor,
        ResonancePriceRelation.CONTAINS_PRICE: config.contains_price_factor,
        ResonancePriceRelation.OPPOSITE_SIDE: config.opposite_side_factor,
    }[relation]
    if (
        zone.reference_price != price
        or zone.price_relation is not relation
        or zone.distance != distance
        or zone.distance_factor != distance_factor
        or zone.placement_factor != placement
        or zone.explanation.distance_horizon != horizon
    ):
        raise ResonanceScoringEngineError("zone price relation or distance facts are inconsistent")
    expected_class = (
        ResonanceClass.SINGLE
        if len(members) == 1
        else ResonanceClass.MULTI_CONTEXT_RESONANCE
        if len(members) >= config.minimum_resonant_evidence_count
        and len(expected_contexts) >= config.minimum_resonant_context_count
        else ResonanceClass.LOCAL_CLUSTER
    )
    if zone.resonance_class is not expected_class:
        raise ResonanceScoringEngineError("zone resonance class is inconsistent")
    expected_rationale = ResonanceClassRationale(
        evidence_count=len(members),
        distinct_context_count=len(expected_contexts),
        minimum_resonant_evidence_count=config.minimum_resonant_evidence_count,
        minimum_resonant_context_count=config.minimum_resonant_context_count,
        assigned_class=expected_class,
    )
    if zone.explanation.resonance_class_rationale != expected_rationale:
        raise ResonanceScoringEngineError(
            "zone explanation resonance class rationale is inconsistent"
        )
    member_boundary_ranges = tuple(
        {
            "subject_id": item.subject_id,
            "price_range": item.boundary.price_range.to_dict(),
        }
        for item in sorted(members, key=lambda item: item.subject_id)
    )
    expected_key = _zone_key_id(
        engine_id=config.engine_id,
        engine_version=config.engine_version,
        policy_id=config.policy_id,
        side=zone.side.value,
        price_range=zone.price_range.to_dict(),
        member_subject_ids=expected_subjects,
        member_boundary_ranges=member_boundary_ranges,
        schema_version=SCHEMA_VERSION,
    )
    if zone.zone_key_id != expected_key:
        raise ResonanceScoringEngineError("zone_key_id does not match structural identity")
    score_payload = {
        "dependency_adjusted_base_score": str(zone.dependency_adjusted_base_score),
        "source_diversity_bonus": str(zone.source_diversity_bonus),
        "context_diversity_bonus": str(zone.context_diversity_bonus),
        "quality_score": str(zone.quality_score),
        "reference_price": str(zone.reference_price),
        "distance_factor": str(zone.distance_factor),
        "placement_factor": str(zone.placement_factor),
        "selection_score": str(zone.selection_score),
    }
    expected_snapshot = _zone_snapshot_id(
        source_frame_id=frame.frame_id,
        config=config.to_dict(),
        zone_key_id=expected_key,
        member_evidence_ids=zone.member_evidence_ids,
        contribution_ids=tuple(item.contribution_id for item in zone.contributions),
        dependency_component_ids=tuple(item.component_id for item in zone.dependency_components),
        scores=score_payload,
        price_relation=zone.price_relation.value,
        distance=str(zone.distance),
        resonance_class=zone.resonance_class.value,
        schema_version=SCHEMA_VERSION,
    )
    if zone.zone_snapshot_id != expected_snapshot:
        raise ResonanceScoringEngineError("zone_snapshot_id does not match current observation")
    expected_parents = tuple(sorted({
        frame.frame_id,
        *zone.member_evidence_ids,
        *(item.contribution_id for item in zone.contributions),
        *(item.component_id for item in zone.dependency_components),
    }))
    if (
        zone.provenance.source_module != _SCORING_MODULE
        or zone.provenance.source_version != config.engine_version
        or zone.provenance.source_object_id != zone.zone_snapshot_id
        or zone.provenance.policy_id != config.policy_id
        or zone.provenance.parent_object_ids != expected_parents
        or zone.provenance.notes != (f"engine_id={config.engine_id}",)
    ):
        raise ResonanceScoringEngineError("zone provenance is inconsistent")
    expected_dependency_base = sum(
        (item.adjusted_component_score for item in zone.dependency_components),
        Decimal("0"),
    )
    expected_quality = (
        expected_dependency_base + expected_source_bonus + expected_context_bonus
    )
    expected_selection = expected_quality * distance_factor * placement
    expected_rank_key = ResonanceRankKey(
        selection_score=expected_selection,
        quality_score=expected_quality,
        distinct_context_count=len(expected_contexts),
        distinct_source_type_count=len(expected_sources),
        distance=distance,
        latest_evidence_confirm_time=max(times),
        zone_key_id=expected_key,
        zone_snapshot_id=expected_snapshot,
    )
    expected_explanation = ResonanceZoneExplanation(
        effective_clustering_tolerance=effective_tolerance,
        direct_member_gaps=direct_gaps,
        single_link_member_evidence_ids=zone.member_evidence_ids,
        chain_bridged=chain_bridged,
        member_evidence_ids=zone.member_evidence_ids,
        member_subject_ids=expected_subjects,
        member_contexts=expected_contexts,
        context_weights=expected_context_weights,
        contributions=zone.contributions,
        dependency_family_edges=expected_dependency_edges,
        dependency_components=zone.dependency_components,
        dependency_repeat_credit=config.dependency_repeat_credit,
        dependency_adjusted_base_score=expected_dependency_base,
        source_diversity_bonus=expected_source_bonus,
        context_diversity_bonus=expected_context_bonus,
        quality_score=expected_quality,
        reference_price=price,
        price_relation=relation,
        distance=distance,
        distance_horizon=horizon,
        distance_factor=distance_factor,
        placement_factor=placement,
        selection_score=expected_selection,
        resonance_class_rationale=expected_rationale,
        side_rank_key=expected_rank_key,
        assumptions=_ASSUMPTIONS,
    )
    if zone.explanation != expected_explanation:
        raise ResonanceScoringEngineError(
            "zone explanation does not match authoritative Frame and config facts"
        )
