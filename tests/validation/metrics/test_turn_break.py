from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide, MarketRole
from msa.validation import (
    BreakResolution,
    MetricEventKind,
    MetricObservationStatus,
    TurnResolution,
    ValidationMetricName,
)
from msa.validation.metrics.events import _event
from msa.validation.metrics.observations import _continued_break
from tests.research.timeframe_state.fixtures import START, bar

from .fixtures import direction_report, formula, metric_config


def test_turn_opposite_is_resolved_zero() -> None:
    observation = next(
        item
        for item in direction_report().observations
        if item.metric_name is ValidationMetricName.FALSE_TURN_RATE
    )
    facts = dict(item.split("=", 1) for item in observation.facts)
    assert observation.status is MetricObservationStatus.MATURED
    assert observation.value == Decimal("0")
    assert facts["resolution"] == TurnResolution.OPPOSITE_CONFIRMED.value


def break_event(side: BoundarySide):
    return _event(
        kind=MetricEventKind.BREAK_CONFIRMATION,
        event_confirm_time=START + timedelta(hours=1),
        first_observed_as_of_time=START + timedelta(hours=1),
        symbol="XAUUSD",
        reference_timeframe="H1",
        source_object_ids=(f"{side.value}-break",),
        boundary_side=side,
        market_role=(
            MarketRole.RESISTANCE
            if side is BoundarySide.UPPER
            else MarketRole.SUPPORT
        ),
        context_key=f"context-{side.value}",
        anchor_price=(
            Decimal("111")
            if side is BoundarySide.UPPER
            else Decimal("90")
        ),
        causal_atr=Decimal("10"),
        facts=(
            "boundary_high=111",
            "boundary_low=90",
            f"lifecycle_break_event_id={side.value}-break",
            f"origin_time={START.isoformat()}",
        ),
    )


def test_upper_break_continues_and_lower_break_does_not() -> None:
    bars = (
        bar(0, high="111", low="90", close="100"),
        bar(1, high="122", low="86", close="100"),
    )
    config = metric_config(break_continuation_atr=Decimal("1"))
    upper = _continued_break(
        formula(ValidationMetricName.CONTINUED_BREAK_RATE),
        break_event(BoundarySide.UPPER),
        config,
        bars,
        bars[-1].available_time,
    )
    lower = _continued_break(
        formula(ValidationMetricName.CONTINUED_BREAK_RATE),
        break_event(BoundarySide.LOWER),
        config,
        bars,
        bars[-1].available_time,
    )
    assert upper.value == Decimal("1")
    assert lower.value == Decimal("0")
    assert "resolution=CONTINUED" in upper.facts
    assert (
        f"resolution={BreakResolution.NOT_CONTINUED.value}"
        in lower.facts
    )


def test_incomplete_break_window_is_right_censored() -> None:
    event = break_event(BoundarySide.UPPER)
    value = _continued_break(
        formula(ValidationMetricName.CONTINUED_BREAK_RATE),
        event,
        metric_config(break_observation_bars=2),
        (bar(0), bar(1)),
        bar(1).available_time,
    )
    assert value.status is MetricObservationStatus.CENSORED_RIGHT
    assert value.value is None
