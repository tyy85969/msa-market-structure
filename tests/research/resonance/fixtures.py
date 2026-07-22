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
from msa.research.resonance import (
    ReferencePriceField,
    ResonanceContext,
    ResonanceEvidencePolicy,
    ResonanceFrameAssembler,
    ResonanceFrameConfig,
    ResonanceFrameInput,
)
from msa.research.timeframe_state import (
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateEngine,
    TimeframeStateInput,
)


UTC = timezone.utc
START = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
T1 = START + timedelta(hours=1)
T2 = START + timedelta(hours=2)
T3 = START + timedelta(hours=3)
T4 = START + timedelta(hours=4)
PRIMARY = ScaleDescriptor("primary", 1)
MACRO = ScaleDescriptor("macro", 2)
EXTRA = ScaleDescriptor("extra", 0)
H4_PRIMARY = ResonanceContext(Timeframe.H4, PRIMARY)
H12_MACRO = ResonanceContext(Timeframe.H12, MACRO)


def bar(
    index: int,
    *,
    high: str = "105",
    low: str = "95",
    close: str = "100",
    available_time: datetime | None = None,
    is_complete: bool = True,
    source: str = "resonance-fixture",
) -> CanonicalBar:
    timestamp = START + timedelta(hours=index)
    end = timestamp + timedelta(hours=1)
    return CanonicalBar(
        symbol="XAUUSD",
        timeframe=Timeframe.H1,
        timestamp=timestamp,
        end_time=end,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=None,
        volume_type=VolumeType.UNAVAILABLE,
        source=source,
        source_timezone="UTC",
        is_complete=is_complete,
        available_time=available_time or end,
        session_id="fixture-session",
        boundary_policy=None,
    )


def source_config(
    *, source: str = "resonance-fixture", timeframe: Timeframe = Timeframe.H1
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
        session_id="fixture-session",
        boundary_policy=None,
        end_time_column=None,
        strict=True,
    )


def load_result(
    bars: tuple[CanonicalBar, ...], *, config: SourceDataConfig | None = None
) -> LoadResult:
    cfg = config or source_config(source=bars[0].source)
    report = validate_bar_sequence(
        bars, source=cfg.source, timeframe=cfg.timeframe
    )
    return LoadResult(bars, report, cfg, len(bars), len(bars), 0)


def subject(
    subject_id: str,
    side: BoundarySide,
    low: str,
    high: str,
    *,
    timeframe: Timeframe = Timeframe.H4,
    scale: ScaleDescriptor = PRIMARY,
    confirm_time: datetime = START,
    source_types: tuple[StructureSourceType, ...] = (StructureSourceType.SWING,),
    families: tuple[str, ...] = ("fixture-family",),
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
        lifecycle_state=LifecycleState.CONFIRMED,
        origin_time=START - timedelta(days=10),
        confirm_time=confirm_time,
        source_types=source_types,
        structure_families=families,
        provenance=ProvenanceRef(
            "tests.resonance", "1", f"source-{subject_id}",
            "fixture-policy", (), ("fixture subject",),
        ),
    )


def base_subjects(*, include_extra: bool = False) -> tuple[BoundaryRef, ...]:
    values = (
        subject("upper-a-old", BoundarySide.UPPER, "110", "111"),
        subject("upper-z-new", BoundarySide.UPPER, "110.5", "111"),
        subject("lower-main", BoundarySide.LOWER, "90", "91"),
        subject(
            "upper-macro", BoundarySide.UPPER, "120", "121",
            timeframe=Timeframe.H12, scale=MACRO,
            source_types=(StructureSourceType.PERIODIC_EXTREME,),
            families=("macro-family",),
        ),
        subject(
            "lower-macro", BoundarySide.LOWER, "80", "81",
            timeframe=Timeframe.H12, scale=MACRO,
            source_types=(StructureSourceType.HISTORICAL_REACTION,),
            families=("macro-lower-family",),
        ),
    )
    if not include_extra:
        return values
    return values + (
        subject(
            "non-config", BoundarySide.UPPER, "130", "131",
            timeframe=Timeframe.M30, scale=EXTRA,
        ),
    )


