from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from msa.data import (
    CanonicalBar, CompletedBarPolicy, LoadResult, SourceDataConfig,
    Timeframe, TimestampSemantics, VolumeType, validate_bar_sequence,
)
from msa.domain import (
    BoundaryRef, BoundarySide, LifecycleState, MarketRole, PriceRange,
    ProvenanceRef, ScaleDescriptor, StructureObjectKind, StructureSourceType,
)
from msa.research.lifecycle import LifecycleConfig, LifecycleEngine, LifecycleInput


UTC = timezone.utc
START = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
T1 = START + timedelta(hours=1)
T2 = START + timedelta(hours=2)
T3 = START + timedelta(hours=3)
T4 = START + timedelta(hours=4)
T5 = START + timedelta(hours=5)


def bar(index: int, *, open: str = "95", high: str = "98", low: str = "94",
        close: str = "96", available_time: datetime | None = None,
        is_complete: bool = True, symbol: str = "XAUUSD") -> CanonicalBar:
    timestamp = START + timedelta(hours=index)
    end = timestamp + timedelta(hours=1)
    return CanonicalBar(
        symbol=symbol, timeframe=Timeframe.H1, timestamp=timestamp, end_time=end,
        open=Decimal(open), high=Decimal(high), low=Decimal(low), close=Decimal(close),
        volume=None, volume_type=VolumeType.UNAVAILABLE, source="fixture-feed",
        source_timezone="UTC", session_id="fixture-session", boundary_policy=None,
        is_complete=is_complete, available_time=available_time or end,
    )


def source_config(**overrides: object) -> SourceDataConfig:
    values: dict[str, object] = {
        "source": "fixture-feed", "source_timezone": "UTC",
        "source_symbol": "GOLD", "canonical_symbol": "XAUUSD",
        "timeframe": Timeframe.H1, "timestamp_column": "time",
        "timestamp_semantics": TimestampSemantics.OPEN_TIME,
        "timestamp_format": "%Y-%m-%dT%H:%M:%S%z", "open_column": "open",
        "high_column": "high", "low_column": "low", "close_column": "close",
        "volume_column": None, "volume_type": VolumeType.UNAVAILABLE,
        "completed_bar_policy": CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        "availability_lag": timedelta(0), "session_id": "fixture-session",
        "boundary_policy": None, "end_time_column": None, "strict": True,
    }
    values.update(overrides)
    return SourceDataConfig(**values)  # type: ignore[arg-type]


def load_result(bars: tuple[CanonicalBar, ...], *, config: SourceDataConfig | None = None) -> LoadResult:
    cfg = config or source_config()
    report = validate_bar_sequence(bars, source=cfg.source, timeframe=cfg.timeframe)
    return LoadResult(bars, report, cfg, len(bars), len(bars), 0)


def subject(subject_id: str = "upper", *, side: BoundarySide = BoundarySide.UPPER,
            kind: StructureObjectKind = StructureObjectKind.LEVEL_CANDIDATE,
            confirm_time: datetime = T1, symbol: str = "XAUUSD",
            lifecycle_state: LifecycleState = LifecycleState.CONFIRMED,
            role: MarketRole | None = None) -> BoundaryRef:
    price_range = PriceRange(Decimal("100"), Decimal("101")) if side is BoundarySide.UPPER else PriceRange(Decimal("90"), Decimal("91"))
    market_role = role or (MarketRole.RESISTANCE if side is BoundarySide.UPPER else MarketRole.SUPPORT)
    return BoundaryRef(
        object_kind=kind, object_id=subject_id, symbol=symbol, timeframe=Timeframe.H4,
        scale=ScaleDescriptor("subject-scale", 2), price_range=price_range,
        boundary_side=side, market_role=market_role, lifecycle_state=lifecycle_state,
        origin_time=START - timedelta(days=2), confirm_time=confirm_time,
        source_types=(StructureSourceType.SWING,), structure_families=("fixture-structure",),
        provenance=ProvenanceRef("tests.lifecycle", "1", f"source-{subject_id}",
                                 "fixture-policy", (), ("fixture subject",)),
    )


def config(**overrides: object) -> LifecycleConfig:
    values: dict[str, object] = {
        "engine_id": "c006a-lifecycle", "engine_version": "1.0.0",
        "policy_id": "causal-close-baseline-v1", "observation_timeframe": Timeframe.H1,
        "test_tolerance": Decimal("1"), "break_buffer": Decimal("1"),
        "weakening_test_count": 2, "minimum_test_separation_bars": 1,
        "flip_tolerance": Decimal("1"), "flip_confirmation_distance": Decimal("1"),
        "flip_horizon_bars": 3, "failed_break_retirement_buffer": Decimal("1"),
        "strict": True,
    }
    values.update(overrides)
    return LifecycleConfig(**values)  # type: ignore[arg-type]


def engine(**overrides: object) -> LifecycleEngine:
    return LifecycleEngine(config(**overrides))


def lifecycle_input(bars: tuple[CanonicalBar, ...], subjects: tuple[BoundaryRef, ...] | None = None) -> LifecycleInput:
    return LifecycleInput(load_result(bars), subjects or (subject(),))


def upper_break_bars() -> tuple[CanonicalBar, ...]:
    return (
        bar(0),
        bar(1, open="100", high="104", low="100", close="102"),
        bar(2, open="102", high="103", low="100", close="101"),
        bar(3, open="102", high="104", low="102", close="103"),
    )
