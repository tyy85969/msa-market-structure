from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide, MarketRole
from msa.research.resonance import ResonanceClass
from msa.validation import (
    MetricAggregateStatus,
    MetricEventKind,
    ResonanceMatchStatus,
    ValidationMetricName,
    default_metric_formula_registry,
)
from msa.validation.metrics.contracts import make_facts
from msa.validation.metrics.events import _event
from msa.validation.metrics.matching import match_resonance_outcomes
from msa.validation.metrics.observations import (
    _observation,
    build_metric_aggregates,
)
from tests.research.timeframe_state.fixtures import START

from .fixtures import formula, metric_config


def touch_event(
    event_id: str,
    zone_class: ResonanceClass,
    distance: str,
    index: int,
    *,
    side: BoundarySide = BoundarySide.LOWER,
):
    point = START + timedelta(hours=index + 1)
    return _event(
        kind=MetricEventKind.BOUNDARY_FIRST_TOUCH,
        event_confirm_time=point,
        first_observed_as_of_time=point,
        symbol="XAUUSD",
        reference_timeframe="H1",
        source_object_ids=(event_id, f"bar-{index}"),
        boundary_side=side,
        market_role=(
            MarketRole.SUPPORT
            if side is BoundarySide.LOWER
            else MarketRole.RESISTANCE
        ),
        box_key_id=f"box-{event_id}",
        zone_key=f"zone-{event_id}",
        zone_snapshot_id=f"snapshot-{event_id}",
        zone_class=zone_class.value,
        anchor_price=Decimal("100"),
        causal_atr=Decimal("10"),
        facts=make_facts(
            {
                "active_box_created_event_id": f"created-{event_id}",
                "box_created_time": START,
                "creation_causal_atr": Decimal("10"),
                "selection_distance": Decimal(distance) * Decimal("10"),
                "selection_distance_atr": Decimal(distance),
                "touch_bar_id": f"bar-{index}",
                "touch_bar_index": index,
                "zone_context_count": 2,
                "zone_quality_score": Decimal("2"),
                "zone_selection_score": Decimal("1"),
                "zone_source_type_count": 1,
            }
        ),
    )


def reaction(event, value: str):
    item = Decimal(value)
    return _observation(
        formula=formula(ValidationMetricName.FIRST_TOUCH_REACTION),
        event=event,
        status=__import__(
            "msa.validation", fromlist=["MetricObservationStatus"]
        ).MetricObservationStatus.MATURED,
        start=event.event_confirm_time,
        end=event.event_confirm_time,
        bars=(),
        value=item,
        numerator=item,
        denominator=Decimal("1"),
        facts={"fixture": "explicit_reaction"},
    )


def test_known_matched_pair_lift_and_no_outcome_sorting() -> None:
    treatment = touch_event(
        "treatment", ResonanceClass.MULTI_CONTEXT_RESONANCE, "1", 1
    )
    control = touch_event("control", ResonanceClass.SINGLE, "1.25", 4)
    events = (treatment, control)
    observations = (reaction(treatment, "2"), reaction(control, "0.5"))
    matches, pairs = match_resonance_outcomes(
        events,
        observations,
        formula(ValidationMetricName.RESONANCE_LIFT),
        metric_config(),
    )
    assert len(matches) == len(pairs) == 1
    assert matches[0].status is ResonanceMatchStatus.MATCHED
    assert matches[0].pair_value == Decimal("1.5")
    assert pairs[0].value == Decimal("1.5")


def test_cross_side_control_is_not_matched() -> None:
    treatment = touch_event(
        "treatment", ResonanceClass.MULTI_CONTEXT_RESONANCE, "1", 1
    )
    control = touch_event(
        "control",
        ResonanceClass.LOCAL_CLUSTER,
        "1",
        2,
        side=BoundarySide.UPPER,
    )
    matches, pairs = match_resonance_outcomes(
        (treatment, control),
        (reaction(treatment, "2"), reaction(control, "9")),
        formula(ValidationMetricName.RESONANCE_LIFT),
        metric_config(),
    )
    assert matches[0].status is ResonanceMatchStatus.NO_ELIGIBLE_CONTROL
    assert not pairs


def test_control_is_not_reused() -> None:
    treatments = (
        touch_event(
            "treatment-a",
            ResonanceClass.MULTI_CONTEXT_RESONANCE,
            "1",
            1,
        ),
        touch_event(
            "treatment-b",
            ResonanceClass.MULTI_CONTEXT_RESONANCE,
            "1.1",
            2,
        ),
    )
    control = touch_event("control", ResonanceClass.SINGLE, "1", 3)
    events = (*treatments, control)
    observations = tuple(reaction(item, "2") for item in treatments) + (
        reaction(control, "1"),
    )
    matches, pairs = match_resonance_outcomes(
        events,
        observations,
        formula(ValidationMetricName.RESONANCE_LIFT),
        metric_config(),
    )
    assert sum(
        item.status is ResonanceMatchStatus.MATCHED for item in matches
    ) == 1
    assert len(pairs) == 1


def test_insufficient_pair_count_returns_none() -> None:
    aggregates = build_metric_aggregates(
        default_metric_formula_registry(), (), metric_config()
    )
    lift = aggregates[-1]
    assert lift.status is MetricAggregateStatus.INSUFFICIENT_SAMPLE
    assert lift.value is None
