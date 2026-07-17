"""Explicit multi-timeframe OHLCV resampling with causal availability.

The public entry points accept only an error-free C-001B ``LoadResult``.  No
function in this module sorts, deduplicates, repairs, fills, clips, or invents
source bars.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Iterator, Sequence

from msa.data.alignment import (
    AlignmentPolicy,
    ExplicitBoundarySchedule,
    ExplicitFixedAnchorPolicy,
    TargetBucket,
)
from msa.data.contracts import CanonicalBar, Timeframe, VolumeType
from msa.data.loaders import LoadResult


class ResampleConfigurationError(ValueError):
    """Raised when resampling semantics are missing or contradictory."""


class CoveragePolicy(str, Enum):
    """How the complete membership of a target bucket is proven."""

    CONTIGUOUS_FIXED = "CONTIGUOUS_FIXED"
    EXPLICIT_EXPECTED_SLOTS = "EXPLICIT_EXPECTED_SLOTS"


class SessionIdPolicy(str, Enum):
    """Deterministic rule for the target bar's optional session identifier."""

    INHERIT_IF_UNANIMOUS_ELSE_NONE = "INHERIT_IF_UNANIMOUS_ELSE_NONE"
    EXPLICIT = "EXPLICIT"


@dataclass(frozen=True, slots=True)
class ResampleConfig:
    """Immutable snapshot of all resampling and publication semantics."""

    source_timeframe: Timeframe
    target_timeframe: Timeframe
    alignment_policy: AlignmentPolicy
    coverage_policy: CoveragePolicy
    publication_lag: timedelta
    policy_id: str
    session_id_policy: SessionIdPolicy
    output_session_id: str | None = None
    strict: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.source_timeframe, Timeframe):
            raise ResampleConfigurationError(
                "source_timeframe must be a Timeframe"
            )
        if not isinstance(self.target_timeframe, Timeframe):
            raise ResampleConfigurationError(
                "target_timeframe must be a Timeframe"
            )
        source_duration = self.source_timeframe.fixed_duration
        if source_duration is None:
            raise ResampleConfigurationError(
                "C-001C requires a fixed-duration source timeframe"
            )
        if not isinstance(self.coverage_policy, CoveragePolicy):
            raise ResampleConfigurationError(
                "coverage_policy must be a CoveragePolicy"
            )
        if not isinstance(self.publication_lag, timedelta):
            raise ResampleConfigurationError(
                "publication_lag must be an explicit timedelta"
            )
        if self.publication_lag < timedelta(0):
            raise ResampleConfigurationError(
                "publication_lag must be greater than or equal to zero"
            )
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ResampleConfigurationError(
                "policy_id must be a non-empty string"
            )
        if not isinstance(self.session_id_policy, SessionIdPolicy):
            raise ResampleConfigurationError(
                "session_id_policy must be a SessionIdPolicy"
            )
        if self.output_session_id is not None and (
            not isinstance(self.output_session_id, str)
            or not self.output_session_id.strip()
        ):
            raise ResampleConfigurationError(
                "output_session_id must be None or a non-empty string"
            )
        if not isinstance(self.strict, bool):
            raise ResampleConfigurationError("strict must be a bool")
        if (
            self.session_id_policy
            is SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE
            and self.output_session_id is not None
        ):
            raise ResampleConfigurationError(
                "the inheritance session policy cannot set output_session_id"
            )

        policy = self.alignment_policy
        if not isinstance(
            policy, (ExplicitFixedAnchorPolicy, ExplicitBoundarySchedule)
        ):
            raise ResampleConfigurationError(
                "an explicit supported alignment policy is required"
            )
        if policy.policy_id != self.policy_id:
            raise ResampleConfigurationError(
                "config policy_id must equal alignment policy_id"
            )
        if policy.target_timeframe is not self.target_timeframe:
            raise ResampleConfigurationError(
                "alignment target_timeframe must match config target_timeframe"
            )

        target_duration = self.target_timeframe.fixed_duration
        if target_duration is not None:
            if not isinstance(policy, ExplicitFixedAnchorPolicy):
                raise ResampleConfigurationError(
                    "fixed targets require ExplicitFixedAnchorPolicy"
                )
            if target_duration <= source_duration:
                raise ResampleConfigurationError(
                    "target_timeframe must be strictly greater than source_timeframe"
                )
            if target_duration % source_duration != timedelta(0):
                raise ResampleConfigurationError(
                    "fixed target duration must be an integer multiple of source duration"
                )
            if self.coverage_policy is not CoveragePolicy.CONTIGUOUS_FIXED:
                raise ResampleConfigurationError(
                    "fixed targets require CONTIGUOUS_FIXED coverage"
                )
        else:
            if not isinstance(policy, ExplicitBoundarySchedule):
                raise ResampleConfigurationError(
                    "D/W targets require an explicit boundary schedule"
                )
            if self.coverage_policy is not CoveragePolicy.EXPLICIT_EXPECTED_SLOTS:
                raise ResampleConfigurationError(
                    "D/W targets require EXPLICIT_EXPECTED_SLOTS coverage"
                )
            for boundary in policy.boundaries:
                if any(
                    slot + source_duration > boundary.end_time
                    for slot in boundary.expected_source_timestamps
                ):
                    raise ResampleConfigurationError(
                        "an expected source interval crosses a D/W boundary"
                    )

    def assumptions(self) -> tuple[str, ...]:
        """Return the configuration choices that must survive audit."""

        policy = self.alignment_policy
        if isinstance(policy, ExplicitFixedAnchorPolicy):
            alignment = f"explicit fixed anchor: {policy.anchor.isoformat()}"
        else:
            alignment = (
                "explicit calendar boundary schedule with "
                f"{len(policy.boundaries)} boundaries"
            )
        return (
            f"resample policy_id: {self.policy_id}",
            f"alignment: {alignment}",
            f"coverage policy: {self.coverage_policy.value}",
            f"publication lag: {self.publication_lag.total_seconds()} seconds",
            f"session id policy: {self.session_id_policy.value}",
            "target available_time = max(target end_time, maximum source "
            "member available_time) + publication_lag",
        )


