"""Authoritative reference-bar validation and causal Wilder ATR."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from msa.data import CanonicalBar
from msa.research.msa_core import MSACoreRun

from .contracts import StructuralMetricConfig
from .errors import MetricInputError
from .identity import (
    DECIMAL_PRECISION,
    decimal_mean,
    decimal_wilder,
    semantic_id,
)


def canonical_bar_id(bar: CanonicalBar) -> str:
    if not isinstance(bar, CanonicalBar):
        raise MetricInputError("bar must be a CanonicalBar")
    return semantic_id("canonical-reference-bar-v1-", bar.to_dict())


def validate_reference_bars(
    run: MSACoreRun,
) -> tuple[CanonicalBar, ...]:
    """Validate bars exactly as supplied; never sort, fill, or repair."""

    if not isinstance(run, MSACoreRun):
        raise MetricInputError("run must be an MSACoreRun")
    source = run.source_input.reference_price_data
    bars = source.bars
    if not isinstance(bars, tuple) or not bars:
        raise MetricInputError(
            "run reference_price_data.bars must be a non-empty tuple"
        )
    if source.quality_report.has_errors:
        raise MetricInputError("reference bar quality report contains errors")
    symbol = run.config_snapshot.frame_config.symbol
    timeframe = run.config_snapshot.frame_config.reference_price_timeframe
    if (
        source.source_config.canonical_symbol != symbol
        or source.source_config.timeframe is not timeframe
    ):
        raise MetricInputError(
            "reference source config conflicts with the Run"
        )
    identities: list[str] = []
    previous: CanonicalBar | None = None
    for bar in bars:
        if not isinstance(bar, CanonicalBar):
            raise MetricInputError(
                "reference bars must contain CanonicalBar"
            )
        if (
            bar.symbol != symbol
            or bar.timeframe is not timeframe
            or not bar.is_complete
        ):
            raise MetricInputError(
                "reference bar symbol/timeframe/completion conflicts with Run"
            )
        if previous is not None and (
            bar.timestamp <= previous.timestamp
            or bar.available_time <= previous.available_time
        ):
            raise MetricInputError(
                "reference bars must remain in strict formal order"
            )
        identities.append(canonical_bar_id(bar))
        previous = bar
    if len(set(identities)) != len(identities):
        raise MetricInputError("reference bar identities must be unique")
    return bars


def visible_reference_bars(
    bars: tuple[CanonicalBar, ...], cutoff: datetime
) -> tuple[CanonicalBar, ...]:
    if not isinstance(bars, tuple) or any(
        not isinstance(item, CanonicalBar) for item in bars
    ):
        raise MetricInputError("bars must be a CanonicalBar tuple")
    if (
        not isinstance(cutoff, datetime)
        or cutoff.tzinfo is None
        or cutoff.utcoffset() is None
    ):
        raise MetricInputError("cutoff must be an aware datetime")
    return tuple(item for item in bars if item.available_time <= cutoff)


def true_ranges(
    bars: tuple[CanonicalBar, ...],
) -> tuple[Decimal, ...]:
    if not isinstance(bars, tuple) or any(
        not isinstance(item, CanonicalBar) for item in bars
    ):
        raise MetricInputError("bars must be a CanonicalBar tuple")
    if not bars:
        return ()
    values: list[Decimal] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        previous_close: Decimal | None = None
        for bar in bars:
            if previous_close is None:
                value = +(bar.high - bar.low)
            else:
                value = +max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )
            values.append(value)
            previous_close = bar.close
    return tuple(values)


def causal_wilder_atr(
    bars: tuple[CanonicalBar, ...], period: int
) -> tuple[Decimal | None, ...]:
    """Return an ATR aligned to each bar without partial-period values."""

    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise MetricInputError("period must be a positive integer")
    ranges = true_ranges(bars)
    result: list[Decimal | None] = [None] * len(ranges)
    if len(ranges) < period:
        return tuple(result)
    first = decimal_mean(ranges[:period])
    result[period - 1] = first
    previous = first
    for index in range(period, len(ranges)):
        previous = decimal_wilder(previous, ranges[index], period)
        result[index] = previous
    return tuple(result)


def causal_atr_at_or_before(
    bars: tuple[CanonicalBar, ...],
    config: StructuralMetricConfig,
    event_confirm_time: datetime,
) -> Decimal | None:
    visible = tuple(
        item
        for item in bars
        if item.available_time <= event_confirm_time
    )
    if len(visible) < config.atr_period:
        return None
    return causal_wilder_atr(visible, config.atr_period)[-1]


def last_bar_at_or_before(
    bars: tuple[CanonicalBar, ...], point: datetime
) -> CanonicalBar | None:
    selected: CanonicalBar | None = None
    for bar in bars:
        if bar.available_time > point:
            break
        selected = bar
    return selected


def bars_after(
    bars: tuple[CanonicalBar, ...],
    point: datetime,
    cutoff: datetime,
) -> tuple[CanonicalBar, ...]:
    return tuple(
        item
        for item in bars
        if point < item.available_time <= cutoff
    )