def lifecycle_config(**overrides: object) -> LifecycleConfig:
    values: dict[str, object] = {
        "engine_id": "c006a-resonance-fixture",
        "engine_version": "1.0.0",
        "policy_id": "fixture-lifecycle-policy",
        "observation_timeframe": Timeframe.H1,
        "test_tolerance": Decimal("0"),
        "break_buffer": Decimal("100"),
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
    subjects: tuple[BoundaryRef, ...] | None = None,
    bars: tuple[CanonicalBar, ...] | None = None,
):
    values = bars or (
        bar(-1),
        bar(0, high="111", low="90", close="101"),
        bar(1, high="111", low="90", close="102"),
    )
    return LifecycleEngine(lifecycle_config()).build_batch(
        LifecycleInput(load_result(values), subjects or base_subjects())
    )


def timeframe_history(history, context: ResonanceContext):
    cfg = TimeframeStateConfig(
        engine_id="c006b-resonance-fixture",
        engine_version="1.0.0",
        policy_id="latest-causal-v1",
        symbol="XAUUSD",
        target_timeframe=context.timeframe,
        target_scale=context.scale,
        selection_policy=TimeframeSelectionPolicy.LATEST_CAUSAL,
        strict=True,
    )
    return TimeframeStateEngine(cfg).build_batch(TimeframeStateInput(history))


def config(
    *, contexts: tuple[ResonanceContext, ...] = (H4_PRIMARY, H12_MACRO),
    **overrides: object,
) -> ResonanceFrameConfig:
    values: dict[str, object] = {
        "engine_id": "c007a-resonance-frame",
        "engine_version": "1.0.0",
        "policy_id": "all-effective-lifecycle-v1",
        "symbol": "XAUUSD",
        "contexts": contexts,
        "reference_price_timeframe": Timeframe.H1,
        "reference_price_field": ReferencePriceField.CLOSE,
        "evidence_policy": ResonanceEvidencePolicy.ALL_EFFECTIVE_LIFECYCLE_STATES,
        "strict": True,
    }
    values.update(overrides)
    return ResonanceFrameConfig(**values)  # type: ignore[arg-type]


def reference_data(*, include_future: bool = True) -> LoadResult:
    bars = (
        bar(-1, close="100", source="reference-fixture"),
        bar(0, high="106", low="96", close="101", source="reference-fixture"),
        bar(1, high="107", low="97", close="102", source="reference-fixture"),
    )
    if include_future:
        bars += (
            bar(2, high="108", low="98", close="103", source="reference-fixture"),
        )
    return load_result(
        bars, config=source_config(source="reference-fixture")
    )


def frame_input(
    *, include_extra: bool = False, reverse_histories: bool = False
) -> ResonanceFrameInput:
    history = lifecycle_history(base_subjects(include_extra=include_extra))
    histories = tuple(
        timeframe_history(history, context)
        for context in (H4_PRIMARY, H12_MACRO)
    )
    if reverse_histories:
        histories = tuple(reversed(histories))
    return ResonanceFrameInput(history, histories, reference_data())


def assembler(**overrides: object) -> ResonanceFrameAssembler:
    return ResonanceFrameAssembler(config(**overrides))


def custom_bundle(
    subjects: tuple[BoundaryRef, ...],
    bars: tuple[CanonicalBar, ...],
    contexts: tuple[ResonanceContext, ...],
    **lifecycle_overrides: object,
) -> tuple[ResonanceFrameAssembler, ResonanceFrameInput]:
    history = LifecycleEngine(lifecycle_config(**lifecycle_overrides)).build_batch(
        LifecycleInput(load_result(bars), subjects)
    )
    histories = tuple(timeframe_history(history, context) for context in contexts)
    return (
        ResonanceFrameAssembler(config(contexts=contexts)),
        ResonanceFrameInput(history, histories, load_result(bars)),
    )
