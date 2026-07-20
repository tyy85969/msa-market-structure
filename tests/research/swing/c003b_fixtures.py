from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from msa.data import CanonicalBar, Timeframe, VolumeType
from msa.research.swing import (
    AtrReversalDetector,
    AtrReversalDetectorConfig,
    AtrStructureBreakDetector,
    AtrStructureBreakDetectorConfig,
    BreakBasis,
    PendingReplacementPolicy,
    StructureBreakDetector,
    StructureBreakDetectorConfig,
)
from tests.research.swing.fixtures import SCALE, START, pivot_config


def ohlc_bar(
    index: int,
    *,
    open: Decimal | str,
    high: Decimal | str,
    low: Decimal | str,
    close: Decimal | str,
    timestamp: datetime | None = None,
    available_time: datetime | None = None,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.H1,
    source: str = "synthetic-feed",
    is_complete: bool = True,
) -> CanonicalBar:
    start = timestamp or START + index * timedelta(hours=1)
    duration = timeframe.fixed_duration
    if duration is None:
        raise AssertionError("C-003B fixtures use fixed-duration bars")
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
        boundary_policy=None,
        is_complete=is_complete,
        available_time=available_time or end,
    )


def atr_config(**overrides: object) -> AtrReversalDetectorConfig:
    values: dict[str, object] = {
        "detector_id": "atr-turn",
        "detector_version": "1.0.0",
        "atr_period": 1,
        "reversal_multiplier": Decimal("1"),
        "scale": SCALE,
        "policy_id": "atr-sma-turn-v1",
        "strict": True,
    }
    values.update(overrides)
    return AtrReversalDetectorConfig(**values)  # type: ignore[arg-type]


def atr_detector(**overrides: object) -> AtrReversalDetector:
    return AtrReversalDetector(atr_config(**overrides))


def structure_config(**overrides: object) -> StructureBreakDetectorConfig:
    values: dict[str, object] = {
        "detector_id": "pivot-structure-confirm",
        "detector_version": "1.0.0",
        "seed_pivot_config": pivot_config(left_bars=1, right_bars=1),
        "break_buffer": Decimal("0"),
        "break_basis": BreakBasis.CLOSE,
        "pending_replacement_policy": (
            PendingReplacementPolicy.LATEST_CONFIRMED
        ),
        "policy_id": "pivot-structure-close-v1",
        "strict": True,
    }
    values.update(overrides)
    return StructureBreakDetectorConfig(**values)  # type: ignore[arg-type]


def structure_detector(**overrides: object) -> StructureBreakDetector:
    return StructureBreakDetector(structure_config(**overrides))


def combined_config(**overrides: object) -> AtrStructureBreakDetectorConfig:
    values: dict[str, object] = {
        "detector_id": "atr-structure-confirm",
        "detector_version": "1.0.0",
        "seed_atr_config": atr_config(),
        "break_buffer": Decimal("0"),
        "break_basis": BreakBasis.CLOSE,
        "pending_replacement_policy": (
            PendingReplacementPolicy.LATEST_CONFIRMED
        ),
        "policy_id": "atr-structure-close-v1",
        "strict": True,
    }
    values.update(overrides)
    return AtrStructureBreakDetectorConfig(**values)  # type: ignore[arg-type]


def combined_detector(**overrides: object) -> AtrStructureBreakDetector:
    return AtrStructureBreakDetector(combined_config(**overrides))


def atr_turn_bars() -> tuple[CanonicalBar, ...]:
    return (
        ohlc_bar(0, open="10", high="11", low="9", close="10"),
        ohlc_bar(1, open="9", high="10", low="8", close="9"),
        ohlc_bar(2, open="11", high="12", low="9", close="11"),
        ohlc_bar(3, open="13", high="15", low="12", close="14"),
        ohlc_bar(4, open="11", high="13", low="9", close="10"),
    )


def atr_combination_bars(*, break_close: str = "7") -> tuple[CanonicalBar, ...]:
    return atr_turn_bars() + (
        ohlc_bar(5, open="8", high="10", low="6", close=break_close),
    )


def pivot_upper_break_bars(*, break_close: str = "4") -> tuple[CanonicalBar, ...]:
    return (
        ohlc_bar(0, open="11", high="12", low="10", close="11"),
        ohlc_bar(1, open="7", high="11", low="5", close="7"),
        ohlc_bar(2, open="10", high="13", low="8", close="10"),
        ohlc_bar(3, open="16", high="20", low="9", close="16"),
        ohlc_bar(4, open="11", high="14", low="7", close="11"),
        ohlc_bar(5, open="8", high="10", low="4", close=break_close),
    )


def pivot_lower_break_bars(*, break_close: str = "21") -> tuple[CanonicalBar, ...]:
    return (
        ohlc_bar(0, open="9", high="10", low="8", close="9"),
        ohlc_bar(1, open="16", high="20", low="12", close="16"),
        ohlc_bar(2, open="12", high="15", low="9", close="12"),
        ohlc_bar(3, open="8", high="14", low="4", close="8"),
        ohlc_bar(4, open="12", high="18", low="8", close="12"),
        ohlc_bar(5, open="18", high="22", low="15", close=break_close),
    )


def pivot_replacement_bars() -> tuple[CanonicalBar, ...]:
    return (
        ohlc_bar(0, open="11", high="12", low="10", close="11"),
        ohlc_bar(1, open="7", high="11", low="5", close="7"),
        ohlc_bar(2, open="10", high="13", low="8", close="10"),
        ohlc_bar(3, open="16", high="20", low="9", close="16"),
        ohlc_bar(4, open="12", high="14", low="8", close="12"),
        ohlc_bar(5, open="18", high="22", low="9", close="18"),
        ohlc_bar(6, open="12", high="15", low="8", close="12"),
        ohlc_bar(7, open="7", high="10", low="4", close="4"),
    )
