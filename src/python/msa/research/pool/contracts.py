"""Immutable public contracts for deterministic C-005 Level Pool clustering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Self

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ScaleDescriptor,
    StructureCluster,
    StructureSourceType,
)

from .errors import (
    LevelPoolClusteringError,
    LevelPoolConfigurationError,
    LevelPoolInputError,
    LevelPoolSerializationError,
)


SCHEMA_VERSION = 1


def _exact_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise LevelPoolSerializationError(f"{object_name} payload must be a mapping")
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise LevelPoolSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise LevelPoolSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    version = payload["schema_version"]
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise LevelPoolSerializationError(
            f"{object_name}.schema_version must be {SCHEMA_VERSION}"
        )
    return payload


def _text(field_name: str, value: object, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def _finite_decimal(
    field_name: str,
    value: object,
    error_type: type[Exception],
    *,
    minimum: Decimal | None = None,
    exclusive: bool = False,
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise error_type(f"{field_name} must be a finite Decimal")
    if minimum is not None:
        invalid = value <= minimum if exclusive else value < minimum
        if invalid:
            operator = ">" if exclusive else ">="
            raise error_type(f"{field_name} must be {operator} {minimum}")
    return value


def _parse_decimal(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise LevelPoolSerializationError(
            f"{field_name} must be a Decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise LevelPoolSerializationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise LevelPoolSerializationError(f"{field_name} must be finite")
    return parsed


def _normalize_time(
    field_name: str, value: object, error_type: type[Exception]
) -> datetime:
    if not isinstance(value, datetime):
        raise error_type(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error_type(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(field_name: str, value: object) -> datetime:
    if not isinstance(value, str):
        raise LevelPoolSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LevelPoolSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    return _normalize_time(field_name, parsed, LevelPoolSerializationError)


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    return None if value is None else _parse_time(field_name, value)


def _ordered_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise LevelPoolSerializationError(
            f"{object_name}.{field_name} must be an ordered list"
        )
    return value


def _schema(value: object, object_name: str, error_type: type[Exception]) -> None:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error_type(f"{object_name}.schema_version must be {SCHEMA_VERSION}")


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


class _PoolEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact_payload(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise LevelPoolSerializationError(
                f"{cls.__name__}.value is unknown: {data['value']!r}"
            ) from exc


class ToleranceMode(_PoolEnum):
    """Supported explicit tolerance representations."""

    ABSOLUTE = "ABSOLUTE"
    NORMALIZED = "NORMALIZED"


class LinkageMode(_PoolEnum):
    """Supported graph linkage baselines."""

    SINGLE_LINK = "SINGLE_LINK"


@dataclass(frozen=True, slots=True)
class DependencyFamilyAssignment:
    """Caller-supplied evidence that a candidate belongs to a dependency family."""

    candidate_id: str
    dependency_family_id: str
    rationale: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, LevelPoolInputError)
        _text("candidate_id", self.candidate_id, LevelPoolInputError)
        _text("dependency_family_id", self.dependency_family_id, LevelPoolInputError)
        _text("rationale", self.rationale, LevelPoolInputError)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "dependency_family_id": self.dependency_family_id,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> DependencyFamilyAssignment:
        data = _exact_payload(
            payload,
            cls.__name__,
            {"candidate_id", "dependency_family_id", "rationale"},
        )
        try:
            return cls(
                candidate_id=data["candidate_id"],
                dependency_family_id=data["dependency_family_id"],
                rationale=data["rationale"],
                schema_version=data["schema_version"],
            )
        except LevelPoolInputError as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LevelPoolConfig:
    """Explicit immutable policy and output context for one Level Pool."""

    pool_id: str
    pool_version: str
    policy_id: str
    cluster_timeframe: Timeframe
    cluster_scale: ScaleDescriptor
    tolerance_mode: ToleranceMode
    absolute_tolerance: Decimal | None
    normalization_unit: Decimal | None
    normalized_tolerance: Decimal | None
    linkage_mode: LinkageMode
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolConfigurationError)
        for field_name in ("pool_id", "pool_version", "policy_id"):
            _text(field_name, getattr(self, field_name), LevelPoolConfigurationError)
        if not isinstance(self.cluster_timeframe, Timeframe):
            raise LevelPoolConfigurationError(
                "cluster_timeframe must be an explicit Timeframe"
            )
        if not isinstance(self.cluster_scale, ScaleDescriptor):
            raise LevelPoolConfigurationError(
                "cluster_scale must be an explicit ScaleDescriptor"
            )
        if not isinstance(self.tolerance_mode, ToleranceMode):
            raise LevelPoolConfigurationError(
                "tolerance_mode must be a supported ToleranceMode"
            )
        if not isinstance(self.linkage_mode, LinkageMode):
            raise LevelPoolConfigurationError(
                "linkage_mode must be a supported LinkageMode"
            )
        if self.linkage_mode is not LinkageMode.SINGLE_LINK:
            raise LevelPoolConfigurationError("only SINGLE_LINK is supported")
        if not isinstance(self.strict, bool):
            raise LevelPoolConfigurationError("strict must be a bool")
        if self.strict is not True:
            raise LevelPoolConfigurationError(
                "LevelPoolConfig.strict must be True; C-005 supports strict mode only"
            )
        if self.tolerance_mode is ToleranceMode.ABSOLUTE:
            _finite_decimal(
                "absolute_tolerance",
                self.absolute_tolerance,
                LevelPoolConfigurationError,
                minimum=Decimal(0),
            )
            if self.normalization_unit is not None or self.normalized_tolerance is not None:
                raise LevelPoolConfigurationError(
                    "ABSOLUTE mode requires normalization fields to be None"
                )
        elif self.tolerance_mode is ToleranceMode.NORMALIZED:
            if self.absolute_tolerance is not None:
                raise LevelPoolConfigurationError(
                    "NORMALIZED mode requires absolute_tolerance to be None"
                )
            _finite_decimal(
                "normalization_unit",
                self.normalization_unit,
                LevelPoolConfigurationError,
                minimum=Decimal(0),
                exclusive=True,
            )
            _finite_decimal(
                "normalized_tolerance",
                self.normalized_tolerance,
                LevelPoolConfigurationError,
                minimum=Decimal(0),
            )

    @property
    def effective_tolerance(self) -> Decimal:
        if self.tolerance_mode is ToleranceMode.ABSOLUTE:
            if self.absolute_tolerance is None:
                raise LevelPoolConfigurationError("missing absolute_tolerance")
            return self.absolute_tolerance
        if self.normalization_unit is None or self.normalized_tolerance is None:
            raise LevelPoolConfigurationError("missing normalized tolerance fields")
        return self.normalization_unit * self.normalized_tolerance

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pool_id": self.pool_id,
            "pool_version": self.pool_version,
            "policy_id": self.policy_id,
            "cluster_timeframe": self.cluster_timeframe.value,
            "cluster_scale": self.cluster_scale.to_dict(),
            "tolerance_mode": self.tolerance_mode.value,
            "absolute_tolerance": (
                None if self.absolute_tolerance is None else str(self.absolute_tolerance)
            ),
            "normalization_unit": (
                None if self.normalization_unit is None else str(self.normalization_unit)
            ),
            "normalized_tolerance": (
                None
                if self.normalized_tolerance is None
                else str(self.normalized_tolerance)
            ),
            "linkage_mode": self.linkage_mode.value,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelPoolConfig:
        fields = {
            "pool_id",
            "pool_version",
            "policy_id",
            "cluster_timeframe",
            "cluster_scale",
            "tolerance_mode",
            "absolute_tolerance",
            "normalization_unit",
            "normalized_tolerance",
            "linkage_mode",
            "strict",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            timeframe = Timeframe(data["cluster_timeframe"])
            scale = ScaleDescriptor.from_dict(data["cluster_scale"])
            tolerance_mode = ToleranceMode(data["tolerance_mode"])
            linkage_mode = LinkageMode(data["linkage_mode"])
            absolute = (
                None
                if data["absolute_tolerance"] is None
                else _parse_decimal("absolute_tolerance", data["absolute_tolerance"])
            )
            unit = (
                None
                if data["normalization_unit"] is None
                else _parse_decimal("normalization_unit", data["normalization_unit"])
            )
            normalized = (
                None
                if data["normalized_tolerance"] is None
                else _parse_decimal(
                    "normalized_tolerance", data["normalized_tolerance"]
                )
            )
            return cls(
                pool_id=data["pool_id"],
                pool_version=data["pool_version"],
                policy_id=data["policy_id"],
                cluster_timeframe=timeframe,
                cluster_scale=scale,
                tolerance_mode=tolerance_mode,
                absolute_tolerance=absolute,
                normalization_unit=unit,
                normalized_tolerance=normalized,
                linkage_mode=linkage_mode,
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolConfigurationError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LevelPoolInput:
    """Unordered set-like confirmed candidates plus explicit family evidence."""

    candidates: tuple[LevelCandidate, ...]
    family_assignments: tuple[DependencyFamilyAssignment, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolInputError)
        if not isinstance(self.candidates, tuple):
            raise LevelPoolInputError("candidates must be a LevelCandidate tuple")
        if not self.candidates:
            raise LevelPoolInputError("candidate pool must not be empty")
        if any(not isinstance(item, LevelCandidate) for item in self.candidates):
            raise LevelPoolInputError("every candidate must be a LevelCandidate")
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise LevelPoolInputError("candidate_id values must be unique")
        symbols = {item.symbol for item in self.candidates}
        if len(symbols) != 1:
            raise LevelPoolInputError("all candidates must have the same symbol")
        supported_sources = {
            StructureSourceType.SWING,
            StructureSourceType.PERIODIC_EXTREME,
            StructureSourceType.HISTORICAL_REACTION,
        }
        for candidate in self.candidates:
            if candidate.source_type not in supported_sources:
                raise LevelPoolInputError("unsupported candidate source_type")
            if (
                candidate.confirmation_status is not ConfirmationStatus.CONFIRMED
                or candidate.confirm_time is None
            ):
                raise LevelPoolInputError("all candidates must be CONFIRMED")
            if candidate.lifecycle_state is not LifecycleState.CONFIRMED:
                raise LevelPoolInputError(
                    "candidate lifecycle_state must be exactly CONFIRMED"
                )
            expected_role = (
                MarketRole.RESISTANCE
                if candidate.boundary_side is BoundarySide.UPPER
                else MarketRole.SUPPORT
            )
            if candidate.market_role is not expected_role:
                raise LevelPoolInputError("candidate side/role mapping is invalid")
        if not isinstance(self.family_assignments, tuple) or any(
            not isinstance(item, DependencyFamilyAssignment)
            for item in self.family_assignments
        ):
            raise LevelPoolInputError(
                "family_assignments must be a DependencyFamilyAssignment tuple"
            )
        by_id = {item.candidate_id: item for item in self.candidates}
        assigned_ids: set[str] = set()
        family_sides: dict[str, BoundarySide] = {}
        for assignment in self.family_assignments:
            if assignment.candidate_id not in by_id:
                raise LevelPoolInputError(
                    "family assignment references an unknown candidate_id"
                )
            if assignment.candidate_id in assigned_ids:
                raise LevelPoolInputError(
                    "a candidate may have at most one family assignment"
                )
            assigned_ids.add(assignment.candidate_id)
            side = by_id[assignment.candidate_id].boundary_side
            previous = family_sides.setdefault(assignment.dependency_family_id, side)
            if previous is not side:
                raise LevelPoolInputError(
                    "one dependency_family_id cannot span boundary sides"
                )
        implicit_ids = {
            f"candidate:{candidate_id}"
            for candidate_id in candidate_ids
            if candidate_id not in assigned_ids
        }
        if any(
            item.dependency_family_id in implicit_ids
            for item in self.family_assignments
        ):
            raise LevelPoolInputError(
                "explicit dependency family collides with an implicit family ID"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidates": [item.to_dict() for item in self.candidates],
            "family_assignments": [
                item.to_dict() for item in self.family_assignments
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelPoolInput:
        data = _exact_payload(
            payload, cls.__name__, {"candidates", "family_assignments"}
        )
        try:
            candidates = tuple(
                LevelCandidate.from_dict(item)
                for item in _ordered_list(data, cls.__name__, "candidates")
            )
            assignments = tuple(
                DependencyFamilyAssignment.from_dict(item)
                for item in _ordered_list(
                    data, cls.__name__, "family_assignments"
                )
            )
            return cls(candidates, assignments, data["schema_version"])
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolInputError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class DependencyGroup:
    """Dependency-family facts for the members of one price cluster."""

    dependency_family_id: str
    member_candidate_ids: tuple[str, ...]
    source_types: tuple[StructureSourceType, ...]
    timeframes: tuple[Timeframe, ...]
    structure_families: tuple[str, ...]
    explicit_assignment: bool
    rationales: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolClusteringError)
        _text(
            "dependency_family_id",
            self.dependency_family_id,
            LevelPoolClusteringError,
        )
        members = _text_tuple(
            name,
            "member_candidate_ids",
            self.member_candidate_ids,
            LevelPoolClusteringError,
            non_empty=True,
            unique=True,
            sort_values=True,
        )
        if not isinstance(self.source_types, tuple) or not self.source_types:
            raise LevelPoolClusteringError(
                "DependencyGroup.source_types must be a non-empty tuple"
            )
        if any(not isinstance(item, StructureSourceType) for item in self.source_types):
            raise LevelPoolClusteringError(
                "DependencyGroup.source_types must contain StructureSourceType"
            )
        sources = tuple(sorted(set(self.source_types), key=lambda item: item.value))
        if len(sources) != len(self.source_types):
            raise LevelPoolClusteringError(
                "DependencyGroup.source_types must contain unique values"
            )
        if not isinstance(self.timeframes, tuple) or not self.timeframes:
            raise LevelPoolClusteringError(
                "DependencyGroup.timeframes must be a non-empty tuple"
            )
        if any(not isinstance(item, Timeframe) for item in self.timeframes):
            raise LevelPoolClusteringError(
                "DependencyGroup.timeframes must contain Timeframe"
            )
        timeframes = tuple(sorted(set(self.timeframes), key=lambda item: item.value))
        if len(timeframes) != len(self.timeframes):
            raise LevelPoolClusteringError(
                "DependencyGroup.timeframes must contain unique values"
            )
        families = _text_tuple(
            name,
            "structure_families",
            self.structure_families,
            LevelPoolClusteringError,
            non_empty=True,
            unique=True,
            sort_values=True,
        )
        if not isinstance(self.explicit_assignment, bool):
            raise LevelPoolClusteringError("explicit_assignment must be a bool")
        rationales = _text_tuple(
            name,
            "rationales",
            self.rationales,
            LevelPoolClusteringError,
            non_empty=True,
            unique=True,
            sort_values=True,
        )
        object.__setattr__(self, "member_candidate_ids", members)
        object.__setattr__(self, "source_types", sources)
        object.__setattr__(self, "timeframes", timeframes)
        object.__setattr__(self, "structure_families", families)
        object.__setattr__(self, "rationales", rationales)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dependency_family_id": self.dependency_family_id,
            "member_candidate_ids": list(self.member_candidate_ids),
            "source_types": [item.value for item in self.source_types],
            "timeframes": [item.value for item in self.timeframes],
            "structure_families": list(self.structure_families),
            "explicit_assignment": self.explicit_assignment,
            "rationales": list(self.rationales),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DependencyGroup:
        fields = {
            "dependency_family_id",
            "member_candidate_ids",
            "source_types",
            "timeframes",
            "structure_families",
            "explicit_assignment",
            "rationales",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                dependency_family_id=data["dependency_family_id"],
                member_candidate_ids=tuple(
                    _ordered_list(data, cls.__name__, "member_candidate_ids")
                ),
                source_types=tuple(
                    StructureSourceType(item)
                    for item in _ordered_list(data, cls.__name__, "source_types")
                ),
                timeframes=tuple(
                    Timeframe(item)
                    for item in _ordered_list(data, cls.__name__, "timeframes")
                ),
                structure_families=tuple(
                    _ordered_list(data, cls.__name__, "structure_families")
                ),
                explicit_assignment=data["explicit_assignment"],
                rationales=tuple(
                    _ordered_list(data, cls.__name__, "rationales")
                ),
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ClusterExplanation:
    """Explainable member, family, source, time, and tolerance facts."""

    cluster_id: str
    member_candidate_ids: tuple[str, ...]
    raw_member_count: int
    dependency_family_count: int
    dependency_groups: tuple[DependencyGroup, ...]
    source_types: tuple[StructureSourceType, ...]
    timeframes: tuple[Timeframe, ...]
    member_scales: tuple[ScaleDescriptor, ...]
    structure_families: tuple[str, ...]
    boundary_side: BoundarySide
    price_range: PriceRange
    origin_time: datetime
    confirm_time: datetime
    effective_tolerance: Decimal
    tolerance_mode: ToleranceMode
    linkage_mode: LinkageMode
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolClusteringError)
        _text("cluster_id", self.cluster_id, LevelPoolClusteringError)
        members = _text_tuple(
            name,
            "member_candidate_ids",
            self.member_candidate_ids,
            LevelPoolClusteringError,
            non_empty=True,
            unique=True,
            sort_values=True,
        )
        for field_name in ("raw_member_count", "dependency_family_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise LevelPoolClusteringError(f"{field_name} must be >= 1")
        if self.raw_member_count != len(members):
            raise LevelPoolClusteringError(
                "raw_member_count must equal member_candidate_ids length"
            )
        if not isinstance(self.dependency_groups, tuple) or any(
            not isinstance(item, DependencyGroup) for item in self.dependency_groups
        ):
            raise LevelPoolClusteringError(
                "dependency_groups must be a DependencyGroup tuple"
            )
        groups = tuple(
            sorted(
                self.dependency_groups,
                key=lambda item: item.dependency_family_id,
            )
        )
        if len({item.dependency_family_id for item in groups}) != len(groups):
            raise LevelPoolClusteringError(
                "dependency_groups must have unique family IDs"
            )
        if self.dependency_family_count != len(groups):
            raise LevelPoolClusteringError(
                "dependency_family_count must equal dependency_groups length"
            )
        grouped_members = tuple(
            sorted(
                member
                for group in groups
                for member in group.member_candidate_ids
            )
        )
        if grouped_members != members:
            raise LevelPoolClusteringError(
                "dependency_groups must partition all cluster members exactly once"
            )
        if not isinstance(self.source_types, tuple) or any(
            not isinstance(item, StructureSourceType) for item in self.source_types
        ):
            raise LevelPoolClusteringError("source_types must be a tuple")
        sources = tuple(sorted(set(self.source_types), key=lambda item: item.value))
        if len(sources) != len(self.source_types):
            raise LevelPoolClusteringError("source_types must be unique")
        if not isinstance(self.timeframes, tuple) or any(
            not isinstance(item, Timeframe) for item in self.timeframes
        ):
            raise LevelPoolClusteringError("timeframes must be a tuple")
        timeframes = tuple(sorted(set(self.timeframes), key=lambda item: item.value))
        if len(timeframes) != len(self.timeframes):
            raise LevelPoolClusteringError("timeframes must be unique")
        if not isinstance(self.member_scales, tuple) or any(
            not isinstance(item, ScaleDescriptor) for item in self.member_scales
        ):
            raise LevelPoolClusteringError(
                "member_scales must be a ScaleDescriptor tuple"
            )
        scales = tuple(
            sorted(
                set(self.member_scales),
                key=lambda item: (item.scale_id, -1 if item.rank is None else item.rank),
            )
        )
        if len(scales) != len(self.member_scales):
            raise LevelPoolClusteringError("member_scales must be unique")
        families = _text_tuple(
            name,
            "structure_families",
            self.structure_families,
            LevelPoolClusteringError,
            non_empty=True,
            unique=True,
            sort_values=True,
        )
        if not isinstance(self.boundary_side, BoundarySide):
            raise LevelPoolClusteringError("boundary_side must be a BoundarySide")
        if not isinstance(self.price_range, PriceRange):
            raise LevelPoolClusteringError("price_range must be a PriceRange")
        origin = _normalize_time(
            "origin_time", self.origin_time, LevelPoolClusteringError
        )
        confirm = _normalize_time(
            "confirm_time", self.confirm_time, LevelPoolClusteringError
        )
        if confirm < origin:
            raise LevelPoolClusteringError("confirm_time must be >= origin_time")
        _finite_decimal(
            "effective_tolerance",
            self.effective_tolerance,
            LevelPoolClusteringError,
            minimum=Decimal(0),
        )
        if not isinstance(self.tolerance_mode, ToleranceMode):
            raise LevelPoolClusteringError("tolerance_mode must be a ToleranceMode")
        if self.linkage_mode is not LinkageMode.SINGLE_LINK:
            raise LevelPoolClusteringError("linkage_mode must be SINGLE_LINK")
        object.__setattr__(self, "member_candidate_ids", members)
        object.__setattr__(self, "dependency_groups", groups)
        object.__setattr__(self, "source_types", sources)
        object.__setattr__(self, "timeframes", timeframes)
        object.__setattr__(self, "member_scales", scales)
        object.__setattr__(self, "structure_families", families)
        object.__setattr__(self, "origin_time", origin)
        object.__setattr__(self, "confirm_time", confirm)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "cluster_id": self.cluster_id,
            "member_candidate_ids": list(self.member_candidate_ids),
            "raw_member_count": self.raw_member_count,
            "dependency_family_count": self.dependency_family_count,
            "dependency_groups": [item.to_dict() for item in self.dependency_groups],
            "source_types": [item.value for item in self.source_types],
            "timeframes": [item.value for item in self.timeframes],
            "member_scales": [item.to_dict() for item in self.member_scales],
            "structure_families": list(self.structure_families),
            "boundary_side": self.boundary_side.value,
            "price_range": self.price_range.to_dict(),
            "origin_time": self.origin_time.isoformat(),
            "confirm_time": self.confirm_time.isoformat(),
            "effective_tolerance": str(self.effective_tolerance),
            "tolerance_mode": self.tolerance_mode.value,
            "linkage_mode": self.linkage_mode.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ClusterExplanation:
        fields = {
            "cluster_id",
            "member_candidate_ids",
            "raw_member_count",
            "dependency_family_count",
            "dependency_groups",
            "source_types",
            "timeframes",
            "member_scales",
            "structure_families",
            "boundary_side",
            "price_range",
            "origin_time",
            "confirm_time",
            "effective_tolerance",
            "tolerance_mode",
            "linkage_mode",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                cluster_id=data["cluster_id"],
                member_candidate_ids=tuple(
                    _ordered_list(data, cls.__name__, "member_candidate_ids")
                ),
                raw_member_count=data["raw_member_count"],
                dependency_family_count=data["dependency_family_count"],
                dependency_groups=tuple(
                    DependencyGroup.from_dict(item)
                    for item in _ordered_list(
                        data, cls.__name__, "dependency_groups"
                    )
                ),
                source_types=tuple(
                    StructureSourceType(item)
                    for item in _ordered_list(data, cls.__name__, "source_types")
                ),
                timeframes=tuple(
                    Timeframe(item)
                    for item in _ordered_list(data, cls.__name__, "timeframes")
                ),
                member_scales=tuple(
                    ScaleDescriptor.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "member_scales")
                ),
                structure_families=tuple(
                    _ordered_list(data, cls.__name__, "structure_families")
                ),
                boundary_side=BoundarySide(data["boundary_side"]),
                price_range=PriceRange.from_dict(data["price_range"]),
                origin_time=_parse_time("origin_time", data["origin_time"]),
                confirm_time=_parse_time("confirm_time", data["confirm_time"]),
                effective_tolerance=_parse_decimal(
                    "effective_tolerance", data["effective_tolerance"]
                ),
                tolerance_mode=ToleranceMode(data["tolerance_mode"]),
                linkage_mode=LinkageMode(data["linkage_mode"]),
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def _count_pairs(
    object_name: str, field_name: str, value: object
) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, tuple):
        raise LevelPoolClusteringError(f"{field_name} must be a tuple")
    pairs: list[tuple[str, int]] = []
    for index, item in enumerate(value):
        if not isinstance(item, tuple) or len(item) != 2:
            raise LevelPoolClusteringError(
                f"{field_name}[{index}] must be a two-item tuple"
            )
        key = _text(
            f"{object_name}.{field_name}[{index}][0]",
            item[0],
            LevelPoolClusteringError,
        )
        count = item[1]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise LevelPoolClusteringError(
                f"{field_name}[{index}][1] must be a non-negative integer"
            )
        pairs.append((key, count))
    if len({key for key, _ in pairs}) != len(pairs):
        raise LevelPoolClusteringError(f"{field_name} keys must be unique")
    return tuple(sorted(pairs))


@dataclass(frozen=True, slots=True)
class LevelPoolReport:
    """Bounded audit summary for one Level Pool snapshot."""

    input_candidate_count: int
    visible_candidate_count: int
    upper_candidate_count: int
    lower_candidate_count: int
    cluster_count: int
    singleton_cluster_count: int
    merged_cluster_count: int
    graph_edge_count: int
    explicit_assignment_count: int
    implicit_family_count: int
    dependency_family_count: int
    split_dependency_family_count: int
    source_type_counts: tuple[tuple[str, int], ...]
    timeframe_counts: tuple[tuple[str, int], ...]
    structure_family_count: int
    earliest_candidate_origin_time: datetime | None
    latest_candidate_origin_time: datetime | None
    earliest_candidate_confirm_time: datetime | None
    latest_candidate_confirm_time: datetime | None
    earliest_cluster_confirm_time: datetime | None
    latest_cluster_confirm_time: datetime | None
    tolerance_mode: ToleranceMode
    effective_tolerance: Decimal
    linkage_mode: LinkageMode
    pool_id: str
    pool_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolClusteringError)
        count_fields = (
            "input_candidate_count",
            "visible_candidate_count",
            "upper_candidate_count",
            "lower_candidate_count",
            "cluster_count",
            "singleton_cluster_count",
            "merged_cluster_count",
            "graph_edge_count",
            "explicit_assignment_count",
            "implicit_family_count",
            "dependency_family_count",
            "split_dependency_family_count",
            "structure_family_count",
        )
        for field_name in count_fields:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LevelPoolClusteringError(
                    f"{field_name} must be a non-negative integer"
                )
        if self.visible_candidate_count > self.input_candidate_count:
            raise LevelPoolClusteringError(
                "visible_candidate_count cannot exceed input_candidate_count"
            )
        if self.upper_candidate_count + self.lower_candidate_count != self.visible_candidate_count:
            raise LevelPoolClusteringError(
                "side counts must equal visible_candidate_count"
            )
        if self.singleton_cluster_count + self.merged_cluster_count != self.cluster_count:
            raise LevelPoolClusteringError(
                "singleton and merged counts must equal cluster_count"
            )
        source_counts = _count_pairs(name, "source_type_counts", self.source_type_counts)
        timeframe_counts = _count_pairs(name, "timeframe_counts", self.timeframe_counts)
        if sum(count for _, count in source_counts) != self.visible_candidate_count:
            raise LevelPoolClusteringError(
                "source_type_counts must sum to visible_candidate_count"
            )
        if sum(count for _, count in timeframe_counts) != self.visible_candidate_count:
            raise LevelPoolClusteringError(
                "timeframe_counts must sum to visible_candidate_count"
            )
        time_fields = (
            "earliest_candidate_origin_time",
            "latest_candidate_origin_time",
            "earliest_candidate_confirm_time",
            "latest_candidate_confirm_time",
            "earliest_cluster_confirm_time",
            "latest_cluster_confirm_time",
        )
        for field_name in time_fields:
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _normalize_time(field_name, value, LevelPoolClusteringError),
                )
        if not isinstance(self.tolerance_mode, ToleranceMode):
            raise LevelPoolClusteringError("tolerance_mode must be a ToleranceMode")
        _finite_decimal(
            "effective_tolerance",
            self.effective_tolerance,
            LevelPoolClusteringError,
            minimum=Decimal(0),
        )
        if self.linkage_mode is not LinkageMode.SINGLE_LINK:
            raise LevelPoolClusteringError("linkage_mode must be SINGLE_LINK")
        for field_name in ("pool_id", "pool_version", "policy_id"):
            _text(field_name, getattr(self, field_name), LevelPoolClusteringError)
        for field_name in ("assumptions", "warnings", "errors"):
            normalized = _text_tuple(
                name,
                field_name,
                getattr(self, field_name),
                LevelPoolClusteringError,
            )
            object.__setattr__(self, field_name, normalized)
        object.__setattr__(self, "source_type_counts", source_counts)
        object.__setattr__(self, "timeframe_counts", timeframe_counts)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        for field_name in (
            "input_candidate_count",
            "visible_candidate_count",
            "upper_candidate_count",
            "lower_candidate_count",
            "cluster_count",
            "singleton_cluster_count",
            "merged_cluster_count",
            "graph_edge_count",
            "explicit_assignment_count",
            "implicit_family_count",
            "dependency_family_count",
            "split_dependency_family_count",
            "structure_family_count",
        ):
            result[field_name] = getattr(self, field_name)
        result["source_type_counts"] = [list(item) for item in self.source_type_counts]
        result["timeframe_counts"] = [list(item) for item in self.timeframe_counts]
        for field_name in (
            "earliest_candidate_origin_time",
            "latest_candidate_origin_time",
            "earliest_candidate_confirm_time",
            "latest_candidate_confirm_time",
            "earliest_cluster_confirm_time",
            "latest_cluster_confirm_time",
        ):
            value = getattr(self, field_name)
            result[field_name] = None if value is None else value.isoformat()
        result.update(
            {
                "tolerance_mode": self.tolerance_mode.value,
                "effective_tolerance": str(self.effective_tolerance),
                "linkage_mode": self.linkage_mode.value,
                "pool_id": self.pool_id,
                "pool_version": self.pool_version,
                "policy_id": self.policy_id,
                "assumptions": list(self.assumptions),
                "warnings": list(self.warnings),
                "errors": list(self.errors),
            }
        )
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelPoolReport:
        fields = {
            "input_candidate_count",
            "visible_candidate_count",
            "upper_candidate_count",
            "lower_candidate_count",
            "cluster_count",
            "singleton_cluster_count",
            "merged_cluster_count",
            "graph_edge_count",
            "explicit_assignment_count",
            "implicit_family_count",
            "dependency_family_count",
            "split_dependency_family_count",
            "source_type_counts",
            "timeframe_counts",
            "structure_family_count",
            "earliest_candidate_origin_time",
            "latest_candidate_origin_time",
            "earliest_candidate_confirm_time",
            "latest_candidate_confirm_time",
            "earliest_cluster_confirm_time",
            "latest_cluster_confirm_time",
            "tolerance_mode",
            "effective_tolerance",
            "linkage_mode",
            "pool_id",
            "pool_version",
            "policy_id",
            "assumptions",
            "warnings",
            "errors",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            raw_source_counts = _ordered_list(
                data, cls.__name__, "source_type_counts"
            )
            raw_timeframe_counts = _ordered_list(
                data, cls.__name__, "timeframe_counts"
            )
            if any(not isinstance(item, list) for item in raw_source_counts):
                raise LevelPoolSerializationError(
                    "source_type_counts entries must be ordered lists"
                )
            if any(not isinstance(item, list) for item in raw_timeframe_counts):
                raise LevelPoolSerializationError(
                    "timeframe_counts entries must be ordered lists"
                )
            kwargs = {
                key: data[key]
                for key in (
                    "input_candidate_count",
                    "visible_candidate_count",
                    "upper_candidate_count",
                    "lower_candidate_count",
                    "cluster_count",
                    "singleton_cluster_count",
                    "merged_cluster_count",
                    "graph_edge_count",
                    "explicit_assignment_count",
                    "implicit_family_count",
                    "dependency_family_count",
                    "split_dependency_family_count",
                    "structure_family_count",
                    "pool_id",
                    "pool_version",
                    "policy_id",
                )
            }
            return cls(
                **kwargs,
                source_type_counts=tuple(tuple(item) for item in raw_source_counts),
                timeframe_counts=tuple(tuple(item) for item in raw_timeframe_counts),
                earliest_candidate_origin_time=_parse_optional_time(
                    "earliest_candidate_origin_time",
                    data["earliest_candidate_origin_time"],
                ),
                latest_candidate_origin_time=_parse_optional_time(
                    "latest_candidate_origin_time",
                    data["latest_candidate_origin_time"],
                ),
                earliest_candidate_confirm_time=_parse_optional_time(
                    "earliest_candidate_confirm_time",
                    data["earliest_candidate_confirm_time"],
                ),
                latest_candidate_confirm_time=_parse_optional_time(
                    "latest_candidate_confirm_time",
                    data["latest_candidate_confirm_time"],
                ),
                earliest_cluster_confirm_time=_parse_optional_time(
                    "earliest_cluster_confirm_time",
                    data["earliest_cluster_confirm_time"],
                ),
                latest_cluster_confirm_time=_parse_optional_time(
                    "latest_cluster_confirm_time",
                    data["latest_cluster_confirm_time"],
                ),
                tolerance_mode=ToleranceMode(data["tolerance_mode"]),
                effective_tolerance=_parse_decimal(
                    "effective_tolerance", data["effective_tolerance"]
                ),
                linkage_mode=LinkageMode(data["linkage_mode"]),
                assumptions=tuple(
                    _ordered_list(data, cls.__name__, "assumptions")
                ),
                warnings=tuple(_ordered_list(data, cls.__name__, "warnings")),
                errors=tuple(_ordered_list(data, cls.__name__, "errors")),
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LevelPoolSnapshot:
    """Immutable As-Of cluster state and its bounded explanation/report."""

    snapshot_id: str
    as_of_time: datetime
    visible_candidate_ids: tuple[str, ...]
    clusters: tuple[StructureCluster, ...]
    explanations: tuple[ClusterExplanation, ...]
    report: LevelPoolReport
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolClusteringError)
        _text("snapshot_id", self.snapshot_id, LevelPoolClusteringError)
        as_of = _normalize_time(
            "as_of_time", self.as_of_time, LevelPoolClusteringError
        )
        visible = _text_tuple(
            name,
            "visible_candidate_ids",
            self.visible_candidate_ids,
            LevelPoolClusteringError,
            unique=True,
            sort_values=True,
        )
        if not isinstance(self.clusters, tuple) or any(
            not isinstance(item, StructureCluster) for item in self.clusters
        ):
            raise LevelPoolClusteringError(
                "clusters must be a StructureCluster tuple"
            )
        clusters = tuple(sorted(self.clusters, key=lambda item: item.cluster_id))
        if len({item.cluster_id for item in clusters}) != len(clusters):
            raise LevelPoolClusteringError("cluster IDs must be unique")
        if any(item.confirm_time > as_of for item in clusters):
            raise LevelPoolClusteringError(
                "cluster.confirm_time cannot exceed snapshot.as_of_time"
            )
        if not isinstance(self.explanations, tuple) or any(
            not isinstance(item, ClusterExplanation)
            for item in self.explanations
        ):
            raise LevelPoolClusteringError(
                "explanations must be a ClusterExplanation tuple"
            )
        explanations = tuple(
            sorted(self.explanations, key=lambda item: item.cluster_id)
        )
        if tuple(item.cluster_id for item in explanations) != tuple(
            item.cluster_id for item in clusters
        ):
            raise LevelPoolClusteringError(
                "ClusterExplanation must correspond one-to-one with clusters"
            )
        if not isinstance(self.report, LevelPoolReport):
            raise LevelPoolClusteringError("report must be a LevelPoolReport")
        if self.report.visible_candidate_count != len(visible):
            raise LevelPoolClusteringError(
                "report visible count must equal visible_candidate_ids"
            )
        if self.report.cluster_count != len(clusters):
            raise LevelPoolClusteringError(
                "report cluster count must equal clusters length"
            )
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "visible_candidate_ids", visible)
        object.__setattr__(self, "clusters", clusters)
        object.__setattr__(self, "explanations", explanations)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "as_of_time": self.as_of_time.isoformat(),
            "visible_candidate_ids": list(self.visible_candidate_ids),
            "clusters": [item.to_dict() for item in self.clusters],
            "explanations": [item.to_dict() for item in self.explanations],
            "report": self.report.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelPoolSnapshot:
        data = _exact_payload(
            payload,
            cls.__name__,
            {
                "snapshot_id",
                "as_of_time",
                "visible_candidate_ids",
                "clusters",
                "explanations",
                "report",
            },
        )
        try:
            return cls(
                snapshot_id=data["snapshot_id"],
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                visible_candidate_ids=tuple(
                    _ordered_list(data, cls.__name__, "visible_candidate_ids")
                ),
                clusters=tuple(
                    StructureCluster.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "clusters")
                ),
                explanations=tuple(
                    ClusterExplanation.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "explanations")
                ),
                report=LevelPoolReport.from_dict(data["report"]),
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ClusterFormationEvent:
    """First immutable formation of a cluster snapshot and prior lineage."""

    first_seen_time: datetime
    cluster: StructureCluster
    supersedes_cluster_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolClusteringError)
        first_seen = _normalize_time(
            "first_seen_time", self.first_seen_time, LevelPoolClusteringError
        )
        if not isinstance(self.cluster, StructureCluster):
            raise LevelPoolClusteringError("cluster must be a StructureCluster")
        if first_seen != self.cluster.confirm_time:
            raise LevelPoolClusteringError(
                "first_seen_time must equal cluster.confirm_time"
            )
        supersedes = _text_tuple(
            name,
            "supersedes_cluster_ids",
            self.supersedes_cluster_ids,
            LevelPoolClusteringError,
            unique=True,
            sort_values=True,
        )
        if self.cluster.cluster_id in supersedes:
            raise LevelPoolClusteringError("a cluster cannot supersede itself")
        object.__setattr__(self, "first_seen_time", first_seen)
        object.__setattr__(self, "supersedes_cluster_ids", supersedes)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "first_seen_time": self.first_seen_time.isoformat(),
            "cluster": self.cluster.to_dict(),
            "supersedes_cluster_ids": list(self.supersedes_cluster_ids),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ClusterFormationEvent:
        data = _exact_payload(
            payload,
            cls.__name__,
            {"first_seen_time", "cluster", "supersedes_cluster_ids"},
        )
        try:
            return cls(
                first_seen_time=_parse_time(
                    "first_seen_time", data["first_seen_time"]
                ),
                cluster=StructureCluster.from_dict(data["cluster"]),
                supersedes_cluster_ids=tuple(
                    _ordered_list(
                        data, cls.__name__, "supersedes_cluster_ids"
                    )
                ),
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LevelPoolHistory:
    """Deterministic first-formation events and the final batch snapshot."""

    formation_events: tuple[ClusterFormationEvent, ...]
    final_snapshot: LevelPoolSnapshot
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LevelPoolClusteringError)
        if not isinstance(self.formation_events, tuple) or any(
            not isinstance(item, ClusterFormationEvent)
            for item in self.formation_events
        ):
            raise LevelPoolClusteringError(
                "formation_events must be a ClusterFormationEvent tuple"
            )
        expected = tuple(
            sorted(
                self.formation_events,
                key=lambda item: (item.first_seen_time, item.cluster.cluster_id),
            )
        )
        if expected != self.formation_events:
            raise LevelPoolClusteringError(
                "formation_events must be ordered by first_seen_time and cluster_id"
            )
        if len({item.cluster.cluster_id for item in expected}) != len(expected):
            raise LevelPoolClusteringError(
                "formation_events must contain each cluster ID at most once"
            )
        if not isinstance(self.final_snapshot, LevelPoolSnapshot):
            raise LevelPoolClusteringError(
                "final_snapshot must be a LevelPoolSnapshot"
            )
        if any(
            item.first_seen_time > self.final_snapshot.as_of_time
            for item in expected
        ):
            raise LevelPoolClusteringError(
                "formation event cannot follow final snapshot"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "formation_events": [
                item.to_dict() for item in self.formation_events
            ],
            "final_snapshot": self.final_snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelPoolHistory:
        data = _exact_payload(
            payload, cls.__name__, {"formation_events", "final_snapshot"}
        )
        try:
            return cls(
                formation_events=tuple(
                    ClusterFormationEvent.from_dict(item)
                    for item in _ordered_list(
                        data, cls.__name__, "formation_events"
                    )
                ),
                final_snapshot=LevelPoolSnapshot.from_dict(
                    data["final_snapshot"]
                ),
                schema_version=data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc
