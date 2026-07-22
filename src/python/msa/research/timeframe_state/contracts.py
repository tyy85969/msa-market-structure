"""Immutable public contracts for the causal C-006B timeframe-state engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Self

from msa.data import Timeframe
from msa.domain import (
    Direction,
    ProvenanceRef,
    ScaleDescriptor,
    TimeframeState,
)
from msa.research.lifecycle import LifecycleHistory

from .errors import (
    TimeframeStateConfigurationError,
    TimeframeStateEngineError,
    TimeframeStateInputError,
    TimeframeStateSerializationError,
)


SCHEMA_VERSION = 1
SEMANTIC_FIELDS = (
    "direction",
    "candidate_upper_boundary",
    "candidate_lower_boundary",
    "confirmed_upper_boundary",
    "confirmed_lower_boundary",
    "forming_candidate_ids",
)
CROSSED_PAIR_OLDER_SIDE = "CROSSED_PAIR_OLDER_SIDE"


def _exact_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise TimeframeStateSerializationError(
            f"{object_name} payload must be a mapping"
        )
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise TimeframeStateSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise TimeframeStateSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    _schema(payload["schema_version"], object_name, TimeframeStateSerializationError)
    return payload


def _schema(value: object, object_name: str, error_type: type[Exception]) -> None:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error_type(f"{object_name}.schema_version must be {SCHEMA_VERSION}")


def _text(field_name: str, value: object, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def _optional_text(
    field_name: str, value: object, error_type: type[Exception]
) -> str | None:
    return None if value is None else _text(field_name, value, error_type)


def _boolean(field_name: str, value: object, error_type: type[Exception]) -> bool:
    if not isinstance(value, bool):
        raise error_type(f"{field_name} must be a bool")
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
        raise TimeframeStateSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        return _time(
            field_name,
            datetime.fromisoformat(value),
            TimeframeStateSerializationError,
        )
    except ValueError as exc:
        raise TimeframeStateSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    return None if value is None else _parse_time(field_name, value)


def _ordered_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise TimeframeStateSerializationError(
            f"{object_name}.{field_name} must be an ordered list"
        )
    return value


def _text_tuple(
    object_name: str,
    field_name: str,
    values: object,
    error_type: type[Exception],
    *,
    unique: bool = False,
    sort_values: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise error_type(f"{object_name}.{field_name} must be a tuple")
    result = tuple(
        _text(f"{object_name}.{field_name}[{index}]", item, error_type)
        for index, item in enumerate(values)
    )
    if unique and len(set(result)) != len(result):
        raise error_type(f"{object_name}.{field_name} must contain unique values")
    return tuple(sorted(result)) if sort_values else result


def _optional_id_tuple(
    object_name: str,
    field_name: str,
    values: object,
    error_type: type[Exception],
) -> tuple[str, ...]:
    result = _text_tuple(object_name, field_name, values, error_type, unique=True)
    if len(result) not in {0, 2}:
        raise error_type(f"{object_name}.{field_name} must contain zero or two IDs")
    return result


def _decimal_tuple(
    object_name: str,
    field_name: str,
    values: object,
    error_type: type[Exception],
) -> tuple[Decimal, ...]:
    if not isinstance(values, tuple) or len(values) not in {0, 2}:
        raise error_type(
            f"{object_name}.{field_name} must be a tuple containing zero or two Decimals"
        )
    for item in values:
        if not isinstance(item, Decimal) or not item.is_finite():
            raise error_type(f"{object_name}.{field_name} must contain finite Decimals")
    return values


def _parse_decimal(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise TimeframeStateSerializationError(
            f"{field_name} must be a Decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise TimeframeStateSerializationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise TimeframeStateSerializationError(f"{field_name} must be finite")
    return parsed


def _ids(values: tuple[str, ...]) -> list[str]:
    return list(values)


def _boundary_id(boundary: object) -> str | None:
    return None if boundary is None else boundary.object_id  # type: ignore[attr-defined]


class _TimeframeStateEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact_payload(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise TimeframeStateSerializationError(
                f"{cls.__name__}.value is unknown: {data['value']!r}"
            ) from exc


class TimeframeSelectionPolicy(_TimeframeStateEnum):
    LATEST_CAUSAL = "LATEST_CAUSAL"


class TimeframeStateEventType(_TimeframeStateEnum):
    INITIALIZED = "INITIALIZED"
    SELECTION_CHANGED = "SELECTION_CHANGED"
    DIRECTION_CHANGED = "DIRECTION_CHANGED"
    STATE_CHANGED = "STATE_CHANGED"


@dataclass(frozen=True, slots=True)
class TimeframeStateConfig:
    engine_id: str
    engine_version: str
    policy_id: str
    symbol: str
    target_timeframe: Timeframe
    target_scale: ScaleDescriptor
    selection_policy: TimeframeSelectionPolicy
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateConfigurationError)
        for field_name in ("engine_id", "engine_version", "policy_id", "symbol"):
            _text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                TimeframeStateConfigurationError,
            )
        if not isinstance(self.target_timeframe, Timeframe):
            raise TimeframeStateConfigurationError(
                "TimeframeStateConfig.target_timeframe must be an explicit Timeframe"
            )
        if not isinstance(self.target_scale, ScaleDescriptor):
            raise TimeframeStateConfigurationError(
                "TimeframeStateConfig.target_scale must be an explicit ScaleDescriptor"
            )
        if self.selection_policy is not TimeframeSelectionPolicy.LATEST_CAUSAL:
            raise TimeframeStateConfigurationError(
                "TimeframeStateConfig.selection_policy must be LATEST_CAUSAL"
            )
        _boolean(f"{name}.strict", self.strict, TimeframeStateConfigurationError)
        if self.strict is not True:
            raise TimeframeStateConfigurationError(
                "TimeframeStateConfig.strict must be True; C-006B supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "policy_id": self.policy_id,
            "symbol": self.symbol,
            "target_timeframe": self.target_timeframe.value,
            "target_scale": self.target_scale.to_dict(),
            "selection_policy": self.selection_policy.value,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateConfig:
        fields = {
            "engine_id",
            "engine_version",
            "policy_id",
            "symbol",
            "target_timeframe",
            "target_scale",
            "selection_policy",
            "strict",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                engine_id=data["engine_id"],
                engine_version=data["engine_version"],
                policy_id=data["policy_id"],
                symbol=data["symbol"],
                target_timeframe=Timeframe(data["target_timeframe"]),
                target_scale=ScaleDescriptor.from_dict(data["target_scale"]),
                selection_policy=TimeframeSelectionPolicy(data["selection_policy"]),
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, TimeframeStateConfigurationError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class TimeframeStateInput:
    lifecycle_history: LifecycleHistory
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateInputError)
        if not isinstance(self.lifecycle_history, LifecycleHistory):
            raise TimeframeStateInputError(
                "TimeframeStateInput.lifecycle_history must be a LifecycleHistory"
            )
        if not self.lifecycle_history.snapshots:
            raise TimeframeStateInputError(
                "TimeframeStateInput.lifecycle_history must not be empty"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lifecycle_history": self.lifecycle_history.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateInput:
        data = _exact_payload(payload, cls.__name__, {"lifecycle_history"})
        try:
            return cls(
                lifecycle_history=LifecycleHistory.from_dict(
                    data["lifecycle_history"]
                ),
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class BoundarySelectionKey:
    state_confirm_time: datetime
    structural_confirm_time: datetime
    subject_id: str
    lifecycle_state_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateEngineError)
        state_time = _time(
            f"{name}.state_confirm_time",
            self.state_confirm_time,
            TimeframeStateEngineError,
        )
        structural_time = _time(
            f"{name}.structural_confirm_time",
            self.structural_confirm_time,
            TimeframeStateEngineError,
        )
        if state_time < structural_time:
            raise TimeframeStateEngineError(
                "BoundarySelectionKey.state_confirm_time cannot precede structural_confirm_time"
            )
        _text(f"{name}.subject_id", self.subject_id, TimeframeStateEngineError)
        _text(
            f"{name}.lifecycle_state_id",
            self.lifecycle_state_id,
            TimeframeStateEngineError,
        )
        object.__setattr__(self, "state_confirm_time", state_time)
        object.__setattr__(self, "structural_confirm_time", structural_time)

    @property
    def comparison_tuple(self) -> tuple[datetime, datetime, str, str]:
        return (
            self.state_confirm_time,
            self.structural_confirm_time,
            self.subject_id,
            self.lifecycle_state_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "state_confirm_time": self.state_confirm_time.isoformat(),
            "structural_confirm_time": self.structural_confirm_time.isoformat(),
            "subject_id": self.subject_id,
            "lifecycle_state_id": self.lifecycle_state_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BoundarySelectionKey:
        data = _exact_payload(
            payload,
            cls.__name__,
            {
                "state_confirm_time",
                "structural_confirm_time",
                "subject_id",
                "lifecycle_state_id",
            },
        )
        try:
            return cls(
                state_confirm_time=_parse_time(
                    "state_confirm_time", data["state_confirm_time"]
                ),
                structural_confirm_time=_parse_time(
                    "structural_confirm_time", data["structural_confirm_time"]
                ),
                subject_id=data["subject_id"],
                lifecycle_state_id=data["lifecycle_state_id"],
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, TimeframeStateEngineError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class BoundarySelectionExplanation:
    target_symbol: str
    target_timeframe: Timeframe
    target_scale: ScaleDescriptor
    selection_policy: TimeframeSelectionPolicy
    relevant_subject_ids: tuple[str, ...]
    candidate_eligible_subject_ids: tuple[str, ...]
    confirmed_eligible_subject_ids: tuple[str, ...]
    excluded_broken_ids: tuple[str, ...]
    excluded_retired_ids: tuple[str, ...]
    raw_candidate_upper_state_id: str | None
    raw_candidate_lower_state_id: str | None
    raw_confirmed_upper_state_id: str | None
    raw_confirmed_lower_state_id: str | None
    raw_candidate_upper_boundary_id: str | None
    raw_candidate_lower_boundary_id: str | None
    raw_confirmed_upper_boundary_id: str | None
    raw_confirmed_lower_boundary_id: str | None
    candidate_crossing_conflict: bool
    confirmed_crossing_conflict: bool
    candidate_retained_boundary_id: str | None
    candidate_dropped_boundary_id: str | None
    candidate_dropped_reason: str | None
    confirmed_retained_boundary_id: str | None
    confirmed_dropped_boundary_id: str | None
    confirmed_dropped_reason: str | None
    selected_candidate_upper_id: str | None
    selected_candidate_lower_id: str | None
    selected_confirmed_upper_id: str | None
    selected_confirmed_lower_id: str | None
    selected_lifecycle_state_ids: tuple[str, ...]
    selected_lifecycle_event_ids: tuple[str, ...]
    stable_comparison_keys: tuple[BoundarySelectionKey, ...]
    previous_complete_pair_subject_ids: tuple[str, ...]
    current_complete_pair_subject_ids: tuple[str, ...]
    previous_complete_pair_state_ids: tuple[str, ...]
    current_complete_pair_state_ids: tuple[str, ...]
    previous_complete_pair_boundary_ids: tuple[str, ...]
    current_complete_pair_boundary_ids: tuple[str, ...]
    previous_pair_midpoints: tuple[Decimal, ...]
    current_pair_midpoints: tuple[Decimal, ...]
    pair_position_changed: bool
    raw_direction: Direction
    previous_direction: Direction
    final_direction: Direction
    direction_rationale: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateEngineError)
        _text(f"{name}.target_symbol", self.target_symbol, TimeframeStateEngineError)
        if not isinstance(self.target_timeframe, Timeframe):
            raise TimeframeStateEngineError(
                "BoundarySelectionExplanation.target_timeframe must be a Timeframe"
            )
        if not isinstance(self.target_scale, ScaleDescriptor):
            raise TimeframeStateEngineError(
                "BoundarySelectionExplanation.target_scale must be a ScaleDescriptor"
            )
        if self.selection_policy is not TimeframeSelectionPolicy.LATEST_CAUSAL:
            raise TimeframeStateEngineError(
                "BoundarySelectionExplanation supports LATEST_CAUSAL only"
            )
        canonical_fields = (
            "relevant_subject_ids",
            "candidate_eligible_subject_ids",
            "confirmed_eligible_subject_ids",
            "excluded_broken_ids",
            "excluded_retired_ids",
            "selected_lifecycle_state_ids",
            "selected_lifecycle_event_ids",
        )
        for field_name in canonical_fields:
            values = _text_tuple(
                name,
                field_name,
                getattr(self, field_name),
                TimeframeStateEngineError,
                unique=True,
                sort_values=True,
            )
            object.__setattr__(self, field_name, values)
        for field_name in (
            "raw_candidate_upper_state_id",
            "raw_candidate_lower_state_id",
            "raw_confirmed_upper_state_id",
            "raw_confirmed_lower_state_id",
            "raw_candidate_upper_boundary_id",
            "raw_candidate_lower_boundary_id",
            "raw_confirmed_upper_boundary_id",
            "raw_confirmed_lower_boundary_id",
            "candidate_retained_boundary_id",
            "candidate_dropped_boundary_id",
            "candidate_dropped_reason",
            "confirmed_retained_boundary_id",
            "confirmed_dropped_boundary_id",
            "confirmed_dropped_reason",
            "selected_candidate_upper_id",
            "selected_candidate_lower_id",
            "selected_confirmed_upper_id",
            "selected_confirmed_lower_id",
        ):
            _optional_text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                TimeframeStateEngineError,
            )
        for prefix in ("candidate", "confirmed"):
            conflict = _boolean(
                f"{name}.{prefix}_crossing_conflict",
                getattr(self, f"{prefix}_crossing_conflict"),
                TimeframeStateEngineError,
            )
            retained = getattr(self, f"{prefix}_retained_boundary_id")
            dropped = getattr(self, f"{prefix}_dropped_boundary_id")
            reason = getattr(self, f"{prefix}_dropped_reason")
            if conflict:
                if retained is None or dropped is None or reason != CROSSED_PAIR_OLDER_SIDE:
                    raise TimeframeStateEngineError(
                        f"{prefix} crossing requires retained/dropped IDs and CROSSED_PAIR_OLDER_SIDE"
                    )
            elif any(item is not None for item in (retained, dropped, reason)):
                raise TimeframeStateEngineError(
                    f"{prefix} non-crossing explanation cannot contain dropped facts"
                )
        if not isinstance(self.stable_comparison_keys, tuple) or any(
            not isinstance(item, BoundarySelectionKey)
            for item in self.stable_comparison_keys
        ):
            raise TimeframeStateEngineError(
                "stable_comparison_keys must be a BoundarySelectionKey tuple"
            )
        ordered_keys = tuple(
            sorted(
                self.stable_comparison_keys,
                key=lambda item: item.comparison_tuple,
                reverse=True,
            )
        )
        if len({item.lifecycle_state_id for item in ordered_keys}) != len(ordered_keys):
            raise TimeframeStateEngineError(
                "stable_comparison_keys must have unique lifecycle_state_id values"
            )
        object.__setattr__(self, "stable_comparison_keys", ordered_keys)
        for field_name in (
            "previous_complete_pair_subject_ids",
            "current_complete_pair_subject_ids",
            "previous_complete_pair_state_ids",
            "current_complete_pair_state_ids",
            "previous_complete_pair_boundary_ids",
            "current_complete_pair_boundary_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_id_tuple(
                    name,
                    field_name,
                    getattr(self, field_name),
                    TimeframeStateEngineError,
                ),
            )
        previous_midpoints = _decimal_tuple(
            name,
            "previous_pair_midpoints",
            self.previous_pair_midpoints,
            TimeframeStateEngineError,
        )
        current_midpoints = _decimal_tuple(
            name,
            "current_pair_midpoints",
            self.current_pair_midpoints,
            TimeframeStateEngineError,
        )
        if len(previous_midpoints) != len(self.previous_complete_pair_subject_ids):
            raise TimeframeStateEngineError(
                "previous pair identity and midpoint lengths must agree"
            )
        if len(current_midpoints) != len(self.current_complete_pair_subject_ids):
            raise TimeframeStateEngineError(
                "current pair identity and midpoint lengths must agree"
            )
        _boolean(
            f"{name}.pair_position_changed",
            self.pair_position_changed,
            TimeframeStateEngineError,
        )
        for field_name in ("raw_direction", "previous_direction", "final_direction"):
            if not isinstance(getattr(self, field_name), Direction):
                raise TimeframeStateEngineError(
                    f"BoundarySelectionExplanation.{field_name} must be a Direction"
                )
        _text(
            f"{name}.direction_rationale",
            self.direction_rationale,
            TimeframeStateEngineError,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        for field_name in self.__dataclass_fields__:
            if field_name == "schema_version":
                continue
            value = getattr(self, field_name)
            if isinstance(value, Enum):
                result[field_name] = value.value
            elif isinstance(value, ScaleDescriptor):
                result[field_name] = value.to_dict()
            elif field_name == "stable_comparison_keys":
                result[field_name] = [item.to_dict() for item in value]
            elif field_name in {"previous_pair_midpoints", "current_pair_midpoints"}:
                result[field_name] = [str(item) for item in value]
            elif isinstance(value, tuple):
                result[field_name] = list(value)
            else:
                result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BoundarySelectionExplanation:
        fields = set(cls.__dataclass_fields__) - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        list_fields = {
            "relevant_subject_ids",
            "candidate_eligible_subject_ids",
            "confirmed_eligible_subject_ids",
            "excluded_broken_ids",
            "excluded_retired_ids",
            "selected_lifecycle_state_ids",
            "selected_lifecycle_event_ids",
            "previous_complete_pair_subject_ids",
            "current_complete_pair_subject_ids",
            "previous_complete_pair_state_ids",
            "current_complete_pair_state_ids",
            "previous_complete_pair_boundary_ids",
            "current_complete_pair_boundary_ids",
        }
        try:
            kwargs: dict[str, object] = {
                field_name: tuple(_ordered_list(data, cls.__name__, field_name))
                for field_name in list_fields
            }
            kwargs.update(
                target_symbol=data["target_symbol"],
                target_timeframe=Timeframe(data["target_timeframe"]),
                target_scale=ScaleDescriptor.from_dict(data["target_scale"]),
                selection_policy=TimeframeSelectionPolicy(data["selection_policy"]),
                stable_comparison_keys=tuple(
                    BoundarySelectionKey.from_dict(item)
                    for item in _ordered_list(
                        data, cls.__name__, "stable_comparison_keys"
                    )
                ),
                previous_pair_midpoints=tuple(
                    _parse_decimal("previous_pair_midpoints", item)
                    for item in _ordered_list(
                        data, cls.__name__, "previous_pair_midpoints"
                    )
                ),
                current_pair_midpoints=tuple(
                    _parse_decimal("current_pair_midpoints", item)
                    for item in _ordered_list(
                        data, cls.__name__, "current_pair_midpoints"
                    )
                ),
                raw_direction=Direction(data["raw_direction"]),
                previous_direction=Direction(data["previous_direction"]),
                final_direction=Direction(data["final_direction"]),
            )
            copied = fields - set(kwargs)
            kwargs.update({field_name: data[field_name] for field_name in copied})
            return cls(**kwargs, schema_version=data["schema_version"])  # type: ignore[arg-type]
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, TimeframeStateEngineError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class TimeframeStateEvent:
    event_id: str
    previous_state_id: str | None
    current_state_id: str
    event_type: TimeframeStateEventType
    event_confirm_time: datetime
    first_seen_time: datetime
    previous_direction: Direction | None
    current_direction: Direction
    changed_fields: tuple[str, ...]
    candidate_upper_id: str | None
    candidate_lower_id: str | None
    confirmed_upper_id: str | None
    confirmed_lower_id: str | None
    source_lifecycle_snapshot_id: str
    source_lifecycle_event_ids: tuple[str, ...]
    prior_event_id: str | None
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateEngineError)
        _text(f"{name}.event_id", self.event_id, TimeframeStateEngineError)
        _optional_text(
            f"{name}.previous_state_id",
            self.previous_state_id,
            TimeframeStateEngineError,
        )
        _text(
            f"{name}.current_state_id",
            self.current_state_id,
            TimeframeStateEngineError,
        )
        if not isinstance(self.event_type, TimeframeStateEventType):
            raise TimeframeStateEngineError(
                "TimeframeStateEvent.event_type must be a TimeframeStateEventType"
            )
        confirm = _time(
            f"{name}.event_confirm_time",
            self.event_confirm_time,
            TimeframeStateEngineError,
        )
        first_seen = _time(
            f"{name}.first_seen_time",
            self.first_seen_time,
            TimeframeStateEngineError,
        )
        if first_seen != confirm:
            raise TimeframeStateEngineError(
                "TimeframeStateEvent.first_seen_time must equal event_confirm_time"
            )
        if self.previous_direction is not None and not isinstance(
            self.previous_direction, Direction
        ):
            raise TimeframeStateEngineError("previous_direction must be Direction or None")
        if not isinstance(self.current_direction, Direction):
            raise TimeframeStateEngineError("current_direction must be a Direction")
        changed = _text_tuple(
            name,
            "changed_fields",
            self.changed_fields,
            TimeframeStateEngineError,
            unique=True,
        )
        expected_changed = tuple(field for field in SEMANTIC_FIELDS if field in changed)
        if (
            not changed
            or changed != expected_changed
            or set(changed) - set(SEMANTIC_FIELDS)
        ):
            raise TimeframeStateEngineError(
                "TimeframeStateEvent.changed_fields must be canonical semantic fields"
            )
        for field_name in (
            "candidate_upper_id",
            "candidate_lower_id",
            "confirmed_upper_id",
            "confirmed_lower_id",
            "prior_event_id",
        ):
            _optional_text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                TimeframeStateEngineError,
            )
        _text(
            f"{name}.source_lifecycle_snapshot_id",
            self.source_lifecycle_snapshot_id,
            TimeframeStateEngineError,
        )
        source_ids = _text_tuple(
            name,
            "source_lifecycle_event_ids",
            self.source_lifecycle_event_ids,
            TimeframeStateEngineError,
            unique=True,
            sort_values=True,
        )
        if not isinstance(self.provenance, ProvenanceRef):
            raise TimeframeStateEngineError("event provenance must be a ProvenanceRef")
        if self.provenance.source_object_id != self.event_id:
            raise TimeframeStateEngineError(
                "event provenance source_object_id must equal event_id"
            )
        if self.event_type is TimeframeStateEventType.INITIALIZED:
            if self.previous_state_id is not None or self.previous_direction is not None:
                raise TimeframeStateEngineError(
                    "INITIALIZED must not have a previous state or direction"
                )
            if self.prior_event_id is not None:
                raise TimeframeStateEngineError(
                    "INITIALIZED must not have a prior_event_id"
                )
            if changed != SEMANTIC_FIELDS:
                raise TimeframeStateEngineError(
                    "INITIALIZED changed_fields must contain every semantic field"
                )
        elif (
            self.previous_state_id is None
            or self.previous_direction is None
            or self.prior_event_id is None
        ):
            raise TimeframeStateEngineError(
                "non-initial events require previous state, direction, and event IDs"
            )
        else:
            direction_changed = self.previous_direction is not self.current_direction
            boundary_changed = any(item != "direction" for item in changed)
            if ("direction" in changed) != direction_changed:
                raise TimeframeStateEngineError(
                    "changed_fields direction contradicts event directions"
                )
            expected_type = (
                TimeframeStateEventType.STATE_CHANGED
                if direction_changed and boundary_changed
                else TimeframeStateEventType.DIRECTION_CHANGED
                if direction_changed
                else TimeframeStateEventType.SELECTION_CHANGED
            )
            if self.event_type is not expected_type:
                raise TimeframeStateEngineError(
                    "event_type contradicts changed_fields and directions"
                )
        object.__setattr__(self, "event_confirm_time", confirm)
        object.__setattr__(self, "first_seen_time", first_seen)
        object.__setattr__(self, "changed_fields", changed)
        object.__setattr__(self, "source_lifecycle_event_ids", source_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "previous_state_id": self.previous_state_id,
            "current_state_id": self.current_state_id,
            "event_type": self.event_type.value,
            "event_confirm_time": self.event_confirm_time.isoformat(),
            "first_seen_time": self.first_seen_time.isoformat(),
            "previous_direction": (
                None if self.previous_direction is None else self.previous_direction.value
            ),
            "current_direction": self.current_direction.value,
            "changed_fields": list(self.changed_fields),
            "candidate_upper_id": self.candidate_upper_id,
            "candidate_lower_id": self.candidate_lower_id,
            "confirmed_upper_id": self.confirmed_upper_id,
            "confirmed_lower_id": self.confirmed_lower_id,
            "source_lifecycle_snapshot_id": self.source_lifecycle_snapshot_id,
            "source_lifecycle_event_ids": list(self.source_lifecycle_event_ids),
            "prior_event_id": self.prior_event_id,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateEvent:
        fields = set(cls.__dataclass_fields__) - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                event_id=data["event_id"],
                previous_state_id=data["previous_state_id"],
                current_state_id=data["current_state_id"],
                event_type=TimeframeStateEventType(data["event_type"]),
                event_confirm_time=_parse_time(
                    "event_confirm_time", data["event_confirm_time"]
                ),
                first_seen_time=_parse_time(
                    "first_seen_time", data["first_seen_time"]
                ),
                previous_direction=(
                    None
                    if data["previous_direction"] is None
                    else Direction(data["previous_direction"])
                ),
                current_direction=Direction(data["current_direction"]),
                changed_fields=tuple(
                    _ordered_list(data, cls.__name__, "changed_fields")
                ),
                candidate_upper_id=data["candidate_upper_id"],
                candidate_lower_id=data["candidate_lower_id"],
                confirmed_upper_id=data["confirmed_upper_id"],
                confirmed_lower_id=data["confirmed_lower_id"],
                source_lifecycle_snapshot_id=data["source_lifecycle_snapshot_id"],
                source_lifecycle_event_ids=tuple(
                    _ordered_list(
                        data, cls.__name__, "source_lifecycle_event_ids"
                    )
                ),
                prior_event_id=data["prior_event_id"],
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, TimeframeStateEngineError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class TimeframeStateReport:
    as_of_time: datetime
    lifecycle_snapshot_count: int
    relevant_subject_count: int
    candidate_eligible_count: int
    confirmed_eligible_count: int
    upper_candidate_count: int
    lower_candidate_count: int
    upper_confirmed_count: int
    lower_confirmed_count: int
    excluded_broken_count: int
    excluded_retired_count: int
    candidate_pair_crossing_conflict: bool
    confirmed_pair_crossing_conflict: bool
    selected_candidate_upper_id: str | None
    selected_candidate_lower_id: str | None
    selected_confirmed_upper_id: str | None
    selected_confirmed_lower_id: str | None
    complete_candidate_pair: bool
    complete_confirmed_pair: bool
    direction: Direction
    state_event_count: int
    earliest_state_event_time: datetime | None
    latest_state_event_time: datetime | None
    engine_id: str
    engine_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateEngineError)
        as_of = _time(
            f"{name}.as_of_time", self.as_of_time, TimeframeStateEngineError
        )
        for field_name in self.__dataclass_fields__:
            if field_name.endswith("_count"):
                _integer(
                    f"{name}.{field_name}",
                    getattr(self, field_name),
                    TimeframeStateEngineError,
                )
        for field_name in (
            "candidate_pair_crossing_conflict",
            "confirmed_pair_crossing_conflict",
            "complete_candidate_pair",
            "complete_confirmed_pair",
        ):
            _boolean(
                f"{name}.{field_name}",
                getattr(self, field_name),
                TimeframeStateEngineError,
            )
        for field_name in (
            "selected_candidate_upper_id",
            "selected_candidate_lower_id",
            "selected_confirmed_upper_id",
            "selected_confirmed_lower_id",
        ):
            _optional_text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                TimeframeStateEngineError,
            )
        if self.complete_candidate_pair != (
            self.selected_candidate_upper_id is not None
            and self.selected_candidate_lower_id is not None
        ):
            raise TimeframeStateEngineError(
                "complete_candidate_pair contradicts selected candidate boundaries"
            )
        if self.complete_confirmed_pair != (
            self.selected_confirmed_upper_id is not None
            and self.selected_confirmed_lower_id is not None
        ):
            raise TimeframeStateEngineError(
                "complete_confirmed_pair contradicts selected confirmed boundaries"
            )
        if not isinstance(self.direction, Direction):
            raise TimeframeStateEngineError("report direction must be a Direction")
        earliest = _optional_time(
            "earliest_state_event_time",
            self.earliest_state_event_time,
            TimeframeStateEngineError,
        )
        latest = _optional_time(
            "latest_state_event_time",
            self.latest_state_event_time,
            TimeframeStateEngineError,
        )
        if (earliest is None) != (latest is None):
            raise TimeframeStateEngineError("report event time bounds are incomplete")
        if earliest is not None and (earliest > latest or latest > as_of):
            raise TimeframeStateEngineError("report event time bounds are invalid")
        if self.state_event_count == 0 and earliest is not None:
            raise TimeframeStateEngineError("zero events require empty event time bounds")
        if self.state_event_count > 0 and earliest is None:
            raise TimeframeStateEngineError("positive events require event time bounds")
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                TimeframeStateEngineError,
            )
        for field_name in ("assumptions", "warnings", "errors"):
            object.__setattr__(
                self,
                field_name,
                _text_tuple(
                    name,
                    field_name,
                    getattr(self, field_name),
                    TimeframeStateEngineError,
                ),
            )
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "earliest_state_event_time", earliest)
        object.__setattr__(self, "latest_state_event_time", latest)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        for field_name in self.__dataclass_fields__:
            if field_name == "schema_version":
                continue
            value = getattr(self, field_name)
            if isinstance(value, datetime):
                result[field_name] = value.isoformat()
            elif isinstance(value, Direction):
                result[field_name] = value.value
            elif isinstance(value, tuple):
                result[field_name] = list(value)
            else:
                result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateReport:
        fields = set(cls.__dataclass_fields__) - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            kwargs = {
                field_name: data[field_name]
                for field_name in fields
                if field_name
                not in {
                    "as_of_time",
                    "earliest_state_event_time",
                    "latest_state_event_time",
                    "direction",
                    "assumptions",
                    "warnings",
                    "errors",
                }
            }
            return cls(
                **kwargs,
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                earliest_state_event_time=_parse_optional_time(
                    "earliest_state_event_time", data["earliest_state_event_time"]
                ),
                latest_state_event_time=_parse_optional_time(
                    "latest_state_event_time", data["latest_state_event_time"]
                ),
                direction=Direction(data["direction"]),
                assumptions=tuple(
                    _ordered_list(data, cls.__name__, "assumptions")
                ),
                warnings=tuple(_ordered_list(data, cls.__name__, "warnings")),
                errors=tuple(_ordered_list(data, cls.__name__, "errors")),
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, TimeframeStateEngineError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def _validate_event_chain(events: tuple[TimeframeStateEvent, ...]) -> None:
    if not events:
        raise TimeframeStateEngineError("timeframe-state event ledger must not be empty")
    expected = tuple(
        sorted(events, key=lambda item: (item.event_confirm_time, item.event_id))
    )
    if expected != events or len({item.event_id for item in events}) != len(events):
        raise TimeframeStateEngineError(
            "timeframe-state events must be uniquely and stably ordered"
        )
    if events[0].event_type is not TimeframeStateEventType.INITIALIZED:
        raise TimeframeStateEngineError("first timeframe-state event must be INITIALIZED")
    if sum(item.event_type is TimeframeStateEventType.INITIALIZED for item in events) != 1:
        raise TimeframeStateEngineError("INITIALIZED must occur exactly once")
    previous: TimeframeStateEvent | None = None
    for event in events:
        if previous is not None:
            if event.prior_event_id != previous.event_id:
                raise TimeframeStateEngineError(
                    "event prior_event_id must reference the direct predecessor"
                )
            if event.previous_state_id != previous.current_state_id:
                raise TimeframeStateEngineError(
                    "event previous_state_id must reference the direct semantic state"
                )
            if event.previous_direction is not previous.current_direction:
                raise TimeframeStateEngineError(
                    "event previous_direction must match the direct predecessor"
                )
        previous = event


def _validate_snapshot_views(
    state: TimeframeState,
    explanation: BoundarySelectionExplanation,
    report: TimeframeStateReport,
    config: TimeframeStateConfig,
    events: tuple[TimeframeStateEvent, ...],
    source_lifecycle_snapshot_id: str,
) -> None:
    if (
        explanation.target_symbol != config.symbol
        or explanation.target_timeframe is not config.target_timeframe
        or explanation.target_scale != config.target_scale
        or explanation.selection_policy is not config.selection_policy
    ):
        raise TimeframeStateEngineError("explanation target contradicts config")
    selected = (
        explanation.selected_candidate_upper_id,
        explanation.selected_candidate_lower_id,
        explanation.selected_confirmed_upper_id,
        explanation.selected_confirmed_lower_id,
    )
    actual = (
        _boundary_id(state.candidate_upper_boundary),
        _boundary_id(state.candidate_lower_boundary),
        _boundary_id(state.confirmed_upper_boundary),
        _boundary_id(state.confirmed_lower_boundary),
    )
    if selected != actual:
        raise TimeframeStateEngineError("explanation selected boundaries contradict state")
    if explanation.final_direction is not state.direction:
        raise TimeframeStateEngineError("explanation final direction contradicts state")
    report_selected = (
        report.selected_candidate_upper_id,
        report.selected_candidate_lower_id,
        report.selected_confirmed_upper_id,
        report.selected_confirmed_lower_id,
    )
    if report_selected != actual or report.direction is not state.direction:
        raise TimeframeStateEngineError("report selected state contradicts state")
    if (
        report.candidate_pair_crossing_conflict
        != explanation.candidate_crossing_conflict
        or report.confirmed_pair_crossing_conflict
        != explanation.confirmed_crossing_conflict
    ):
        raise TimeframeStateEngineError("report crossing facts contradict explanation")
    if report.state_event_count != len(events):
        raise TimeframeStateEngineError("report state_event_count contradicts events")
    if (
        report.engine_id != config.engine_id
        or report.engine_version != config.engine_version
        or report.policy_id != config.policy_id
    ):
        raise TimeframeStateEngineError("report engine identity contradicts config")
    if state.state_version != config.engine_version:
        raise TimeframeStateEngineError("state_version must equal config.engine_version")
    if (
        state.symbol != config.symbol
        or state.timeframe is not config.target_timeframe
        or state.scale != config.target_scale
    ):
        raise TimeframeStateEngineError("state target context contradicts config")
    latest = events[-1]
    if latest.current_direction is not state.direction:
        raise TimeframeStateEngineError(
            "last event current_direction contradicts state"
        )
    event_selected = (
        latest.candidate_upper_id,
        latest.candidate_lower_id,
        latest.confirmed_upper_id,
        latest.confirmed_lower_id,
    )
    if event_selected != actual:
        raise TimeframeStateEngineError(
            "last event selected boundary IDs contradict state"
        )
    if report.relevant_subject_count != len(explanation.relevant_subject_ids):
        raise TimeframeStateEngineError(
            "report relevant_subject_count contradicts explanation"
        )
    if report.candidate_eligible_count != len(
        explanation.candidate_eligible_subject_ids
    ):
        raise TimeframeStateEngineError(
            "report candidate_eligible_count contradicts explanation"
        )
    if report.confirmed_eligible_count != len(
        explanation.confirmed_eligible_subject_ids
    ):
        raise TimeframeStateEngineError(
            "report confirmed_eligible_count contradicts explanation"
        )
    if report.excluded_broken_count != len(explanation.excluded_broken_ids):
        raise TimeframeStateEngineError(
            "report excluded_broken_count contradicts explanation"
        )
    if report.excluded_retired_count != len(explanation.excluded_retired_ids):
        raise TimeframeStateEngineError(
            "report excluded_retired_count contradicts explanation"
        )
    for event in events:
        required_event_parents = {
            event.source_lifecycle_snapshot_id,
            *event.source_lifecycle_event_ids,
            *(() if event.prior_event_id is None else (event.prior_event_id,)),
        }
        if (
            event.provenance.source_module
            != "msa.research.timeframe_state.engine"
            or event.provenance.source_version != config.engine_version
            or event.provenance.policy_id != config.policy_id
            or not required_event_parents.issubset(
                event.provenance.parent_object_ids
            )
        ):
            raise TimeframeStateEngineError("event provenance is inconsistent")
    required_state_parents = {
        events[-1].source_lifecycle_snapshot_id,
        events[-1].event_id,
        *explanation.selected_lifecycle_state_ids,
        *explanation.selected_lifecycle_event_ids,
    }
    if state.provenance.source_object_id != state.state_id:
        raise TimeframeStateEngineError("state provenance source_object_id is inconsistent")
    if (
        state.provenance.source_module
        != "msa.research.timeframe_state.engine"
        or state.provenance.source_version != config.engine_version
        or state.provenance.policy_id != config.policy_id
        or not required_state_parents.issubset(state.provenance.parent_object_ids)
    ):
        raise TimeframeStateEngineError("state provenance is inconsistent")


@dataclass(frozen=True, slots=True)
class TimeframeStateSnapshot:
    snapshot_id: str
    as_of_time: datetime
    source_lifecycle_snapshot_id: str
    state: TimeframeState
    explanation: BoundarySelectionExplanation
    events: tuple[TimeframeStateEvent, ...]
    report: TimeframeStateReport
    config_snapshot: TimeframeStateConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateEngineError)
        _text(f"{name}.snapshot_id", self.snapshot_id, TimeframeStateEngineError)
        as_of = _time(
            f"{name}.as_of_time", self.as_of_time, TimeframeStateEngineError
        )
        _text(
            f"{name}.source_lifecycle_snapshot_id",
            self.source_lifecycle_snapshot_id,
            TimeframeStateEngineError,
        )
        if not isinstance(self.state, TimeframeState):
            raise TimeframeStateEngineError("snapshot state must be a TimeframeState")
        if self.state.as_of_time != as_of or self.state.confirm_time > as_of:
            raise TimeframeStateEngineError("snapshot state causal times are inconsistent")
        boundaries = (
            self.state.candidate_upper_boundary,
            self.state.candidate_lower_boundary,
            self.state.confirmed_upper_boundary,
            self.state.confirmed_lower_boundary,
        )
        if any(item is not None and item.confirm_time > as_of for item in boundaries):
            raise TimeframeStateEngineError("selected boundary follows snapshot as_of_time")
        if not isinstance(self.events, tuple) or any(
            not isinstance(item, TimeframeStateEvent) for item in self.events
        ):
            raise TimeframeStateEngineError(
                "snapshot events must be a TimeframeStateEvent tuple"
            )
        _validate_event_chain(self.events)
        if any(item.event_confirm_time > as_of for item in self.events):
            raise TimeframeStateEngineError("snapshot event follows as_of_time")
        if self.state.state_id != self.events[-1].current_state_id:
            raise TimeframeStateEngineError(
                "snapshot state_id must equal the last event current_state_id"
            )
        if not isinstance(self.explanation, BoundarySelectionExplanation):
            raise TimeframeStateEngineError(
                "snapshot explanation must be BoundarySelectionExplanation"
            )
        if not isinstance(self.report, TimeframeStateReport):
            raise TimeframeStateEngineError("snapshot report must be TimeframeStateReport")
        if not isinstance(self.config_snapshot, TimeframeStateConfig):
            raise TimeframeStateEngineError(
                "snapshot config_snapshot must be TimeframeStateConfig"
            )
        if self.report.as_of_time != as_of:
            raise TimeframeStateEngineError("report.as_of_time must equal snapshot.as_of_time")
        event_times = tuple(item.event_confirm_time for item in self.events)
        if self.report.earliest_state_event_time != min(event_times):
            raise TimeframeStateEngineError("report earliest event time is inconsistent")
        if self.report.latest_state_event_time != max(event_times):
            raise TimeframeStateEngineError("report latest event time is inconsistent")
        _validate_snapshot_views(
            self.state,
            self.explanation,
            self.report,
            self.config_snapshot,
            self.events,
            self.source_lifecycle_snapshot_id,
        )
        object.__setattr__(self, "as_of_time", as_of)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "as_of_time": self.as_of_time.isoformat(),
            "source_lifecycle_snapshot_id": self.source_lifecycle_snapshot_id,
            "state": self.state.to_dict(),
            "explanation": self.explanation.to_dict(),
            "events": [item.to_dict() for item in self.events],
            "report": self.report.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateSnapshot:
        fields = set(cls.__dataclass_fields__) - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                snapshot_id=data["snapshot_id"],
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                source_lifecycle_snapshot_id=data["source_lifecycle_snapshot_id"],
                state=TimeframeState.from_dict(data["state"]),
                explanation=BoundarySelectionExplanation.from_dict(
                    data["explanation"]
                ),
                events=tuple(
                    TimeframeStateEvent.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "events")
                ),
                report=TimeframeStateReport.from_dict(data["report"]),
                config_snapshot=TimeframeStateConfig.from_dict(
                    data["config_snapshot"]
                ),
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def _state_without_as_of(state: TimeframeState) -> dict[str, object]:
    payload = state.to_dict()
    del payload["as_of_time"]
    return payload


@dataclass(frozen=True, slots=True)
class TimeframeStateHistory:
    events: tuple[TimeframeStateEvent, ...]
    snapshots: tuple[TimeframeStateSnapshot, ...]
    final_snapshot: TimeframeStateSnapshot
    config_snapshot: TimeframeStateConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, TimeframeStateEngineError)
        if not isinstance(self.events, tuple) or any(
            not isinstance(item, TimeframeStateEvent) for item in self.events
        ):
            raise TimeframeStateEngineError(
                "history events must be a TimeframeStateEvent tuple"
            )
        _validate_event_chain(self.events)
        if not isinstance(self.snapshots, tuple) or not self.snapshots:
            raise TimeframeStateEngineError(
                "history snapshots must be a non-empty tuple"
            )
        if any(
            not isinstance(item, TimeframeStateSnapshot) for item in self.snapshots
        ):
            raise TimeframeStateEngineError(
                "history snapshots must contain TimeframeStateSnapshot"
            )
        if any(
            current.as_of_time <= previous.as_of_time
            for previous, current in zip(self.snapshots, self.snapshots[1:])
        ):
            raise TimeframeStateEngineError(
                "history snapshots must be strictly chronological"
            )
        if not isinstance(self.config_snapshot, TimeframeStateConfig):
            raise TimeframeStateEngineError(
                "history config_snapshot must be TimeframeStateConfig"
            )
        if any(
            item.config_snapshot != self.config_snapshot for item in self.snapshots
        ):
            raise TimeframeStateEngineError(
                "history snapshot configurations must be identical"
            )
        previous: TimeframeStateSnapshot | None = None
        for snapshot in self.snapshots:
            if snapshot.events != self.events[: len(snapshot.events)]:
                raise TimeframeStateEngineError(
                    "each history snapshot must contain the exact event prefix"
                )
            if previous is not None:
                new_events = snapshot.events[len(previous.events) :]
                if not new_events and _state_without_as_of(snapshot.state) != _state_without_as_of(previous.state):
                    raise TimeframeStateEngineError(
                        "state facts cannot change without a new timeframe-state event"
                    )
                if new_events and snapshot.state.state_id == previous.state.state_id:
                    raise TimeframeStateEngineError(
                        "a new timeframe-state event requires a new state_id"
                    )
                if not new_events and snapshot.state.state_id != previous.state.state_id:
                    raise TimeframeStateEngineError(
                        "state_id cannot change without a new timeframe-state event"
                    )
            previous = snapshot
        if not isinstance(self.final_snapshot, TimeframeStateSnapshot):
            raise TimeframeStateEngineError(
                "history final_snapshot must be a TimeframeStateSnapshot"
            )
        if self.final_snapshot != self.snapshots[-1]:
            raise TimeframeStateEngineError(
                "history final_snapshot must equal the last snapshot"
            )
        if self.final_snapshot.events != self.events:
            raise TimeframeStateEngineError(
                "history events must equal final_snapshot.events"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "events": [item.to_dict() for item in self.events],
            "snapshots": [item.to_dict() for item in self.snapshots],
            "final_snapshot": self.final_snapshot.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateHistory:
        fields = {"events", "snapshots", "final_snapshot", "config_snapshot"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                events=tuple(
                    TimeframeStateEvent.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "events")
                ),
                snapshots=tuple(
                    TimeframeStateSnapshot.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "snapshots")
                ),
                final_snapshot=TimeframeStateSnapshot.from_dict(
                    data["final_snapshot"]
                ),
                config_snapshot=TimeframeStateConfig.from_dict(
                    data["config_snapshot"]
                ),
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc
