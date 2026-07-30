"""Deterministic production-owned synthetic inputs for C-008C."""

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
from msa.reference import core_alpha_v1_config
from msa.research.lifecycle import (
    LifecycleConfig,
    LifecycleEngine,
    LifecycleHistory,
    LifecycleInput,
)
from msa.research.msa_core.contracts import validate_source_input
from msa.research.resonance import (
    ResonanceContext,
    ResonanceFrameInput,
)
from msa.research.timeframe_state import (
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateEngine,
    TimeframeStateInput,
)
from msa.validation.contracts import SyntheticScenarioKind

from .errors import ExperimentInputError


UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)
GENERATED_WARMUP_BARS = 32
GENERATED_POST_CONFIRM_BARS = 64
GENERATED_TOTAL_BARS = GENERATED_WARMUP_BARS + GENERATED_POST_CONFIRM_BARS
DATA_START = START - timedelta(hours=GENERATED_WARMUP_BARS)
LIFECYCLE_BREAK_BUFFER = Decimal("1")
PRIMARY = ScaleDescriptor("primary", 1)
MACRO = ScaleDescriptor("macro", 2)
H4_PRIMARY = ResonanceContext(Timeframe.H4, PRIMARY)
H12_MACRO = ResonanceContext(Timeframe.H12, MACRO)

_SCENARIO_BASE_PRICES = {
    SyntheticScenarioKind.SINGLE_TREND: "100",
    SyntheticScenarioKind.RANGE: "102",
    SyntheticScenarioKind.V_REVERSAL: "104",
    SyntheticScenarioKind.FALSE_BREAK: "106",
    SyntheticScenarioKind.GAP_SHOCK: "108",
}
_RANGE_OFFSETS = (
    Decimal("-2"),
    Decimal("-1"),
    Decimal("1"),
    Decimal("2"),
    Decimal("1"),
    Decimal("-1"),
)


def _source_name(kind: SyntheticScenarioKind, seed: int) -> str:
    return f"c008c-{kind.value.lower().replace('_', '-')}-seed-{seed}"


def _prices(
    kind: SyntheticScenarioKind, seed: int
) -> tuple[Decimal, ...]:
    offset = Decimal(seed) / Decimal("10")
    base = Decimal(_SCENARIO_BASE_PRICES[kind]) + offset
    if kind is SyntheticScenarioKind.SINGLE_TREND:
        return tuple(
            base - Decimal("8") + Decimal(index) * Decimal("0.2")
            for index in range(GENERATED_TOTAL_BARS)
        )
    if kind is SyntheticScenarioKind.RANGE:
        return tuple(
            base + _RANGE_OFFSETS[index % len(_RANGE_OFFSETS)]
            for index in range(GENERATED_TOTAL_BARS)
        )
    if kind is SyntheticScenarioKind.V_REVERSAL:
        return tuple(
            (
                base
                + Decimal("8")
                - Decimal(index) * Decimal("0.25")
                if index < 48
                else base
                - Decimal("4")
                + Decimal(index - 48) * Decimal("0.35")
            )
            for index in range(GENERATED_TOTAL_BARS)
        )
    if kind is SyntheticScenarioKind.FALSE_BREAK:
        values: list[Decimal] = []
        for index in range(GENERATED_TOTAL_BARS):
            if index < GENERATED_WARMUP_BARS:
                values.append(
                    base
                    + _RANGE_OFFSETS[index % len(_RANGE_OFFSETS)]
                    / Decimal("4")
                )
                continue
            post_index = index - GENERATED_WARMUP_BARS
            if post_index < 8:
                values.append(base + Decimal(post_index) * Decimal("0.25"))
            elif post_index == 8:
                values.append(base + Decimal("12"))
            elif post_index == 9:
                values.append(base + Decimal("8"))
            else:
                values.append(
                    base
                    + _RANGE_OFFSETS[post_index % len(_RANGE_OFFSETS)]
                    / Decimal("2")
                )
        return tuple(values)
    values = []
    for index in range(GENERATED_TOTAL_BARS):
        if index < GENERATED_WARMUP_BARS:
            values.append(
                base
                + _RANGE_OFFSETS[index % len(_RANGE_OFFSETS)]
                / Decimal("4")
            )
            continue
        post_index = index - GENERATED_WARMUP_BARS
        if post_index < 12:
            values.append(base + Decimal(post_index) * Decimal("0.1"))
        else:
            values.append(
                base
                + Decimal("14")
                + Decimal(post_index - 12) * Decimal("0.1")
            )
    return tuple(values)


def _bar(
    index: int,
    close: Decimal,
    *,
    source: str,
) -> CanonicalBar:
    timestamp = DATA_START + timedelta(hours=index)
    end_time = timestamp + timedelta(hours=1)
    return CanonicalBar(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=timestamp,
        end_time=end_time,
        open=close,
        high=close + Decimal("0.75"),
        low=close - Decimal("0.75"),
        close=close,
        volume=None,
        volume_type=VolumeType.UNAVAILABLE,
        source=source,
        source_timezone="UTC",
        is_complete=True,
        available_time=end_time,
        session_id="c008c-synthetic",
        boundary_policy=None,
    )


def _source_config(source: str) -> SourceDataConfig:
    return SourceDataConfig(
        source=source,
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
        session_id="c008c-synthetic",
        boundary_policy=None,
        end_time_column=None,
        strict=True,
    )


def _load_result(
    bars: tuple[CanonicalBar, ...], source: str
) -> LoadResult:
    config = _source_config(source)
    report = validate_bar_sequence(
        bars, source=config.source, timeframe=config.timeframe
    )
    return LoadResult(
        bars=bars,
        quality_report=report,
        source_config=config,
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )


