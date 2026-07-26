"""Immutable public contracts for C-008B structural metric evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Self

from msa.domain import BoundarySide, MarketRole
from msa.validation import ValidationMetricName

from .errors import (
    MetricConfigurationError,
    MetricEventError,
    MetricMatchingError,
    MetricObservationError,
    MetricSerializationError,
)
from .identity import decimal_divide, digest, require_semantic_id


SCHEMA_VERSION = 1
FORMULA_STATUS_FROZEN = "FROZEN_C008B_V1"
METRIC_REPORT_ASSUMPTIONS = (
    "This report is an ex-post structural evaluation",
    "Outcome windows do not participate in original event generation",
    "Right-censored samples are not treated as failures",
    "Metrics do not represent profit or trading advice",
    "Parameters have not been optimized for XAUUSD",
)
METRIC_REPORT_PROVENANCE_ENTRY = (
    "msa.validation.metrics.evaluate_structural_metrics"
)
_DESERIALIZATION_ERRORS = (
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
)


class _MetricEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


class MetricEventKind(_MetricEnum):
    STRUCTURE_CONFIRMATION = "STRUCTURE_CONFIRMATION"
    TURN_CANDIDATE = "TURN_CANDIDATE"
    BREAK_CONFIRMATION = "BREAK_CONFIRMATION"
    DIRECTION_EPISODE = "DIRECTION_EPISODE"
    BOX_EPISODE_CREATED = "BOX_EPISODE_CREATED"
    BOUNDARY_FIRST_TOUCH = "BOUNDARY_FIRST_TOUCH"


class MetricObservationStatus(_MetricEnum):
    MATURED = "MATURED"
    CENSORED_RIGHT = "CENSORED_RIGHT"
    UNAVAILABLE_INPUT = "UNAVAILABLE_INPUT"


class MetricAggregateStatus(_MetricEnum):
    AVAILABLE = "AVAILABLE"
    NO_ELIGIBLE_EVENTS = "NO_ELIGIBLE_EVENTS"
    NO_MATURED_OBSERVATIONS = "NO_MATURED_OBSERVATIONS"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class TurnResolution(_MetricEnum):
    OPPOSITE_CONFIRMED = "OPPOSITE_CONFIRMED"
    PRIOR_DIRECTION_RESUMED = "PRIOR_DIRECTION_RESUMED"


class BreakResolution(_MetricEnum):
    CONTINUED = "CONTINUED"
    NOT_CONTINUED = "NOT_CONTINUED"


class ResonanceMatchStatus(_MetricEnum):
    MATCHED = "MATCHED"
    NO_ELIGIBLE_CONTROL = "NO_ELIGIBLE_CONTROL"


def _schema(
    value: object, object_name: str, error_type: type[ValueError]
) -> int:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error_type(
            f"{object_name}.schema_version must be {SCHEMA_VERSION}"
        )
    return SCHEMA_VERSION


def _exact(
    payload: Mapping[str, Any], object_name: str, names: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise MetricSerializationError(
            f"{object_name} payload must be a mapping"
        )
    expected = names | {"schema_version"}
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise MetricSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise MetricSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    _schema(
        payload["schema_version"], object_name, MetricSerializationError
    )
    return payload


def _ordered(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise MetricSerializationError(
            f"{object_name}.{field_name} must be an ordered list"
        )
    return value


def _text(
    value: object, field_name: str, error_type: type[ValueError]
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def _optional_text(
    value: object, field_name: str, error_type: type[ValueError]
) -> str | None:
    return None if value is None else _text(value, field_name, error_type)


def _integer(
    value: object,
    field_name: str,
    error_type: type[ValueError],
    *,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise error_type(
            f"{field_name} must be an integer >= {minimum}"
        )
    return value


def _boolean(
    value: object, field_name: str, error_type: type[ValueError]
) -> bool:
    if not isinstance(value, bool):
        raise error_type(f"{field_name} must be a bool")
    return value


def _time(
    value: object, field_name: str, error_type: type[ValueError]
) -> datetime:
    if not isinstance(value, datetime):
        raise error_type(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error_type(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_time(
    value: object, field_name: str, error_type: type[ValueError]
) -> datetime | None:
    return None if value is None else _time(value, field_name, error_type)


def _parse_time(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise MetricSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MetricSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    return _time(parsed, field_name, MetricSerializationError)


def _parse_optional_time(value: object, field_name: str) -> datetime | None:
    return None if value is None else _parse_time(value, field_name)


def _decimal(
    value: object,
    field_name: str,
    error_type: type[ValueError],
    *,
    non_negative: bool = False,
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise error_type(f"{field_name} must be a finite Decimal")
    if non_negative and value < 0:
        raise error_type(f"{field_name} must be non-negative")
    return value


def _optional_decimal(
    value: object,
    field_name: str,
    error_type: type[ValueError],
    *,
    non_negative: bool = False,
) -> Decimal | None:
    if value is None:
        return None
    return _decimal(
        value, field_name, error_type, non_negative=non_negative
    )


def _parse_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise MetricSerializationError(
            f"{field_name} must be a Decimal string"
        )
    try:
        parsed = Decimal(value)
    except (TypeError, ValueError) as exc:
        raise MetricSerializationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    return _decimal(parsed, field_name, MetricSerializationError)


def _parse_optional_decimal(
    value: object, field_name: str
) -> Decimal | None:
    return None if value is None else _parse_decimal(value, field_name)


def _text_tuple(
    value: object,
    field_name: str,
    error_type: type[ValueError],
    *,
    non_empty: bool = False,
    unique: bool = False,
    canonical: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise error_type(f"{field_name} must be a tuple")
    result = tuple(
        _text(item, f"{field_name}[{index}]", error_type)
        for index, item in enumerate(value)
    )
    if non_empty and not result:
        raise error_type(f"{field_name} must not be empty")
    if unique and len(set(result)) != len(result):
        raise error_type(f"{field_name} must contain unique values")
    if canonical and result != tuple(sorted(result)):
        raise error_type(f"{field_name} must be canonically ordered")
    return result


def make_facts(values: Mapping[str, object]) -> tuple[str, ...]:
    """Encode bounded scalar facts into a deterministic immutable tuple."""

    if not isinstance(values, Mapping):
        raise MetricSerializationError("facts source must be a mapping")
    encoded: list[str] = []
    for key in sorted(values):
        _text(key, "fact key", MetricSerializationError)
        value = values[key]
        if isinstance(value, datetime):
            item = _time(
                value, f"facts.{key}", MetricSerializationError
            ).isoformat()
        elif isinstance(value, Decimal):
            _decimal(value, f"facts.{key}", MetricSerializationError)
            item = str(value)
        elif isinstance(value, Enum):
            item = str(value.value)
        elif value is None:
            item = "null"
        elif isinstance(value, bool):
            item = "true" if value else "false"
        elif isinstance(value, int):
            item = str(value)
        elif isinstance(value, str) and value:
            item = value
        else:
            raise MetricSerializationError(
                f"facts.{key} must be a supported immutable scalar"
            )
        if "\n" in item or "\r" in item:
            raise MetricSerializationError(
                f"facts.{key} must be single-line"
            )
        encoded.append(f"{key}={item}")
    return tuple(encoded)


def fact_mapping(
    facts: tuple[str, ...], *, error_type: type[ValueError]
) -> dict[str, str]:
    _text_tuple(
        facts,
        "facts",
        error_type,
        non_empty=True,
        unique=True,
        canonical=True,
    )
    result: dict[str, str] = {}
    for item in facts:
        if "=" not in item:
            raise error_type("facts must use key=value form")
        key, value = item.split("=", 1)
        if not key or not value or key in result:
            raise error_type("facts must contain unique non-empty keys")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class StructuralMetricConfig:
    engine_id: str = "c008b-structural-metrics"
    engine_version: str = "1.0.0"
    policy_id: str = "causal-structural-metrics-v1"
    atr_period: int = 14
    turn_resolution_bars: int = 8
    break_observation_bars: int = 8
    break_continuation_atr: Decimal = Decimal("1")
    trend_capture_bars: int = 24
    reaction_observation_bars: int = 8
    resonance_match_max_distance_atr: Decimal = Decimal("1")
    resonance_min_pair_count: int = 1
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricConfigurationError)
        for field_name in ("engine_id", "engine_version", "policy_id"):
            _text(
                getattr(self, field_name),
                f"{name}.{field_name}",
                MetricConfigurationError,
            )
        for field_name in (
            "atr_period",
            "turn_resolution_bars",
            "break_observation_bars",
            "trend_capture_bars",
            "reaction_observation_bars",
            "resonance_min_pair_count",
        ):
            _integer(
                getattr(self, field_name),
                f"{name}.{field_name}",
                MetricConfigurationError,
                minimum=1,
            )
        for field_name in (
            "break_continuation_atr",
            "resonance_match_max_distance_atr",
        ):
            _decimal(
                getattr(self, field_name),
                f"{name}.{field_name}",
                MetricConfigurationError,
                non_negative=True,
            )
        _boolean(self.strict, f"{name}.strict", MetricConfigurationError)
        if self.strict is not True:
            raise MetricConfigurationError(
                "StructuralMetricConfig.strict must be True"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "policy_id": self.policy_id,
            "atr_period": self.atr_period,
            "turn_resolution_bars": self.turn_resolution_bars,
            "break_observation_bars": self.break_observation_bars,
            "break_continuation_atr": str(self.break_continuation_atr),
            "trend_capture_bars": self.trend_capture_bars,
            "reaction_observation_bars": self.reaction_observation_bars,
            "resonance_match_max_distance_atr": str(
                self.resonance_match_max_distance_atr
            ),
            "resonance_min_pair_count": self.resonance_min_pair_count,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> StructuralMetricConfig:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                engine_id=data["engine_id"],
                engine_version=data["engine_version"],
                policy_id=data["policy_id"],
                atr_period=data["atr_period"],
                turn_resolution_bars=data["turn_resolution_bars"],
                break_observation_bars=data["break_observation_bars"],
                break_continuation_atr=_parse_decimal(
                    data["break_continuation_atr"],
                    "break_continuation_atr",
                ),
                trend_capture_bars=data["trend_capture_bars"],
                reaction_observation_bars=data[
                    "reaction_observation_bars"
                ],
                resonance_match_max_distance_atr=_parse_decimal(
                    data["resonance_match_max_distance_atr"],
                    "resonance_match_max_distance_atr",
                ),
                resonance_min_pair_count=data[
                    "resonance_min_pair_count"
                ],
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


def resolve_metric_config(
    value: StructuralMetricConfig | None,
) -> StructuralMetricConfig:
    if value is None:
        return StructuralMetricConfig()
    if not isinstance(value, StructuralMetricConfig):
        raise MetricConfigurationError(
            "config must be StructuralMetricConfig or None"
        )
    try:
        restored = StructuralMetricConfig.from_dict(value.to_dict())
    except _DESERIALIZATION_ERRORS as exc:
        raise MetricConfigurationError(
            "config is not a formal StructuralMetricConfig"
        ) from exc
    if restored != value:
        raise MetricConfigurationError(
            "config payload is not formally self-consistent"
        )
    return value


@dataclass(frozen=True, slots=True)
class MetricFormulaDefinition:
    metric_formula_id: str
    metric_definition_id: str
    metric_name: ValidationMetricName
    formula_version: str
    formula_status: str
    event_kind: MetricEventKind
    formula_expression: str
    aggregation_rule: str
    censoring_rule: str
    required_fields: tuple[str, ...]
    parameters: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "metric_definition_id": self.metric_definition_id,
            "metric_name": self.metric_name.value,
            "formula_version": self.formula_version,
            "formula_status": self.formula_status,
            "event_kind": self.event_kind.value,
            "formula_expression": self.formula_expression,
            "aggregation_rule": self.aggregation_rule,
            "censoring_rule": self.censoring_rule,
            "required_fields": list(self.required_fields),
            "parameters": list(self.parameters),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricConfigurationError)
        _text(
            self.metric_definition_id,
            "metric_definition_id",
            MetricConfigurationError,
        )
        if not isinstance(self.metric_name, ValidationMetricName):
            raise MetricConfigurationError(
                "metric_name must be ValidationMetricName"
            )
        if not isinstance(self.event_kind, MetricEventKind):
            raise MetricConfigurationError(
                "event_kind must be MetricEventKind"
            )
        for field_name in (
            "formula_version",
            "formula_expression",
            "aggregation_rule",
            "censoring_rule",
        ):
            _text(
                getattr(self, field_name),
                field_name,
                MetricConfigurationError,
            )
        if self.formula_status != FORMULA_STATUS_FROZEN:
            raise MetricConfigurationError(
                f"formula_status must be {FORMULA_STATUS_FROZEN}"
            )
        _text_tuple(
            self.required_fields,
            "required_fields",
            MetricConfigurationError,
            non_empty=True,
            unique=True,
        )
        _text_tuple(
            self.parameters,
            "parameters",
            MetricConfigurationError,
            unique=True,
        )
        require_semantic_id(
            self.metric_formula_id,
            prefix="structural-metric-formula-v1-",
            payload=self._identity_payload(),
            field_name="metric_formula_id",
            error_type=MetricConfigurationError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_formula_id": self.metric_formula_id,
            "metric_definition_id": self.metric_definition_id,
            "metric_name": self.metric_name.value,
            "formula_version": self.formula_version,
            "formula_status": self.formula_status,
            "event_kind": self.event_kind.value,
            "formula_expression": self.formula_expression,
            "aggregation_rule": self.aggregation_rule,
            "censoring_rule": self.censoring_rule,
            "required_fields": list(self.required_fields),
            "parameters": list(self.parameters),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> MetricFormulaDefinition:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                metric_formula_id=data["metric_formula_id"],
                metric_definition_id=data["metric_definition_id"],
                metric_name=ValidationMetricName(data["metric_name"]),
                formula_version=data["formula_version"],
                formula_status=data["formula_status"],
                event_kind=MetricEventKind(data["event_kind"]),
                formula_expression=data["formula_expression"],
                aggregation_rule=data["aggregation_rule"],
                censoring_rule=data["censoring_rule"],
                required_fields=tuple(
                    _ordered(data, cls.__name__, "required_fields")
                ),
                parameters=tuple(
                    _ordered(data, cls.__name__, "parameters")
                ),
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class StructuralMetricEvent:
    metric_event_id: str
    kind: MetricEventKind
    event_confirm_time: datetime
    first_observed_as_of_time: datetime
    symbol: str
    reference_timeframe: str
    source_object_ids: tuple[str, ...]
    boundary_side: BoundarySide | None = None
    market_role: MarketRole | None = None
    context_key: str | None = None
    box_key_id: str | None = None
    zone_key: str | None = None
    zone_snapshot_id: str | None = None
    zone_class: str | None = None
    anchor_price: Decimal | None = None
    causal_atr: Decimal | None = None
    facts: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "event_confirm_time": self.event_confirm_time.isoformat(),
            "first_observed_as_of_time": (
                self.first_observed_as_of_time.isoformat()
            ),
            "symbol": self.symbol,
            "reference_timeframe": self.reference_timeframe,
            "source_object_ids": list(self.source_object_ids),
            "boundary_side": (
                None if self.boundary_side is None
                else self.boundary_side.value
            ),
            "market_role": (
                None if self.market_role is None else self.market_role.value
            ),
            "context_key": self.context_key,
            "box_key_id": self.box_key_id,
            "zone_key": self.zone_key,
            "zone_snapshot_id": self.zone_snapshot_id,
            "zone_class": self.zone_class,
            "anchor_price": (
                None if self.anchor_price is None else str(self.anchor_price)
            ),
            "causal_atr": (
                None if self.causal_atr is None else str(self.causal_atr)
            ),
            "facts": list(self.facts),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricEventError)
        if not isinstance(self.kind, MetricEventKind):
            raise MetricEventError("kind must be MetricEventKind")
        confirm = _time(
            self.event_confirm_time,
            "event_confirm_time",
            MetricEventError,
        )
        observed = _time(
            self.first_observed_as_of_time,
            "first_observed_as_of_time",
            MetricEventError,
        )
        if observed < confirm:
            raise MetricEventError(
                "first_observed_as_of_time cannot precede event_confirm_time"
            )
        _text(self.symbol, "symbol", MetricEventError)
        _text(
            self.reference_timeframe,
            "reference_timeframe",
            MetricEventError,
        )
        source_ids = _text_tuple(
            self.source_object_ids,
            "source_object_ids",
            MetricEventError,
            non_empty=True,
            unique=True,
            canonical=True,
        )
        if self.boundary_side is not None and not isinstance(
            self.boundary_side, BoundarySide
        ):
            raise MetricEventError(
                "boundary_side must be BoundarySide or None"
            )
        if self.market_role is not None and not isinstance(
            self.market_role, MarketRole
        ):
            raise MetricEventError(
                "market_role must be MarketRole or None"
            )
        for field_name in (
            "context_key",
            "box_key_id",
            "zone_key",
            "zone_snapshot_id",
            "zone_class",
        ):
            _optional_text(
                getattr(self, field_name), field_name, MetricEventError
            )
        _optional_decimal(
            self.anchor_price, "anchor_price", MetricEventError
        )
        _optional_decimal(
            self.causal_atr,
            "causal_atr",
            MetricEventError,
            non_negative=True,
        )
        parsed_facts = fact_mapping(self.facts, error_type=MetricEventError)
        if (
            parsed_facts.get("event_confirm_time")
            != confirm.isoformat()
            or parsed_facts.get("source_object_ids_digest")
            != digest(list(source_ids))
        ):
            raise MetricEventError(
                "event facts must bind confirm time and source object IDs"
            )
        forbidden = {
            "evaluation_as_of_time",
            "future_bar_id",
            "mfe",
            "mae",
            "outcome",
            "pair_value",
            "success",
            "failure",
        }
        if forbidden & set(parsed_facts):
            raise MetricEventError(
                "event facts contain future observation or evaluation output"
            )
        required_facts = {
            MetricEventKind.STRUCTURE_CONFIRMATION: {
                "boundary_high",
                "boundary_low",
                "origin_anchor",
                "origin_time",
                "subject_id",
            },
            MetricEventKind.TURN_CANDIDATE: {
                "prior_stable_direction",
                "turn_origin_time",
            },
            MetricEventKind.BREAK_CONFIRMATION: {
                "boundary_high",
                "boundary_low",
                "lifecycle_break_event_id",
                "origin_time",
            },
            MetricEventKind.DIRECTION_EPISODE: {
                "direction",
                "origin_time",
                "state_id",
            },
            MetricEventKind.BOX_EPISODE_CREATED: {
                "active_box_created_event_id",
                "lower_zone_key",
                "lower_zone_snapshot_id",
                "selection_price",
                "upper_zone_key",
                "upper_zone_snapshot_id",
            },
            MetricEventKind.BOUNDARY_FIRST_TOUCH: {
                "active_box_created_event_id",
                "box_created_time",
                "creation_causal_atr",
                "selection_distance",
                "selection_distance_atr",
                "touch_bar_id",
                "touch_bar_index",
                "zone_context_count",
                "zone_quality_score",
                "zone_selection_score",
                "zone_source_type_count",
            },
        }[self.kind]
        if not required_facts.issubset(parsed_facts):
            raise MetricEventError(
                f"{self.kind.value} event is missing authoritative facts"
            )
        if self.kind is MetricEventKind.STRUCTURE_CONFIRMATION and (
            self.boundary_side is None
            or self.market_role is None
            or self.context_key is None
            or self.anchor_price is None
        ):
            raise MetricEventError(
                "STRUCTURE_CONFIRMATION fields are incomplete"
            )
        if self.kind in {
            MetricEventKind.TURN_CANDIDATE,
            MetricEventKind.DIRECTION_EPISODE,
        } and self.context_key is None:
            raise MetricEventError(
                f"{self.kind.value} requires context_key"
            )
        if self.kind is MetricEventKind.BREAK_CONFIRMATION and (
            self.boundary_side is None
            or self.market_role is None
            or self.context_key is None
            or self.anchor_price is None
        ):
            raise MetricEventError(
                "BREAK_CONFIRMATION fields are incomplete"
            )
        if self.kind is MetricEventKind.BOX_EPISODE_CREATED and (
            self.box_key_id is None or self.anchor_price is None
        ):
            raise MetricEventError(
                "BOX_EPISODE_CREATED fields are incomplete"
            )
        if self.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH and (
            self.boundary_side is None
            or self.market_role is None
            or self.box_key_id is None
            or self.zone_key is None
            or self.zone_snapshot_id is None
            or self.zone_class is None
            or self.anchor_price is None
        ):
            raise MetricEventError(
                "BOUNDARY_FIRST_TOUCH fields are incomplete"
            )
        require_semantic_id(
            self.metric_event_id,
            prefix="structural-metric-event-v1-",
            payload=self._identity_payload(),
            field_name="metric_event_id",
            error_type=MetricEventError,
        )
        object.__setattr__(self, "event_confirm_time", confirm)
        object.__setattr__(
            self, "first_observed_as_of_time", observed
        )
        object.__setattr__(self, "source_object_ids", source_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_event_id": self.metric_event_id,
            "kind": self.kind.value,
            "event_confirm_time": self.event_confirm_time.isoformat(),
            "first_observed_as_of_time": (
                self.first_observed_as_of_time.isoformat()
            ),
            "symbol": self.symbol,
            "reference_timeframe": self.reference_timeframe,
            "source_object_ids": list(self.source_object_ids),
            "boundary_side": (
                None if self.boundary_side is None
                else self.boundary_side.value
            ),
            "market_role": (
                None if self.market_role is None else self.market_role.value
            ),
            "context_key": self.context_key,
            "box_key_id": self.box_key_id,
            "zone_key": self.zone_key,
            "zone_snapshot_id": self.zone_snapshot_id,
            "zone_class": self.zone_class,
            "anchor_price": (
                None if self.anchor_price is None else str(self.anchor_price)
            ),
            "causal_atr": (
                None if self.causal_atr is None else str(self.causal_atr)
            ),
            "facts": list(self.facts),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> StructuralMetricEvent:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                metric_event_id=data["metric_event_id"],
                kind=MetricEventKind(data["kind"]),
                event_confirm_time=_parse_time(
                    data["event_confirm_time"], "event_confirm_time"
                ),
                first_observed_as_of_time=_parse_time(
                    data["first_observed_as_of_time"],
                    "first_observed_as_of_time",
                ),
                symbol=data["symbol"],
                reference_timeframe=data["reference_timeframe"],
                source_object_ids=tuple(
                    _ordered(data, cls.__name__, "source_object_ids")
                ),
                boundary_side=(
                    None if data["boundary_side"] is None
                    else BoundarySide(data["boundary_side"])
                ),
                market_role=(
                    None if data["market_role"] is None
                    else MarketRole(data["market_role"])
                ),
                context_key=data["context_key"],
                box_key_id=data["box_key_id"],
                zone_key=data["zone_key"],
                zone_snapshot_id=data["zone_snapshot_id"],
                zone_class=data["zone_class"],
                anchor_price=_parse_optional_decimal(
                    data["anchor_price"], "anchor_price"
                ),
                causal_atr=_parse_optional_decimal(
                    data["causal_atr"], "causal_atr"
                ),
                facts=tuple(_ordered(data, cls.__name__, "facts")),
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class StructuralMetricObservation:
    metric_observation_id: str
    metric_name: ValidationMetricName
    metric_formula_id: str
    metric_event_id: str
    status: MetricObservationStatus
    observation_start_time: datetime
    observation_end_time: datetime
    observed_bar_ids: tuple[str, ...]
    value: Decimal | None
    numerator: Decimal | None
    denominator: Decimal | None
    facts: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "metric_name": self.metric_name.value,
            "metric_formula_id": self.metric_formula_id,
            "metric_event_id": self.metric_event_id,
            "status": self.status.value,
            "observation_start_time": (
                self.observation_start_time.isoformat()
            ),
            "observation_end_time": self.observation_end_time.isoformat(),
            "observed_bar_ids": list(self.observed_bar_ids),
            "value": None if self.value is None else str(self.value),
            "numerator": (
                None if self.numerator is None else str(self.numerator)
            ),
            "denominator": (
                None if self.denominator is None else str(self.denominator)
            ),
            "facts": list(self.facts),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricObservationError)
        if not isinstance(self.metric_name, ValidationMetricName):
            raise MetricObservationError(
                "metric_name must be ValidationMetricName"
            )
        _text(
            self.metric_formula_id,
            "metric_formula_id",
            MetricObservationError,
        )
        _text(
            self.metric_event_id,
            "metric_event_id",
            MetricObservationError,
        )
        if not isinstance(self.status, MetricObservationStatus):
            raise MetricObservationError(
                "status must be MetricObservationStatus"
            )
        start = _time(
            self.observation_start_time,
            "observation_start_time",
            MetricObservationError,
        )
        end = _time(
            self.observation_end_time,
            "observation_end_time",
            MetricObservationError,
        )
        if end < start:
            raise MetricObservationError(
                "observation_end_time cannot precede start"
            )
        bars = _text_tuple(
            self.observed_bar_ids,
            "observed_bar_ids",
            MetricObservationError,
            unique=True,
        )
        value = _optional_decimal(
            self.value, "value", MetricObservationError
        )
        numerator = _optional_decimal(
            self.numerator, "numerator", MetricObservationError
        )
        denominator = _optional_decimal(
            self.denominator, "denominator", MetricObservationError
        )
        parsed_facts = fact_mapping(
            self.facts, error_type=MetricObservationError
        )
        expected_window = (
            f"{start.isoformat()}|{end.isoformat()}"
        )
        if (
            parsed_facts.get("observation_window") != expected_window
            or parsed_facts.get("observed_bar_ids_digest")
            != digest(list(bars))
        ):
            raise MetricObservationError(
                "observation facts must bind its window and bar identities"
            )
        if self.status is MetricObservationStatus.MATURED:
            if value is None or numerator is None:
                raise MetricObservationError(
                    "MATURED observation requires value and numerator"
                )
            expected = (
                numerator if denominator is None
                else decimal_divide(numerator, denominator)
            )
            if value != expected:
                raise MetricObservationError(
                    "MATURED value contradicts numerator/denominator"
                )
        elif any(
            item is not None for item in (value, numerator, denominator)
        ):
            raise MetricObservationError(
                "non-MATURED observations must not carry numeric results"
            )
        require_semantic_id(
            self.metric_observation_id,
            prefix="structural-metric-observation-v1-",
            payload=self._identity_payload(),
            field_name="metric_observation_id",
            error_type=MetricObservationError,
        )
        object.__setattr__(self, "observation_start_time", start)
        object.__setattr__(self, "observation_end_time", end)
        object.__setattr__(self, "observed_bar_ids", bars)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_observation_id": self.metric_observation_id,
            "metric_name": self.metric_name.value,
            "metric_formula_id": self.metric_formula_id,
            "metric_event_id": self.metric_event_id,
            "status": self.status.value,
            "observation_start_time": (
                self.observation_start_time.isoformat()
            ),
            "observation_end_time": self.observation_end_time.isoformat(),
            "observed_bar_ids": list(self.observed_bar_ids),
            "value": None if self.value is None else str(self.value),
            "numerator": (
                None if self.numerator is None else str(self.numerator)
            ),
            "denominator": (
                None if self.denominator is None else str(self.denominator)
            ),
            "facts": list(self.facts),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> StructuralMetricObservation:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                metric_observation_id=data["metric_observation_id"],
                metric_name=ValidationMetricName(data["metric_name"]),
                metric_formula_id=data["metric_formula_id"],
                metric_event_id=data["metric_event_id"],
                status=MetricObservationStatus(data["status"]),
                observation_start_time=_parse_time(
                    data["observation_start_time"],
                    "observation_start_time",
                ),
                observation_end_time=_parse_time(
                    data["observation_end_time"],
                    "observation_end_time",
                ),
                observed_bar_ids=tuple(
                    _ordered(data, cls.__name__, "observed_bar_ids")
                ),
                value=_parse_optional_decimal(data["value"], "value"),
                numerator=_parse_optional_decimal(
                    data["numerator"], "numerator"
                ),
                denominator=_parse_optional_decimal(
                    data["denominator"], "denominator"
                ),
                facts=tuple(_ordered(data, cls.__name__, "facts")),
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class StructuralMetricAggregate:
    metric_aggregate_id: str
    metric_name: ValidationMetricName
    formula_id: str
    status: MetricAggregateStatus
    value: Decimal | None
    eligible_count: int
    matured_count: int
    censored_count: int
    unavailable_count: int
    numerator: Decimal | None
    denominator: Decimal | None
    source_observation_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "metric_name": self.metric_name.value,
            "formula_id": self.formula_id,
            "status": self.status.value,
            "value": None if self.value is None else str(self.value),
            "eligible_count": self.eligible_count,
            "matured_count": self.matured_count,
            "censored_count": self.censored_count,
            "unavailable_count": self.unavailable_count,
            "numerator": (
                None if self.numerator is None else str(self.numerator)
            ),
            "denominator": (
                None if self.denominator is None else str(self.denominator)
            ),
            "source_observation_ids": list(self.source_observation_ids),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricObservationError)
        if not isinstance(self.metric_name, ValidationMetricName):
            raise MetricObservationError(
                "metric_name must be ValidationMetricName"
            )
        _text(self.formula_id, "formula_id", MetricObservationError)
        if not isinstance(self.status, MetricAggregateStatus):
            raise MetricObservationError(
                "status must be MetricAggregateStatus"
            )
        for field_name in (
            "eligible_count",
            "matured_count",
            "censored_count",
            "unavailable_count",
        ):
            _integer(
                getattr(self, field_name),
                field_name,
                MetricObservationError,
            )
        observation_ids = _text_tuple(
            self.source_observation_ids,
            "source_observation_ids",
            MetricObservationError,
            unique=True,
        )
        if (
            self.eligible_count != len(observation_ids)
            or self.eligible_count
            != self.matured_count
            + self.censored_count
            + self.unavailable_count
        ):
            raise MetricObservationError(
                "aggregate sample counts are inconsistent"
            )
        value = _optional_decimal(
            self.value, "value", MetricObservationError
        )
        numerator = _optional_decimal(
            self.numerator, "numerator", MetricObservationError
        )
        denominator = _optional_decimal(
            self.denominator, "denominator", MetricObservationError
        )
        if self.status is MetricAggregateStatus.AVAILABLE:
            if self.matured_count < 1 or value is None or numerator is None:
                raise MetricObservationError(
                    "AVAILABLE aggregate requires matured numeric results"
                )
            expected = (
                numerator if denominator is None
                else decimal_divide(numerator, denominator)
            )
            if value != expected:
                raise MetricObservationError(
                    "aggregate value contradicts numerator/denominator"
                )
        elif any(
            item is not None for item in (value, numerator, denominator)
        ):
            raise MetricObservationError(
                "unavailable aggregate must not carry numeric results"
            )
        if (
            self.status is MetricAggregateStatus.NO_ELIGIBLE_EVENTS
            and self.eligible_count != 0
        ):
            raise MetricObservationError(
                "NO_ELIGIBLE_EVENTS requires eligible_count=0"
            )
        if (
            self.status
            is MetricAggregateStatus.NO_MATURED_OBSERVATIONS
            and (self.eligible_count == 0 or self.matured_count != 0)
        ):
            raise MetricObservationError(
                "NO_MATURED_OBSERVATIONS count facts are invalid"
            )
        require_semantic_id(
            self.metric_aggregate_id,
            prefix="structural-metric-aggregate-v1-",
            payload=self._identity_payload(),
            field_name="metric_aggregate_id",
            error_type=MetricObservationError,
        )
        object.__setattr__(self, "source_observation_ids", observation_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_aggregate_id": self.metric_aggregate_id,
            "metric_name": self.metric_name.value,
            "formula_id": self.formula_id,
            "status": self.status.value,
            "value": None if self.value is None else str(self.value),
            "eligible_count": self.eligible_count,
            "matured_count": self.matured_count,
            "censored_count": self.censored_count,
            "unavailable_count": self.unavailable_count,
            "numerator": (
                None if self.numerator is None else str(self.numerator)
            ),
            "denominator": (
                None if self.denominator is None else str(self.denominator)
            ),
            "source_observation_ids": list(self.source_observation_ids),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> StructuralMetricAggregate:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                metric_aggregate_id=data["metric_aggregate_id"],
                metric_name=ValidationMetricName(data["metric_name"]),
                formula_id=data["formula_id"],
                status=MetricAggregateStatus(data["status"]),
                value=_parse_optional_decimal(data["value"], "value"),
                eligible_count=data["eligible_count"],
                matured_count=data["matured_count"],
                censored_count=data["censored_count"],
                unavailable_count=data["unavailable_count"],
                numerator=_parse_optional_decimal(
                    data["numerator"], "numerator"
                ),
                denominator=_parse_optional_decimal(
                    data["denominator"], "denominator"
                ),
                source_observation_ids=tuple(
                    _ordered(
                        data, cls.__name__, "source_observation_ids"
                    )
                ),
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ResonanceOutcomeMatch:
    resonance_match_id: str
    status: ResonanceMatchStatus
    treatment_event_id: str
    control_event_id: str | None
    boundary_side: BoundarySide
    treatment_distance_atr: Decimal
    control_distance_atr: Decimal | None
    distance_atr_gap: Decimal | None
    treatment_touch_bar_index: int
    control_touch_bar_index: int | None
    pair_value: Decimal | None
    facts: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "treatment_event_id": self.treatment_event_id,
            "control_event_id": self.control_event_id,
            "boundary_side": self.boundary_side.value,
            "treatment_distance_atr": str(
                self.treatment_distance_atr
            ),
            "control_distance_atr": (
                None if self.control_distance_atr is None
                else str(self.control_distance_atr)
            ),
            "distance_atr_gap": (
                None if self.distance_atr_gap is None
                else str(self.distance_atr_gap)
            ),
            "treatment_touch_bar_index": (
                self.treatment_touch_bar_index
            ),
            "control_touch_bar_index": self.control_touch_bar_index,
            "pair_value": (
                None if self.pair_value is None else str(self.pair_value)
            ),
            "facts": list(self.facts),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricMatchingError)
        if not isinstance(self.status, ResonanceMatchStatus):
            raise MetricMatchingError(
                "status must be ResonanceMatchStatus"
            )
        _text(
            self.treatment_event_id,
            "treatment_event_id",
            MetricMatchingError,
        )
        _optional_text(
            self.control_event_id,
            "control_event_id",
            MetricMatchingError,
        )
        if not isinstance(self.boundary_side, BoundarySide):
            raise MetricMatchingError(
                "boundary_side must be BoundarySide"
            )
        _decimal(
            self.treatment_distance_atr,
            "treatment_distance_atr",
            MetricMatchingError,
            non_negative=True,
        )
        _optional_decimal(
            self.control_distance_atr,
            "control_distance_atr",
            MetricMatchingError,
            non_negative=True,
        )
        _optional_decimal(
            self.distance_atr_gap,
            "distance_atr_gap",
            MetricMatchingError,
            non_negative=True,
        )
        _integer(
            self.treatment_touch_bar_index,
            "treatment_touch_bar_index",
            MetricMatchingError,
        )
        if self.control_touch_bar_index is not None:
            _integer(
                self.control_touch_bar_index,
                "control_touch_bar_index",
                MetricMatchingError,
            )
        _optional_decimal(
            self.pair_value, "pair_value", MetricMatchingError
        )
        fact_mapping(self.facts, error_type=MetricMatchingError)
        if self.status is ResonanceMatchStatus.MATCHED:
            if (
                self.control_event_id is None
                or self.control_event_id == self.treatment_event_id
                or self.control_distance_atr is None
                or self.distance_atr_gap is None
                or self.control_touch_bar_index is None
                or self.pair_value is None
            ):
                raise MetricMatchingError(
                    "MATCHED outcome requires complete distinct pair facts"
                )
            if self.distance_atr_gap != abs(
                self.treatment_distance_atr
                - self.control_distance_atr
            ):
                raise MetricMatchingError(
                    "distance_atr_gap contradicts pair distances"
                )
        elif any(
            item is not None
            for item in (
                self.control_event_id,
                self.control_distance_atr,
                self.distance_atr_gap,
                self.control_touch_bar_index,
                self.pair_value,
            )
        ):
            raise MetricMatchingError(
                "unmatched treatment must not carry control or outcome facts"
            )
        require_semantic_id(
            self.resonance_match_id,
            prefix="resonance-outcome-match-v1-",
            payload=self._identity_payload(),
            field_name="resonance_match_id",
            error_type=MetricMatchingError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "resonance_match_id": self.resonance_match_id,
            "status": self.status.value,
            "treatment_event_id": self.treatment_event_id,
            "control_event_id": self.control_event_id,
            "boundary_side": self.boundary_side.value,
            "treatment_distance_atr": str(
                self.treatment_distance_atr
            ),
            "control_distance_atr": (
                None if self.control_distance_atr is None
                else str(self.control_distance_atr)
            ),
            "distance_atr_gap": (
                None if self.distance_atr_gap is None
                else str(self.distance_atr_gap)
            ),
            "treatment_touch_bar_index": (
                self.treatment_touch_bar_index
            ),
            "control_touch_bar_index": self.control_touch_bar_index,
            "pair_value": (
                None if self.pair_value is None else str(self.pair_value)
            ),
            "facts": list(self.facts),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ResonanceOutcomeMatch:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                resonance_match_id=data["resonance_match_id"],
                status=ResonanceMatchStatus(data["status"]),
                treatment_event_id=data["treatment_event_id"],
                control_event_id=data["control_event_id"],
                boundary_side=BoundarySide(data["boundary_side"]),
                treatment_distance_atr=_parse_decimal(
                    data["treatment_distance_atr"],
                    "treatment_distance_atr",
                ),
                control_distance_atr=_parse_optional_decimal(
                    data["control_distance_atr"],
                    "control_distance_atr",
                ),
                distance_atr_gap=_parse_optional_decimal(
                    data["distance_atr_gap"], "distance_atr_gap"
                ),
                treatment_touch_bar_index=data[
                    "treatment_touch_bar_index"
                ],
                control_touch_bar_index=data[
                    "control_touch_bar_index"
                ],
                pair_value=_parse_optional_decimal(
                    data["pair_value"], "pair_value"
                ),
                facts=tuple(_ordered(data, cls.__name__, "facts")),
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class MetricEvaluationReport:
    metric_report_id: str
    source_run_id: str
    evaluation_as_of_time: datetime
    config_snapshot: StructuralMetricConfig
    formula_registry: tuple[MetricFormulaDefinition, ...]
    events: tuple[StructuralMetricEvent, ...]
    observations: tuple[StructuralMetricObservation, ...]
    resonance_matches: tuple[ResonanceOutcomeMatch, ...]
    aggregates: tuple[StructuralMetricAggregate, ...]
    event_count: int
    matured_observation_count: int
    censored_observation_count: int
    unavailable_observation_count: int
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    provenance: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "source_run_id": self.source_run_id,
            "evaluation_as_of_time": (
                self.evaluation_as_of_time.isoformat()
            ),
            "config_snapshot": self.config_snapshot.to_dict(),
            "formula_registry": [
                item.to_dict() for item in self.formula_registry
            ],
            "events": [item.to_dict() for item in self.events],
            "observations": [
                item.to_dict() for item in self.observations
            ],
            "resonance_matches": [
                item.to_dict() for item in self.resonance_matches
            ],
            "aggregates": [item.to_dict() for item in self.aggregates],
            "event_count": self.event_count,
            "matured_observation_count": (
                self.matured_observation_count
            ),
            "censored_observation_count": (
                self.censored_observation_count
            ),
            "unavailable_observation_count": (
                self.unavailable_observation_count
            ),
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MetricObservationError)
        _text(self.source_run_id, "source_run_id", MetricObservationError)
        cutoff = _time(
            self.evaluation_as_of_time,
            "evaluation_as_of_time",
            MetricObservationError,
        )
        config = resolve_metric_config(self.config_snapshot)
        if not isinstance(self.formula_registry, tuple):
            raise MetricObservationError(
                "formula_registry must be a tuple"
            )
        from .formula_registry import default_metric_formula_registry

        expected_registry = default_metric_formula_registry()
        if self.formula_registry != expected_registry:
            raise MetricObservationError(
                "formula_registry must equal the frozen C-008B registry"
            )
        if not isinstance(self.events, tuple) or any(
            not isinstance(item, StructuralMetricEvent)
            for item in self.events
        ):
            raise MetricObservationError(
                "events must be a StructuralMetricEvent tuple"
            )
        event_key = lambda item: (
            item.event_confirm_time,
            item.kind.value,
            item.metric_event_id,
        )
        if (
            self.events != tuple(sorted(self.events, key=event_key))
            or len({item.metric_event_id for item in self.events})
            != len(self.events)
            or any(item.event_confirm_time > cutoff for item in self.events)
        ):
            raise MetricObservationError(
                "events must be unique, causal, and deterministically ordered"
            )
        if not isinstance(self.observations, tuple) or any(
            not isinstance(item, StructuralMetricObservation)
            for item in self.observations
        ):
            raise MetricObservationError(
                "observations must be a StructuralMetricObservation tuple"
            )
        formula_index = {
            item.metric_formula_id: index
            for index, item in enumerate(self.formula_registry)
        }
        event_by_id = {
            item.metric_event_id: item for item in self.events
        }
        formula_by_id = {
            item.metric_formula_id: item for item in self.formula_registry
        }
        for observation in self.observations:
            event = event_by_id.get(observation.metric_event_id)
            formula = formula_by_id.get(observation.metric_formula_id)
            if (
                event is None
                or formula is None
                or observation.metric_name is not formula.metric_name
                or event.kind is not formula.event_kind
                or observation.observation_end_time > cutoff
            ):
                raise MetricObservationError(
                    "observation source event/formula/cutoff binding is invalid"
                )
        observation_key = lambda item: (
            formula_index[item.metric_formula_id],
            event_by_id[item.metric_event_id].event_confirm_time,
            item.metric_event_id,
            item.metric_observation_id,
        )
        if (
            self.observations
            != tuple(sorted(self.observations, key=observation_key))
            or len(
                {
                    item.metric_observation_id
                    for item in self.observations
                }
            )
            != len(self.observations)
        ):
            raise MetricObservationError(
                "observations must be unique and deterministically ordered"
            )
        if not isinstance(self.resonance_matches, tuple) or any(
            not isinstance(item, ResonanceOutcomeMatch)
            for item in self.resonance_matches
        ):
            raise MetricObservationError(
                "resonance_matches must be a ResonanceOutcomeMatch tuple"
            )
        match_key = lambda item: (
            event_by_id[item.treatment_event_id].event_confirm_time,
            item.treatment_event_id,
            item.resonance_match_id,
        )
        used_controls: set[str] = set()
        for match in self.resonance_matches:
            treatment = event_by_id.get(match.treatment_event_id)
            control = (
                None if match.control_event_id is None
                else event_by_id.get(match.control_event_id)
            )
            if (
                treatment is None
                or treatment.kind
                is not MetricEventKind.BOUNDARY_FIRST_TOUCH
                or treatment.boundary_side is not match.boundary_side
                or (
                    match.status is ResonanceMatchStatus.MATCHED
                    and (
                        control is None
                        or control.boundary_side is not match.boundary_side
                        or match.control_event_id in used_controls
                    )
                )
            ):
                raise MetricObservationError(
                    "resonance match event or side binding is invalid"
                )
            if match.control_event_id is not None:
                used_controls.add(match.control_event_id)
        if (
            self.resonance_matches
            != tuple(sorted(self.resonance_matches, key=match_key))
            or len(
                {item.resonance_match_id for item in self.resonance_matches}
            )
            != len(self.resonance_matches)
        ):
            raise MetricObservationError(
                "resonance matches must be unique and deterministically ordered"
            )
        from .matching import match_resonance_outcomes

        resonance_formula = next(
            item
            for item in self.formula_registry
            if item.metric_name is ValidationMetricName.RESONANCE_LIFT
        )
        non_resonance_observations = tuple(
            item
            for item in self.observations
            if item.metric_name is not ValidationMetricName.RESONANCE_LIFT
        )
        expected_matches, expected_pair_observations = (
            match_resonance_outcomes(
                self.events,
                non_resonance_observations,
                resonance_formula,
                config,
            )
        )
        actual_pair_observations = tuple(
            item
            for item in self.observations
            if item.metric_name is ValidationMetricName.RESONANCE_LIFT
        )
        if (
            self.resonance_matches != expected_matches
            or actual_pair_observations != expected_pair_observations
        ):
            raise MetricObservationError(
                "resonance matches and pair outcomes must exactly recompute"
            )
        if (
            not isinstance(self.aggregates, tuple)
            or len(self.aggregates) != len(self.formula_registry)
            or any(
                not isinstance(item, StructuralMetricAggregate)
                for item in self.aggregates
            )
        ):
            raise MetricObservationError(
                "aggregates must contain exactly ten formal metrics"
            )
        observation_by_id = {
            item.metric_observation_id: item
            for item in self.observations
        }
        for aggregate, formula in zip(
            self.aggregates, self.formula_registry
        ):
            if (
                aggregate.metric_name is not formula.metric_name
                or aggregate.formula_id != formula.metric_formula_id
            ):
                raise MetricObservationError(
                    "aggregate order/name/formula binding is invalid"
                )
            selected = tuple(
                item
                for item in self.observations
                if item.metric_formula_id == formula.metric_formula_id
            )
            if aggregate.source_observation_ids != tuple(
                item.metric_observation_id for item in selected
            ):
                raise MetricObservationError(
                    "aggregate source observations are incomplete or reordered"
                )
            if any(
                item_id not in observation_by_id
                for item_id in aggregate.source_observation_ids
            ):
                raise MetricObservationError(
                    "aggregate references an unknown observation"
                )
            expected_counts = (
                len(selected),
                sum(
                    item.status is MetricObservationStatus.MATURED
                    for item in selected
                ),
                sum(
                    item.status
                    is MetricObservationStatus.CENSORED_RIGHT
                    for item in selected
                ),
                sum(
                    item.status
                    is MetricObservationStatus.UNAVAILABLE_INPUT
                    for item in selected
                ),
            )
            if (
                aggregate.eligible_count,
                aggregate.matured_count,
                aggregate.censored_count,
                aggregate.unavailable_count,
            ) != expected_counts:
                raise MetricObservationError(
                    "aggregate counts contradict source observations"
                )
        from .observations import build_metric_aggregates

        if self.aggregates != build_metric_aggregates(
            self.formula_registry, self.observations, config
        ):
            raise MetricObservationError(
                "aggregate results must exactly recompute from observations"
            )
        _integer(
            self.event_count,
            "event_count",
            MetricObservationError,
        )
        _integer(
            self.matured_observation_count,
            "matured_observation_count",
            MetricObservationError,
        )
        _integer(
            self.censored_observation_count,
            "censored_observation_count",
            MetricObservationError,
        )
        _integer(
            self.unavailable_observation_count,
            "unavailable_observation_count",
            MetricObservationError,
        )
        if (
            self.event_count != len(self.events)
            or self.matured_observation_count
            != sum(
                item.status is MetricObservationStatus.MATURED
                for item in self.observations
            )
            or self.censored_observation_count
            != sum(
                item.status is MetricObservationStatus.CENSORED_RIGHT
                for item in self.observations
            )
            or self.unavailable_observation_count
            != sum(
                item.status is MetricObservationStatus.UNAVAILABLE_INPUT
                for item in self.observations
            )
        ):
            raise MetricObservationError(
                "report counts contradict events or observations"
            )
        assumptions = _text_tuple(
            self.assumptions,
            "assumptions",
            MetricObservationError,
            non_empty=True,
            unique=True,
        )
        warnings = _text_tuple(
            self.warnings,
            "warnings",
            MetricObservationError,
            unique=True,
        )
        provenance = _text_tuple(
            self.provenance,
            "provenance",
            MetricObservationError,
            non_empty=True,
            unique=True,
        )
        digest_prefix = "source_run_payload_digest="
        if len(provenance) != 5 or not provenance[2].startswith(
            digest_prefix
        ):
            raise MetricObservationError(
                "provenance must include the complete source Run payload digest"
            )
        source_run_payload_digest = provenance[2][len(digest_prefix) :]
        if (
            len(source_run_payload_digest) != 64
            or any(
                character not in "0123456789abcdef"
                for character in source_run_payload_digest
            )
        ):
            raise MetricObservationError(
                "source_run_payload_digest must be a lowercase SHA-256 digest"
            )
        expected_provenance = (
            METRIC_REPORT_PROVENANCE_ENTRY,
            f"source_run_id={self.source_run_id}",
            f"source_run_payload_digest={source_run_payload_digest}",
            f"evaluation_as_of_time={cutoff.isoformat()}",
            f"engine_id={config.engine_id}",
        )
        if assumptions != METRIC_REPORT_ASSUMPTIONS:
            raise MetricObservationError(
                "assumptions must equal the frozen C-008B assumptions"
            )
        if provenance != expected_provenance:
            raise MetricObservationError(
                "provenance must bind source ID, payload, cutoff, and engine"
            )
        require_semantic_id(
            self.metric_report_id,
            prefix="metric-evaluation-report-v1-",
            payload=self._identity_payload(),
            field_name="metric_report_id",
            error_type=MetricObservationError,
        )
        object.__setattr__(self, "evaluation_as_of_time", cutoff)
        object.__setattr__(self, "config_snapshot", config)
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "provenance", provenance)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_report_id": self.metric_report_id,
            "source_run_id": self.source_run_id,
            "evaluation_as_of_time": (
                self.evaluation_as_of_time.isoformat()
            ),
            "config_snapshot": self.config_snapshot.to_dict(),
            "formula_registry": [
                item.to_dict() for item in self.formula_registry
            ],
            "events": [item.to_dict() for item in self.events],
            "observations": [
                item.to_dict() for item in self.observations
            ],
            "resonance_matches": [
                item.to_dict() for item in self.resonance_matches
            ],
            "aggregates": [item.to_dict() for item in self.aggregates],
            "event_count": self.event_count,
            "matured_observation_count": (
                self.matured_observation_count
            ),
            "censored_observation_count": (
                self.censored_observation_count
            ),
            "unavailable_observation_count": (
                self.unavailable_observation_count
            ),
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> MetricEvaluationReport:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                metric_report_id=data["metric_report_id"],
                source_run_id=data["source_run_id"],
                evaluation_as_of_time=_parse_time(
                    data["evaluation_as_of_time"],
                    "evaluation_as_of_time",
                ),
                config_snapshot=StructuralMetricConfig.from_dict(
                    data["config_snapshot"]
                ),
                formula_registry=tuple(
                    MetricFormulaDefinition.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "formula_registry"
                    )
                ),
                events=tuple(
                    StructuralMetricEvent.from_dict(item)
                    for item in _ordered(data, cls.__name__, "events")
                ),
                observations=tuple(
                    StructuralMetricObservation.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "observations"
                    )
                ),
                resonance_matches=tuple(
                    ResonanceOutcomeMatch.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "resonance_matches"
                    )
                ),
                aggregates=tuple(
                    StructuralMetricAggregate.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "aggregates"
                    )
                ),
                event_count=data["event_count"],
                matured_observation_count=data[
                    "matured_observation_count"
                ],
                censored_observation_count=data[
                    "censored_observation_count"
                ],
                unavailable_observation_count=data[
                    "unavailable_observation_count"
                ],
                assumptions=tuple(
                    _ordered(data, cls.__name__, "assumptions")
                ),
                warnings=tuple(
                    _ordered(data, cls.__name__, "warnings")
                ),
                provenance=tuple(
                    _ordered(data, cls.__name__, "provenance")
                ),
                schema_version=data["schema_version"],
            )
        except _DESERIALIZATION_ERRORS as exc:
            raise MetricSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc
