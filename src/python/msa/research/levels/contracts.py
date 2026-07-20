"""Immutable public contracts for C-004 research level generators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from msa.data import LoadResult, Timeframe
from msa.domain import ConfirmationStatus, LevelCandidate, ScaleDescriptor

from .errors import (
    LevelConfigurationError,
    LevelGenerationError,
    LevelInputError,
)


SCHEMA_VERSION = 1


def _require_exact_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise LevelConfigurationError(f"{object_name} payload must be a mapping")
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise LevelConfigurationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise LevelConfigurationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    version = payload["schema_version"]
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise LevelConfigurationError(
            f"{object_name}.schema_version must be {SCHEMA_VERSION}"
        )
    return payload


def _require_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LevelConfigurationError(f"{field_name} must be a non-empty string")
    return value


def _require_integer(field_name: str, value: object, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LevelConfigurationError(f"{field_name} must be >= {minimum}")
    return value


def _require_decimal(
    field_name: str, value: object, *, minimum: Decimal, exclusive: bool = False
) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise LevelConfigurationError(f"{field_name} must be a finite Decimal")
    invalid = value <= minimum if exclusive else value < minimum
    if invalid:
        operator = ">" if exclusive else ">="
        raise LevelConfigurationError(f"{field_name} must be {operator} {minimum}")
    return value


def _parse_decimal(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise LevelConfigurationError(f"{field_name} must be a Decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise LevelConfigurationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise LevelConfigurationError(f"{field_name} must be finite")
    return parsed


def _normalize_time(field_name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise LevelGenerationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LevelGenerationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LevelConfigurationError(
            f"{field_name} must be an aware ISO-8601 string or null"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LevelConfigurationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LevelConfigurationError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_scale(value: object) -> ScaleDescriptor:
    try:
        return ScaleDescriptor.from_dict(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise LevelConfigurationError("invalid scale payload") from exc


@dataclass(frozen=True, slots=True)
class LevelGenerationInput:
    """Explicit immutable C-001 bars plus ordered C-002 seed snapshots."""

    source: LoadResult
    seed_candidates: tuple[LevelCandidate, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, LoadResult):
            raise LevelInputError("source must be a C-001 LoadResult")
        if not isinstance(self.seed_candidates, tuple) or any(
            not isinstance(item, LevelCandidate) for item in self.seed_candidates
        ):
            raise LevelInputError(
                "seed_candidates must be an ordered LevelCandidate tuple"
            )


@dataclass(frozen=True, slots=True)
class PeriodicExtremeConfig:
    """Explicit configuration for direct periodic-bar high/low candidates."""

    generator_id: str
    generator_version: str
    period_timeframe: Timeframe
    scale: ScaleDescriptor
    policy_id: str
    emit_high: bool = True
    emit_low: bool = True
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text("generator_id", self.generator_id)
        _require_text("generator_version", self.generator_version)
        _require_text("policy_id", self.policy_id)
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LevelConfigurationError(
                f"schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.period_timeframe, Timeframe):
            raise LevelConfigurationError("period_timeframe must be a Timeframe")
        if not isinstance(self.scale, ScaleDescriptor):
            raise LevelConfigurationError("scale must be an explicit ScaleDescriptor")
        if not isinstance(self.emit_high, bool) or not isinstance(self.emit_low, bool):
            raise LevelConfigurationError("emit_high and emit_low must be bool")
        if not self.emit_high and not self.emit_low:
            raise LevelConfigurationError(
                "at least one of emit_high or emit_low must be True"
            )
        if not isinstance(self.strict, bool):
            raise LevelConfigurationError("strict must be a bool")
        if self.strict is not True:
            raise LevelConfigurationError(
                "PeriodicExtremeConfig.strict must be True; C-004 supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_id": self.generator_id,
            "generator_version": self.generator_version,
            "period_timeframe": self.period_timeframe.value,
            "scale": self.scale.to_dict(),
            "policy_id": self.policy_id,
            "emit_high": self.emit_high,
            "emit_low": self.emit_low,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PeriodicExtremeConfig:
        fields = {
            "generator_id",
            "generator_version",
            "period_timeframe",
            "scale",
            "policy_id",
            "emit_high",
            "emit_low",
            "strict",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        try:
            timeframe = Timeframe(data["period_timeframe"])
        except (TypeError, ValueError) as exc:
            raise LevelConfigurationError("unknown period_timeframe") from exc
        return cls(
            generator_id=data["generator_id"],
            generator_version=data["generator_version"],
            period_timeframe=timeframe,
            scale=_parse_scale(data["scale"]),
            policy_id=data["policy_id"],
            emit_high=data["emit_high"],
            emit_low=data["emit_low"],
            strict=data["strict"],
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class HistoricalReactionConfig:
    """Explicit baseline parameters for seed-specific historical reactions."""

    generator_id: str
    generator_version: str
    touch_tolerance: Decimal
    min_reactions: int
    min_separation_bars: int
    confirmation_horizon_bars: int
    min_reaction_distance: Decimal
    max_penetration: Decimal
    scale: ScaleDescriptor
    policy_id: str
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text("generator_id", self.generator_id)
        _require_text("generator_version", self.generator_version)
        _require_text("policy_id", self.policy_id)
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LevelConfigurationError(
                f"schema_version must be {SCHEMA_VERSION}"
            )
        _require_decimal("touch_tolerance", self.touch_tolerance, minimum=Decimal(0))
        _require_integer("min_reactions", self.min_reactions, 2)
        _require_integer("min_separation_bars", self.min_separation_bars, 1)
        _require_integer(
            "confirmation_horizon_bars", self.confirmation_horizon_bars, 1
        )
        _require_decimal(
            "min_reaction_distance",
            self.min_reaction_distance,
            minimum=Decimal(0),
            exclusive=True,
        )
        _require_decimal("max_penetration", self.max_penetration, minimum=Decimal(0))
        if not isinstance(self.scale, ScaleDescriptor):
            raise LevelConfigurationError("scale must be an explicit ScaleDescriptor")
        if not isinstance(self.strict, bool):
            raise LevelConfigurationError("strict must be a bool")
        if self.strict is not True:
            raise LevelConfigurationError(
                "HistoricalReactionConfig.strict must be True; C-004 supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generator_id": self.generator_id,
            "generator_version": self.generator_version,
            "touch_tolerance": str(self.touch_tolerance),
            "min_reactions": self.min_reactions,
            "min_separation_bars": self.min_separation_bars,
            "confirmation_horizon_bars": self.confirmation_horizon_bars,
            "min_reaction_distance": str(self.min_reaction_distance),
            "max_penetration": str(self.max_penetration),
            "scale": self.scale.to_dict(),
            "policy_id": self.policy_id,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> HistoricalReactionConfig:
        fields = {
            "generator_id",
            "generator_version",
            "touch_tolerance",
            "min_reactions",
            "min_separation_bars",
            "confirmation_horizon_bars",
            "min_reaction_distance",
            "max_penetration",
            "scale",
            "policy_id",
            "strict",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        return cls(
            generator_id=data["generator_id"],
            generator_version=data["generator_version"],
            touch_tolerance=_parse_decimal("touch_tolerance", data["touch_tolerance"]),
            min_reactions=data["min_reactions"],
            min_separation_bars=data["min_separation_bars"],
            confirmation_horizon_bars=data["confirmation_horizon_bars"],
            min_reaction_distance=_parse_decimal(
                "min_reaction_distance", data["min_reaction_distance"]
            ),
            max_penetration=_parse_decimal(
                "max_penetration", data["max_penetration"]
            ),
            scale=_parse_scale(data["scale"]),
            policy_id=data["policy_id"],
            strict=data["strict"],
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class LevelGenerationReport:
    """Bounded immutable audit report for one generation evaluation."""

    input_bar_count: int
    visible_bar_count: int
    seed_count: int
    eligible_seed_count: int
    periodic_high_count: int
    periodic_low_count: int
    reaction_candidate_count: int
    ignored_incomplete_count: int
    evaluated_touch_count: int
    successful_reaction_count: int
    rejected_reaction_attempt_count: int
    gap_count: int
    earliest_origin_time: datetime | None
    latest_origin_time: datetime | None
    earliest_confirm_time: datetime | None
    latest_confirm_time: datetime | None
    generator_id: str
    generator_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LevelGenerationError(
                f"LevelGenerationReport.schema_version must be {SCHEMA_VERSION}"
            )
        count_fields = (
            "input_bar_count",
            "visible_bar_count",
            "seed_count",
            "eligible_seed_count",
            "periodic_high_count",
            "periodic_low_count",
            "reaction_candidate_count",
            "ignored_incomplete_count",
            "evaluated_touch_count",
            "successful_reaction_count",
            "rejected_reaction_attempt_count",
            "gap_count",
        )
        if any(
            isinstance(getattr(self, name), bool)
            or not isinstance(getattr(self, name), int)
            or getattr(self, name) < 0
            for name in count_fields
        ):
            raise LevelGenerationError("LevelGenerationReport counts must be >= 0")
        for name in ("generator_id", "generator_version", "policy_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LevelGenerationError(f"{name} must be non-empty text")
        for name in ("assumptions", "warnings", "errors"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item.strip() for item in values
            ):
                raise LevelGenerationError(f"{name} must be a tuple of text")
        for name in (
            "earliest_origin_time",
            "latest_origin_time",
            "earliest_confirm_time",
            "latest_confirm_time",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _normalize_time(name, value))

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"schema_version": self.schema_version}
        for name in (
            "input_bar_count",
            "visible_bar_count",
            "seed_count",
            "eligible_seed_count",
            "periodic_high_count",
            "periodic_low_count",
            "reaction_candidate_count",
            "ignored_incomplete_count",
            "evaluated_touch_count",
            "successful_reaction_count",
            "rejected_reaction_attempt_count",
            "gap_count",
        ):
            result[name] = getattr(self, name)
        for name in (
            "earliest_origin_time",
            "latest_origin_time",
            "earliest_confirm_time",
            "latest_confirm_time",
        ):
            value = getattr(self, name)
            result[name] = None if value is None else value.isoformat()
        result.update(
            {
                "generator_id": self.generator_id,
                "generator_version": self.generator_version,
                "policy_id": self.policy_id,
                "assumptions": list(self.assumptions),
                "warnings": list(self.warnings),
                "errors": list(self.errors),
            }
        )
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelGenerationReport:
        fields = {
            "input_bar_count",
            "visible_bar_count",
            "seed_count",
            "eligible_seed_count",
            "periodic_high_count",
            "periodic_low_count",
            "reaction_candidate_count",
            "ignored_incomplete_count",
            "evaluated_touch_count",
            "successful_reaction_count",
            "rejected_reaction_attempt_count",
            "gap_count",
            "earliest_origin_time",
            "latest_origin_time",
            "earliest_confirm_time",
            "latest_confirm_time",
            "generator_id",
            "generator_version",
            "policy_id",
            "assumptions",
            "warnings",
            "errors",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        for name in ("assumptions", "warnings", "errors"):
            if not isinstance(data[name], list):
                raise LevelConfigurationError(f"{name} must be an ordered list")
        return cls(
            input_bar_count=data["input_bar_count"],
            visible_bar_count=data["visible_bar_count"],
            seed_count=data["seed_count"],
            eligible_seed_count=data["eligible_seed_count"],
            periodic_high_count=data["periodic_high_count"],
            periodic_low_count=data["periodic_low_count"],
            reaction_candidate_count=data["reaction_candidate_count"],
            ignored_incomplete_count=data["ignored_incomplete_count"],
            evaluated_touch_count=data["evaluated_touch_count"],
            successful_reaction_count=data["successful_reaction_count"],
            rejected_reaction_attempt_count=data[
                "rejected_reaction_attempt_count"
            ],
            gap_count=data["gap_count"],
            earliest_origin_time=_parse_optional_time(
                "earliest_origin_time", data["earliest_origin_time"]
            ),
            latest_origin_time=_parse_optional_time(
                "latest_origin_time", data["latest_origin_time"]
            ),
            earliest_confirm_time=_parse_optional_time(
                "earliest_confirm_time", data["earliest_confirm_time"]
            ),
            latest_confirm_time=_parse_optional_time(
                "latest_confirm_time", data["latest_confirm_time"]
            ),
            generator_id=data["generator_id"],
            generator_version=data["generator_version"],
            policy_id=data["policy_id"],
            assumptions=tuple(data["assumptions"]),
            warnings=tuple(data["warnings"]),
            errors=tuple(data["errors"]),
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class LevelGenerationResult:
    """Immutable ordered confirmed candidates plus bounded report."""

    candidates: tuple[LevelCandidate, ...]
    report: LevelGenerationReport
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LevelGenerationError(
                f"LevelGenerationResult.schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, LevelCandidate) for item in self.candidates
        ):
            raise LevelGenerationError("candidates must be a LevelCandidate tuple")
        if not isinstance(self.report, LevelGenerationReport):
            raise LevelGenerationError("report must be a LevelGenerationReport")
        if any(
            item.confirmation_status is not ConfirmationStatus.CONFIRMED
            or item.confirm_time is None
            for item in self.candidates
        ):
            raise LevelGenerationError(
                "LevelGenerationResult contains confirmed candidates only"
            )
        expected = tuple(
            sorted(self.candidates, key=lambda item: (item.confirm_time, item.candidate_id))
        )
        if self.candidates != expected:
            raise LevelGenerationError(
                "candidates must be ordered by (confirm_time, candidate_id)"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidates": [item.to_dict() for item in self.candidates],
            "report": self.report.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelGenerationResult:
        data = _require_exact_payload(payload, cls.__name__, {"candidates", "report"})
        if not isinstance(data["candidates"], list):
            raise LevelConfigurationError("candidates must be an ordered list")
        try:
            candidates = tuple(
                LevelCandidate.from_dict(item) for item in data["candidates"]
            )
        except (TypeError, ValueError) as exc:
            raise LevelConfigurationError("invalid candidate payload") from exc
        return cls(
            candidates=candidates,
            report=LevelGenerationReport.from_dict(data["report"]),
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class LevelGenerationEvent:
    """First causal appearance of one confirmed generated candidate."""

    first_seen_time: datetime
    candidate: LevelCandidate
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LevelGenerationError(
                f"LevelGenerationEvent.schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.candidate, LevelCandidate):
            raise LevelGenerationError("candidate must be a LevelCandidate")
        normalized = _normalize_time("first_seen_time", self.first_seen_time)
        if self.candidate.confirm_time != normalized:
            raise LevelGenerationError(
                "first_seen_time must equal candidate.confirm_time"
            )
        object.__setattr__(self, "first_seen_time", normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "first_seen_time": self.first_seen_time.isoformat(),
            "candidate": self.candidate.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelGenerationEvent:
        data = _require_exact_payload(
            payload, cls.__name__, {"first_seen_time", "candidate"}
        )
        parsed = _parse_optional_time("first_seen_time", data["first_seen_time"])
        if parsed is None:
            raise LevelConfigurationError("first_seen_time cannot be null")
        try:
            candidate = LevelCandidate.from_dict(data["candidate"])
        except (TypeError, ValueError) as exc:
            raise LevelConfigurationError("invalid candidate payload") from exc
        return cls(parsed, candidate, data["schema_version"])


@runtime_checkable
class LevelGeneratorConfig(Protocol):
    schema_version: int
    generator_id: str
    generator_version: str
    policy_id: str

    def to_dict(self) -> dict[str, object]: ...


@runtime_checkable
class LevelGenerator(Protocol):
    """Pluggable causal generator interface shared by C-004 baselines."""

    @property
    def generator_id(self) -> str: ...

    @property
    def generator_version(self) -> str: ...

    @property
    def config(self) -> LevelGeneratorConfig: ...

    def generate_batch(self, data: LevelGenerationInput) -> LevelGenerationResult: ...

    def generate_as_of(
        self, data: LevelGenerationInput, processing_time: datetime
    ) -> LevelGenerationResult: ...

    def iter_events(
        self, data: LevelGenerationInput
    ) -> Iterator[LevelGenerationEvent]: ...