class BucketStatus(str, Enum):
    """Audit outcome for one inspected target bucket."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class BucketAudit:
    """Bounded membership summary; it deliberately omits the full member list."""

    start_time: datetime
    end_time: datetime
    status: BucketStatus
    expected_slot_count: int
    source_member_count: int
    missing_slot_count: int
    extra_slot_count: int
    earliest_source_timestamp: datetime | None
    latest_source_timestamp: datetime | None
    maximum_source_available_time: datetime | None
    target_available_time: datetime | None


@dataclass(frozen=True, slots=True)
class ResampleReport:
    """Immutable, explainable result of boundary and coverage validation."""

    input_bar_count: int
    output_bar_count: int
    complete_bucket_count: int
    incomplete_bucket_count: int
    rejected_bucket_count: int
    missing_slot_count: int
    misaligned_bar_count: int
    cross_boundary_count: int
    source_identity_error_count: int
    earliest_target_timestamp: datetime | None
    latest_target_timestamp: datetime | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    assumptions: tuple[str, ...]
    policy_id: str
    bucket_audits: tuple[BucketAudit, ...]

    def __post_init__(self) -> None:
        count_fields = (
            "input_bar_count",
            "output_bar_count",
            "complete_bucket_count",
            "incomplete_bucket_count",
            "rejected_bucket_count",
            "missing_slot_count",
            "misaligned_bar_count",
            "cross_boundary_count",
            "source_identity_error_count",
        )
        if any(getattr(self, field_name) < 0 for field_name in count_fields):
            raise ValueError("resample report counts cannot be negative")
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("resample report policy_id must be non-empty")

    @property
    def has_errors(self) -> bool:
        """Whether strict resampling must reject the operation."""

        return bool(self.errors)


class ResampleError(ValueError):
    """Raised when strict resampling finds an input or bucket error."""

    def __init__(self, report: ResampleReport) -> None:
        self.report = report
        detail = report.errors[0] if report.errors else "unknown error"
        super().__init__(f"market-data resampling failed: {detail}")


@dataclass(frozen=True, slots=True)
class ResampleResult:
    """Immutable target bars, report, and complete configuration snapshot."""

    bars: tuple[CanonicalBar, ...]
    report: ResampleReport
    config_snapshot: ResampleConfig
    source_timeframe: Timeframe
    target_timeframe: Timeframe
    input_bar_count: int
    output_bar_count: int

    def __post_init__(self) -> None:
        if self.source_timeframe is not self.config_snapshot.source_timeframe:
            raise ValueError("source_timeframe must match config snapshot")
        if self.target_timeframe is not self.config_snapshot.target_timeframe:
            raise ValueError("target_timeframe must match config snapshot")
        if self.input_bar_count != self.report.input_bar_count:
            raise ValueError("input_bar_count must match report")
        if self.output_bar_count != self.report.output_bar_count:
            raise ValueError("output_bar_count must match report")
        if self.output_bar_count != len(self.bars):
            raise ValueError("output_bar_count must equal bars length")

    @property
    def config(self) -> ResampleConfig:
        """Compatibility alias for the immutable configuration snapshot."""

        return self.config_snapshot


@dataclass(slots=True)
class _BucketState:
    bucket: TargetBucket
    members: list[CanonicalBar]
    misaligned_bar_count: int = 0
    cross_boundary_count: int = 0


def resample_load_result(
    load_result: LoadResult, config: ResampleConfig
) -> ResampleResult:
    """Batch-resample every complete bucket while preserving true availability."""

    _validate_public_input(load_result, config)
    bars, report = _resample_visible_bars(
        load_result.bars,
        config,
        coverage_errors_are_warnings=False,
    )
    return _result(bars, report, config)


def resample_as_of(
    load_result: LoadResult,
    config: ResampleConfig,
    processing_time: datetime,
) -> ResampleResult:
    """Replay using only source and target bars available at ``processing_time``."""

    normalized_time = _processing_time(processing_time)
    _validate_public_input(load_result, config)
    confirmed_source = tuple(
        bar for bar in load_result.bars if bar.is_confirmed_at(normalized_time)
    )
    candidate_bars, report = _resample_visible_bars(
        confirmed_source,
        config,
        coverage_errors_are_warnings=True,
    )
    visible_targets = tuple(
        bar for bar in candidate_bars if bar.available_time <= normalized_time
    )
    report = replace(
        report,
        output_bar_count=len(visible_targets),
        earliest_target_timestamp=(
            min(bar.timestamp for bar in visible_targets)
            if visible_targets
            else None
        ),
        latest_target_timestamp=(
            max(bar.timestamp for bar in visible_targets)
            if visible_targets
            else None
        ),
    )
    return _result(visible_targets, report, config)


def iter_resample_events(
    load_result: LoadResult, config: ResampleConfig
) -> Iterator[CanonicalBar]:
    """Iterate batch target bars in first-availability event order."""

    result = resample_load_result(load_result, config)
    return iter(
        sorted(result.bars, key=lambda bar: (bar.available_time, bar.timestamp))
    )


def _result(
    bars: tuple[CanonicalBar, ...],
    report: ResampleReport,
    config: ResampleConfig,
) -> ResampleResult:
    return ResampleResult(
        bars=bars,
        report=report,
        config_snapshot=config,
        source_timeframe=config.source_timeframe,
        target_timeframe=config.target_timeframe,
        input_bar_count=report.input_bar_count,
        output_bar_count=len(bars),
    )


def _processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_public_input(
    load_result: LoadResult, config: ResampleConfig
) -> None:
    if not isinstance(load_result, LoadResult):
        raise TypeError("public resampling requires a C-001B LoadResult")
    if not isinstance(config, ResampleConfig):
        raise TypeError("config must be a ResampleConfig")

    errors: list[str] = []
    identity_error_count = 0
    if load_result.quality_report.has_errors:
        errors.append("LoadResult quality_report contains errors")
        identity_error_count += 1
    if load_result.source_config.timeframe is not config.source_timeframe:
        errors.append("LoadResult source_config timeframe does not match config")
        identity_error_count += 1
    if load_result.quality_report.timeframe is not config.source_timeframe:
        errors.append("LoadResult quality report timeframe does not match config")
        identity_error_count += 1

    bars = load_result.bars
    if bars:
        first = bars[0]
        metadata_checks = (
            (
                load_result.source_config.source == first.source,
                "LoadResult source_config source does not match canonical bars",
            ),
            (
                load_result.source_config.source_timezone
                == first.source_timezone,
                "LoadResult source_config timezone does not match canonical bars",
            ),
            (
                load_result.source_config.canonical_symbol == first.symbol,
                "LoadResult canonical symbol does not match canonical bars",
            ),
            (
                load_result.source_config.volume_type is first.volume_type,
                "LoadResult volume_type does not match canonical bars",
            ),
            (
                load_result.quality_report.source == first.source,
                "LoadResult quality report source does not match canonical bars",
            ),
        )
        for matches, message in metadata_checks:
            if not matches:
                errors.append(message)
                identity_error_count += 1
        identity_fields = (
            "symbol",
            "timeframe",
            "source",
            "source_timezone",
            "volume_type",
        )
        for index, bar in enumerate(bars):
            bar_errors: list[str] = []
            if not bar.is_complete:
                bar_errors.append("source bar is incomplete")
            if bar.timeframe is not config.source_timeframe:
                bar_errors.append("source timeframe differs from config")
            for field_name in identity_fields:
                if getattr(bar, field_name) != getattr(first, field_name):
                    bar_errors.append(f"source identity field {field_name} differs")
            if (
                bar.volume_type is VolumeType.UNAVAILABLE
                and bar.volume is not None
            ) or (
                bar.volume_type is not VolumeType.UNAVAILABLE
                and bar.volume is None
            ):
                bar_errors.append("source volume contradicts volume_type")
            if bar_errors:
                identity_error_count += 1
                errors.append(
                    f"source bar {index + 1}: " + "; ".join(bar_errors)
                )

        seen_timestamps: set[datetime] = set()
        for index, bar in enumerate(bars):
            if bar.timestamp in seen_timestamps:
                errors.append(f"source bar {index + 1}: duplicate timestamp")
                identity_error_count += 1
            seen_timestamps.add(bar.timestamp)
            if index == 0:
                continue
            previous = bars[index - 1]
            if bar.timestamp <= previous.timestamp:
                errors.append(
                    f"source bar {index + 1}: timestamps are not strictly ascending"
                )
                identity_error_count += 1
            if bar.timestamp < previous.end_time:
                errors.append(f"source bar {index + 1}: source intervals overlap")
                identity_error_count += 1

    if errors:
        raise ResampleError(
            _input_error_report(
                input_bar_count=len(bars),
                config=config,
                errors=tuple(errors),
                identity_error_count=identity_error_count,
            )
        )


def _input_error_report(
    *,
    input_bar_count: int,
    config: ResampleConfig,
    errors: tuple[str, ...],
    identity_error_count: int,
) -> ResampleReport:
    return ResampleReport(
        input_bar_count=input_bar_count,
        output_bar_count=0,
        complete_bucket_count=0,
        incomplete_bucket_count=0,
        rejected_bucket_count=0,
        missing_slot_count=0,
        misaligned_bar_count=0,
        cross_boundary_count=0,
        source_identity_error_count=identity_error_count,
        earliest_target_timestamp=None,
        latest_target_timestamp=None,
        warnings=(),
        errors=errors,
        assumptions=config.assumptions(),
        policy_id=config.policy_id,
        bucket_audits=(),
    )


def _resample_visible_bars(
    bars: Sequence[CanonicalBar],
    config: ResampleConfig,
    *,
    coverage_errors_are_warnings: bool,
) -> tuple[tuple[CanonicalBar, ...], ResampleReport]:
    states, setup_errors, outside_misaligned_count = _bucket_states(bars, config)
    warnings: list[str] = []
    errors = list(setup_errors)
    audits: list[BucketAudit] = []
    output: list[CanonicalBar] = []
    complete_count = 0
    incomplete_count = 0
    rejected_count = 0
    missing_count = 0
    misaligned_count = outside_misaligned_count
    cross_count = 0

    last_start = states[-1].bucket.start_time if states else None
    for state in states:
        bucket = state.bucket
        members = tuple(sorted(state.members, key=lambda bar: bar.timestamp))
        expected = set(bucket.expected_source_timestamps)
        actual = {bar.timestamp for bar in members}
        missing = tuple(sorted(expected - actual))
        extra = tuple(sorted(actual - expected))
        missing_count += len(missing)
        misaligned_count += state.misaligned_bar_count
        cross_count += state.cross_boundary_count

        structural_error = bool(
            extra
            or state.misaligned_bar_count
            or state.cross_boundary_count
        )
        if structural_error:
            rejected_count += 1
            errors.append(
                f"bucket {bucket.start_time.isoformat()} rejected: "
                f"{len(extra)} extra slots, "
                f"{state.misaligned_bar_count} misaligned bars, "
                f"{state.cross_boundary_count} cross-boundary bars"
            )
            audits.append(
                _bucket_audit(
                    bucket,
                    members,
                    BucketStatus.REJECTED,
                    missing_count=len(missing),
                    extra_count=len(extra),
                    target_available_time=None,
                )
            )
            continue

        if missing:
            incomplete_count += 1
            message = (
                f"bucket {bucket.start_time.isoformat()} is incomplete: "
                f"missing {len(missing)} expected source slots"
            )
            trailing_truncation = _is_trailing_truncation(
                state,
                missing,
                is_last_bucket=bucket.start_time == last_start,
            )
            if coverage_errors_are_warnings or trailing_truncation:
                warnings.append(message)
            else:
                errors.append(message)
            audits.append(
                _bucket_audit(
                    bucket,
                    members,
                    BucketStatus.INCOMPLETE,
                    missing_count=len(missing),
                    extra_count=0,
                    target_available_time=None,
                )
            )
            continue

        target, session_warning = _aggregate_bucket(members, bucket, config)
        if session_warning is not None:
            warnings.append(session_warning)
        complete_count += 1
        output.append(target)
        audits.append(
            _bucket_audit(
                bucket,
                members,
                BucketStatus.COMPLETE,
                missing_count=0,
                extra_count=0,
                target_available_time=target.available_time,
            )
        )

    output_tuple = tuple(sorted(output, key=lambda bar: bar.timestamp))
    report = ResampleReport(
        input_bar_count=len(bars),
        output_bar_count=len(output_tuple),
        complete_bucket_count=complete_count,
        incomplete_bucket_count=incomplete_count,
        rejected_bucket_count=rejected_count,
        missing_slot_count=missing_count,
        misaligned_bar_count=misaligned_count,
        cross_boundary_count=cross_count,
        source_identity_error_count=0,
        earliest_target_timestamp=(
            output_tuple[0].timestamp if output_tuple else None
        ),
        latest_target_timestamp=(
            output_tuple[-1].timestamp if output_tuple else None
        ),
        warnings=tuple(warnings),
        errors=tuple(errors),
        assumptions=config.assumptions(),
        policy_id=config.policy_id,
        bucket_audits=tuple(audits),
    )
    if config.strict and report.has_errors:
        raise ResampleError(report)
    return output_tuple, report


def _bucket_states(
    bars: Sequence[CanonicalBar], config: ResampleConfig
) -> tuple[list[_BucketState], tuple[str, ...], int]:
    source_duration = config.source_timeframe.fixed_duration
    assert source_duration is not None
    raw_states: dict[datetime, _BucketState] = {}
    errors: list[str] = []
    outside_misaligned_count = 0

    for index, bar in enumerate(bars):
        bucket = config.alignment_policy.bucket_for(
            bar.timestamp, source_duration
        )
        if bucket is None:
            outside_misaligned_count += 1
            errors.append(
                f"source bar {index + 1} at {bar.timestamp.isoformat()} "
                "is outside the explicit boundary schedule"
            )
            continue
        state = raw_states.setdefault(
            bucket.start_time, _BucketState(bucket=bucket, members=[])
        )
        state.members.append(bar)
        if bar.timestamp not in bucket.expected_source_timestamps:
            state.misaligned_bar_count += 1
        if bar.timestamp < bucket.start_time or bar.end_time > bucket.end_time:
            state.cross_boundary_count += 1

    if not raw_states:
        return [], tuple(errors), outside_misaligned_count

    policy = config.alignment_policy
    if isinstance(policy, ExplicitFixedAnchorPolicy):
        target_duration = config.target_timeframe.fixed_duration
        assert target_duration is not None
        first_start = min(raw_states)
        last_start = max(raw_states)
        ordered: list[_BucketState] = []
        start = first_start
        while start <= last_start:
            bucket = policy.bucket_for(start, source_duration)
            ordered.append(
                raw_states.get(start, _BucketState(bucket=bucket, members=[]))
            )
            start += target_duration
        return ordered, tuple(errors), outside_misaligned_count

    assert isinstance(policy, ExplicitBoundarySchedule)
    boundary_indexes = {
        boundary.start_time: index
        for index, boundary in enumerate(policy.boundaries)
    }
    first_index = min(boundary_indexes[start] for start in raw_states)
    last_index = max(boundary_indexes[start] for start in raw_states)
    ordered = []
    for boundary in policy.boundaries[first_index : last_index + 1]:
        bucket = policy.bucket_for(boundary.start_time, source_duration)
        assert bucket is not None
        ordered.append(
            raw_states.get(
                boundary.start_time,
                _BucketState(bucket=bucket, members=[]),
            )
        )
    return ordered, tuple(errors), outside_misaligned_count


def _is_trailing_truncation(
    state: _BucketState,
    missing: Sequence[datetime],
    *,
    is_last_bucket: bool,
) -> bool:
    if not is_last_bucket or not state.members:
        return False
    last_member_end = max(bar.end_time for bar in state.members)
    return all(timestamp >= last_member_end for timestamp in missing)


def _aggregate_bucket(
    members: Sequence[CanonicalBar],
    bucket: TargetBucket,
    config: ResampleConfig,
) -> tuple[CanonicalBar, str | None]:
    first = members[0]
    last = members[-1]
    maximum_available_time = max(bar.available_time for bar in members)
    base_available_time = max(bucket.end_time, maximum_available_time)
    available_time = base_available_time + config.publication_lag

    if first.volume_type is VolumeType.UNAVAILABLE:
        volume = None
    else:
        volumes = [bar.volume for bar in members]
        if any(value is None for value in volumes):
            raise AssertionError("validated volume members cannot be None")
        volume = sum((value for value in volumes if value is not None), Decimal(0))

    session_id, session_warning = _output_session_id(members, bucket, config)
    target = CanonicalBar(
        symbol=first.symbol,
        timeframe=config.target_timeframe,
        timestamp=bucket.start_time,
        end_time=bucket.end_time,
        open=first.open,
        high=max(bar.high for bar in members),
        low=min(bar.low for bar in members),
        close=last.close,
        volume=volume,
        volume_type=first.volume_type,
        source=first.source,
        source_timezone=first.source_timezone,
        session_id=session_id,
        boundary_policy=config.policy_id,
        is_complete=True,
        available_time=available_time,
    )
    return target, session_warning


def _output_session_id(
    members: Sequence[CanonicalBar],
    bucket: TargetBucket,
    config: ResampleConfig,
) -> tuple[str | None, str | None]:
    if config.session_id_policy is SessionIdPolicy.EXPLICIT:
        return config.output_session_id, None
    member_session_ids = {bar.session_id for bar in members}
    if len(member_session_ids) == 1:
        return next(iter(member_session_ids)), None
    return (
        None,
        f"bucket {bucket.start_time.isoformat()} contains conflicting "
        "session_id values; output session_id is explicitly cleared",
    )


def _bucket_audit(
    bucket: TargetBucket,
    members: Sequence[CanonicalBar],
    status: BucketStatus,
    *,
    missing_count: int,
    extra_count: int,
    target_available_time: datetime | None,
) -> BucketAudit:
    return BucketAudit(
        start_time=bucket.start_time,
        end_time=bucket.end_time,
        status=status,
        expected_slot_count=len(bucket.expected_source_timestamps),
        source_member_count=len(members),
        missing_slot_count=missing_count,
        extra_slot_count=extra_count,
        earliest_source_timestamp=(members[0].timestamp if members else None),
        latest_source_timestamp=(members[-1].timestamp if members else None),
        maximum_source_available_time=(
            max(bar.available_time for bar in members) if members else None
        ),
        target_available_time=target_available_time,
    )
