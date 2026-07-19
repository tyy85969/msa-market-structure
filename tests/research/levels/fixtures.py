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
    BoundarySide,
    ConfirmationStatus,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureSourceType,
)
from msa.research.levels import (
    HistoricalReactionConfig,
    HistoricalReactionGenerator,
    LevelGenerationInput,
    PeriodicExtremeConfig,
    PeriodicExtremeGenerator,
)


UTC = timezone.utc
START = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
SCALE = ScaleDescriptor("c004-h1", 1)


def bar(
    index: int,
    *,
    open: str = "100",
    high: str = "101",
    low: str = "99",
    close: str = "100",
    timestamp: datetime | None = None,
    available_time: datetime | None = None,
    timeframe: Timeframe = Timeframe.H1,
    symbol: str = "XAUUSD",
    source: str = "synthetic-feed",
    boundary_policy: str | None = None,
    is_complete: bool = True,
) -> CanonicalBar:
    start = timestamp or START + index * timedelta(hours=1)
    duration = timeframe.fixed_duration
    if duration is None:
        duration = timedelta(days=1 if timeframe is Timeframe.D else 7)
    end = start + duration
    return CanonicalBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=start,
        end_time=end,
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=None,
        volume_type=VolumeType.UNAVAILABLE,
        source=source,
        source_timezone="UTC",
        session_id="synthetic-session",
        boundary_policy=boundary_policy,
        is_complete=is_complete,
        available_time=available_time or end,
    )


def source_config(
    *,
    timeframe: Timeframe = Timeframe.H1,
    source: str = "synthetic-feed",
    boundary_policy: str | None = None,
) -> SourceDataConfig:
    return SourceDataConfig(
        source=source,
        source_timezone="UTC",
        source_symbol="GOLD",
        canonical_symbol="XAUUSD",
        timeframe=timeframe,
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
        session_id="synthetic-session",
        boundary_policy=boundary_policy,
        end_time_column=("end" if timeframe.requires_boundary_policy else None),
    )


def load_result(
    bars: tuple[CanonicalBar, ...],
    *,
    config: SourceDataConfig | None = None,
) -> LoadResult:
    actual = config or source_config(
        timeframe=bars[0].timeframe if bars else Timeframe.H1,
        source=bars[0].source if bars else "synthetic-feed",
        boundary_policy=bars[0].boundary_policy if bars else None,
    )
    report = validate_bar_sequence(
        bars,
        source=actual.source,
        timeframe=actual.timeframe,
        assumptions=actual.assumptions(),
    )
    return LoadResult(
        bars=bars,
        quality_report=report,
        source_config=actual,
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )


def seed(
    *,
    candidate_id: str = "swing-seed-upper",
    price: str = "100",
    side: BoundarySide = BoundarySide.UPPER,
    origin_time: datetime = START,
    confirm_time: datetime = START + timedelta(hours=1),
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.H1,
    source_type: StructureSourceType = StructureSourceType.SWING,
    confirmation_status: ConfirmationStatus = ConfirmationStatus.CONFIRMED,
    lifecycle_state: LifecycleState = LifecycleState.CONFIRMED,
    price_high: str | None = None,
) -> LevelCandidate:
    value = Decimal(price)
    role = MarketRole.RESISTANCE if side is BoundarySide.UPPER else MarketRole.SUPPORT
    return LevelCandidate(
        candidate_id=candidate_id,
        symbol=symbol,
        timeframe=timeframe,
        scale=SCALE,
        price_range=PriceRange(value, Decimal(price_high) if price_high else value),
        source_type=source_type,
        boundary_side=side,
        market_role=role,
        confirmation_status=confirmation_status,
        lifecycle_state=lifecycle_state,
        origin_time=origin_time,
        confirm_time=(
            confirm_time
            if confirmation_status is ConfirmationStatus.CONFIRMED
            else None
        ),
        touch_count=0,
        last_touch_time=None,
        last_touch_confirm_time=None,
        break_time=None,
        break_confirm_time=None,
        structure_family="confirmed-pivot-strict-v1",
        provenance=ProvenanceRef(
            source_module="msa.research.swing.pivot",
            source_version="1.0.0",
            source_object_id=f"pivot-window-{candidate_id}",
            policy_id="pivot-strict-v1",
            parent_object_ids=(f"bar-ref-{candidate_id}",),
            notes=("fixture confirmed Pivot candidate",),
        ),
    )


def periodic_config(**overrides: object) -> PeriodicExtremeConfig:
    values: dict[str, object] = {
        "generator_id": "periodic-extreme",
        "generator_version": "1.0.0",
        "period_timeframe": Timeframe.H1,
        "scale": SCALE,
        "policy_id": "periodic-extreme-v1",
        "emit_high": True,
        "emit_low": True,
        "strict": True,
    }
    values.update(overrides)
    return PeriodicExtremeConfig(**values)  # type: ignore[arg-type]


def periodic_generator(**overrides: object) -> PeriodicExtremeGenerator:
    return PeriodicExtremeGenerator(periodic_config(**overrides))


def reaction_config(**overrides: object) -> HistoricalReactionConfig:
    values: dict[str, object] = {
        "generator_id": "historical-reaction",
        "generator_version": "1.0.0",
        "touch_tolerance": Decimal("1"),
        "min_reactions": 2,
        "min_separation_bars": 2,
        "confirmation_horizon_bars": 2,
        "min_reaction_distance": Decimal("2"),
        "max_penetration": Decimal("2"),
        "scale": SCALE,
        "policy_id": "historical-reaction-v1",
        "strict": True,
    }
    values.update(overrides)
    return HistoricalReactionConfig(**values)  # type: ignore[arg-type]


def reaction_generator(**overrides: object) -> HistoricalReactionGenerator:
    return HistoricalReactionGenerator(reaction_config(**overrides))


def periodic_input(bars: tuple[CanonicalBar, ...]) -> LevelGenerationInput:
    return LevelGenerationInput(load_result(bars), ())


def reaction_input(
    bars: tuple[CanonicalBar, ...], seeds: tuple[LevelCandidate, ...] | None = None
) -> LevelGenerationInput:
    return LevelGenerationInput(load_result(bars), seeds or (seed(),))


def upper_success_bars() -> tuple[CanonicalBar, ...]:
    return (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="100", low="95", open="99", close="96"),
        bar(3, high="101", low="99", open="100", close="100"),
        bar(4, high="100", low="95", open="99", close="96"),
    )


def lower_success_bars() -> tuple[CanonicalBar, ...]:
    return (
        bar(0, high="112", low="110", open="111", close="111"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="105", low="100", open="101", close="104"),
        bar(3, high="101", low="99", open="100", close="100"),
        bar(4, high="105", low="100", open="101", close="104"),
    )
