"""Immutable contracts for the causal C-007A resonance-frame assembler."""

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
    Direction,
    LifecycleState,
    ProvenanceRef,
    ScaleDescriptor,
    StructureSourceType,
    TimeframeState,
)
from msa.research.lifecycle import LifecycleHistory
from msa.research.timeframe_state import TimeframeStateHistory

from .errors import (
    ResonanceFrameConfigurationError,
    ResonanceFrameEngineError,
    ResonanceFrameInputError,
    ResonanceFrameSerializationError,
)
from .identity import _context_state_id, _evidence_id, _frame_id, _reference_id


SCHEMA_VERSION = 1

_ASSEMBLER_MODULE = "msa.research.resonance.assembler"
_LIFECYCLE_MODULE = "msa.research.lifecycle.engine"
_REPORT_ASSUMPTIONS = (
    "LifecycleSnapshot states are the complete evidence universe",
    "TimeframeState supplies direction and exact lifecycle alignment only",
    "reference price is completed CanonicalBar.close visible by available_time",
    "C-007A performs no clustering, score, ranking, or ActiveBox selection",
)

_BAR_FIELDS = {
    "symbol", "timeframe", "timestamp", "end_time", "open", "high", "low",
    "close", "volume", "volume_type", "source", "source_timezone",
    "is_complete", "available_time", "session_id", "boundary_policy",
}

_SOURCE_CONFIG_FIELDS = {
    "source", "source_timezone", "source_symbol", "canonical_symbol", "timeframe",
    "timestamp_column", "timestamp_semantics", "timestamp_format", "open_column",
    "high_column", "low_column", "close_column", "volume_column", "volume_type",
    "completed_bar_policy", "availability_lag_microseconds", "session_id",
    "boundary_policy", "end_time_column", "symbol_column", "open_time_column",
    "complete_column", "observed_time_column", "complete_true_values",
    "complete_false_values", "delimiter", "strict",
}

_QUALITY_FIELDS = {
    "total_rows", "accepted_rows", "rejected_rows", "duplicate_count",
    "conflicting_duplicate_count", "out_of_order_count", "overlap_count",
    "gap_count", "invalid_ohlc_count", "invalid_timestamp_count",
    "invalid_volume_count", "symbol_mismatch_count", "timeframe", "source",
    "earliest_timestamp", "latest_timestamp", "warnings", "errors", "assumptions",
}

_QUALITY_COUNT_FIELDS = (
    "total_rows", "accepted_rows", "rejected_rows", "duplicate_count",
    "conflicting_duplicate_count", "out_of_order_count", "overlap_count",
    "gap_count", "invalid_ohlc_count", "invalid_timestamp_count",
    "invalid_volume_count", "symbol_mismatch_count",
)


def _exact_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ResonanceFrameSerializationError(
            f"{object_name} payload must be a mapping"
        )
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise ResonanceFrameSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise ResonanceFrameSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    _schema(payload["schema_version"], object_name, ResonanceFrameSerializationError)
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
        raise ResonanceFrameSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResonanceFrameSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    return _time(field_name, parsed, ResonanceFrameSerializationError)


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    return None if value is None else _parse_time(field_name, value)


def _elapsed_seconds(delta: timedelta) -> Decimal:
    total_microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    return Decimal(total_microseconds) / Decimal("1000000")


def _engine_id_from_notes(
    provenance: ProvenanceRef, *, object_name: str, error_type: type[Exception]
) -> str:
    values = tuple(
        note.removeprefix("engine_id=")
        for note in provenance.notes
        if note.startswith("engine_id=")
    )
    if len(values) != 1 or not values[0].strip():
        raise error_type(
            f"{object_name} provenance must contain exactly one engine_id note"
        )
    return values[0]


