"""Immutable public contracts for research-only Swing detectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from msa.data import LoadResult
from msa.domain import ConfirmationStatus, LevelCandidate, ScaleDescriptor

from .errors import SwingConfigurationError, SwingDetectionError


SCHEMA_VERSION = 1


class TiePolicy(str, Enum):
    """Supported equality policy for Pivot comparison windows."""

    STRICT = "STRICT"


def _require_exact_payload(
    payload: Mapping[str, Any], object_name: str, fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise SwingConfigurationError(f"{object_name} payload must be a mapping")
    expected = fields | {"schema_version"}
    keys = set(payload)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise SwingConfigurationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise SwingConfigurationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    if payload["schema_version"] != SCHEMA_VERSION or isinstance(
        payload["schema_version"], bool
    ):
        raise SwingConfigurationError(
            f"{object_name}.schema_version must be {SCHEMA_VERSION}"
        )
    return payload


def _require_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SwingConfigurationError(f"{field_name} must be a non-empty string")
    return value


def _normalize_time(field_name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise SwingDetectionError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SwingDetectionError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_optional_time(field_name: str, value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SwingConfigurationError(
            f"{field_name} must be an aware ISO-8601 string or null"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SwingConfigurationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SwingConfigurationError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PivotDetectorConfig:
    """Explicit immutable configuration for the confirmed Pivot baseline."""

    detector_id: str
    detector_version: str
    left_bars: int
    right_bars: int
    tie_policy: TiePolicy
    scale: ScaleDescriptor
    policy_id: str
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text("detector_id", self.detector_id)
        _require_text("detector_version", self.detector_version)
        _require_text("policy_id", self.policy_id)
        if self.schema_version != SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise SwingConfigurationError(
                f"schema_version must be {SCHEMA_VERSION}"
            )
        for field_name in ("left_bars", "right_bars"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SwingConfigurationError(f"{field_name} must be >= 1")
        if not isinstance(self.tie_policy, TiePolicy):
            raise SwingConfigurationError(
                "tie_policy must be an explicitly supported TiePolicy"
            )
        if self.tie_policy is not TiePolicy.STRICT:
            raise SwingConfigurationError("only STRICT tie_policy is supported")
        if not isinstance(self.scale, ScaleDescriptor):
            raise SwingConfigurationError(
                "scale must be an explicit ScaleDescriptor supplied by the caller"
            )
        if not isinstance(self.strict, bool):
            raise SwingConfigurationError("strict must be a bool")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "left_bars": self.left_bars,
            "right_bars": self.right_bars,
            "tie_policy": self.tie_policy.value,
            "scale": self.scale.to_dict(),
            "policy_id": self.policy_id,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PivotDetectorConfig:
        fields = {
            "detector_id",
            "detector_version",
            "left_bars",
            "right_bars",
            "tie_policy",
            "scale",
            "policy_id",
            "strict",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        try:
            tie_policy = TiePolicy(data["tie_policy"])
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError("unknown tie_policy") from exc
        try:
            scale = ScaleDescriptor.from_dict(data["scale"])
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError("invalid scale payload") from exc
        return cls(
            detector_id=data["detector_id"],
            detector_version=data["detector_version"],
            left_bars=data["left_bars"],
            right_bars=data["right_bars"],
            tie_policy=tie_policy,
            scale=scale,
            policy_id=data["policy_id"],
            strict=data["strict"],
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class SwingDetectionReport:
    """Bounded immutable audit report for one detection evaluation."""

    input_bar_count: int
    evaluated_center_count: int
    confirmed_high_count: int
    confirmed_low_count: int
    leading_incomplete_count: int
    trailing_incomplete_count: int
    gap_count: int
    rejected_window_count: int
    earliest_origin_time: datetime | None
    latest_origin_time: datetime | None
    earliest_confirm_time: datetime | None
    latest_confirm_time: datetime | None
    detector_id: str
    detector_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise SwingDetectionError(
                f"SwingDetectionReport.schema_version must be {SCHEMA_VERSION}"
            )
        count_fields = (
            "input_bar_count",
            "evaluated_center_count",
            "confirmed_high_count",
            "confirmed_low_count",
            "leading_incomplete_count",
            "trailing_incomplete_count",
            "gap_count",
            "rejected_window_count",
        )
        if any(
            isinstance(getattr(self, name), bool)
            or not isinstance(getattr(self, name), int)
            or getattr(self, name) < 0
            for name in count_fields
        ):
            raise SwingDetectionError("SwingDetectionReport counts must be >= 0")
        for name in ("detector_id", "detector_version", "policy_id"):
            try:
                _require_text(name, getattr(self, name))
            except SwingConfigurationError as exc:
                raise SwingDetectionError(str(exc)) from exc
        for name in ("assumptions", "warnings", "errors"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item.strip() for item in values
            ):
                raise SwingDetectionError(f"{name} must be a tuple of text")
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
        return {
            "schema_version": self.schema_version,
            "input_bar_count": self.input_bar_count,
            "evaluated_center_count": self.evaluated_center_count,
            "confirmed_high_count": self.confirmed_high_count,
            "confirmed_low_count": self.confirmed_low_count,
            "leading_incomplete_count": self.leading_incomplete_count,
            "trailing_incomplete_count": self.trailing_incomplete_count,
            "gap_count": self.gap_count,
            "rejected_window_count": self.rejected_window_count,
            "earliest_origin_time": _time_text(self.earliest_origin_time),
            "latest_origin_time": _time_text(self.latest_origin_time),
            "earliest_confirm_time": _time_text(self.earliest_confirm_time),
            "latest_confirm_time": _time_text(self.latest_confirm_time),
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "policy_id": self.policy_id,
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SwingDetectionReport:
        fields = {
            "input_bar_count",
            "evaluated_center_count",
            "confirmed_high_count",
            "confirmed_low_count",
            "leading_incomplete_count",
            "trailing_incomplete_count",
            "gap_count",
            "rejected_window_count",
            "earliest_origin_time",
            "latest_origin_time",
            "earliest_confirm_time",
            "latest_confirm_time",
            "detector_id",
            "detector_version",
            "policy_id",
            "assumptions",
            "warnings",
            "errors",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        for name in ("assumptions", "warnings", "errors"):
            if not isinstance(data[name], list):
                raise SwingConfigurationError(f"{name} must be an ordered list")
        return cls(
            input_bar_count=data["input_bar_count"],
            evaluated_center_count=data["evaluated_center_count"],
            confirmed_high_count=data["confirmed_high_count"],
            confirmed_low_count=data["confirmed_low_count"],
            leading_incomplete_count=data["leading_incomplete_count"],
            trailing_incomplete_count=data["trailing_incomplete_count"],
            gap_count=data["gap_count"],
            rejected_window_count=data["rejected_window_count"],
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
            detector_id=data["detector_id"],
            detector_version=data["detector_version"],
            policy_id=data["policy_id"],
            assumptions=tuple(data["assumptions"]),
            warnings=tuple(data["warnings"]),
            errors=tuple(data["errors"]),
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class SwingDetectionResult:
    """Immutable candidates plus their bounded detection report."""

    candidates: tuple[LevelCandidate, ...]
    report: SwingDetectionReport
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise SwingDetectionError(
                f"SwingDetectionResult.schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, LevelCandidate) for item in self.candidates
        ):
            raise SwingDetectionError("candidates must be a LevelCandidate tuple")
        if not isinstance(self.report, SwingDetectionReport):
            raise SwingDetectionError("report must be a SwingDetectionReport")
        if any(
            item.confirmation_status is not ConfirmationStatus.CONFIRMED
            or item.confirm_time is None
            for item in self.candidates
        ):
            raise SwingDetectionError(
                "SwingDetectionResult contains confirmed candidates only"
            )
        expected = tuple(
            sorted(
                self.candidates,
                key=lambda item: (item.confirm_time, item.candidate_id),
            )
        )
        if self.candidates != expected:
            raise SwingDetectionError(
                "candidates must be ordered by (confirm_time, candidate_id)"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidates": [item.to_dict() for item in self.candidates],
            "report": self.report.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SwingDetectionResult:
        data = _require_exact_payload(
            payload, cls.__name__, {"candidates", "report"}
        )
        if not isinstance(data["candidates"], list):
            raise SwingConfigurationError("candidates must be an ordered list")
        try:
            candidates = tuple(
                LevelCandidate.from_dict(item) for item in data["candidates"]
            )
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError("invalid candidate payload") from exc
        return cls(
            candidates=candidates,
            report=SwingDetectionReport.from_dict(data["report"]),
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class SwingDetectionEvent:
    """First causal appearance of one confirmed candidate."""

    first_seen_time: datetime
    candidate: LevelCandidate
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise SwingDetectionError(
                f"SwingDetectionEvent.schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.candidate, LevelCandidate):
            raise SwingDetectionError("candidate must be a LevelCandidate")
        normalized = _normalize_time("first_seen_time", self.first_seen_time)
        if self.candidate.confirm_time != normalized:
            raise SwingDetectionError(
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
    def from_dict(cls, payload: Mapping[str, Any]) -> SwingDetectionEvent:
        data = _require_exact_payload(
            payload, cls.__name__, {"first_seen_time", "candidate"}
        )
        parsed = _parse_optional_time("first_seen_time", data["first_seen_time"])
        if parsed is None:
            raise SwingConfigurationError("first_seen_time cannot be null")
        try:
            candidate = LevelCandidate.from_dict(data["candidate"])
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError("invalid candidate payload") from exc
        return cls(
            first_seen_time=parsed,
            candidate=candidate,
            schema_version=data["schema_version"],
        )


def _time_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


@runtime_checkable
class SwingDetectorConfig(Protocol):
    schema_version: int
    detector_id: str
    detector_version: str
    policy_id: str

    def to_dict(self) -> dict[str, object]: ...


@runtime_checkable
class SwingDetector(Protocol):
    """Pluggable causal detector interface shared by C-003 experiments."""

    @property
    def detector_id(self) -> str: ...

    @property
    def detector_version(self) -> str: ...

    @property
    def config(self) -> SwingDetectorConfig: ...

    def detect_batch(self, source: LoadResult) -> SwingDetectionResult: ...

    def detect_as_of(
        self, source: LoadResult, processing_time: datetime
    ) -> SwingDetectionResult: ...

    def iter_events(self, source: LoadResult) -> Iterator[SwingDetectionEvent]: ...
