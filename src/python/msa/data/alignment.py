"""Explicit, source-independent target-boundary policies for resampling.

Fixed durations describe elapsed length only.  Every fixed-duration policy in
this module therefore requires an explicit UTC anchor.  Calendar-bound D/W
periods use caller-supplied boundary definitions and never infer a broker or
exchange calendar from the input data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from msa.data.contracts import Timeframe


class AlignmentConfigurationError(ValueError):
    """Raised when a boundary policy is ambiguous or internally inconsistent."""


def _non_empty_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlignmentConfigurationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def _utc_datetime(field_name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise AlignmentConfigurationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AlignmentConfigurationError(
            f"{field_name} must be timezone-aware UTC"
        )
    if value.utcoffset() != timedelta(0):
        raise AlignmentConfigurationError(f"{field_name} must be UTC")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class TargetBucket:
    """One explicit target interval and its complete source-slot expectation."""

    start_time: datetime
    end_time: datetime
    policy_id: str
    expected_source_timestamps: tuple[datetime, ...]

    def __post_init__(self) -> None:
        start = _utc_datetime("start_time", self.start_time)
        end = _utc_datetime("end_time", self.end_time)
        policy_id = _non_empty_text("policy_id", self.policy_id)
        expected = tuple(
            _utc_datetime("expected_source_timestamp", timestamp)
            for timestamp in self.expected_source_timestamps
        )
        if end <= start:
            raise AlignmentConfigurationError(
                "target bucket end_time must be later than start_time"
            )
        if not expected:
            raise AlignmentConfigurationError(
                "target bucket must declare at least one expected source slot"
            )
        if expected != tuple(sorted(expected)) or len(expected) != len(set(expected)):
            raise AlignmentConfigurationError(
                "expected source timestamps must be strictly ascending and unique"
            )
        if any(timestamp < start or timestamp >= end for timestamp in expected):
            raise AlignmentConfigurationError(
                "expected source timestamps must start inside the target bucket"
            )
        object.__setattr__(self, "start_time", start)
        object.__setattr__(self, "end_time", end)
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "expected_source_timestamps", expected)


@runtime_checkable
class AlignmentPolicy(Protocol):
    """Interface required by the source-agnostic resampling layer."""

    policy_id: str
    target_timeframe: Timeframe

    def bucket_for(
        self, timestamp: datetime, source_duration: timedelta
    ) -> TargetBucket | None:
        """Return the explicit target bucket containing ``timestamp``."""


@dataclass(frozen=True, slots=True)
class ExplicitFixedAnchorPolicy:
    """Align fixed target periods as ``anchor + n * target_duration``."""

    policy_id: str
    anchor: datetime
    target_timeframe: Timeframe

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _non_empty_text("policy_id", self.policy_id))
        object.__setattr__(self, "anchor", _utc_datetime("anchor", self.anchor))
        if not isinstance(self.target_timeframe, Timeframe):
            raise AlignmentConfigurationError(
                "target_timeframe must be a Timeframe"
            )
        if not self.target_timeframe.is_fixed_duration:
            raise AlignmentConfigurationError(
                "ExplicitFixedAnchorPolicy requires a fixed target timeframe"
            )

    def bucket_for(
        self, timestamp: datetime, source_duration: timedelta
    ) -> TargetBucket:
        normalized = _utc_datetime("timestamp", timestamp)
        if not isinstance(source_duration, timedelta) or source_duration <= timedelta(0):
            raise AlignmentConfigurationError(
                "source_duration must be a positive timedelta"
            )
        target_duration = self.target_timeframe.fixed_duration
        assert target_duration is not None
        if target_duration % source_duration != timedelta(0):
            raise AlignmentConfigurationError(
                "target duration must be an integer multiple of source duration"
            )
        bucket_number = (normalized - self.anchor) // target_duration
        start_time = self.anchor + bucket_number * target_duration
        end_time = start_time + target_duration
        slot_count = target_duration // source_duration
        expected = tuple(
            start_time + index * source_duration for index in range(slot_count)
        )
        return TargetBucket(
            start_time=start_time,
            end_time=end_time,
            policy_id=self.policy_id,
            expected_source_timestamps=expected,
        )


@dataclass(frozen=True, slots=True)
class ExplicitBoundary:
    """One caller-supplied calendar/session boundary and its expected slots."""

    start_time: datetime
    end_time: datetime
    expected_source_timestamps: tuple[datetime, ...]

    def __post_init__(self) -> None:
        bucket = TargetBucket(
            start_time=self.start_time,
            end_time=self.end_time,
            policy_id="validation-placeholder",
            expected_source_timestamps=tuple(self.expected_source_timestamps),
        )
        object.__setattr__(self, "start_time", bucket.start_time)
        object.__setattr__(self, "end_time", bucket.end_time)
        object.__setattr__(
            self,
            "expected_source_timestamps",
            bucket.expected_source_timestamps,
        )


@dataclass(frozen=True, slots=True)
class ExplicitBoundarySchedule:
    """Synthetic or externally approved D/W boundary schedule.

    The schedule does not discover holidays, breaks, daily closes, or weekly
    starts.  Its boundary list is the complete policy input supplied by the
    caller for the interval being processed.
    """

    policy_id: str
    target_timeframe: Timeframe
    boundaries: tuple[ExplicitBoundary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _non_empty_text("policy_id", self.policy_id))
        if not isinstance(self.target_timeframe, Timeframe):
            raise AlignmentConfigurationError(
                "target_timeframe must be a Timeframe"
            )
        if not self.target_timeframe.requires_boundary_policy:
            raise AlignmentConfigurationError(
                "ExplicitBoundarySchedule is reserved for D/W target timeframes"
            )
        boundaries = tuple(self.boundaries)
        if not boundaries:
            raise AlignmentConfigurationError(
                "explicit boundary schedule must contain at least one boundary"
            )
        if any(not isinstance(boundary, ExplicitBoundary) for boundary in boundaries):
            raise AlignmentConfigurationError(
                "boundaries must contain only ExplicitBoundary values"
            )
        if boundaries != tuple(sorted(boundaries, key=lambda item: item.start_time)):
            raise AlignmentConfigurationError(
                "explicit boundaries must be ordered by start_time"
            )
        for previous, current in zip(boundaries, boundaries[1:]):
            if current.start_time < previous.end_time:
                raise AlignmentConfigurationError(
                    "explicit boundaries must not overlap"
                )
        object.__setattr__(self, "boundaries", boundaries)

    def bucket_for(
        self, timestamp: datetime, source_duration: timedelta
    ) -> TargetBucket | None:
        normalized = _utc_datetime("timestamp", timestamp)
        if not isinstance(source_duration, timedelta) or source_duration <= timedelta(0):
            raise AlignmentConfigurationError(
                "source_duration must be a positive timedelta"
            )
        for boundary in self.boundaries:
            if boundary.start_time <= normalized < boundary.end_time:
                if any(
                    slot + source_duration > boundary.end_time
                    for slot in boundary.expected_source_timestamps
                ):
                    raise AlignmentConfigurationError(
                        "an expected source interval crosses its explicit boundary"
                    )
                return TargetBucket(
                    start_time=boundary.start_time,
                    end_time=boundary.end_time,
                    policy_id=self.policy_id,
                    expected_source_timestamps=boundary.expected_source_timestamps,
                )
        return None
