from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from msa.data import (
    CanonicalBar,
    CompletedBarPolicy,
    LoadResult,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    validate_bar_sequence,
)
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureObjectKind,
    StructureSourceType,
)
from msa.research.lifecycle import LifecycleConfig, LifecycleEngine, LifecycleInput
from msa.research.timeframe_state import (
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateEngine,
    TimeframeStateInput,
)


UTC = timezone.utc
START = datetime(2026, 7, 10, 0, 0, tzinfo=UTC)
T1 = START + timedelta(hours=1)
T2 = START + timedelta(hours=2)
T3 = START + timedelta(hours=3)
T4 = START + timedelta(hours=4)
T5 = START + timedelta(hours=5)
T6 = START + timedelta(hours=6)
PRIMARY = ScaleDescriptor("primary", 1)


def bar(
    index: int,
    *,
    high: str = "111",
    low: str = "90",
    close: str = "100",
    available_time: datetime | None = None,
) -> CanonicalBar:
    timestamp = START + timedelta(hours=index)
    end_time = timestamp + timedelta(hours=1)
    return CanonicalBar(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=timestamp,
        end_time=end_time,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=None,
        volume_type=VolumeType.UNAVAILABLE,
        source="timeframe-state-fixture",
        source_timezone="UTC",
        session_id="fixture-session",
        boundary_policy=None,
        is_complete=True,
        available_time=available_time or end_time,
    )


def source_config() -> SourceDataConfig:
    return SourceDataConfig(
        source="timeframe-state-fixture",
        source_timezone="UTC",
        source_symbol="GOLD",
        canonical_symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp_column="time",
        timestamp_semantics=TimestampSemantics.OPEN_TIME,
        timestamp_format="%Y-%m-%dT%H:%M:%S%z",
        open_column="open",
        high_column="high",
        low_column="low",
        close_column="close",
        volume_column=None,
        volume_type=VolumeType.UNAVAILABLE,
        completed_bar_policy=CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        availability_lag=timedelta(0),
        session_id="fixture-session",
        boundary_policy=None,
        end_time_column=None,
        strict=True,
    )


def load_result(bars: tuple[CanonicalBar, ...]) -> LoadResult:
    config = source_config()
    report = validate_bar_sequence(
        bars, source=config.source, timeframe=config.timeframe
    )
    return LoadResult(bars, report, config, len(bars), len(bars), 0)


def subject(
    subject_id: str,
    side: BoundarySide,
    low: str,
    high: str,
    *,
    confirm_time: datetime = START,
    timeframe: Timeframe = Timeframe.H4,
    scale: ScaleDescriptor = PRIMARY,
    lifecycle_state: LifecycleState = LifecycleState.CONFIRMED,
) -> BoundaryRef:
    role = (
        MarketRole.RESISTANCE
        if side is BoundarySide.UPPER
        else MarketRole.SUPPORT
    )
    return BoundaryRef(
        object_kind=StructureObjectKind.LEVEL_CANDIDATE,
        object_id=subject_id,
        symbol="XAUUSD",
        timeframe=timeframe,
        scale=scale,
        price_range=PriceRange(Decimal(low), Decimal(high)),
        boundary_side=side,
        market_role=role,
        lifecycle_state=lifecycle_state,
        origin_time=START - timedelta(days=10),
        confirm_time=confirm_time,
        source_types=(StructureSourceType.SWING,),
        structure_families=("timeframe-state-fixture",),
        provenance=ProvenanceRef(
            "tests.timeframe_state",
            "1",
            f"source-{subject_id}",
            "fixture-policy",
            (),
            ("fixture subject",),
        ),
    )


def lifecycle_config(**overrides: object) -> LifecycleConfig:
    values: dict[str, object] = {
        "engine_id": "c006a-fixture",
        "engine_version": "1.0.0",
        "policy_id": "fixture-lifecycle-policy",
        "observation_timeframe": Timeframe.H1,
        "test_tolerance": Decimal("0"),
        "break_buffer": Decimal("1"),
        "weakening_test_count": 2,
        "minimum_test_separation_bars": 1,
        "flip_tolerance": Decimal("0"),
        "flip_confirmation_distance": Decimal("1"),
        "flip_horizon_bars": 3,
        "failed_break_retirement_buffer": Decimal("1"),
        "strict": True,
    }
    values.update(overrides)
    return LifecycleConfig(**values)  # type: ignore[arg-type]


def lifecycle_history(
    subjects: tuple[BoundaryRef, ...],
    bars: tuple[CanonicalBar, ...],
    **config_overrides: object,
):
    engine = LifecycleEngine(lifecycle_config(**config_overrides))
    return engine.build_batch(LifecycleInput(load_result(bars), subjects))


def timeframe_config(**overrides: object) -> TimeframeStateConfig:
    values: dict[str, object] = {
        "engine_id": "c006b-timeframe-state",
        "engine_version": "1.0.0",
        "policy_id": "latest-causal-v1",
        "symbol": "XAUUSD",
        "target_timeframe": Timeframe.H4,
        "target_scale": PRIMARY,
        "selection_policy": TimeframeSelectionPolicy.LATEST_CAUSAL,
        "strict": True,
    }
    values.update(overrides)
    return TimeframeStateConfig(**values)  # type: ignore[arg-type]


def timeframe_engine(**overrides: object) -> TimeframeStateEngine:
    return TimeframeStateEngine(timeframe_config(**overrides))


def timeframe_input(
    subjects: tuple[BoundaryRef, ...],
    bars: tuple[CanonicalBar, ...],
    **config_overrides: object,
) -> TimeframeStateInput:
    return TimeframeStateInput(
        lifecycle_history(subjects, bars, **config_overrides)
    )


def base_pair() -> tuple[BoundaryRef, BoundaryRef]:
    return (
        subject("upper-old", BoundarySide.UPPER, "110", "111"),
        subject("lower-old", BoundarySide.LOWER, "90", "91"),
    )


def direction_sequence_input() -> TimeframeStateInput:
    subjects = base_pair() + (
        subject(
            "upper-up",
            BoundarySide.UPPER,
            "115",
            "116",
            confirm_time=T1,
        ),
        subject(
            "lower-up",
            BoundarySide.LOWER,
            "95",
            "96",
            confirm_time=T1,
        ),
        subject(
            "upper-down",
            BoundarySide.UPPER,
            "105",
            "106",
            confirm_time=T2,
        ),
        subject(
            "lower-down",
            BoundarySide.LOWER,
            "85",
            "86",
            confirm_time=T2,
        ),
        subject(
            "upper-down-2",
            BoundarySide.UPPER,
            "100",
            "101",
            confirm_time=T3,
        ),
        subject(
            "lower-down-2",
            BoundarySide.LOWER,
            "80",
            "81",
            confirm_time=T3,
        ),
    )
    bars = (
        bar(0, high="111", low="90", close="100"),
        bar(1, high="116", low="95", close="105"),
        bar(2, high="106", low="85", close="95"),
        bar(3, high="101", low="80", close="90"),
    )
    return timeframe_input(subjects, bars)