def _decimal(
    field_name: str, value: object, error_type: type[Exception]
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise error_type(f"{field_name} must be a finite Decimal")
    return value


def _parse_decimal(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise ResonanceFrameSerializationError(
            f"{field_name} must be a Decimal string"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ResonanceFrameSerializationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise ResonanceFrameSerializationError(f"{field_name} must be finite")
    return parsed


def _ordered_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise ResonanceFrameSerializationError(
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
    rank = -1 if context.scale.rank is None else context.scale.rank
    has_rank = 0 if context.scale.rank is None else 1
    return (context.timeframe.value, context.scale.scale_id, has_rank, rank)


def _timedelta_microseconds(value: timedelta) -> int:
    return value.days * 86_400_000_000 + value.seconds * 1_000_000 + value.microseconds


def _source_config_to_dict(value: SourceDataConfig) -> dict[str, object]:
    result = {
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
    return result


def _source_config_from_dict(payload: Mapping[str, Any]) -> SourceDataConfig:
    data = _exact_payload(payload, "SourceDataConfig", _SOURCE_CONFIG_FIELDS)
    micros = data["availability_lag_microseconds"]
    if isinstance(micros, bool) or not isinstance(micros, int):
        raise ResonanceFrameSerializationError(
            "SourceDataConfig.availability_lag_microseconds must be an integer"
        )
    try:
        return SourceDataConfig(
            source=data["source"], source_timezone=data["source_timezone"],
            source_symbol=data["source_symbol"], canonical_symbol=data["canonical_symbol"],
            timeframe=Timeframe(data["timeframe"]),
            timestamp_column=data["timestamp_column"],
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
    except ResonanceFrameSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise ResonanceFrameSerializationError(
            f"invalid serialized SourceDataConfig: {exc}"
        ) from exc


def _issue_to_dict(value: DataQualityIssue) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION, "code": value.code,
        "severity": value.severity.value, "row_number": value.row_number,
        "field": value.field, "raw_value": value.raw_value, "reason": value.reason,
    }


def _issue_from_dict(payload: Mapping[str, Any]) -> DataQualityIssue:
    data = _exact_payload(
        payload, "DataQualityIssue",
        {"code", "severity", "row_number", "field", "raw_value", "reason"},
    )
    try:
        return DataQualityIssue(
            code=data["code"], severity=IssueSeverity(data["severity"]),
            row_number=data["row_number"], field=data["field"],
            raw_value=data["raw_value"], reason=data["reason"],
        )
    except (TypeError, ValueError) as exc:
        raise ResonanceFrameSerializationError(
            f"invalid serialized DataQualityIssue: {exc}"
        ) from exc


def _quality_to_dict(value: DataQualityReport) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "timeframe": value.timeframe.value,
        "source": value.source,
        "earliest_timestamp": None if value.earliest_timestamp is None else value.earliest_timestamp.isoformat(),
        "latest_timestamp": None if value.latest_timestamp is None else value.latest_timestamp.isoformat(),
        "warnings": [_issue_to_dict(item) for item in value.warnings],
        "errors": [_issue_to_dict(item) for item in value.errors],
        "assumptions": list(value.assumptions),
    }
    for field_name in _QUALITY_COUNT_FIELDS:
        result[field_name] = getattr(value, field_name)
    return result


def _quality_from_dict(payload: Mapping[str, Any]) -> DataQualityReport:
    data = _exact_payload(payload, "DataQualityReport", _QUALITY_FIELDS)
    try:
        counts = {field_name: data[field_name] for field_name in _QUALITY_COUNT_FIELDS}
        return DataQualityReport(
            **counts,
            timeframe=Timeframe(data["timeframe"]), source=data["source"],
            earliest_timestamp=_parse_optional_time(
                "earliest_timestamp", data["earliest_timestamp"]
            ),
            latest_timestamp=_parse_optional_time(
                "latest_timestamp", data["latest_timestamp"]
            ),
            warnings=tuple(
                _issue_from_dict(item)
                for item in _ordered_list(data, "DataQualityReport", "warnings")
            ),
            errors=tuple(
                _issue_from_dict(item)
                for item in _ordered_list(data, "DataQualityReport", "errors")
            ),
            assumptions=tuple(
                _ordered_list(data, "DataQualityReport", "assumptions")
            ),
        )
    except ResonanceFrameSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise ResonanceFrameSerializationError(
            f"invalid serialized DataQualityReport: {exc}"
        ) from exc


def _bar_from_dict(payload: Mapping[str, Any]) -> CanonicalBar:
    if not isinstance(payload, Mapping) or set(payload) != _BAR_FIELDS:
        raise ResonanceFrameSerializationError("CanonicalBar fields are invalid")
    for field_name in ("open", "high", "low", "close"):
        if not isinstance(payload[field_name], str):
            raise ResonanceFrameSerializationError(
                f"CanonicalBar.{field_name} must be a Decimal string"
            )
    if payload["volume"] is not None and not isinstance(payload["volume"], str):
        raise ResonanceFrameSerializationError(
            "CanonicalBar.volume must be None or a Decimal string"
        )
    try:
        return CanonicalBar.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise ResonanceFrameSerializationError(
            f"invalid serialized CanonicalBar: {exc}"
        ) from exc


def _load_result_to_dict(value: LoadResult) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "bars": [item.to_dict() for item in value.bars],
        "quality_report": _quality_to_dict(value.quality_report),
        "source_config": _source_config_to_dict(value.source_config),
        "loaded_row_count": value.loaded_row_count,
        "accepted_row_count": value.accepted_row_count,
        "rejected_row_count": value.rejected_row_count,
    }


def _load_result_from_dict(payload: Mapping[str, Any]) -> LoadResult:
    data = _exact_payload(
        payload, "LoadResult",
        {"bars", "quality_report", "source_config", "loaded_row_count",
         "accepted_row_count", "rejected_row_count"},
    )
    try:
        return LoadResult(
            bars=tuple(
                _bar_from_dict(item)
                for item in _ordered_list(data, "LoadResult", "bars")
            ),
            quality_report=_quality_from_dict(data["quality_report"]),
            source_config=_source_config_from_dict(data["source_config"]),
            loaded_row_count=data["loaded_row_count"],
            accepted_row_count=data["accepted_row_count"],
            rejected_row_count=data["rejected_row_count"],
        )
    except ResonanceFrameSerializationError:
        raise
    except (TypeError, ValueError) as exc:
        raise ResonanceFrameSerializationError(
            f"invalid serialized LoadResult: {exc}"
        ) from exc


class _ResonanceEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact_payload(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise ResonanceFrameSerializationError(
                f"{cls.__name__}.value is unknown: {data['value']!r}"
            ) from exc


class ResonanceEvidenceTier(_ResonanceEnum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"


class ResonanceEvidencePolicy(_ResonanceEnum):
    ALL_EFFECTIVE_LIFECYCLE_STATES = "ALL_EFFECTIVE_LIFECYCLE_STATES"


class ReferencePriceField(_ResonanceEnum):
    CLOSE = "CLOSE"


@dataclass(frozen=True, slots=True)
class ResonanceContext:
    timeframe: Timeframe
    scale: ScaleDescriptor
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameConfigurationError)
        if not isinstance(self.timeframe, Timeframe):
            raise ResonanceFrameConfigurationError(
                "ResonanceContext.timeframe must be an explicit Timeframe"
            )
        if not isinstance(self.scale, ScaleDescriptor):
            raise ResonanceFrameConfigurationError(
                "ResonanceContext.scale must be an explicit ScaleDescriptor"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "timeframe": self.timeframe.value,
            "scale": self.scale.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceContext:
        data = _exact_payload(payload, cls.__name__, {"timeframe", "scale"})
        try:
            return cls(
                timeframe=Timeframe(data["timeframe"]),
                scale=ScaleDescriptor.from_dict(data["scale"]),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceFrameConfig:
    engine_id: str
    engine_version: str
    policy_id: str
    symbol: str
    contexts: tuple[ResonanceContext, ...]
    reference_price_timeframe: Timeframe
    reference_price_field: ReferencePriceField
    evidence_policy: ResonanceEvidencePolicy
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameConfigurationError)
        for field_name in ("engine_id", "engine_version", "policy_id", "symbol"):
            _text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                ResonanceFrameConfigurationError,
            )
        if not isinstance(self.contexts, tuple) or not self.contexts:
            raise ResonanceFrameConfigurationError(
                "ResonanceFrameConfig.contexts must be a non-empty tuple"
            )
        if any(not isinstance(item, ResonanceContext) for item in self.contexts):
            raise ResonanceFrameConfigurationError(
                "ResonanceFrameConfig.contexts must contain ResonanceContext"
            )
        contexts = tuple(sorted(self.contexts, key=_context_key))
        if len(set(contexts)) != len(contexts):
            raise ResonanceFrameConfigurationError(
                "ResonanceFrameConfig.contexts must be unique"
            )
        if not isinstance(self.reference_price_timeframe, Timeframe):
            raise ResonanceFrameConfigurationError(
                "reference_price_timeframe must be an explicit Timeframe"
            )
        if self.reference_price_field is not ReferencePriceField.CLOSE:
            raise ResonanceFrameConfigurationError(
                "reference_price_field must be CLOSE in C-007A"
            )
        if (
            self.evidence_policy
            is not ResonanceEvidencePolicy.ALL_EFFECTIVE_LIFECYCLE_STATES
        ):
            raise ResonanceFrameConfigurationError(
                "evidence_policy must be ALL_EFFECTIVE_LIFECYCLE_STATES"
            )
        _boolean(f"{name}.strict", self.strict, ResonanceFrameConfigurationError)
        if self.strict is not True:
            raise ResonanceFrameConfigurationError(
                "ResonanceFrameConfig.strict must be True; C-007A supports strict mode only"
            )
        object.__setattr__(self, "contexts", contexts)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "policy_id": self.policy_id,
            "symbol": self.symbol,
            "contexts": [item.to_dict() for item in self.contexts],
            "reference_price_timeframe": self.reference_price_timeframe.value,
            "reference_price_field": self.reference_price_field.value,
            "evidence_policy": self.evidence_policy.value,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFrameConfig:
        fields = {
            "engine_id",
            "engine_version",
            "policy_id",
            "symbol",
            "contexts",
            "reference_price_timeframe",
            "reference_price_field",
            "evidence_policy",
            "strict",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                engine_id=data["engine_id"],
                engine_version=data["engine_version"],
                policy_id=data["policy_id"],
                symbol=data["symbol"],
                contexts=tuple(
                    ResonanceContext.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "contexts")
                ),
                reference_price_timeframe=Timeframe(
                    data["reference_price_timeframe"]
                ),
                reference_price_field=ReferencePriceField(
                    data["reference_price_field"]
                ),
                evidence_policy=ResonanceEvidencePolicy(data["evidence_policy"]),
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, ResonanceFrameConfigurationError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ReferencePriceSnapshot:
    reference_id: str
    canonical_bar: CanonicalBar
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameEngineError)
        _text(f"{name}.reference_id", self.reference_id, ResonanceFrameEngineError)
        prefix = "resonance-reference-v1-"
        digest = self.reference_id.removeprefix(prefix)
        if (
            not self.reference_id.startswith(prefix)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ResonanceFrameEngineError(
                "ReferencePriceSnapshot.reference_id must be a canonical SHA-256 identity"
            )
        if not isinstance(self.canonical_bar, CanonicalBar):
            raise ResonanceFrameEngineError(
                "ReferencePriceSnapshot.canonical_bar must be a CanonicalBar"
            )
        if not self.canonical_bar.is_complete:
            raise ResonanceFrameEngineError(
                "ReferencePriceSnapshot.canonical_bar must be complete"
            )
        expected_id = _reference_id(
            self.canonical_bar.to_dict(), schema_version=self.schema_version
        )
        if self.reference_id != expected_id:
            raise ResonanceFrameEngineError(
                "reference_id does not match the complete CanonicalBar payload"
            )

    @property
    def symbol(self) -> str:
        return self.canonical_bar.symbol

    @property
    def timeframe(self) -> Timeframe:
        return self.canonical_bar.timeframe

    @property
    def price(self) -> Decimal:
        return self.canonical_bar.close

    @property
    def bar_timestamp(self) -> datetime:
        return self.canonical_bar.timestamp

    @property
    def bar_end_time(self) -> datetime:
        return self.canonical_bar.end_time

    @property
    def available_time(self) -> datetime:
        return self.canonical_bar.available_time

    @property
    def source(self) -> str:
        return self.canonical_bar.source

    @property
    def source_timezone(self) -> str:
        return self.canonical_bar.source_timezone

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "reference_id": self.reference_id,
            "canonical_bar": self.canonical_bar.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ReferencePriceSnapshot:
        fields = {"reference_id", "canonical_bar"}
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                reference_id=data["reference_id"],
                canonical_bar=_bar_from_dict(data["canonical_bar"]),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, ResonanceFrameEngineError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceContextState:
    context_state_id: str
    context: ResonanceContext
    timeframe_snapshot_id: str
    timeframe_snapshot_as_of_time: datetime
    state: TimeframeState
    source_lifecycle_snapshot_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameEngineError)
        if not isinstance(self.context, ResonanceContext):
            raise ResonanceFrameEngineError(
                "ResonanceContextState.context must be a ResonanceContext"
            )
        for field_name in (
            "context_state_id",
            "timeframe_snapshot_id",
            "source_lifecycle_snapshot_id",
        ):
            _text(
                f"{name}.{field_name}",
                getattr(self, field_name),
                ResonanceFrameEngineError,
            )
        snapshot_time = _time(
            f"{name}.timeframe_snapshot_as_of_time",
            self.timeframe_snapshot_as_of_time,
            ResonanceFrameEngineError,
        )
        if not isinstance(self.state, TimeframeState):
            raise ResonanceFrameEngineError(
                "ResonanceContextState.state must be a TimeframeState"
            )
        if self.state.as_of_time != snapshot_time:
            raise ResonanceFrameEngineError(
                "context TimeframeState.as_of_time must equal snapshot as_of_time"
            )
        if (
            self.state.timeframe is not self.context.timeframe
            or self.state.scale != self.context.scale
        ):
            raise ResonanceFrameEngineError(
                "context must equal TimeframeState timeframe and scale"
            )
        expected_id = _context_state_id(
            context=self.context.to_dict(),
            timeframe_snapshot_id=self.timeframe_snapshot_id,
            timeframe_snapshot_as_of_time=snapshot_time.isoformat(),
            state=self.state.to_dict(),
            source_lifecycle_snapshot_id=self.source_lifecycle_snapshot_id,
            schema_version=self.schema_version,
        )
        if self.context_state_id != expected_id:
            raise ResonanceFrameEngineError(
                "context_state_id does not match the complete TimeframeState payload"
            )
        object.__setattr__(self, "timeframe_snapshot_as_of_time", snapshot_time)

    @property
    def timeframe_state_id(self) -> str:
        return self.state.state_id

    @property
    def direction(self) -> Direction:
        return self.state.direction

    @property
    def state_confirm_time(self) -> datetime:
        return self.state.confirm_time

    @property
    def state_origin_time(self) -> datetime:
        return self.state.origin_time

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "context_state_id": self.context_state_id,
            "context": self.context.to_dict(),
            "timeframe_snapshot_id": self.timeframe_snapshot_id,
            "timeframe_snapshot_as_of_time": self.timeframe_snapshot_as_of_time.isoformat(),
            "state": self.state.to_dict(),
            "source_lifecycle_snapshot_id": self.source_lifecycle_snapshot_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceContextState:
        fields = {
            "context_state_id",
            "context",
            "timeframe_snapshot_id",
            "timeframe_snapshot_as_of_time",
            "state",
            "source_lifecycle_snapshot_id",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                context_state_id=data["context_state_id"],
                context=ResonanceContext.from_dict(data["context"]),
                timeframe_snapshot_id=data["timeframe_snapshot_id"],
                timeframe_snapshot_as_of_time=_parse_time(
                    "timeframe_snapshot_as_of_time",
                    data["timeframe_snapshot_as_of_time"],
                ),
                state=TimeframeState.from_dict(data["state"]),
                source_lifecycle_snapshot_id=data[
                    "source_lifecycle_snapshot_id"
                ],
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, ResonanceFrameEngineError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


_EVIDENCE_TIER_BY_STATE = {
    LifecycleState.FRESH: ResonanceEvidenceTier.CANDIDATE,
    LifecycleState.TESTED: ResonanceEvidenceTier.CONFIRMED,
    LifecycleState.WEAKENED: ResonanceEvidenceTier.CONFIRMED,
    LifecycleState.FLIPPED: ResonanceEvidenceTier.CONFIRMED,
}


@dataclass(frozen=True, slots=True)
class ResonanceEvidence:
    evidence_id: str
    subject_id: str
    lifecycle_state_id: str
    lifecycle_event_id: str
    boundary: BoundaryRef
    tier: ResonanceEvidenceTier
    context: ResonanceContext
    direction: Direction
    lifecycle_state: LifecycleState
    structural_confirm_time: datetime
    state_confirm_time: datetime
    touch_count: int
    source_types: tuple[StructureSourceType, ...]
    structure_families: tuple[str, ...]
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameEngineError)
        for field_name in (
            "evidence_id", "subject_id", "lifecycle_state_id", "lifecycle_event_id"
        ):
            _text(
                f"{name}.{field_name}", getattr(self, field_name),
                ResonanceFrameEngineError,
            )
        if not isinstance(self.boundary, BoundaryRef):
            raise ResonanceFrameEngineError("evidence boundary must be a BoundaryRef")
        if not isinstance(self.context, ResonanceContext):
            raise ResonanceFrameEngineError("evidence context must be a ResonanceContext")
        if (
            self.boundary.timeframe is not self.context.timeframe
            or self.boundary.scale != self.context.scale
        ):
            raise ResonanceFrameEngineError(
                "evidence context must equal BoundaryRef timeframe and scale"
            )
        if not isinstance(self.direction, Direction):
            raise ResonanceFrameEngineError("evidence direction must be a Direction")
        expected_tier = _EVIDENCE_TIER_BY_STATE.get(self.lifecycle_state)
        if expected_tier is None or self.tier is not expected_tier:
            raise ResonanceFrameEngineError("evidence tier contradicts lifecycle_state")
        if self.boundary.lifecycle_state is not self.lifecycle_state:
            raise ResonanceFrameEngineError(
                "evidence BoundaryRef lifecycle_state must equal evidence lifecycle_state"
            )
        expected_boundary_id = f"lifecycle-boundary-v1-{self.lifecycle_state_id}"
        expected_boundary_parents = tuple(
            sorted((self.subject_id, self.lifecycle_event_id))
        )
        if (
            self.boundary.object_id != expected_boundary_id
            or self.boundary.provenance.source_module != _LIFECYCLE_MODULE
            or self.boundary.provenance.source_object_id
            != self.lifecycle_state_id
            or self.boundary.provenance.parent_object_ids
            != expected_boundary_parents
        ):
            raise ResonanceFrameEngineError(
                "evidence BoundaryRef is not the formal lifecycle mapping"
            )
        structural_confirm = _time(
            f"{name}.structural_confirm_time", self.structural_confirm_time,
            ResonanceFrameEngineError,
        )
        state_confirm = _time(
            f"{name}.state_confirm_time", self.state_confirm_time,
            ResonanceFrameEngineError,
        )
        if structural_confirm > state_confirm:
            raise ResonanceFrameEngineError(
                "evidence structural_confirm_time cannot follow state_confirm_time"
            )
        if self.boundary.confirm_time != state_confirm:
            raise ResonanceFrameEngineError(
                "evidence BoundaryRef.confirm_time must equal state_confirm_time"
            )
        _integer(f"{name}.touch_count", self.touch_count, ResonanceFrameEngineError)
        if not isinstance(self.source_types, tuple) or any(
            not isinstance(item, StructureSourceType) for item in self.source_types
        ):
            raise ResonanceFrameEngineError(
                "evidence source_types must be a StructureSourceType tuple"
            )
        source_types = tuple(sorted(set(self.source_types), key=lambda item: item.value))
        families = _text_tuple(
            name, "structure_families", self.structure_families,
            ResonanceFrameEngineError, non_empty=True, unique=True, sort_values=True,
        )
        if source_types != self.boundary.source_types:
            raise ResonanceFrameEngineError(
                "evidence source_types must equal BoundaryRef source_types"
            )
        if families != self.boundary.structure_families:
            raise ResonanceFrameEngineError(
                "evidence structure_families must equal BoundaryRef structure_families"
            )
        if not isinstance(self.provenance, ProvenanceRef):
            raise ResonanceFrameEngineError("evidence provenance must be a ProvenanceRef")
        _engine_id_from_notes(
            self.provenance,
            object_name="evidence",
            error_type=ResonanceFrameEngineError,
        )
        expected_id = _evidence_id(
            subject_id=self.subject_id,
            lifecycle_state_id=self.lifecycle_state_id,
            lifecycle_event_id=self.lifecycle_event_id,
            boundary=self.boundary.to_dict(),
            tier=self.tier.value,
            context=self.context.to_dict(),
            direction=self.direction.value,
            lifecycle_state=self.lifecycle_state.value,
            structural_confirm_time=structural_confirm.isoformat(),
            state_confirm_time=state_confirm.isoformat(),
            touch_count=self.touch_count,
            source_types=tuple(item.value for item in source_types),
            structure_families=families,
            schema_version=self.schema_version,
        )
        if self.evidence_id != expected_id:
            raise ResonanceFrameEngineError(
                "evidence_id does not match the recomputed semantic identity"
            )
        expected_parents = tuple(sorted({
            self.subject_id, self.lifecycle_state_id, self.lifecycle_event_id,
            self.boundary.object_id,
        }))
        if (
            self.provenance.source_module != _ASSEMBLER_MODULE
            or self.provenance.source_object_id != self.evidence_id
            or self.provenance.parent_object_ids != expected_parents
        ):
            raise ResonanceFrameEngineError(
                "evidence provenance does not match its exact upstream facts"
            )
        object.__setattr__(self, "structural_confirm_time", structural_confirm)
        object.__setattr__(self, "state_confirm_time", state_confirm)
        object.__setattr__(self, "source_types", source_types)
        object.__setattr__(self, "structure_families", families)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "subject_id": self.subject_id,
            "lifecycle_state_id": self.lifecycle_state_id,
            "lifecycle_event_id": self.lifecycle_event_id,
            "boundary": self.boundary.to_dict(),
            "tier": self.tier.value,
            "context": self.context.to_dict(),
            "direction": self.direction.value,
            "lifecycle_state": self.lifecycle_state.value,
            "structural_confirm_time": self.structural_confirm_time.isoformat(),
            "state_confirm_time": self.state_confirm_time.isoformat(),
            "touch_count": self.touch_count,
            "source_types": [item.value for item in self.source_types],
            "structure_families": list(self.structure_families),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceEvidence:
        fields = {
            "evidence_id", "subject_id", "lifecycle_state_id",
            "lifecycle_event_id", "boundary", "tier", "context", "direction",
            "lifecycle_state", "structural_confirm_time", "state_confirm_time",
            "touch_count", "source_types", "structure_families", "provenance",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                evidence_id=data["evidence_id"],
                subject_id=data["subject_id"],
                lifecycle_state_id=data["lifecycle_state_id"],
                lifecycle_event_id=data["lifecycle_event_id"],
                boundary=BoundaryRef.from_dict(data["boundary"]),
                tier=ResonanceEvidenceTier(data["tier"]),
                context=ResonanceContext.from_dict(data["context"]),
                direction=Direction(data["direction"]),
                lifecycle_state=LifecycleState(data["lifecycle_state"]),
                structural_confirm_time=_parse_time(
                    "structural_confirm_time", data["structural_confirm_time"]
                ),
                state_confirm_time=_parse_time(
                    "state_confirm_time", data["state_confirm_time"]
                ),
                touch_count=data["touch_count"],
                source_types=tuple(
                    StructureSourceType(item)
                    for item in _ordered_list(data, cls.__name__, "source_types")
                ),
                structure_families=tuple(
                    _ordered_list(data, cls.__name__, "structure_families")
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceFrameReport:
    as_of_time: datetime
    context_count: int
    evidence_count: int
    candidate_evidence_count: int
    confirmed_evidence_count: int
    upper_evidence_count: int
    lower_evidence_count: int
    fresh_count: int
    tested_count: int
    weakened_count: int
    flipped_count: int
    excluded_broken_count: int
    excluded_retired_count: int
    distinct_source_type_count: int
    distinct_structure_family_count: int
    earliest_evidence_confirm_time: datetime | None
    latest_evidence_confirm_time: datetime | None
    reference_price: Decimal
    reference_price_available_time: datetime
    reference_price_age_seconds: Decimal
    engine_id: str
    engine_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameEngineError)
        as_of = _time(f"{name}.as_of_time", self.as_of_time, ResonanceFrameEngineError)
        for field_name in self.__dataclass_fields__:
            if field_name.endswith("_count"):
                _integer(
                    f"{name}.{field_name}", getattr(self, field_name),
                    ResonanceFrameEngineError,
                )
        earliest = _optional_time(
            f"{name}.earliest_evidence_confirm_time",
            self.earliest_evidence_confirm_time,
            ResonanceFrameEngineError,
        )
        latest = _optional_time(
            f"{name}.latest_evidence_confirm_time",
            self.latest_evidence_confirm_time,
            ResonanceFrameEngineError,
        )
        if (earliest is None) != (latest is None):
            raise ResonanceFrameEngineError("report evidence time bounds are incomplete")
        if earliest is not None and (earliest > latest or latest > as_of):
            raise ResonanceFrameEngineError("report evidence time bounds are invalid")
        price = _decimal(
            f"{name}.reference_price", self.reference_price,
            ResonanceFrameEngineError,
        )
        available = _time(
            f"{name}.reference_price_available_time",
            self.reference_price_available_time,
            ResonanceFrameEngineError,
        )
        age = _decimal(
            f"{name}.reference_price_age_seconds",
            self.reference_price_age_seconds,
            ResonanceFrameEngineError,
        )
        expected_age = _elapsed_seconds(as_of - available)
        if available > as_of or age != expected_age or age < 0:
            raise ResonanceFrameEngineError("reference price age facts are inconsistent")
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(
                f"{name}.{field_name}", getattr(self, field_name),
                ResonanceFrameEngineError,
            )
        for field_name in ("assumptions", "warnings", "errors"):
            object.__setattr__(
                self, field_name,
                _text_tuple(
                    name, field_name, getattr(self, field_name),
                    ResonanceFrameEngineError,
                ),
            )
        if self.assumptions != _REPORT_ASSUMPTIONS:
            raise ResonanceFrameEngineError(
                "report assumptions must equal the fixed C-007A assumptions"
            )
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "earliest_evidence_confirm_time", earliest)
        object.__setattr__(self, "latest_evidence_confirm_time", latest)
        object.__setattr__(self, "reference_price", price)
        object.__setattr__(self, "reference_price_available_time", available)
        object.__setattr__(self, "reference_price_age_seconds", age)

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        for field_name in self.__dataclass_fields__:
            if field_name == "schema_version":
                continue
            value = getattr(self, field_name)
            if isinstance(value, datetime):
                result[field_name] = value.isoformat()
            elif isinstance(value, Decimal):
                result[field_name] = str(value)
            elif isinstance(value, tuple):
                result[field_name] = list(value)
            else:
                result[field_name] = value
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFrameReport:
        fields = set(cls.__dataclass_fields__) - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, fields)
        time_fields = {
            "as_of_time", "earliest_evidence_confirm_time",
            "latest_evidence_confirm_time", "reference_price_available_time",
        }
        decimal_fields = {
            "reference_price", "reference_price_age_seconds",
        }
        tuple_fields = {"assumptions", "warnings", "errors"}
        try:
            kwargs = {
                name: data[name]
                for name in fields - time_fields - decimal_fields - tuple_fields
            }
            return cls(
                **kwargs,
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                earliest_evidence_confirm_time=_parse_optional_time(
                    "earliest_evidence_confirm_time",
                    data["earliest_evidence_confirm_time"],
                ),
                latest_evidence_confirm_time=_parse_optional_time(
                    "latest_evidence_confirm_time",
                    data["latest_evidence_confirm_time"],
                ),
                reference_price_available_time=_parse_time(
                    "reference_price_available_time",
                    data["reference_price_available_time"],
                ),
                reference_price=_parse_decimal(
                    "reference_price", data["reference_price"]
                ),
                reference_price_age_seconds=_parse_decimal(
                    "reference_price_age_seconds",
                    data["reference_price_age_seconds"],
                ),
                assumptions=tuple(_ordered_list(data, cls.__name__, "assumptions")),
                warnings=tuple(_ordered_list(data, cls.__name__, "warnings")),
                errors=tuple(_ordered_list(data, cls.__name__, "errors")),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, ResonanceFrameEngineError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def _evidence_key(value: ResonanceEvidence) -> tuple[object, ...]:
    return (
        value.boundary.boundary_side.value,
        value.context.timeframe.value,
        _context_key(value.context),
        value.state_confirm_time,
        value.structural_confirm_time,
        value.subject_id,
        value.lifecycle_state_id,
    )


@dataclass(frozen=True, slots=True)
class ResonanceFrame:
    frame_id: str
    as_of_time: datetime
    source_lifecycle_snapshot_id: str
    source_lifecycle_snapshot_time: datetime
    reference_price: ReferencePriceSnapshot
    context_states: tuple[ResonanceContextState, ...]
    evidence: tuple[ResonanceEvidence, ...]
    excluded_broken_subject_ids: tuple[str, ...]
    excluded_retired_subject_ids: tuple[str, ...]
    report: ResonanceFrameReport
    config_snapshot: ResonanceFrameConfig
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameEngineError)
        _text(f"{name}.frame_id", self.frame_id, ResonanceFrameEngineError)
        _text(
            f"{name}.source_lifecycle_snapshot_id",
            self.source_lifecycle_snapshot_id,
            ResonanceFrameEngineError,
        )
        as_of = _time(f"{name}.as_of_time", self.as_of_time, ResonanceFrameEngineError)
        source_time = _time(
            f"{name}.source_lifecycle_snapshot_time",
            self.source_lifecycle_snapshot_time,
            ResonanceFrameEngineError,
        )
        if source_time > as_of:
            raise ResonanceFrameEngineError(
                "source LifecycleSnapshot cannot follow Frame.as_of_time"
            )
        if not isinstance(self.config_snapshot, ResonanceFrameConfig):
            raise ResonanceFrameEngineError("frame config_snapshot type is invalid")
        if not isinstance(self.reference_price, ReferencePriceSnapshot):
            raise ResonanceFrameEngineError("frame reference_price type is invalid")
        if (
            self.reference_price.symbol != self.config_snapshot.symbol
            or self.reference_price.timeframe
            is not self.config_snapshot.reference_price_timeframe
            or self.reference_price.available_time > as_of
        ):
            raise ResonanceFrameEngineError(
                "frame reference price contradicts config or causal time"
            )
        if not isinstance(self.context_states, tuple) or any(
            not isinstance(item, ResonanceContextState)
            for item in self.context_states
        ):
            raise ResonanceFrameEngineError(
                "frame context_states must be a ResonanceContextState tuple"
            )
        context_states = tuple(sorted(self.context_states, key=lambda item: _context_key(item.context)))
        if tuple(item.context for item in context_states) != self.config_snapshot.contexts:
            raise ResonanceFrameEngineError(
                "frame context_states must exactly cover config contexts"
            )
        if any(
            item.source_lifecycle_snapshot_id != self.source_lifecycle_snapshot_id
            or item.timeframe_snapshot_as_of_time != source_time
            or item.state.symbol != self.config_snapshot.symbol
            or item.state_confirm_time > as_of
            for item in context_states
        ):
            raise ResonanceFrameEngineError(
                "frame context state alignment or causal time is inconsistent"
            )
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, ResonanceEvidence) for item in self.evidence
        ):
            raise ResonanceFrameEngineError(
                "frame evidence must be a ResonanceEvidence tuple"
            )
        evidence = tuple(sorted(self.evidence, key=_evidence_key))
        if evidence != self.evidence:
            raise ResonanceFrameEngineError("frame evidence must be canonically ordered")
        for field_name, values in (
            ("subject_id", tuple(item.subject_id for item in evidence)),
            ("lifecycle_state_id", tuple(item.lifecycle_state_id for item in evidence)),
            ("evidence_id", tuple(item.evidence_id for item in evidence)),
        ):
            if len(set(values)) != len(values):
                raise ResonanceFrameEngineError(
                    f"frame evidence {field_name} values must be unique"
                )
        directions = {item.context: item.direction for item in context_states}
        if any(
            item.context not in self.config_snapshot.contexts
            or item.direction is not directions[item.context]
            or item.boundary.symbol != self.config_snapshot.symbol
            or item.state_confirm_time > as_of
            or item.boundary.confirm_time > as_of
            for item in evidence
        ):
            raise ResonanceFrameEngineError(
                "frame evidence context, direction, or causal time is inconsistent"
            )
        broken = _text_tuple(
            name, "excluded_broken_subject_ids", self.excluded_broken_subject_ids,
            ResonanceFrameEngineError, unique=True, sort_values=True,
        )
        retired = _text_tuple(
            name, "excluded_retired_subject_ids", self.excluded_retired_subject_ids,
            ResonanceFrameEngineError, unique=True, sort_values=True,
        )
        if set(broken) & set(retired):
            raise ResonanceFrameEngineError(
                "BROKEN and RETIRED exclusion IDs must be disjoint"
            )
        evidence_subject_ids = {item.subject_id for item in evidence}
        if evidence_subject_ids & set(broken):
            raise ResonanceFrameEngineError(
                "effective evidence and BROKEN exclusions must be disjoint"
            )
        if evidence_subject_ids & set(retired):
            raise ResonanceFrameEngineError(
                "effective evidence and RETIRED exclusions must be disjoint"
            )
        for item in evidence:
            evidence_engine_id = _engine_id_from_notes(
                item.provenance,
                object_name="evidence",
                error_type=ResonanceFrameEngineError,
            )
            if (
                item.provenance.source_module != _ASSEMBLER_MODULE
                or item.provenance.source_version
                != self.config_snapshot.engine_version
                or item.provenance.policy_id != self.config_snapshot.policy_id
                or evidence_engine_id != self.config_snapshot.engine_id
            ):
                raise ResonanceFrameEngineError(
                    "evidence provenance contradicts frame config"
                )
        if not isinstance(self.report, ResonanceFrameReport):
            raise ResonanceFrameEngineError("frame report type is invalid")
        self._validate_report(context_states, evidence, broken, retired, as_of)
        if not isinstance(self.provenance, ProvenanceRef):
            raise ResonanceFrameEngineError("frame provenance type is invalid")
        expected_id = _frame_id(
            config=self.config_snapshot.to_dict(),
            as_of_time=as_of.isoformat(),
            source_lifecycle_snapshot_id=self.source_lifecycle_snapshot_id,
            source_lifecycle_snapshot_time=source_time.isoformat(),
            reference_price_id=self.reference_price.reference_id,
            context_state_ids=tuple(item.context_state_id for item in context_states),
            evidence_ids=tuple(item.evidence_id for item in evidence),
            excluded_broken_subject_ids=broken,
            excluded_retired_subject_ids=retired,
            schema_version=self.schema_version,
        )
        if self.frame_id != expected_id:
            raise ResonanceFrameEngineError(
                "frame_id does not match the recomputed semantic identity"
            )
        expected_parents = tuple(sorted({
            self.source_lifecycle_snapshot_id,
            self.reference_price.reference_id,
            *(item.timeframe_snapshot_id for item in context_states),
            *(item.lifecycle_state_id for item in evidence),
        }))
        if (
            self.provenance.source_module != _ASSEMBLER_MODULE
            or self.provenance.source_object_id != self.frame_id
            or self.provenance.source_version != self.config_snapshot.engine_version
            or self.provenance.policy_id != self.config_snapshot.policy_id
            or self.provenance.parent_object_ids != expected_parents
            or _engine_id_from_notes(
                self.provenance,
                object_name="frame",
                error_type=ResonanceFrameEngineError,
            )
            != self.config_snapshot.engine_id
        ):
            raise ResonanceFrameEngineError(
                "frame provenance does not match exact upstream parents"
            )
        object.__setattr__(self, "as_of_time", as_of)
        object.__setattr__(self, "source_lifecycle_snapshot_time", source_time)
        object.__setattr__(self, "context_states", context_states)
        object.__setattr__(self, "excluded_broken_subject_ids", broken)
        object.__setattr__(self, "excluded_retired_subject_ids", retired)

    def _validate_report(
        self,
        context_states: tuple[ResonanceContextState, ...],
        evidence: tuple[ResonanceEvidence, ...],
        broken: tuple[str, ...],
        retired: tuple[str, ...],
        as_of: datetime,
    ) -> None:
        times = tuple(item.state_confirm_time for item in evidence)
        source_types = {item for value in evidence for item in value.source_types}
        families = {item for value in evidence for item in value.structure_families}
        expected = {
            "as_of_time": as_of,
            "context_count": len(context_states),
            "evidence_count": len(evidence),
            "candidate_evidence_count": sum(item.tier is ResonanceEvidenceTier.CANDIDATE for item in evidence),
            "confirmed_evidence_count": sum(item.tier is ResonanceEvidenceTier.CONFIRMED for item in evidence),
            "upper_evidence_count": sum(item.boundary.boundary_side is BoundarySide.UPPER for item in evidence),
            "lower_evidence_count": sum(item.boundary.boundary_side is BoundarySide.LOWER for item in evidence),
            "fresh_count": sum(item.lifecycle_state is LifecycleState.FRESH for item in evidence),
            "tested_count": sum(item.lifecycle_state is LifecycleState.TESTED for item in evidence),
            "weakened_count": sum(item.lifecycle_state is LifecycleState.WEAKENED for item in evidence),
            "flipped_count": sum(item.lifecycle_state is LifecycleState.FLIPPED for item in evidence),
            "excluded_broken_count": len(broken),
            "excluded_retired_count": len(retired),
            "distinct_source_type_count": len(source_types),
            "distinct_structure_family_count": len(families),
            "earliest_evidence_confirm_time": min(times) if times else None,
            "latest_evidence_confirm_time": max(times) if times else None,
            "reference_price": self.reference_price.price,
            "reference_price_available_time": self.reference_price.available_time,
            "reference_price_age_seconds": _elapsed_seconds(
                as_of - self.reference_price.available_time
            ),
            "engine_id": self.config_snapshot.engine_id,
            "engine_version": self.config_snapshot.engine_version,
            "policy_id": self.config_snapshot.policy_id,
        }
        if any(getattr(self.report, field_name) != value for field_name, value in expected.items()):
            raise ResonanceFrameEngineError("frame report contradicts frame facts")
        if (
            self.report.assumptions != _REPORT_ASSUMPTIONS
            or self.report.warnings
            or self.report.errors
        ):
            raise ResonanceFrameEngineError(
                "successful frame report assumptions/warnings/errors are invalid"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "frame_id": self.frame_id,
            "as_of_time": self.as_of_time.isoformat(),
            "source_lifecycle_snapshot_id": self.source_lifecycle_snapshot_id,
            "source_lifecycle_snapshot_time": self.source_lifecycle_snapshot_time.isoformat(),
            "reference_price": self.reference_price.to_dict(),
            "context_states": [item.to_dict() for item in self.context_states],
            "evidence": [item.to_dict() for item in self.evidence],
            "excluded_broken_subject_ids": list(self.excluded_broken_subject_ids),
            "excluded_retired_subject_ids": list(self.excluded_retired_subject_ids),
            "report": self.report.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFrame:
        fields = {
            "frame_id", "as_of_time", "source_lifecycle_snapshot_id",
            "source_lifecycle_snapshot_time", "reference_price", "context_states",
            "evidence", "excluded_broken_subject_ids",
            "excluded_retired_subject_ids", "report", "config_snapshot",
            "provenance",
        }
        data = _exact_payload(payload, cls.__name__, fields)
        try:
            return cls(
                frame_id=data["frame_id"],
                as_of_time=_parse_time("as_of_time", data["as_of_time"]),
                source_lifecycle_snapshot_id=data["source_lifecycle_snapshot_id"],
                source_lifecycle_snapshot_time=_parse_time(
                    "source_lifecycle_snapshot_time",
                    data["source_lifecycle_snapshot_time"],
                ),
                reference_price=ReferencePriceSnapshot.from_dict(
                    data["reference_price"]
                ),
                context_states=tuple(
                    ResonanceContextState.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "context_states")
                ),
                evidence=tuple(
                    ResonanceEvidence.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "evidence")
                ),
                excluded_broken_subject_ids=tuple(
                    _ordered_list(data, cls.__name__, "excluded_broken_subject_ids")
                ),
                excluded_retired_subject_ids=tuple(
                    _ordered_list(data, cls.__name__, "excluded_retired_subject_ids")
                ),
                report=ResonanceFrameReport.from_dict(data["report"]),
                config_snapshot=ResonanceFrameConfig.from_dict(
                    data["config_snapshot"]
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceFrameInput:
    lifecycle_history: LifecycleHistory
    timeframe_state_histories: tuple[TimeframeStateHistory, ...]
    reference_price_data: LoadResult
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameInputError)
        if not isinstance(self.lifecycle_history, LifecycleHistory):
            raise ResonanceFrameInputError(
                "ResonanceFrameInput.lifecycle_history must be a LifecycleHistory"
            )
        if not self.lifecycle_history.snapshots:
            raise ResonanceFrameInputError(
                "ResonanceFrameInput.lifecycle_history must not be empty"
            )
        if not isinstance(self.timeframe_state_histories, tuple) or not self.timeframe_state_histories or any(
            not isinstance(item, TimeframeStateHistory)
            for item in self.timeframe_state_histories
        ):
            raise ResonanceFrameInputError(
                "timeframe_state_histories must be a non-empty TimeframeStateHistory tuple"
            )
        if not isinstance(self.reference_price_data, LoadResult):
            raise ResonanceFrameInputError(
                "reference_price_data must be a LoadResult"
            )
        if self.reference_price_data.quality_report.has_errors:
            raise ResonanceFrameInputError(
                "reference_price_data must be error-free"
            )
        if not self.reference_price_data.bars:
            raise ResonanceFrameInputError(
                "reference_price_data must contain at least one bar"
            )
        if any(not item.is_complete for item in self.reference_price_data.bars):
            raise ResonanceFrameInputError(
                "reference_price_data must contain only completed bars"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lifecycle_history": self.lifecycle_history.to_dict(),
            "timeframe_state_histories": [
                item.to_dict() for item in self.timeframe_state_histories
            ],
            "reference_price_data": _load_result_to_dict(
                self.reference_price_data
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFrameInput:
        data = _exact_payload(
            payload,
            cls.__name__,
            {"lifecycle_history", "timeframe_state_histories", "reference_price_data"},
        )
        try:
            return cls(
                lifecycle_history=LifecycleHistory.from_dict(
                    data["lifecycle_history"]
                ),
                timeframe_state_histories=tuple(
                    TimeframeStateHistory.from_dict(item)
                    for item in _ordered_list(
                        data, cls.__name__, "timeframe_state_histories"
                    )
                ),
                reference_price_data=_load_result_from_dict(
                    data["reference_price_data"]
                ),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceFrameHistory:
    frames: tuple[ResonanceFrame, ...]
    final_frame: ResonanceFrame
    config_snapshot: ResonanceFrameConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ResonanceFrameEngineError)
        if not isinstance(self.frames, tuple) or not self.frames:
            raise ResonanceFrameEngineError(
                "ResonanceFrameHistory.frames must be a non-empty tuple"
            )
        if any(not isinstance(item, ResonanceFrame) for item in self.frames):
            raise ResonanceFrameEngineError(
                "ResonanceFrameHistory.frames must contain ResonanceFrame"
            )
        if any(
            current.as_of_time <= previous.as_of_time
            for previous, current in zip(self.frames, self.frames[1:])
        ):
            raise ResonanceFrameEngineError(
                "history frame times must be strictly increasing"
            )
        if not isinstance(self.config_snapshot, ResonanceFrameConfig):
            raise ResonanceFrameEngineError(
                "history config_snapshot must be a ResonanceFrameConfig"
            )
        if any(item.config_snapshot != self.config_snapshot for item in self.frames):
            raise ResonanceFrameEngineError(
                "history frame configurations must be identical"
            )
        if len({item.frame_id for item in self.frames}) != len(self.frames):
            raise ResonanceFrameEngineError("history frame IDs must be unique")
        if not isinstance(self.final_frame, ResonanceFrame) or self.final_frame != self.frames[-1]:
            raise ResonanceFrameEngineError(
                "history final_frame must equal the last frame"
            )
        for previous, current in zip(self.frames, self.frames[1:]):
            if current.source_lifecycle_snapshot_time < previous.source_lifecycle_snapshot_time:
                raise ResonanceFrameEngineError(
                    "history LifecycleSnapshot source time cannot regress"
                )
            if current.reference_price.available_time < previous.reference_price.available_time:
                raise ResonanceFrameEngineError(
                    "history reference price available_time cannot regress"
                )
            if (
                current.source_lifecycle_snapshot_id
                == previous.source_lifecycle_snapshot_id
                and current.reference_price.reference_id
                == previous.reference_price.reference_id
            ):
                if (
                    current.context_states != previous.context_states
                    or current.evidence != previous.evidence
                    or current.excluded_broken_subject_ids
                    != previous.excluded_broken_subject_ids
                    or current.excluded_retired_subject_ids
                    != previous.excluded_retired_subject_ids
                ):
                    raise ResonanceFrameEngineError(
                        "extra AsOf frame changed structural facts without a new source"
                    )
                stable_report_fields = (
                    "context_count", "evidence_count", "candidate_evidence_count",
                    "confirmed_evidence_count", "upper_evidence_count",
                    "lower_evidence_count", "fresh_count", "tested_count",
                    "weakened_count", "flipped_count", "excluded_broken_count",
                    "excluded_retired_count", "distinct_source_type_count",
                    "distinct_structure_family_count",
                    "earliest_evidence_confirm_time",
                    "latest_evidence_confirm_time", "reference_price",
                    "reference_price_available_time", "engine_id", "engine_version",
                    "policy_id", "assumptions", "warnings", "errors",
                )
                if any(
                    getattr(current.report, field_name)
                    != getattr(previous.report, field_name)
                    for field_name in stable_report_fields
                ):
                    raise ResonanceFrameEngineError(
                        "extra AsOf frame changed stable report facts"
                    )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "frames": [item.to_dict() for item in self.frames],
            "final_frame": self.final_frame.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFrameHistory:
        data = _exact_payload(
            payload, cls.__name__, {"frames", "final_frame", "config_snapshot"}
        )
        try:
            return cls(
                frames=tuple(
                    ResonanceFrame.from_dict(item)
                    for item in _ordered_list(data, cls.__name__, "frames")
                ),
                final_frame=ResonanceFrame.from_dict(data["final_frame"]),
                config_snapshot=ResonanceFrameConfig.from_dict(
                    data["config_snapshot"]
                ),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc
