from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide, Direction, MarketRole
from msa.validation import (
    BreakResolution,
    MetricEventKind,
    MetricObservationStatus,
    TurnResolution,
    ValidationMetricName,
)
from msa.validation.metrics.events import _event
from msa.validation.metrics.observations import _continued_break, _false_turn
from tests.research.timeframe_state.fixtures import START, bar

from .fixtures import (
    direction_report,
    direction_run,
    formula,
    metric_config,
)


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


def _turn_boundary_observation(
    *,
    stable_confirm_time,
    cutoff=None,
    stable_direction: Direction = Direction.DOWN,
    include_n_plus_one_bar: bool = False,
):
    run = deepcopy(direction_run())
    report = direction_report()
    event = next(
        item
        for item in report.events
        if item.kind is MetricEventKind.TURN_CANDIDATE
    )
    history = run.source_input.timeframe_state_histories[0]
    state = history.snapshots[-1].state
    object.__setattr__(state, "confirm_time", stable_confirm_time)
    object.__setattr__(state, "direction", stable_direction)
    bars = run.source_input.reference_price_data.bars
    if include_n_plus_one_bar:
        bars = (*bars, bar(4, high="102", low="79", close="91"))
    return _false_turn(
        formula(ValidationMetricName.FALSE_TURN_RATE),
        event,
        run,
        metric_config(turn_resolution_bars=1),
        bars,
        cutoff or bars[-1].available_time,
    )


def test_turn_stable_confirm_time_equal_window_end_is_matured() -> None:
    run = direction_run()
    window_end = run.source_input.reference_price_data.bars[-1].available_time
    observation = _turn_boundary_observation(
        stable_confirm_time=window_end
    )
    assert observation.status is MetricObservationStatus.MATURED
    assert observation.observation_end_time == window_end


def test_turn_stable_confirm_time_n_plus_one_microsecond_is_not_resolved() -> None:
    run = direction_run()
    window_end = run.source_input.reference_price_data.bars[-1].available_time
    observation = _turn_boundary_observation(
        stable_confirm_time=window_end + timedelta(microseconds=1),
        cutoff=window_end + timedelta(hours=1),
        include_n_plus_one_bar=True,
    )
    assert observation.status is MetricObservationStatus.CENSORED_RIGHT
    assert observation.observation_end_time == window_end


def test_turn_stable_state_between_n_and_n_plus_one_bar_is_not_resolved() -> None:
    run = direction_run()
    window_end = run.source_input.reference_price_data.bars[-1].available_time
    observation = _turn_boundary_observation(
        stable_confirm_time=window_end + timedelta(minutes=30),
        cutoff=window_end + timedelta(hours=1),
        include_n_plus_one_bar=True,
    )
    assert observation.status is MetricObservationStatus.CENSORED_RIGHT
    assert observation.observation_end_time == window_end


def test_turn_unfinished_nth_bar_is_right_censored() -> None:
    run = direction_run()
    window_end = run.source_input.reference_price_data.bars[-1].available_time
    observation = _turn_boundary_observation(
        stable_confirm_time=window_end,
        cutoff=window_end - timedelta(microseconds=1),
    )
    assert observation.status is MetricObservationStatus.CENSORED_RIGHT
    assert "reason=turn_resolution_window_incomplete" in observation.facts


def test_turn_complete_window_without_stable_direction_is_right_censored() -> None:
    run = direction_run()
    window_end = run.source_input.reference_price_data.bars[-1].available_time
    observation = _turn_boundary_observation(
        stable_confirm_time=window_end,
        stable_direction=Direction.RANGE,
    )
    assert observation.status is MetricObservationStatus.CENSORED_RIGHT
    assert observation.observation_end_time == window_end


def test_turn_stable_direction_after_window_does_not_rewrite_old_cutoff() -> None:
    run = direction_run()
    window_end = run.source_input.reference_price_data.bars[-1].available_time
    old = _turn_boundary_observation(
        stable_confirm_time=window_end + timedelta(minutes=30),
        cutoff=window_end,
    )
    appended = _turn_boundary_observation(
        stable_confirm_time=window_end + timedelta(minutes=30),
        cutoff=window_end + timedelta(hours=1),
        include_n_plus_one_bar=True,
    )
    assert old.to_dict() == appended.to_dict()


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