def _subject(
    identity: str,
    side: BoundarySide,
    low: Decimal,
    high: Decimal,
    *,
    timeframe: Timeframe,
    scale: ScaleDescriptor,
    source_type: StructureSourceType,
) -> BoundaryRef:
    return BoundaryRef(
        object_kind=StructureObjectKind.LEVEL_CANDIDATE,
        object_id=identity,
        symbol="XAUUSD",
        timeframe=timeframe,
        scale=scale,
        price_range=PriceRange(low, high),
        boundary_side=side,
        market_role=(
            MarketRole.RESISTANCE
            if side is BoundarySide.UPPER
            else MarketRole.SUPPORT
        ),
        lifecycle_state=LifecycleState.CONFIRMED,
        origin_time=START - timedelta(days=10),
        confirm_time=START,
        source_types=(source_type,),
        structure_families=(f"{identity}-family",),
        provenance=ProvenanceRef(
            source_module="msa.validation.experiments.synthetic_suite",
            source_version="1.0.0",
            source_object_id=f"source-{identity}",
            policy_id="c008c-synthetic-v1",
            parent_object_ids=(),
            notes=("Deterministic engineering fixture",),
        ),
    )


def _subjects(
    kind: SyntheticScenarioKind, seed: int, center: Decimal
) -> tuple[BoundaryRef, ...]:
    tag = _source_name(kind, seed)
    return (
        _subject(
            f"{tag}-upper-primary",
            BoundarySide.UPPER,
            center + Decimal("9"),
            center + Decimal("10"),
            timeframe=Timeframe.H4,
            scale=PRIMARY,
            source_type=StructureSourceType.SWING,
        ),
        _subject(
            f"{tag}-lower-primary",
            BoundarySide.LOWER,
            center - Decimal("10"),
            center - Decimal("9"),
            timeframe=Timeframe.H4,
            scale=PRIMARY,
            source_type=StructureSourceType.SWING,
        ),
        _subject(
            f"{tag}-upper-macro",
            BoundarySide.UPPER,
            center + Decimal("19"),
            center + Decimal("20"),
            timeframe=Timeframe.H12,
            scale=MACRO,
            source_type=StructureSourceType.PERIODIC_EXTREME,
        ),
        _subject(
            f"{tag}-lower-macro",
            BoundarySide.LOWER,
            center - Decimal("20"),
            center - Decimal("19"),
            timeframe=Timeframe.H12,
            scale=MACRO,
            source_type=StructureSourceType.HISTORICAL_REACTION,
        ),
    )


def _lifecycle_config() -> LifecycleConfig:
    return LifecycleConfig(
        engine_id="c006a-c008c-synthetic",
        engine_version="1.0.0",
        policy_id="c008c-synthetic-lifecycle-capacity-v1",
        observation_timeframe=Timeframe.H1,
        test_tolerance=Decimal("0"),
        break_buffer=LIFECYCLE_BREAK_BUFFER,
        weakening_test_count=2,
        minimum_test_separation_bars=1,
        flip_tolerance=Decimal("0"),
        flip_confirmation_distance=Decimal("1"),
        flip_horizon_bars=3,
        failed_break_retirement_buffer=Decimal("1"),
        strict=True,
    )


def _timeframe_history(history: object, context: ResonanceContext) -> object:
    config = TimeframeStateConfig(
        engine_id="c006b-c008c-synthetic",
        engine_version="1.0.0",
        policy_id="latest-causal-v1",
        symbol="XAUUSD",
        target_timeframe=context.timeframe,
        target_scale=context.scale,
        selection_policy=TimeframeSelectionPolicy.LATEST_CAUSAL,
        strict=True,
    )
    return TimeframeStateEngine(config).build_batch(
        TimeframeStateInput(history)  # type: ignore[arg-type]
    )


def _lifecycle_history(
    data: LoadResult, subjects: tuple[BoundaryRef, ...]
) -> LifecycleHistory:
    engine = LifecycleEngine(_lifecycle_config())
    source = LifecycleInput(data, subjects)
    confirm_snapshot = engine.build_as_of(source, START)
    final_snapshot = engine.build_as_of(
        source, data.bars[-1].available_time
    )
    return LifecycleHistory(
        events=final_snapshot.events,
        snapshots=(confirm_snapshot, final_snapshot),
        final_snapshot=final_snapshot,
    )


def build_synthetic_source_input(
    kind: SyntheticScenarioKind, seed: int
) -> ResonanceFrameInput:
    """Build one formal deterministic source input without global randomness."""

    if not isinstance(kind, SyntheticScenarioKind):
        raise ExperimentInputError("kind must be SyntheticScenarioKind")
    if type(seed) is not int or seed not in (0, 1, 2, 3):
        raise ExperimentInputError("seed must be one of 0, 1, 2, 3")
    try:
        source = _source_name(kind, seed)
        prices = _prices(kind, seed)
        center = Decimal(_SCENARIO_BASE_PRICES[kind]) + (
            Decimal(seed) / Decimal("10")
        )
        bars = tuple(
            _bar(index, close, source=source)
            for index, close in enumerate(prices)
        )
        data = _load_result(bars, source)
        lifecycle_history = _lifecycle_history(
            data, _subjects(kind, seed, center)
        )
        histories = tuple(
            _timeframe_history(lifecycle_history, context)
            for context in (H4_PRIMARY, H12_MACRO)
        )
        result = ResonanceFrameInput(lifecycle_history, histories, data)
        return validate_source_input(result, core_alpha_v1_config())
    except (
        AssertionError,
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentInputError(
            "unable to build the formal synthetic source input"
        ) from exc
