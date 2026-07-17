"""Immutable C-002 domain models with causal event-time semantics.

The classes in this module validate caller-supplied facts. They do not detect
structures, cluster levels, transition lifecycle state, or select Active Boxes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from msa.data.contracts import Timeframe

from .enums import (
    ActiveBoxStatus,
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    StructureObjectKind,
    StructureSourceType,
)
from .errors import (
    DomainAvailabilityError,
    DomainSerializationError,
    DomainValidationError,
)
from .primitives import (
    SCHEMA_VERSION,
    PriceRange,
    ScaleDescriptor,
    _canonical_enum_tuple,
    _canonical_text_tuple,
    _deserialize_datetime,
    _deserialize_decimal,
    _deserialize_enum,
    _deserialize_list,
    _deserialize_optional_datetime,
    _normalize_optional_utc_datetime,
    _normalize_utc_datetime,
    _require_decimal,
    _require_instance,
    _require_int,
    _require_non_empty_text,
    _require_tuple,
    _strict_payload,
    _wrap_validation,
)
from .provenance import ProvenanceRef


def _serialize_datetime(value: datetime) -> str:
    return value.isoformat()


def _serialize_optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _require_available(
    object_name: str,
    object_id: str,
    processing_time: datetime,
    available_time: datetime,
) -> None:
    normalized = _normalize_utc_datetime(
        object_name, "processing_time", processing_time
    )
    if normalized < available_time:
        raise DomainAvailabilityError(
            f"{object_name} {object_id!r} is not available at processing_time; "
            f"confirm_time is {available_time.isoformat()}"
        )


@dataclass(frozen=True, slots=True)
class BoundaryRef:
    """Causal snapshot of a confirmed candidate or cluster boundary."""

    object_kind: StructureObjectKind
    object_id: str
    symbol: str
    timeframe: Timeframe
    scale: ScaleDescriptor
    price_range: PriceRange
    boundary_side: BoundarySide
    market_role: MarketRole
    lifecycle_state: LifecycleState
    origin_time: datetime
    confirm_time: datetime
    source_types: tuple[StructureSourceType, ...]
    structure_families: tuple[str, ...]
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        object_name = type(self).__name__
        _require_instance(
            object_name, "object_kind", self.object_kind, StructureObjectKind
        )
        _require_non_empty_text(object_name, "object_id", self.object_id)
        _require_non_empty_text(object_name, "symbol", self.symbol)
        _require_instance(object_name, "timeframe", self.timeframe, Timeframe)
        _require_instance(object_name, "scale", self.scale, ScaleDescriptor)
        _require_instance(
            object_name, "price_range", self.price_range, PriceRange
        )
        _require_instance(
            object_name, "boundary_side", self.boundary_side, BoundarySide
        )
        _require_instance(object_name, "market_role", self.market_role, MarketRole)
        _require_instance(
            object_name, "lifecycle_state", self.lifecycle_state, LifecycleState
        )
        if self.lifecycle_state is LifecycleState.CANDIDATE:
            raise DomainValidationError(
                "BoundaryRef.lifecycle_state cannot be CANDIDATE because "
                "forming objects cannot be referenced"
            )
        origin = _normalize_utc_datetime(object_name, "origin_time", self.origin_time)
        confirm = _normalize_utc_datetime(
            object_name, "confirm_time", self.confirm_time
        )
        if confirm < origin:
            raise DomainValidationError(
                "BoundaryRef.confirm_time must be >= BoundaryRef.origin_time"
            )
        source_types = _canonical_enum_tuple(
            object_name,
            "source_types",
            self.source_types,
            StructureSourceType,
            non_empty=True,
        )
        families = _canonical_text_tuple(
            object_name,
            "structure_families",
            self.structure_families,
            non_empty=True,
            unique=True,
            sort_values=True,
        )
        _require_instance(
            object_name, "provenance", self.provenance, ProvenanceRef
        )
        object.__setattr__(self, "origin_time", origin)
        object.__setattr__(self, "confirm_time", confirm)
        object.__setattr__(self, "source_types", source_types)
        object.__setattr__(self, "structure_families", families)

    def is_confirmed_at(self, processing_time: datetime) -> bool:
        normalized = _normalize_utc_datetime(
            type(self).__name__, "processing_time", processing_time
        )
        return normalized >= self.confirm_time

    def require_confirmed_at(self, processing_time: datetime) -> BoundaryRef:
        _require_available(
            type(self).__name__,
            self.object_id,
            processing_time,
            self.confirm_time,
        )
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "object_kind": self.object_kind.value,
            "object_id": self.object_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "scale": self.scale.to_dict(),
            "price_range": self.price_range.to_dict(),
            "boundary_side": self.boundary_side.value,
            "market_role": self.market_role.value,
            "lifecycle_state": self.lifecycle_state.value,
            "origin_time": _serialize_datetime(self.origin_time),
            "confirm_time": _serialize_datetime(self.confirm_time),
            "source_types": [item.value for item in self.source_types],
            "structure_families": list(self.structure_families),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BoundaryRef:
        object_name = cls.__name__
        fields = {
            "object_kind",
            "object_id",
            "symbol",
            "timeframe",
            "scale",
            "price_range",
            "boundary_side",
            "market_role",
            "lifecycle_state",
            "origin_time",
            "confirm_time",
            "source_types",
            "structure_families",
            "provenance",
        }
        data = _strict_payload(payload, object_name, fields)
        try:
            raw_sources = _deserialize_list(data, object_name, "source_types")
            return cls(
                object_kind=_deserialize_enum(
                    data, object_name, "object_kind", StructureObjectKind
                ),
                object_id=data["object_id"],
                symbol=data["symbol"],
                timeframe=_deserialize_enum(
                    data, object_name, "timeframe", Timeframe
                ),
                scale=ScaleDescriptor.from_dict(data["scale"]),
                price_range=PriceRange.from_dict(data["price_range"]),
                boundary_side=_deserialize_enum(
                    data, object_name, "boundary_side", BoundarySide
                ),
                market_role=_deserialize_enum(
                    data, object_name, "market_role", MarketRole
                ),
                lifecycle_state=_deserialize_enum(
                    data, object_name, "lifecycle_state", LifecycleState
                ),
                origin_time=_deserialize_datetime(data, object_name, "origin_time"),
                confirm_time=_deserialize_datetime(
                    data, object_name, "confirm_time"
                ),
                source_types=tuple(
                    StructureSourceType(item) for item in raw_sources
                ),
                structure_families=tuple(
                    _deserialize_list(data, object_name, "structure_families")
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)
        except (TypeError, ValueError) as exc:
            raise DomainSerializationError(
                f"invalid serialized {object_name}.source_types: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LevelCandidate:
    """Immutable structural candidate facts without detection behavior."""

    candidate_id: str
    symbol: str
    timeframe: Timeframe
    scale: ScaleDescriptor
    price_range: PriceRange
    source_type: StructureSourceType
    boundary_side: BoundarySide
    market_role: MarketRole
    confirmation_status: ConfirmationStatus
    lifecycle_state: LifecycleState
    origin_time: datetime
    confirm_time: datetime | None
    touch_count: int
    last_touch_time: datetime | None
    last_touch_confirm_time: datetime | None
    break_time: datetime | None
    break_confirm_time: datetime | None
    structure_family: str
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        object_name = type(self).__name__
        _require_non_empty_text(object_name, "candidate_id", self.candidate_id)
        _require_non_empty_text(object_name, "symbol", self.symbol)
        _require_instance(object_name, "timeframe", self.timeframe, Timeframe)
        _require_instance(object_name, "scale", self.scale, ScaleDescriptor)
        _require_instance(
            object_name, "price_range", self.price_range, PriceRange
        )
        _require_instance(
            object_name, "source_type", self.source_type, StructureSourceType
        )
        _require_instance(
            object_name, "boundary_side", self.boundary_side, BoundarySide
        )
        _require_instance(object_name, "market_role", self.market_role, MarketRole)
        _require_instance(
            object_name,
            "confirmation_status",
            self.confirmation_status,
            ConfirmationStatus,
        )
        _require_instance(
            object_name, "lifecycle_state", self.lifecycle_state, LifecycleState
        )
        origin = _normalize_utc_datetime(object_name, "origin_time", self.origin_time)
        confirm = _normalize_optional_utc_datetime(
            object_name, "confirm_time", self.confirm_time
        )
        if self.confirmation_status is ConfirmationStatus.FORMING:
            if confirm is not None:
                raise DomainValidationError(
                    "LevelCandidate.confirm_time must be None when "
                    "confirmation_status is FORMING"
                )
            if self.lifecycle_state is not LifecycleState.CANDIDATE:
                raise DomainValidationError(
                    "LevelCandidate.lifecycle_state must be CANDIDATE when "
                    "confirmation_status is FORMING"
                )
        else:
            if confirm is None:
                raise DomainValidationError(
                    "LevelCandidate.confirm_time is required when "
                    "confirmation_status is CONFIRMED"
                )
            if confirm < origin:
                raise DomainValidationError(
                    "LevelCandidate.confirm_time must be >= "
                    "LevelCandidate.origin_time"
                )
            if self.lifecycle_state is LifecycleState.CANDIDATE:
                raise DomainValidationError(
                    "LevelCandidate.lifecycle_state cannot be CANDIDATE when "
                    "confirmation_status is CONFIRMED"
                )

        touch_count = _require_int(
            object_name, "touch_count", self.touch_count, minimum=0
        )
        last_touch = _normalize_optional_utc_datetime(
            object_name, "last_touch_time", self.last_touch_time
        )
        last_touch_confirm = _normalize_optional_utc_datetime(
            object_name,
            "last_touch_confirm_time",
            self.last_touch_confirm_time,
        )
        if touch_count == 0 and (
            last_touch is not None or last_touch_confirm is not None
        ):
            raise DomainValidationError(
                "LevelCandidate last-touch fields must be None when touch_count is 0"
            )
        if touch_count > 0 and (
            last_touch is None or last_touch_confirm is None
        ):
            raise DomainValidationError(
                "LevelCandidate last_touch_time and last_touch_confirm_time are "
                "both required when touch_count is positive"
            )
        if (
            last_touch is not None
            and last_touch_confirm is not None
            and last_touch_confirm < last_touch
        ):
            raise DomainValidationError(
                "LevelCandidate.last_touch_confirm_time must be >= "
                "LevelCandidate.last_touch_time"
            )
        if last_touch is not None and last_touch < origin:
            raise DomainValidationError(
                "LevelCandidate.last_touch_time must be >= "
                "LevelCandidate.origin_time"
            )
        if last_touch_confirm is not None and (
            confirm is None or last_touch_confirm > confirm
        ):
            raise DomainValidationError(
                "LevelCandidate.last_touch_confirm_time must be <= "
                "LevelCandidate.confirm_time"
            )

        break_time = _normalize_optional_utc_datetime(
            object_name, "break_time", self.break_time
        )
        break_confirm = _normalize_optional_utc_datetime(
            object_name, "break_confirm_time", self.break_confirm_time
        )
        if (break_time is None) != (break_confirm is None):
            raise DomainValidationError(
                "LevelCandidate.break_time and break_confirm_time must both be "
                "None or both be present"
            )
        if (
            break_time is not None
            and break_confirm is not None
            and break_confirm < break_time
        ):
            raise DomainValidationError(
                "LevelCandidate.break_confirm_time must be >= "
                "LevelCandidate.break_time"
            )
        if break_time is not None and break_time < origin:
            raise DomainValidationError(
                "LevelCandidate.break_time must be >= LevelCandidate.origin_time"
            )
        if break_confirm is not None and (
            confirm is None or break_confirm > confirm
        ):
            raise DomainValidationError(
                "LevelCandidate.break_confirm_time must be <= "
                "LevelCandidate.confirm_time"
            )
        _require_non_empty_text(
            object_name, "structure_family", self.structure_family
        )
        _require_instance(
            object_name, "provenance", self.provenance, ProvenanceRef
        )
        object.__setattr__(self, "origin_time", origin)
        object.__setattr__(self, "confirm_time", confirm)
        object.__setattr__(self, "last_touch_time", last_touch)
        object.__setattr__(self, "last_touch_confirm_time", last_touch_confirm)
        object.__setattr__(self, "break_time", break_time)
        object.__setattr__(self, "break_confirm_time", break_confirm)

    def is_confirmed_at(self, processing_time: datetime) -> bool:
        normalized = _normalize_utc_datetime(
            type(self).__name__, "processing_time", processing_time
        )
        return (
            self.confirmation_status is ConfirmationStatus.CONFIRMED
            and self.confirm_time is not None
            and normalized >= self.confirm_time
        )

    def require_confirmed_at(self, processing_time: datetime) -> LevelCandidate:
        if self.confirm_time is None or not self.is_confirmed_at(processing_time):
            raise DomainAvailabilityError(
                f"LevelCandidate {self.candidate_id!r} is not confirmed at "
                "processing_time"
            )
        return self

    def to_boundary_ref(self) -> BoundaryRef:
        if self.confirm_time is None or (
            self.confirmation_status is not ConfirmationStatus.CONFIRMED
        ):
            raise DomainAvailabilityError(
                f"LevelCandidate {self.candidate_id!r} is FORMING and cannot "
                "be converted to BoundaryRef"
            )
        return BoundaryRef(
            object_kind=StructureObjectKind.LEVEL_CANDIDATE,
            object_id=self.candidate_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            scale=self.scale,
            price_range=self.price_range,
            boundary_side=self.boundary_side,
            market_role=self.market_role,
            lifecycle_state=self.lifecycle_state,
            origin_time=self.origin_time,
            confirm_time=self.confirm_time,
            source_types=(self.source_type,),
            structure_families=(self.structure_family,),
            provenance=self.provenance,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "scale": self.scale.to_dict(),
            "price_range": self.price_range.to_dict(),
            "source_type": self.source_type.value,
            "boundary_side": self.boundary_side.value,
            "market_role": self.market_role.value,
            "confirmation_status": self.confirmation_status.value,
            "lifecycle_state": self.lifecycle_state.value,
            "origin_time": _serialize_datetime(self.origin_time),
            "confirm_time": _serialize_optional_datetime(self.confirm_time),
            "touch_count": self.touch_count,
            "last_touch_time": _serialize_optional_datetime(self.last_touch_time),
            "last_touch_confirm_time": _serialize_optional_datetime(
                self.last_touch_confirm_time
            ),
            "break_time": _serialize_optional_datetime(self.break_time),
            "break_confirm_time": _serialize_optional_datetime(
                self.break_confirm_time
            ),
            "structure_family": self.structure_family,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelCandidate:
        object_name = cls.__name__
        fields = {
            "candidate_id",
            "symbol",
            "timeframe",
            "scale",
            "price_range",
            "source_type",
            "boundary_side",
            "market_role",
            "confirmation_status",
            "lifecycle_state",
            "origin_time",
            "confirm_time",
            "touch_count",
            "last_touch_time",
            "last_touch_confirm_time",
            "break_time",
            "break_confirm_time",
            "structure_family",
            "provenance",
        }
        data = _strict_payload(payload, object_name, fields)
        try:
            return cls(
                candidate_id=data["candidate_id"],
                symbol=data["symbol"],
                timeframe=_deserialize_enum(
                    data, object_name, "timeframe", Timeframe
                ),
                scale=ScaleDescriptor.from_dict(data["scale"]),
                price_range=PriceRange.from_dict(data["price_range"]),
                source_type=_deserialize_enum(
                    data, object_name, "source_type", StructureSourceType
                ),
                boundary_side=_deserialize_enum(
                    data, object_name, "boundary_side", BoundarySide
                ),
                market_role=_deserialize_enum(
                    data, object_name, "market_role", MarketRole
                ),
                confirmation_status=_deserialize_enum(
                    data, object_name, "confirmation_status", ConfirmationStatus
                ),
                lifecycle_state=_deserialize_enum(
                    data, object_name, "lifecycle_state", LifecycleState
                ),
                origin_time=_deserialize_datetime(data, object_name, "origin_time"),
                confirm_time=_deserialize_optional_datetime(
                    data, object_name, "confirm_time"
                ),
                touch_count=data["touch_count"],
                last_touch_time=_deserialize_optional_datetime(
                    data, object_name, "last_touch_time"
                ),
                last_touch_confirm_time=_deserialize_optional_datetime(
                    data, object_name, "last_touch_confirm_time"
                ),
                break_time=_deserialize_optional_datetime(
                    data, object_name, "break_time"
                ),
                break_confirm_time=_deserialize_optional_datetime(
                    data, object_name, "break_confirm_time"
                ),
                structure_family=data["structure_family"],
                provenance=ProvenanceRef.from_dict(data["provenance"]),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)


@dataclass(frozen=True, slots=True)
class StructureCluster:
    """Immutable cluster facts supplied by a future C-005 algorithm."""

    cluster_id: str
    symbol: str
    timeframe: Timeframe
    scale: ScaleDescriptor
    price_range: PriceRange
    boundary_side: BoundarySide
    market_role: MarketRole
    lifecycle_state: LifecycleState
    origin_time: datetime
    confirm_time: datetime
    member_refs: tuple[BoundaryRef, ...]
    cluster_family: str
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        object_name = type(self).__name__
        _require_non_empty_text(object_name, "cluster_id", self.cluster_id)
        _require_non_empty_text(object_name, "symbol", self.symbol)
        _require_instance(object_name, "timeframe", self.timeframe, Timeframe)
        _require_instance(object_name, "scale", self.scale, ScaleDescriptor)
        _require_instance(
            object_name, "price_range", self.price_range, PriceRange
        )
        _require_instance(
            object_name, "boundary_side", self.boundary_side, BoundarySide
        )
        _require_instance(object_name, "market_role", self.market_role, MarketRole)
        _require_instance(
            object_name, "lifecycle_state", self.lifecycle_state, LifecycleState
        )
        if self.lifecycle_state is LifecycleState.CANDIDATE:
            raise DomainValidationError(
                "StructureCluster.lifecycle_state cannot be CANDIDATE"
            )
        origin = _normalize_utc_datetime(object_name, "origin_time", self.origin_time)
        confirm = _normalize_utc_datetime(
            object_name, "confirm_time", self.confirm_time
        )
        if confirm < origin:
            raise DomainValidationError(
                "StructureCluster.confirm_time must be >= "
                "StructureCluster.origin_time"
            )
        members = _require_tuple(object_name, "member_refs", self.member_refs)
        if not members:
            raise DomainValidationError(
                "StructureCluster.member_refs must not be empty"
            )
        for index, member in enumerate(members):
            _require_instance(
                object_name, f"member_refs[{index}]", member, BoundaryRef
            )
        member_ids = tuple(member.object_id for member in members)
        if len(set(member_ids)) != len(member_ids):
            raise DomainValidationError(
                "StructureCluster.member_refs must have unique object_id values"
            )
        for member in members:
            if member.symbol != self.symbol:
                raise DomainValidationError(
                    "StructureCluster.member_refs symbol must match "
                    "StructureCluster.symbol"
                )
            if member.boundary_side is not self.boundary_side:
                raise DomainValidationError(
                    "StructureCluster.member_refs boundary_side must match "
                    "StructureCluster.boundary_side"
                )
            if member.confirm_time > confirm:
                raise DomainValidationError(
                    "StructureCluster.confirm_time must be >= every member "
                    "BoundaryRef.confirm_time"
                )
        _require_non_empty_text(object_name, "cluster_family", self.cluster_family)
        _require_instance(
            object_name, "provenance", self.provenance, ProvenanceRef
        )
        object.__setattr__(self, "origin_time", origin)
        object.__setattr__(self, "confirm_time", confirm)

    @property
    def source_types(self) -> tuple[StructureSourceType, ...]:
        return tuple(
            sorted(
                {item for member in self.member_refs for item in member.source_types},
                key=lambda item: item.value,
            )
        )

    @property
    def timeframes(self) -> tuple[Timeframe, ...]:
        return tuple(
            sorted({member.timeframe for member in self.member_refs}, key=lambda x: x.value)
        )

    @property
    def structure_families(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    family
                    for member in self.member_refs
                    for family in member.structure_families
                }
            )
        )

    def is_confirmed_at(self, processing_time: datetime) -> bool:
        normalized = _normalize_utc_datetime(
            type(self).__name__, "processing_time", processing_time
        )
        return normalized >= self.confirm_time

    def require_confirmed_at(self, processing_time: datetime) -> StructureCluster:
        _require_available(
            type(self).__name__,
            self.cluster_id,
            processing_time,
            self.confirm_time,
        )
        return self

    def to_boundary_ref(self) -> BoundaryRef:
        return BoundaryRef(
            object_kind=StructureObjectKind.STRUCTURE_CLUSTER,
            object_id=self.cluster_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            scale=self.scale,
            price_range=self.price_range,
            boundary_side=self.boundary_side,
            market_role=self.market_role,
            lifecycle_state=self.lifecycle_state,
            origin_time=self.origin_time,
            confirm_time=self.confirm_time,
            source_types=self.source_types,
            structure_families=tuple(
                sorted({self.cluster_family, *self.structure_families})
            ),
            provenance=self.provenance,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "cluster_id": self.cluster_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "scale": self.scale.to_dict(),
            "price_range": self.price_range.to_dict(),
            "boundary_side": self.boundary_side.value,
            "market_role": self.market_role.value,
            "lifecycle_state": self.lifecycle_state.value,
            "origin_time": _serialize_datetime(self.origin_time),
            "confirm_time": _serialize_datetime(self.confirm_time),
            "member_refs": [member.to_dict() for member in self.member_refs],
            "cluster_family": self.cluster_family,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StructureCluster:
        object_name = cls.__name__
        fields = {
            "cluster_id",
            "symbol",
            "timeframe",
            "scale",
            "price_range",
            "boundary_side",
            "market_role",
            "lifecycle_state",
            "origin_time",
            "confirm_time",
            "member_refs",
            "cluster_family",
            "provenance",
        }
        data = _strict_payload(payload, object_name, fields)
        try:
            return cls(
                cluster_id=data["cluster_id"],
                symbol=data["symbol"],
                timeframe=_deserialize_enum(
                    data, object_name, "timeframe", Timeframe
                ),
                scale=ScaleDescriptor.from_dict(data["scale"]),
                price_range=PriceRange.from_dict(data["price_range"]),
                boundary_side=_deserialize_enum(
                    data, object_name, "boundary_side", BoundarySide
                ),
                market_role=_deserialize_enum(
                    data, object_name, "market_role", MarketRole
                ),
                lifecycle_state=_deserialize_enum(
                    data, object_name, "lifecycle_state", LifecycleState
                ),
                origin_time=_deserialize_datetime(data, object_name, "origin_time"),
                confirm_time=_deserialize_datetime(
                    data, object_name, "confirm_time"
                ),
                member_refs=tuple(
                    BoundaryRef.from_dict(item)
                    for item in _deserialize_list(data, object_name, "member_refs")
                ),
                cluster_family=data["cluster_family"],
                provenance=ProvenanceRef.from_dict(data["provenance"]),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)


@dataclass(frozen=True, slots=True)
class TimeframeState:
    """Immutable, causally available structural snapshot for one timeframe."""

    state_id: str
    state_version: str
    symbol: str
    timeframe: Timeframe
    scale: ScaleDescriptor
    origin_time: datetime
    confirm_time: datetime
    as_of_time: datetime
    upper_boundary: BoundaryRef | None
    lower_boundary: BoundaryRef | None
    forming_candidate_ids: tuple[str, ...]
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        object_name = type(self).__name__
        _require_non_empty_text(object_name, "state_id", self.state_id)
        _require_non_empty_text(object_name, "state_version", self.state_version)
        _require_non_empty_text(object_name, "symbol", self.symbol)
        _require_instance(object_name, "timeframe", self.timeframe, Timeframe)
        _require_instance(object_name, "scale", self.scale, ScaleDescriptor)
        origin = _normalize_utc_datetime(object_name, "origin_time", self.origin_time)
        confirm = _normalize_utc_datetime(
            object_name, "confirm_time", self.confirm_time
        )
        as_of = _normalize_utc_datetime(object_name, "as_of_time", self.as_of_time)
        if confirm < origin:
            raise DomainValidationError(
                "TimeframeState.confirm_time must be >= TimeframeState.origin_time"
            )
        if as_of < confirm:
            raise DomainValidationError(
                "TimeframeState.as_of_time must be >= TimeframeState.confirm_time"
            )
        for field_name, boundary, side in (
            ("upper_boundary", self.upper_boundary, BoundarySide.UPPER),
            ("lower_boundary", self.lower_boundary, BoundarySide.LOWER),
        ):
            if boundary is None:
                continue
            _require_instance(object_name, field_name, boundary, BoundaryRef)
            if boundary.symbol != self.symbol:
                raise DomainValidationError(
                    f"TimeframeState.{field_name}.symbol must match "
                    "TimeframeState.symbol"
                )
            if boundary.boundary_side is not side:
                raise DomainValidationError(
                    f"TimeframeState.{field_name}.boundary_side must be {side.value}"
                )
            if boundary.confirm_time > confirm:
                raise DomainValidationError(
                    f"TimeframeState.{field_name}.confirm_time cannot be later "
                    "than TimeframeState.confirm_time"
                )
        if (
            self.lower_boundary is not None
            and self.upper_boundary is not None
            and self.lower_boundary.price_range.high
            > self.upper_boundary.price_range.low
        ):
            raise DomainValidationError(
                "TimeframeState lower boundary must not be above upper boundary"
            )
        forming_ids = _canonical_text_tuple(
            object_name,
            "forming_candidate_ids",
            self.forming_candidate_ids,
            non_empty=False,
            unique=True,
            sort_values=True,
        )
        _require_instance(
            object_name, "provenance", self.provenance, ProvenanceRef
        )
        object.__setattr__(self, "origin_time", origin)
        object.__setattr__(self, "confirm_time", confirm)
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "forming_candidate_ids", forming_ids)

    def is_available_at(self, processing_time: datetime) -> bool:
        normalized = _normalize_utc_datetime(
            type(self).__name__, "processing_time", processing_time
        )
        return normalized >= self.confirm_time

    def require_available_at(self, processing_time: datetime) -> TimeframeState:
        _require_available(
            type(self).__name__,
            self.state_id,
            processing_time,
            self.confirm_time,
        )
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "state_id": self.state_id,
            "state_version": self.state_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "scale": self.scale.to_dict(),
            "origin_time": _serialize_datetime(self.origin_time),
            "confirm_time": _serialize_datetime(self.confirm_time),
            "as_of_time": _serialize_datetime(self.as_of_time),
            "upper_boundary": (
                None if self.upper_boundary is None else self.upper_boundary.to_dict()
            ),
            "lower_boundary": (
                None if self.lower_boundary is None else self.lower_boundary.to_dict()
            ),
            "forming_candidate_ids": list(self.forming_candidate_ids),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeState:
        object_name = cls.__name__
        fields = {
            "state_id",
            "state_version",
            "symbol",
            "timeframe",
            "scale",
            "origin_time",
            "confirm_time",
            "as_of_time",
            "upper_boundary",
            "lower_boundary",
            "forming_candidate_ids",
            "provenance",
        }
        data = _strict_payload(payload, object_name, fields)
        try:
            return cls(
                state_id=data["state_id"],
                state_version=data["state_version"],
                symbol=data["symbol"],
                timeframe=_deserialize_enum(
                    data, object_name, "timeframe", Timeframe
                ),
                scale=ScaleDescriptor.from_dict(data["scale"]),
                origin_time=_deserialize_datetime(data, object_name, "origin_time"),
                confirm_time=_deserialize_datetime(
                    data, object_name, "confirm_time"
                ),
                as_of_time=_deserialize_datetime(data, object_name, "as_of_time"),
                upper_boundary=(
                    None
                    if data["upper_boundary"] is None
                    else BoundaryRef.from_dict(data["upper_boundary"])
                ),
                lower_boundary=(
                    None
                    if data["lower_boundary"] is None
                    else BoundaryRef.from_dict(data["lower_boundary"])
                ),
                forming_candidate_ids=tuple(
                    _deserialize_list(data, object_name, "forming_candidate_ids")
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)


@dataclass(frozen=True, slots=True)
class ActiveBox:
    """Immutable snapshot of explicitly selected lower and upper boundaries."""

    box_id: str
    symbol: str
    timeframe: Timeframe
    scale: ScaleDescriptor
    lower_boundary: BoundaryRef
    upper_boundary: BoundaryRef
    selection_price: Decimal
    status: ActiveBoxStatus
    origin_time: datetime
    confirm_time: datetime
    as_of_time: datetime
    frozen_time: datetime | None
    retired_time: datetime | None
    provenance: ProvenanceRef

    def __post_init__(self) -> None:
        object_name = type(self).__name__
        _require_non_empty_text(object_name, "box_id", self.box_id)
        _require_non_empty_text(object_name, "symbol", self.symbol)
        _require_instance(object_name, "timeframe", self.timeframe, Timeframe)
        _require_instance(object_name, "scale", self.scale, ScaleDescriptor)
        lower = _require_instance(
            object_name, "lower_boundary", self.lower_boundary, BoundaryRef
        )
        upper = _require_instance(
            object_name, "upper_boundary", self.upper_boundary, BoundaryRef
        )
        if lower.boundary_side is not BoundarySide.LOWER:
            raise DomainValidationError(
                "ActiveBox.lower_boundary.boundary_side must be LOWER"
            )
        if upper.boundary_side is not BoundarySide.UPPER:
            raise DomainValidationError(
                "ActiveBox.upper_boundary.boundary_side must be UPPER"
            )
        if lower.symbol != self.symbol or upper.symbol != self.symbol:
            raise DomainValidationError(
                "ActiveBox boundary symbols must match ActiveBox.symbol"
            )
        if lower.price_range.high > upper.price_range.low:
            raise DomainValidationError(
                "ActiveBox lower boundary must not be above upper boundary"
            )
        selection = _require_decimal(
            object_name, "selection_price", self.selection_price
        )
        if not lower.price_range.high <= selection <= upper.price_range.low:
            raise DomainValidationError(
                "ActiveBox.selection_price must be between the inner boundary "
                "edges, inclusive"
            )
        _require_instance(object_name, "status", self.status, ActiveBoxStatus)
        origin = _normalize_utc_datetime(object_name, "origin_time", self.origin_time)
        confirm = _normalize_utc_datetime(
            object_name, "confirm_time", self.confirm_time
        )
        as_of = _normalize_utc_datetime(object_name, "as_of_time", self.as_of_time)
        if confirm < origin:
            raise DomainValidationError(
                "ActiveBox.confirm_time must be >= ActiveBox.origin_time"
            )
        if as_of < confirm:
            raise DomainValidationError(
                "ActiveBox.as_of_time must be >= ActiveBox.confirm_time"
            )
        if lower.confirm_time > confirm or upper.confirm_time > confirm:
            raise DomainValidationError(
                "ActiveBox boundaries must be confirmed no later than "
                "ActiveBox.confirm_time"
            )
        frozen = _normalize_optional_utc_datetime(
            object_name, "frozen_time", self.frozen_time
        )
        retired = _normalize_optional_utc_datetime(
            object_name, "retired_time", self.retired_time
        )
        if self.status is ActiveBoxStatus.FROZEN and frozen is None:
            raise DomainValidationError(
                "ActiveBox.frozen_time is required when status is FROZEN"
            )
        if self.status is ActiveBoxStatus.RETIRED and retired is None:
            raise DomainValidationError(
                "ActiveBox.retired_time is required when status is RETIRED"
            )
        if self.status is not ActiveBoxStatus.RETIRED and retired is not None:
            raise DomainValidationError(
                "ActiveBox.retired_time must be None unless status is RETIRED"
            )
        if frozen is not None and frozen > confirm:
            raise DomainValidationError(
                "ActiveBox.frozen_time must be <= ActiveBox.confirm_time"
            )
        if retired is not None and retired > confirm:
            raise DomainValidationError(
                "ActiveBox.retired_time must be <= ActiveBox.confirm_time"
            )
        if frozen is not None and retired is not None and frozen > retired:
            raise DomainValidationError(
                "ActiveBox.frozen_time must be <= ActiveBox.retired_time"
            )
        _require_instance(
            object_name, "provenance", self.provenance, ProvenanceRef
        )
        object.__setattr__(self, "origin_time", origin)
        object.__setattr__(self, "confirm_time", confirm)
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "frozen_time", frozen)
        object.__setattr__(self, "retired_time", retired)

    def is_available_at(self, processing_time: datetime) -> bool:
        normalized = _normalize_utc_datetime(
            type(self).__name__, "processing_time", processing_time
        )
        return normalized >= self.confirm_time

    def require_available_at(self, processing_time: datetime) -> ActiveBox:
        _require_available(
            type(self).__name__,
            self.box_id,
            processing_time,
            self.confirm_time,
        )
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "box_id": self.box_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "scale": self.scale.to_dict(),
            "lower_boundary": self.lower_boundary.to_dict(),
            "upper_boundary": self.upper_boundary.to_dict(),
            "selection_price": str(self.selection_price),
            "status": self.status.value,
            "origin_time": _serialize_datetime(self.origin_time),
            "confirm_time": _serialize_datetime(self.confirm_time),
            "as_of_time": _serialize_datetime(self.as_of_time),
            "frozen_time": _serialize_optional_datetime(self.frozen_time),
            "retired_time": _serialize_optional_datetime(self.retired_time),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ActiveBox:
        object_name = cls.__name__
        fields = {
            "box_id",
            "symbol",
            "timeframe",
            "scale",
            "lower_boundary",
            "upper_boundary",
            "selection_price",
            "status",
            "origin_time",
            "confirm_time",
            "as_of_time",
            "frozen_time",
            "retired_time",
            "provenance",
        }
        data = _strict_payload(payload, object_name, fields)
        try:
            return cls(
                box_id=data["box_id"],
                symbol=data["symbol"],
                timeframe=_deserialize_enum(
                    data, object_name, "timeframe", Timeframe
                ),
                scale=ScaleDescriptor.from_dict(data["scale"]),
                lower_boundary=BoundaryRef.from_dict(data["lower_boundary"]),
                upper_boundary=BoundaryRef.from_dict(data["upper_boundary"]),
                selection_price=_deserialize_decimal(
                    data, object_name, "selection_price"
                ),
                status=_deserialize_enum(
                    data, object_name, "status", ActiveBoxStatus
                ),
                origin_time=_deserialize_datetime(data, object_name, "origin_time"),
                confirm_time=_deserialize_datetime(
                    data, object_name, "confirm_time"
                ),
                as_of_time=_deserialize_datetime(data, object_name, "as_of_time"),
                frozen_time=_deserialize_optional_datetime(
                    data, object_name, "frozen_time"
                ),
                retired_time=_deserialize_optional_datetime(
                    data, object_name, "retired_time"
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)
