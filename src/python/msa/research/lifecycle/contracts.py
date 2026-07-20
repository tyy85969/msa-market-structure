"""Immutable public contracts for the causal C-006A lifecycle engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Self

from msa.data import (
    CanonicalBar,
    CompletedBarPolicy,
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    LoadResult,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
)
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    LifecycleState,
    MarketRole,
    ProvenanceRef,
    StructureObjectKind,
)

from .errors import (
    LifecycleConfigurationError,
    LifecycleEngineError,
    LifecycleInputError,
    LifecycleSerializationError,
)


SCHEMA_VERSION = 1


def _exact_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise LifecycleSerializationError(f"{object_name} payload must be a mapping")
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise LifecycleSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise LifecycleSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    _schema(payload["schema_version"], object_name, LifecycleSerializationError)
    return payload


def _schema(value: object, object_name: str, error_type: type[Exception]) -> None:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error_type(f"{object_name}.schema_version must be {SCHEMA_VERSION}")


def _text(field_name: str, value: object, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def _bool(field_name: str, value: object, error_type: type[Exception]) -> bool:
    if not isinstance(value, bool):
        raise error_type(f"{field_name} must be a bool")
    return value


def _integer(
    field_name: str, value: object, error_type: type[Exception], *, minimum: int = 0
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise error_type(f"{field_name} must be an integer >= {minimum}")
    return value


def _decimal(
    field_name: str, value: object, error_type: type[Exception], *, minimum: Decimal | None = None
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise error_type(f"{field_name} must be a finite Decimal")
    if minimum is not None and value < minimum:
        raise error_type(f"{field_name} must be >= {minimum}")
    return value


def _parse_decimal(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise LifecycleSerializationError(f"{field_name} must be a Decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise LifecycleSerializationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise LifecycleSerializationError(f"{field_name} must be finite")
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
        raise LifecycleSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LifecycleSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    return _time(field_name, parsed, LifecycleSerializationError)


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    return None if value is None else _parse_time(field_name, value)


def _ordered_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise LifecycleSerializationError(
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
    result = tuple(
        _text(f"{object_name}.{field_name}[{index}]", item, error_type)
        for index, item in enumerate(values)
    )
    if unique and len(set(result)) != len(result):
        raise error_type(f"{object_name}.{field_name} must contain unique values")
    return tuple(sorted(result)) if sort_values else result


class _LifecycleEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact_payload(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise LifecycleSerializationError(
                f"{cls.__name__}.value is unknown: {data['value']!r}"
            ) from exc


class LifecycleEventType(_LifecycleEnum):
    ACTIVATED = "ACTIVATED"
    TEST = "TEST"
    WEAKENED = "WEAKENED"
    BROKEN = "BROKEN"
    FLIP_TOUCH = "FLIP_TOUCH"
    FLIPPED = "FLIPPED"
    RETIRED = "RETIRED"


class RetirementReason(_LifecycleEnum):
    FAILED_BREAK = "FAILED_BREAK"
    FLIP_HORIZON_EXPIRED = "FLIP_HORIZON_EXPIRED"


@dataclass(frozen=True, slots=True)
class LifecycleConfig:
    engine_id: str
    engine_version: str
    policy_id: str
    observation_timeframe: Timeframe
    test_tolerance: Decimal
    break_buffer: Decimal
    weakening_test_count: int
    minimum_test_separation_bars: int
    flip_tolerance: Decimal
    flip_confirmation_distance: Decimal
    flip_horizon_bars: int
    failed_break_retirement_buffer: Decimal
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleConfigurationError)
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(field_name, getattr(self, field_name), LifecycleConfigurationError)
        if not isinstance(self.observation_timeframe, Timeframe):
            raise LifecycleConfigurationError(
                "observation_timeframe must be an explicit Timeframe"
            )
        for field_name in (
            "test_tolerance",
            "break_buffer",
            "flip_tolerance",
            "flip_confirmation_distance",
            "failed_break_retirement_buffer",
        ):
            _decimal(
                field_name,
                getattr(self, field_name),
                LifecycleConfigurationError,
                minimum=Decimal(0),
            )
        _integer(
            "weakening_test_count",
            self.weakening_test_count,
            LifecycleConfigurationError,
            minimum=2,
        )
        _integer(
            "minimum_test_separation_bars",
            self.minimum_test_separation_bars,
            LifecycleConfigurationError,
            minimum=1,
        )
        _integer(
            "flip_horizon_bars",
            self.flip_horizon_bars,
            LifecycleConfigurationError,
            minimum=1,
        )
        _bool("strict", self.strict, LifecycleConfigurationError)
        if self.strict is not True:
            raise LifecycleConfigurationError(
                "LifecycleConfig.strict must be True; C-006A supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "policy_id": self.policy_id,
            "observation_timeframe": self.observation_timeframe.value,
            "test_tolerance": str(self.test_tolerance),
            "break_buffer": str(self.break_buffer),
            "weakening_test_count": self.weakening_test_count,
            "minimum_test_separation_bars": self.minimum_test_separation_bars,
            "flip_tolerance": str(self.flip_tolerance),
            "flip_confirmation_distance": str(self.flip_confirmation_distance),
            "flip_horizon_bars": self.flip_horizon_bars,
            "failed_break_retirement_buffer": str(
                self.failed_break_retirement_buffer
            ),
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleConfig:
        fields = {
            "engine_id", "engine_version", "policy_id", "observation_timeframe",
            "test_tolerance", "break_buffer", "weakening_test_count",
            "minimum_test_separation_bars", "flip_tolerance",
            "flip_confirmation_distance", "flip_horizon_bars",
            "failed_break_retirement_buffer", "strict",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                engine_id=data["engine_id"],
                engine_version=data["engine_version"],
                policy_id=data["policy_id"],
                observation_timeframe=Timeframe(data["observation_timeframe"]),
                test_tolerance=_parse_decimal("test_tolerance", data["test_tolerance"]),
                break_buffer=_parse_decimal("break_buffer", data["break_buffer"]),
                weakening_test_count=data["weakening_test_count"],
                minimum_test_separation_bars=data["minimum_test_separation_bars"],
                flip_tolerance=_parse_decimal("flip_tolerance", data["flip_tolerance"]),
                flip_confirmation_distance=_parse_decimal(
                    "flip_confirmation_distance", data["flip_confirmation_distance"]
                ),
                flip_horizon_bars=data["flip_horizon_bars"],
                failed_break_retirement_buffer=_parse_decimal(
                    "failed_break_retirement_buffer",
                    data["failed_break_retirement_buffer"],
                ),
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleConfigurationError) as exc:
            raise LifecycleSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


_BAR_FIELDS = {
    "symbol", "timeframe", "timestamp", "end_time", "open", "high", "low",
    "close", "volume", "volume_type", "source", "source_timezone",
    "is_complete", "available_time", "session_id", "boundary_policy",
}


def _bar_from_dict(payload: Mapping[str, Any]) -> CanonicalBar:
    if not isinstance(payload, Mapping):
        raise LifecycleSerializationError("CanonicalBar payload must be a mapping")
    keys = set(payload)
    if keys != _BAR_FIELDS:
        missing = _BAR_FIELDS - keys
        unknown = keys - _BAR_FIELDS
        detail = f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        raise LifecycleSerializationError(f"invalid CanonicalBar fields: {detail}")
    for field_name in ("open", "high", "low", "close"):
        if not isinstance(payload[field_name], str):
            raise LifecycleSerializationError(
                f"CanonicalBar.{field_name} must be a Decimal string"
            )
    if payload["volume"] is not None and not isinstance(payload["volume"], str):
        raise LifecycleSerializationError(
            "CanonicalBar.volume must be None or a Decimal string"
        )
    try:
        return CanonicalBar.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise LifecycleSerializationError(f"invalid CanonicalBar: {exc}") from exc


def _timedelta_microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


_SOURCE_CONFIG_FIELDS = {
    "source", "source_timezone", "source_symbol", "canonical_symbol", "timeframe",
    "timestamp_column", "timestamp_semantics", "timestamp_format", "open_column",
    "high_column", "low_column", "close_column", "volume_column", "volume_type",
    "completed_bar_policy", "availability_lag_microseconds", "session_id",
    "boundary_policy", "end_time_column", "symbol_column", "open_time_column",
    "complete_column", "observed_time_column", "complete_true_values",
    "complete_false_values", "delimiter", "strict",
}


def _source_config_to_dict(value: SourceDataConfig) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": value.source,
        "source_timezone": value.source_timezone,
        "source_symbol": value.source_symbol,
        "canonical_symbol": value.canonical_symbol,
        "timeframe": value.timeframe.value,
        "timestamp_column": value.timestamp_column,
        "timestamp_semantics": value.timestamp_semantics.value,
        "timestamp_format": value.timestamp_format,
        "open_column": value.open_column,
        "high_column": value.high_column,
        "low_column": value.low_column,
        "close_column": value.close_column,
        "volume_column": value.volume_column,
        "volume_type": value.volume_type.value,
        "completed_bar_policy": value.completed_bar_policy.value,
        "availability_lag_microseconds": _timedelta_microseconds(value.availability_lag),
        "session_id": value.session_id,
        "boundary_policy": value.boundary_policy,
        "end_time_column": value.end_time_column,
        "symbol_column": value.symbol_column,
        "open_time_column": value.open_time_column,
        "complete_column": value.complete_column,
        "observed_time_column": value.observed_time_column,
        "complete_true_values": list(value.complete_true_values),
        "complete_false_values": list(value.complete_false_values),
        "delimiter": value.delimiter,
        "strict": value.strict,
    }


def _source_config_from_dict(payload: Mapping[str, Any]) -> SourceDataConfig:
    data = _exact_payload(payload, "SourceDataConfig", _SOURCE_CONFIG_FIELDS)
    micros = data["availability_lag_microseconds"]
    if isinstance(micros, bool) or not isinstance(micros, int):
        raise LifecycleSerializationError(
            "SourceDataConfig.availability_lag_microseconds must be an integer"
        )
    try:
        return SourceDataConfig(
            source=data["source"], source_timezone=data["source_timezone"],
            source_symbol=data["source_symbol"], canonical_symbol=data["canonical_symbol"],
            timeframe=Timeframe(data["timeframe"]), timestamp_column=data["timestamp_column"],
            timestamp_semantics=TimestampSemantics(data["timestamp_semantics"]),
            timestamp_format=data["timestamp_format"], open_column=data["open_column"],
            high_column=data["high_column"], low_column=data["low_column"],
            close_column=data["close_column"], volume_column=data["volume_column"],
            volume_type=VolumeType(data["volume_type"]),
            completed_bar_policy=CompletedBarPolicy(data["completed_bar_policy"]),
            availability_lag=timedelta(microseconds=micros),
            session_id=data["session_id"], boundary_policy=data["boundary_policy"],
            end_time_column=data["end_time_column"], symbol_column=data["symbol_column"],
            open_time_column=data["open_time_column"], complete_column=data["complete_column"],
            observed_time_column=data["observed_time_column"],
            complete_true_values=tuple(_ordered_list(data, "SourceDataConfig", "complete_true_values")),
            complete_false_values=tuple(_ordered_list(data, "SourceDataConfig", "complete_false_values")),
            delimiter=data["delimiter"], strict=data["strict"],
        )
    except LifecycleSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise LifecycleSerializationError(f"invalid SourceDataConfig: {exc}") from exc


_ISSUE_FIELDS = {"code", "severity", "row_number", "field", "raw_value", "reason"}


def _issue_to_dict(value: DataQualityIssue) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "code": value.code,
            "severity": value.severity.value, "row_number": value.row_number,
            "field": value.field, "raw_value": value.raw_value, "reason": value.reason}


def _issue_from_dict(payload: Mapping[str, Any]) -> DataQualityIssue:
    data = _exact_payload(payload, "DataQualityIssue", _ISSUE_FIELDS)
    try:
        _integer("DataQualityIssue.row_number", data["row_number"],
                 LifecycleSerializationError, minimum=1)
        return DataQualityIssue(data["code"], IssueSeverity(data["severity"]),
                                data["row_number"], data["field"],
                                data["raw_value"], data["reason"])
    except (TypeError, ValueError) as exc:
        raise LifecycleSerializationError(f"invalid DataQualityIssue: {exc}") from exc


_REPORT_FIELDS = {
    "total_rows", "accepted_rows", "rejected_rows", "duplicate_count",
    "conflicting_duplicate_count", "out_of_order_count", "overlap_count",
    "gap_count", "invalid_ohlc_count", "invalid_timestamp_count",
    "invalid_volume_count", "symbol_mismatch_count", "timeframe", "source",
    "earliest_timestamp", "latest_timestamp", "warnings", "errors", "assumptions",
}


def _quality_report_to_dict(value: DataQualityReport) -> dict[str, object]:
    result = {field: getattr(value, field) for field in (
        "total_rows", "accepted_rows", "rejected_rows", "duplicate_count",
        "conflicting_duplicate_count", "out_of_order_count", "overlap_count",
        "gap_count", "invalid_ohlc_count", "invalid_timestamp_count",
        "invalid_volume_count", "symbol_mismatch_count")}
    result.update({"schema_version": SCHEMA_VERSION, "timeframe": value.timeframe.value,
                   "source": value.source,
                   "earliest_timestamp": None if value.earliest_timestamp is None else value.earliest_timestamp.isoformat(),
                   "latest_timestamp": None if value.latest_timestamp is None else value.latest_timestamp.isoformat(),
                   "warnings": [_issue_to_dict(item) for item in value.warnings],
                   "errors": [_issue_to_dict(item) for item in value.errors],
                   "assumptions": list(value.assumptions)})
    return result


def _quality_report_from_dict(payload: Mapping[str, Any]) -> DataQualityReport:
    data = _exact_payload(payload, "DataQualityReport", _REPORT_FIELDS)
    try:
        kwargs = {field: data[field] for field in (
            "total_rows", "accepted_rows", "rejected_rows", "duplicate_count",
            "conflicting_duplicate_count", "out_of_order_count", "overlap_count",
            "gap_count", "invalid_ohlc_count", "invalid_timestamp_count",
            "invalid_volume_count", "symbol_mismatch_count")}
        for field_name, value in kwargs.items():
            _integer(f"DataQualityReport.{field_name}", value,
                     LifecycleSerializationError)
        return DataQualityReport(
            **kwargs, timeframe=Timeframe(data["timeframe"]), source=data["source"],
            earliest_timestamp=_parse_optional_time("earliest_timestamp", data["earliest_timestamp"]),
            latest_timestamp=_parse_optional_time("latest_timestamp", data["latest_timestamp"]),
            warnings=tuple(_issue_from_dict(item) for item in _ordered_list(data, "DataQualityReport", "warnings")),
            errors=tuple(_issue_from_dict(item) for item in _ordered_list(data, "DataQualityReport", "errors")),
            assumptions=tuple(_ordered_list(data, "DataQualityReport", "assumptions")),
        )
    except LifecycleSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise LifecycleSerializationError(f"invalid DataQualityReport: {exc}") from exc


def _load_result_to_dict(value: LoadResult) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION,
            "bars": [item.to_dict() for item in value.bars],
            "quality_report": _quality_report_to_dict(value.quality_report),
            "source_config": _source_config_to_dict(value.source_config),
            "loaded_row_count": value.loaded_row_count,
            "accepted_row_count": value.accepted_row_count,
            "rejected_row_count": value.rejected_row_count}


def _load_result_from_dict(payload: Mapping[str, Any]) -> LoadResult:
    data = _exact_payload(payload, "LoadResult", {"bars", "quality_report", "source_config",
                                                  "loaded_row_count", "accepted_row_count",
                                                  "rejected_row_count"})
    try:
        return LoadResult(
            bars=tuple(_bar_from_dict(item) for item in _ordered_list(data, "LoadResult", "bars")),
            quality_report=_quality_report_from_dict(data["quality_report"]),
            source_config=_source_config_from_dict(data["source_config"]),
            loaded_row_count=data["loaded_row_count"], accepted_row_count=data["accepted_row_count"],
            rejected_row_count=data["rejected_row_count"],
        )
    except LifecycleSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise LifecycleSerializationError(f"invalid LoadResult: {exc}") from exc


@dataclass(frozen=True, slots=True)
class LifecycleInput:
    source: LoadResult
    subjects: tuple[BoundaryRef, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleInputError)
        if not isinstance(self.source, LoadResult):
            raise LifecycleInputError("source must be a C-001 LoadResult")
        if not isinstance(self.subjects, tuple) or not self.subjects:
            raise LifecycleInputError("subjects must be a non-empty BoundaryRef tuple")
        if any(not isinstance(item, BoundaryRef) for item in self.subjects):
            raise LifecycleInputError("subjects must contain only BoundaryRef values")
        ids = tuple(item.object_id for item in self.subjects)
        if len(ids) != len(set(ids)):
            raise LifecycleInputError("subject object_id values must be unique")
        for subject in self.subjects:
            if subject.object_kind not in {
                StructureObjectKind.LEVEL_CANDIDATE,
                StructureObjectKind.STRUCTURE_CLUSTER,
            }:
                raise LifecycleInputError("unsupported lifecycle subject object_kind")
            if subject.lifecycle_state is not LifecycleState.CONFIRMED:
                raise LifecycleInputError(
                    "subject lifecycle_state must be exactly CONFIRMED"
                )
            valid = (
                subject.boundary_side is BoundarySide.UPPER
                and subject.market_role is MarketRole.RESISTANCE
            ) or (
                subject.boundary_side is BoundarySide.LOWER
                and subject.market_role is MarketRole.SUPPORT
            )
            if not valid:
                raise LifecycleInputError("subject side/role mapping is invalid")

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version,
                "source": _load_result_to_dict(self.source),
                "subjects": [item.to_dict() for item in self.subjects]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleInput:
        data = _exact_payload(payload, cls.__name__, {"source", "subjects"})
        try:
            return cls(
                source=_load_result_from_dict(data["source"]),
                subjects=tuple(BoundaryRef.from_dict(item) for item in _ordered_list(data, cls.__name__, "subjects")),
                schema_version=data["schema_version"],
            )
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleInputError) as exc:
            raise LifecycleSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


_TRANSITIONS = {
    (LifecycleEventType.ACTIVATED, LifecycleState.CONFIRMED, LifecycleState.FRESH),
    (LifecycleEventType.TEST, LifecycleState.FRESH, LifecycleState.TESTED),
    (LifecycleEventType.TEST, LifecycleState.TESTED, LifecycleState.TESTED),
    (LifecycleEventType.WEAKENED, LifecycleState.TESTED, LifecycleState.WEAKENED),
    (LifecycleEventType.TEST, LifecycleState.WEAKENED, LifecycleState.WEAKENED),
    (LifecycleEventType.BROKEN, LifecycleState.FRESH, LifecycleState.BROKEN),
    (LifecycleEventType.BROKEN, LifecycleState.TESTED, LifecycleState.BROKEN),
    (LifecycleEventType.BROKEN, LifecycleState.WEAKENED, LifecycleState.BROKEN),
    (LifecycleEventType.FLIP_TOUCH, LifecycleState.BROKEN, LifecycleState.BROKEN),
    (LifecycleEventType.FLIPPED, LifecycleState.BROKEN, LifecycleState.FLIPPED),
    (LifecycleEventType.RETIRED, LifecycleState.BROKEN, LifecycleState.RETIRED),
}


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    event_id: str
    subject_id: str
    event_type: LifecycleEventType
    from_state: LifecycleState
    to_state: LifecycleState
    event_origin_time: datetime
    event_confirm_time: datetime
    first_seen_time: datetime
    source_bar_key: str | None
    source_price: Decimal | None
    test_count: int
    effective_boundary_side: BoundarySide
    effective_market_role: MarketRole
    retirement_reason: RetirementReason | None
    evidence: tuple[str, ...]
    prior_event_ids: tuple[str, ...]
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleEngineError)
        _text("event_id", self.event_id, LifecycleEngineError)
        _text("subject_id", self.subject_id, LifecycleEngineError)
        if not isinstance(self.event_type, LifecycleEventType):
            raise LifecycleEngineError("event_type must be a LifecycleEventType")
        if not isinstance(self.from_state, LifecycleState) or not isinstance(self.to_state, LifecycleState):
            raise LifecycleEngineError("from_state and to_state must be LifecycleState values")
        if (self.event_type, self.from_state, self.to_state) not in _TRANSITIONS:
            raise LifecycleEngineError("illegal lifecycle event transition")
        origin = _time("event_origin_time", self.event_origin_time, LifecycleEngineError)
        confirm = _time("event_confirm_time", self.event_confirm_time, LifecycleEngineError)
        first_seen = _time("first_seen_time", self.first_seen_time, LifecycleEngineError)
        if confirm < origin:
            raise LifecycleEngineError("event_confirm_time must be >= event_origin_time")
        if first_seen != confirm:
            raise LifecycleEngineError("first_seen_time must equal event_confirm_time")
        if self.event_type is LifecycleEventType.ACTIVATED:
            if self.source_bar_key is not None or self.source_price is not None:
                raise LifecycleEngineError("ACTIVATED cannot reference a source bar or price")
        else:
            _text("source_bar_key", self.source_bar_key, LifecycleEngineError)
            _decimal("source_price", self.source_price, LifecycleEngineError)
        _integer("test_count", self.test_count, LifecycleEngineError)
        if not isinstance(self.effective_boundary_side, BoundarySide) or not isinstance(self.effective_market_role, MarketRole):
            raise LifecycleEngineError("event effective side/role types are invalid")
        valid_role = (
            self.effective_boundary_side is BoundarySide.UPPER
            and self.effective_market_role is MarketRole.RESISTANCE
        ) or (
            self.effective_boundary_side is BoundarySide.LOWER
            and self.effective_market_role is MarketRole.SUPPORT
        )
        if not valid_role:
            raise LifecycleEngineError("event effective side/role mapping is invalid")
        if self.event_type is LifecycleEventType.RETIRED:
            if not isinstance(self.retirement_reason, RetirementReason):
                raise LifecycleEngineError("RETIRED requires retirement_reason")
        elif self.retirement_reason is not None:
            raise LifecycleEngineError("retirement_reason is valid only for RETIRED")
        evidence = _text_tuple(name, "evidence", self.evidence, LifecycleEngineError,
                               non_empty=True)
        prior = _text_tuple(name, "prior_event_ids", self.prior_event_ids,
                            LifecycleEngineError, unique=True)
        if len(prior) > 1:
            raise LifecycleEngineError("prior_event_ids is bounded to the immediate prior event")
        if self.event_type is LifecycleEventType.ACTIVATED:
            if prior or self.test_count != 0:
                raise LifecycleEngineError("ACTIVATED must be the first zero-test event")
        elif len(prior) != 1:
            raise LifecycleEngineError("non-activation events require the immediate prior event ID")
        if self.event_type in {LifecycleEventType.TEST, LifecycleEventType.WEAKENED} and self.test_count < 1:
            raise LifecycleEngineError("test and weakened events require positive test_count")
        if not isinstance(self.provenance, ProvenanceRef):
            raise LifecycleEngineError("provenance must be a ProvenanceRef")
        object.__setattr__(self, "event_origin_time", origin)
        object.__setattr__(self, "event_confirm_time", confirm)
        object.__setattr__(self, "first_seen_time", first_seen)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "prior_event_ids", prior)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "event_id": self.event_id,
                "subject_id": self.subject_id, "event_type": self.event_type.value,
                "from_state": self.from_state.value, "to_state": self.to_state.value,
                "event_origin_time": self.event_origin_time.isoformat(),
                "event_confirm_time": self.event_confirm_time.isoformat(),
                "first_seen_time": self.first_seen_time.isoformat(),
                "source_bar_key": self.source_bar_key,
                "source_price": None if self.source_price is None else str(self.source_price),
                "test_count": self.test_count,
                "effective_boundary_side": self.effective_boundary_side.value,
                "effective_market_role": self.effective_market_role.value,
                "retirement_reason": None if self.retirement_reason is None else self.retirement_reason.value,
                "evidence": list(self.evidence), "prior_event_ids": list(self.prior_event_ids),
                "provenance": self.provenance.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleEvent:
        fields = {"event_id", "subject_id", "event_type", "from_state", "to_state",
                  "event_origin_time", "event_confirm_time", "first_seen_time",
                  "source_bar_key", "source_price", "test_count",
                  "effective_boundary_side", "effective_market_role",
                  "retirement_reason", "evidence", "prior_event_ids", "provenance"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                event_id=data["event_id"], subject_id=data["subject_id"],
                event_type=LifecycleEventType(data["event_type"]),
                from_state=LifecycleState(data["from_state"]), to_state=LifecycleState(data["to_state"]),
                event_origin_time=_parse_time("event_origin_time", data["event_origin_time"]),
                event_confirm_time=_parse_time("event_confirm_time", data["event_confirm_time"]),
                first_seen_time=_parse_time("first_seen_time", data["first_seen_time"]),
                source_bar_key=data["source_bar_key"],
                source_price=None if data["source_price"] is None else _parse_decimal("source_price", data["source_price"]),
                test_count=data["test_count"],
                effective_boundary_side=BoundarySide(data["effective_boundary_side"]),
                effective_market_role=MarketRole(data["effective_market_role"]),
                retirement_reason=None if data["retirement_reason"] is None else RetirementReason(data["retirement_reason"]),
                evidence=tuple(_ordered_list(data, cls.__name__, "evidence")),
                prior_event_ids=tuple(_ordered_list(data, cls.__name__, "prior_event_ids")),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleEngineError) as exc:
            raise LifecycleSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class LifecycleSubjectState:
    state_id: str
    subject_ref: BoundaryRef
    lifecycle_state: LifecycleState
    effective_boundary_side: BoundarySide
    effective_market_role: MarketRole
    structural_origin_time: datetime
    structural_confirm_time: datetime
    state_confirm_time: datetime
    as_of_time: datetime
    test_count: int
    last_test_time: datetime | None
    last_test_confirm_time: datetime | None
    last_test_bar_key: str | None
    break_time: datetime | None
    break_confirm_time: datetime | None
    break_bar_key: str | None
    break_close: Decimal | None
    break_threshold: Decimal | None
    flip_touch_time: datetime | None
    flip_touch_confirm_time: datetime | None
    flip_touch_bar_key: str | None
    flipped_time: datetime | None
    flipped_confirm_time: datetime | None
    flip_confirmation_close: Decimal | None
    flip_confirmation_threshold: Decimal | None
    retired_time: datetime | None
    retired_confirm_time: datetime | None
    retirement_reason: RetirementReason | None
    event_ids: tuple[str, ...]
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleEngineError)
        _text("state_id", self.state_id, LifecycleEngineError)
        if not isinstance(self.subject_ref, BoundaryRef):
            raise LifecycleEngineError("subject_ref must be a BoundaryRef")
        if self.lifecycle_state not in {
            LifecycleState.FRESH, LifecycleState.TESTED, LifecycleState.WEAKENED,
            LifecycleState.BROKEN, LifecycleState.FLIPPED, LifecycleState.RETIRED,
        }:
            raise LifecycleEngineError("LifecycleSubjectState has an invalid lifecycle_state")
        if not isinstance(self.effective_boundary_side, BoundarySide) or not isinstance(self.effective_market_role, MarketRole):
            raise LifecycleEngineError("effective side/role types are invalid")
        original_side = self.subject_ref.boundary_side
        original_role = self.subject_ref.market_role
        expected_side = (
            BoundarySide.LOWER if original_side is BoundarySide.UPPER else BoundarySide.UPPER
        ) if self.lifecycle_state is LifecycleState.FLIPPED else original_side
        expected_role = (
            MarketRole.SUPPORT if original_role is MarketRole.RESISTANCE else MarketRole.RESISTANCE
        ) if self.lifecycle_state is LifecycleState.FLIPPED else original_role
        if self.effective_boundary_side is not expected_side or self.effective_market_role is not expected_role:
            raise LifecycleEngineError("effective side/role contradict lifecycle_state")
        structural_origin = _time("structural_origin_time", self.structural_origin_time, LifecycleEngineError)
        structural_confirm = _time("structural_confirm_time", self.structural_confirm_time, LifecycleEngineError)
        state_confirm = _time("state_confirm_time", self.state_confirm_time, LifecycleEngineError)
        as_of = _time("as_of_time", self.as_of_time, LifecycleEngineError)
        if structural_origin != self.subject_ref.origin_time or structural_confirm != self.subject_ref.confirm_time:
            raise LifecycleEngineError("structural times must preserve subject_ref facts")
        if state_confirm < structural_confirm or as_of < state_confirm:
            raise LifecycleEngineError("state/as-of causal time ordering is invalid")
        test_count = _integer("test_count", self.test_count, LifecycleEngineError)
        last_test = _optional_time("last_test_time", self.last_test_time, LifecycleEngineError)
        last_test_confirm = _optional_time("last_test_confirm_time", self.last_test_confirm_time, LifecycleEngineError)
        if test_count == 0:
            if any(value is not None for value in (last_test, last_test_confirm, self.last_test_bar_key)):
                raise LifecycleEngineError("last-test facts must be absent when test_count is zero")
        else:
            if last_test is None or last_test_confirm is None:
                raise LifecycleEngineError("positive test_count requires last-test times")
            _text("last_test_bar_key", self.last_test_bar_key, LifecycleEngineError)
            if last_test_confirm < last_test:
                raise LifecycleEngineError("last_test_confirm_time must be >= last_test_time")
        if self.lifecycle_state is LifecycleState.FRESH and test_count != 0:
            raise LifecycleEngineError("FRESH must have zero tests")
        if self.lifecycle_state in {LifecycleState.TESTED, LifecycleState.WEAKENED} and test_count < 1:
            raise LifecycleEngineError("TESTED and WEAKENED require a positive test_count")
        break_time = _optional_time("break_time", self.break_time, LifecycleEngineError)
        break_confirm = _optional_time("break_confirm_time", self.break_confirm_time, LifecycleEngineError)
        break_values = (break_time, break_confirm, self.break_bar_key, self.break_close, self.break_threshold)
        has_break = all(value is not None for value in break_values)
        if any(value is not None for value in break_values) and not has_break:
            raise LifecycleEngineError("break facts must be present or absent together")
        if has_break:
            _text("break_bar_key", self.break_bar_key, LifecycleEngineError)
            _decimal("break_close", self.break_close, LifecycleEngineError)
            _decimal("break_threshold", self.break_threshold, LifecycleEngineError)
            if break_confirm < break_time:  # type: ignore[operator]
                raise LifecycleEngineError("break_confirm_time must be >= break_time")
        if self.lifecycle_state in {LifecycleState.FRESH, LifecycleState.TESTED, LifecycleState.WEAKENED} and has_break:
            raise LifecycleEngineError("pre-break state cannot contain break facts")
        if self.lifecycle_state in {LifecycleState.BROKEN, LifecycleState.FLIPPED, LifecycleState.RETIRED} and not has_break:
            raise LifecycleEngineError("post-break state requires break facts")
        touch_time = _optional_time("flip_touch_time", self.flip_touch_time, LifecycleEngineError)
        touch_confirm = _optional_time("flip_touch_confirm_time", self.flip_touch_confirm_time, LifecycleEngineError)
        touch_values = (touch_time, touch_confirm, self.flip_touch_bar_key)
        has_touch = all(value is not None for value in touch_values)
        if any(value is not None for value in touch_values) and not has_touch:
            raise LifecycleEngineError("flip-touch facts must be present or absent together")
        if has_touch:
            _text("flip_touch_bar_key", self.flip_touch_bar_key, LifecycleEngineError)
            if touch_confirm < touch_time:  # type: ignore[operator]
                raise LifecycleEngineError("flip_touch_confirm_time must be >= flip_touch_time")
            if not has_break or touch_time <= break_time or touch_confirm < break_confirm:  # type: ignore[operator]
                raise LifecycleEngineError("flip touch must causally follow Break")
        flipped_time = _optional_time("flipped_time", self.flipped_time, LifecycleEngineError)
        flipped_confirm = _optional_time("flipped_confirm_time", self.flipped_confirm_time, LifecycleEngineError)
        flipped_values = (flipped_time, flipped_confirm, self.flip_confirmation_close, self.flip_confirmation_threshold)
        has_flipped = all(value is not None for value in flipped_values)
        if any(value is not None for value in flipped_values) and not has_flipped:
            raise LifecycleEngineError("flip-confirmation facts must be present or absent together")
        if self.lifecycle_state is LifecycleState.FLIPPED:
            if not has_touch or not has_flipped:
                raise LifecycleEngineError("FLIPPED requires touch and confirmation facts")
        elif has_flipped:
            raise LifecycleEngineError("only FLIPPED may contain flip-confirmation facts")
        if has_flipped:
            _decimal("flip_confirmation_close", self.flip_confirmation_close, LifecycleEngineError)
            _decimal("flip_confirmation_threshold", self.flip_confirmation_threshold, LifecycleEngineError)
            if flipped_confirm < flipped_time or flipped_time <= touch_time:  # type: ignore[operator]
                raise LifecycleEngineError("flip confirmation must causally follow its touch bar")
        retired_time = _optional_time("retired_time", self.retired_time, LifecycleEngineError)
        retired_confirm = _optional_time("retired_confirm_time", self.retired_confirm_time, LifecycleEngineError)
        if self.lifecycle_state is LifecycleState.RETIRED:
            if retired_time is None or retired_confirm is None or not isinstance(self.retirement_reason, RetirementReason):
                raise LifecycleEngineError("RETIRED requires retirement facts and reason")
        elif any(value is not None for value in (retired_time, retired_confirm, self.retirement_reason)):
            raise LifecycleEngineError("retirement facts are valid only for RETIRED")
        if retired_time is not None and retired_confirm < retired_time:  # type: ignore[operator]
            raise LifecycleEngineError("retired_confirm_time must be >= retired_time")
        if retired_time is not None and (not has_break or retired_time <= break_time or retired_confirm < break_confirm):  # type: ignore[operator]
            raise LifecycleEngineError("retirement must causally follow Break")
        for field_name, value in (
            ("last_test_time", last_test), ("break_time", break_time),
            ("flip_touch_time", touch_time), ("flipped_time", flipped_time),
            ("retired_time", retired_time),
        ):
            if value is not None and value < structural_confirm:
                raise LifecycleEngineError(f"{field_name} cannot precede structural ConfirmTime")
        confirms = [structural_confirm]
        for value in (last_test_confirm, break_confirm, touch_confirm, flipped_confirm, retired_confirm):
            if value is not None:
                confirms.append(value)
        if state_confirm != max(confirms):
            raise LifecycleEngineError("state_confirm_time must equal the latest lifecycle event time")
        event_ids = _text_tuple(name, "event_ids", self.event_ids, LifecycleEngineError,
                                non_empty=True, unique=True)
        if not isinstance(self.provenance, ProvenanceRef):
            raise LifecycleEngineError("provenance must be a ProvenanceRef")
        for field_name, value in (
            ("structural_origin_time", structural_origin), ("structural_confirm_time", structural_confirm),
            ("state_confirm_time", state_confirm), ("as_of_time", as_of),
            ("last_test_time", last_test), ("last_test_confirm_time", last_test_confirm),
            ("break_time", break_time), ("break_confirm_time", break_confirm),
            ("flip_touch_time", touch_time), ("flip_touch_confirm_time", touch_confirm),
            ("flipped_time", flipped_time), ("flipped_confirm_time", flipped_confirm),
            ("retired_time", retired_time), ("retired_confirm_time", retired_confirm),
        ):
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "event_ids", event_ids)

    def to_boundary_ref(self) -> BoundaryRef:
        latest_event_id = self.event_ids[-1]
        provenance = ProvenanceRef(
            source_module="msa.research.lifecycle.engine",
            source_version=self.provenance.source_version,
            source_object_id=self.state_id,
            policy_id=self.provenance.policy_id,
            parent_object_ids=(self.subject_ref.object_id, latest_event_id),
            notes=("immutable lifecycle boundary snapshot", f"state={self.lifecycle_state.value}"),
        )
        return BoundaryRef(
            object_kind=self.subject_ref.object_kind,
            object_id=f"lifecycle-boundary-v1-{self.state_id}",
            symbol=self.subject_ref.symbol,
            timeframe=self.subject_ref.timeframe,
            scale=self.subject_ref.scale,
            price_range=self.subject_ref.price_range,
            boundary_side=self.effective_boundary_side,
            market_role=self.effective_market_role,
            lifecycle_state=self.lifecycle_state,
            origin_time=self.structural_origin_time,
            confirm_time=self.state_confirm_time,
            source_types=self.subject_ref.source_types,
            structure_families=self.subject_ref.structure_families,
            provenance=provenance,
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version,
            "state_id": self.state_id, "subject_ref": self.subject_ref.to_dict(),
            "lifecycle_state": self.lifecycle_state.value,
            "effective_boundary_side": self.effective_boundary_side.value,
            "effective_market_role": self.effective_market_role.value,
            "test_count": self.test_count, "last_test_bar_key": self.last_test_bar_key,
            "break_bar_key": self.break_bar_key, "flip_touch_bar_key": self.flip_touch_bar_key,
            "retirement_reason": None if self.retirement_reason is None else self.retirement_reason.value,
            "event_ids": list(self.event_ids), "provenance": self.provenance.to_dict()}
        for field_name in ("structural_origin_time", "structural_confirm_time", "state_confirm_time", "as_of_time",
                           "last_test_time", "last_test_confirm_time", "break_time", "break_confirm_time",
                           "flip_touch_time", "flip_touch_confirm_time", "flipped_time", "flipped_confirm_time",
                           "retired_time", "retired_confirm_time"):
            value = getattr(self, field_name)
            result[field_name] = None if value is None else value.isoformat()
        for field_name in ("break_close", "break_threshold", "flip_confirmation_close", "flip_confirmation_threshold"):
            value = getattr(self, field_name)
            result[field_name] = None if value is None else str(value)
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleSubjectState:
        fields = {field.name for field in cls.__dataclass_fields__.values()} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            time_fields = {name: _parse_optional_time(name, data[name]) for name in (
                "last_test_time", "last_test_confirm_time", "break_time", "break_confirm_time",
                "flip_touch_time", "flip_touch_confirm_time", "flipped_time", "flipped_confirm_time",
                "retired_time", "retired_confirm_time")}
            decimal_fields = {name: None if data[name] is None else _parse_decimal(name, data[name]) for name in (
                "break_close", "break_threshold", "flip_confirmation_close", "flip_confirmation_threshold")}
            return cls(
                state_id=data["state_id"], subject_ref=BoundaryRef.from_dict(data["subject_ref"]),
                lifecycle_state=LifecycleState(data["lifecycle_state"]),
                effective_boundary_side=BoundarySide(data["effective_boundary_side"]),
                effective_market_role=MarketRole(data["effective_market_role"]),
                structural_origin_time=_parse_time("structural_origin_time", data["structural_origin_time"]),
                structural_confirm_time=_parse_time("structural_confirm_time", data["structural_confirm_time"]),
                state_confirm_time=_parse_time("state_confirm_time", data["state_confirm_time"]),
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                test_count=data["test_count"], last_test_bar_key=data["last_test_bar_key"],
                break_bar_key=data["break_bar_key"], flip_touch_bar_key=data["flip_touch_bar_key"],
                retirement_reason=None if data["retirement_reason"] is None else RetirementReason(data["retirement_reason"]),
                event_ids=tuple(_ordered_list(data, cls.__name__, "event_ids")),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"], **time_fields, **decimal_fields,
            )
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleEngineError) as exc:
            raise LifecycleSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class LifecycleReport:
    input_subject_count: int
    visible_subject_count: int
    fresh_count: int
    tested_count: int
    weakened_count: int
    broken_count: int
    flipped_count: int
    retired_count: int
    test_event_count: int
    break_event_count: int
    flip_touch_event_count: int
    flip_event_count: int
    retirement_event_count: int
    processed_bar_count: int
    causal_prefix_truncated: bool
    gap_count: int
    earliest_event_confirm_time: datetime | None
    latest_event_confirm_time: datetime | None
    engine_id: str
    engine_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleEngineError)
        count_fields = tuple(field for field in self.__dataclass_fields__ if field.endswith("_count"))
        for field_name in count_fields:
            _integer(field_name, getattr(self, field_name), LifecycleEngineError)
        if self.visible_subject_count > self.input_subject_count:
            raise LifecycleEngineError("visible_subject_count cannot exceed input_subject_count")
        if sum(getattr(self, field) for field in ("fresh_count", "tested_count", "weakened_count", "broken_count", "flipped_count", "retired_count")) != self.visible_subject_count:
            raise LifecycleEngineError("lifecycle state counts must equal visible_subject_count")
        _bool("causal_prefix_truncated", self.causal_prefix_truncated, LifecycleEngineError)
        earliest = _optional_time("earliest_event_confirm_time", self.earliest_event_confirm_time, LifecycleEngineError)
        latest = _optional_time("latest_event_confirm_time", self.latest_event_confirm_time, LifecycleEngineError)
        if (earliest is None) != (latest is None) or (earliest is not None and earliest > latest):
            raise LifecycleEngineError("event confirm time bounds are inconsistent")
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(field_name, getattr(self, field_name), LifecycleEngineError)
        for field_name in ("assumptions", "warnings", "errors"):
            object.__setattr__(self, field_name, _text_tuple(name, field_name, getattr(self, field_name), LifecycleEngineError))
        object.__setattr__(self, "earliest_event_confirm_time", earliest)
        object.__setattr__(self, "latest_event_confirm_time", latest)

    def to_dict(self) -> dict[str, object]:
        result = {field: getattr(self, field) for field in self.__dataclass_fields__ if field not in {
            "schema_version", "earliest_event_confirm_time", "latest_event_confirm_time", "assumptions", "warnings", "errors"}}
        result.update({"schema_version": self.schema_version,
                       "earliest_event_confirm_time": None if self.earliest_event_confirm_time is None else self.earliest_event_confirm_time.isoformat(),
                       "latest_event_confirm_time": None if self.latest_event_confirm_time is None else self.latest_event_confirm_time.isoformat(),
                       "assumptions": list(self.assumptions), "warnings": list(self.warnings), "errors": list(self.errors)})
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleReport:
        fields = set(cls.__dataclass_fields__) - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            kwargs = {field: data[field] for field in fields if field not in {
                "earliest_event_confirm_time", "latest_event_confirm_time", "assumptions", "warnings", "errors"}}
            return cls(**kwargs,
                       earliest_event_confirm_time=_parse_optional_time("earliest_event_confirm_time", data["earliest_event_confirm_time"]),
                       latest_event_confirm_time=_parse_optional_time("latest_event_confirm_time", data["latest_event_confirm_time"]),
                       assumptions=tuple(_ordered_list(data, cls.__name__, "assumptions")),
                       warnings=tuple(_ordered_list(data, cls.__name__, "warnings")),
                       errors=tuple(_ordered_list(data, cls.__name__, "errors")),
                       schema_version=data["schema_version"])
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleEngineError) as exc:
            raise LifecycleSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    snapshot_id: str
    as_of_time: datetime
    states: tuple[LifecycleSubjectState, ...]
    events: tuple[LifecycleEvent, ...]
    report: LifecycleReport
    config_snapshot: LifecycleConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleEngineError)
        _text("snapshot_id", self.snapshot_id, LifecycleEngineError)
        as_of = _time("as_of_time", self.as_of_time, LifecycleEngineError)
        if not isinstance(self.states, tuple) or any(not isinstance(item, LifecycleSubjectState) for item in self.states):
            raise LifecycleEngineError("states must be a LifecycleSubjectState tuple")
        states = tuple(sorted(self.states, key=lambda item: item.subject_ref.object_id))
        if len({item.subject_ref.object_id for item in states}) != len(states):
            raise LifecycleEngineError("snapshot states must have unique subject IDs")
        if any(item.as_of_time != as_of for item in states):
            raise LifecycleEngineError("every state.as_of_time must equal snapshot.as_of_time")
        if not isinstance(self.events, tuple) or any(not isinstance(item, LifecycleEvent) for item in self.events):
            raise LifecycleEngineError("events must be a LifecycleEvent tuple")
        events = tuple(sorted(self.events, key=lambda item: (item.event_confirm_time, item.subject_id, item.event_id)))
        if events != self.events or len({item.event_id for item in events}) != len(events):
            raise LifecycleEngineError("events must be uniquely and stably ordered")
        if any(item.event_confirm_time > as_of for item in events):
            raise LifecycleEngineError("event cannot follow snapshot.as_of_time")
        by_subject = {item.subject_ref.object_id: item for item in states}
        for subject_id, state in by_subject.items():
            expected = tuple(item.event_id for item in events if item.subject_id == subject_id)
            if state.event_ids != expected:
                raise LifecycleEngineError("state.event_ids must equal the subject event ledger")
        if {item.subject_id for item in events} - set(by_subject):
            raise LifecycleEngineError("event references a subject absent from snapshot states")
        if not isinstance(self.report, LifecycleReport) or not isinstance(self.config_snapshot, LifecycleConfig):
            raise LifecycleEngineError("snapshot report/config types are invalid")
        if (
            self.report.engine_id != self.config_snapshot.engine_id
            or self.report.engine_version != self.config_snapshot.engine_version
            or self.report.policy_id != self.config_snapshot.policy_id
        ):
            raise LifecycleEngineError("report engine identity must match config_snapshot")
        if self.report.visible_subject_count != len(states):
            raise LifecycleEngineError("report visible count must equal states length")
        state_counts = {
            LifecycleState.FRESH: self.report.fresh_count,
            LifecycleState.TESTED: self.report.tested_count,
            LifecycleState.WEAKENED: self.report.weakened_count,
            LifecycleState.BROKEN: self.report.broken_count,
            LifecycleState.FLIPPED: self.report.flipped_count,
            LifecycleState.RETIRED: self.report.retired_count,
        }
        if any(
            expected != sum(item.lifecycle_state is state for item in states)
            for state, expected in state_counts.items()
        ):
            raise LifecycleEngineError("report lifecycle counts contradict snapshot states")
        event_counts = {
            LifecycleEventType.TEST: self.report.test_event_count,
            LifecycleEventType.BROKEN: self.report.break_event_count,
            LifecycleEventType.FLIP_TOUCH: self.report.flip_touch_event_count,
            LifecycleEventType.FLIPPED: self.report.flip_event_count,
            LifecycleEventType.RETIRED: self.report.retirement_event_count,
        }
        if any(
            expected != sum(item.event_type is event_type for item in events)
            for event_type, expected in event_counts.items()
        ):
            raise LifecycleEngineError("report event counts contradict snapshot events")
        event_times = tuple(item.event_confirm_time for item in events)
        if self.report.earliest_event_confirm_time != (min(event_times) if event_times else None):
            raise LifecycleEngineError("report earliest event time contradicts snapshot events")
        if self.report.latest_event_confirm_time != (max(event_times) if event_times else None):
            raise LifecycleEngineError("report latest event time contradicts snapshot events")
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "states", states)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "snapshot_id": self.snapshot_id,
                "as_of_time": self.as_of_time.isoformat(),
                "states": [item.to_dict() for item in self.states],
                "events": [item.to_dict() for item in self.events],
                "report": self.report.to_dict(), "config_snapshot": self.config_snapshot.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleSnapshot:
        data = _exact_payload(payload, cls.__name__, {"snapshot_id", "as_of_time", "states", "events", "report", "config_snapshot"})
        try:
            return cls(snapshot_id=data["snapshot_id"], as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                       states=tuple(LifecycleSubjectState.from_dict(item) for item in _ordered_list(data, cls.__name__, "states")),
                       events=tuple(LifecycleEvent.from_dict(item) for item in _ordered_list(data, cls.__name__, "events")),
                       report=LifecycleReport.from_dict(data["report"]),
                       config_snapshot=LifecycleConfig.from_dict(data["config_snapshot"]),
                       schema_version=data["schema_version"])
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleEngineError) as exc:
            raise LifecycleSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class LifecycleHistory:
    events: tuple[LifecycleEvent, ...]
    snapshots: tuple[LifecycleSnapshot, ...]
    final_snapshot: LifecycleSnapshot
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, LifecycleEngineError)
        if not isinstance(self.events, tuple) or any(not isinstance(item, LifecycleEvent) for item in self.events):
            raise LifecycleEngineError("history events must be a LifecycleEvent tuple")
        expected_events = tuple(sorted(self.events, key=lambda item: (item.event_confirm_time, item.subject_id, item.event_id)))
        if expected_events != self.events or len({item.event_id for item in self.events}) != len(self.events):
            raise LifecycleEngineError("history events must be uniquely and stably ordered")
        if not isinstance(self.snapshots, tuple) or not self.snapshots:
            raise LifecycleEngineError("history snapshots must be a non-empty tuple")
        if any(not isinstance(item, LifecycleSnapshot) for item in self.snapshots):
            raise LifecycleEngineError("history snapshots must contain LifecycleSnapshot")
        if any(current.as_of_time <= previous.as_of_time for previous, current in zip(self.snapshots, self.snapshots[1:])):
            raise LifecycleEngineError("history snapshots must be strictly chronological")
        if not isinstance(self.final_snapshot, LifecycleSnapshot) or self.final_snapshot != self.snapshots[-1]:
            raise LifecycleEngineError("final_snapshot must equal the last history snapshot")
        if self.final_snapshot.events != self.events:
            raise LifecycleEngineError("history events must equal final snapshot events")
        for snapshot in self.snapshots:
            expected_prefix = tuple(item for item in self.events if item.event_confirm_time <= snapshot.as_of_time)
            if snapshot.events != expected_prefix:
                raise LifecycleEngineError("each history snapshot must contain the exact event prefix")

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version,
                "events": [item.to_dict() for item in self.events],
                "snapshots": [item.to_dict() for item in self.snapshots],
                "final_snapshot": self.final_snapshot.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleHistory:
        data = _exact_payload(payload, cls.__name__, {"events", "snapshots", "final_snapshot"})
        try:
            return cls(events=tuple(LifecycleEvent.from_dict(item) for item in _ordered_list(data, cls.__name__, "events")),
                       snapshots=tuple(LifecycleSnapshot.from_dict(item) for item in _ordered_list(data, cls.__name__, "snapshots")),
                       final_snapshot=LifecycleSnapshot.from_dict(data["final_snapshot"]),
                       schema_version=data["schema_version"])
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleEngineError) as exc:
            raise LifecycleSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc
