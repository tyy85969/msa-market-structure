"""Deterministic, without-replacement resonance outcome matching."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from msa.domain import BoundarySide
from msa.research.resonance import ResonanceClass
from msa.validation import ValidationMetricName

from .contracts import (
    MetricFormulaDefinition,
    MetricObservationStatus,
    ResonanceMatchStatus,
    ResonanceOutcomeMatch,
    StructuralMetricConfig,
    StructuralMetricEvent,
    StructuralMetricObservation,
    fact_mapping,
    make_facts,
)
from .errors import MetricMatchingError
from .identity import DECIMAL_PRECISION, digest, semantic_id


def _event_distance(
    event: StructuralMetricEvent,
) -> tuple[Decimal, int] | None:
    facts = fact_mapping(event.facts, error_type=MetricMatchingError)
    raw_distance = facts.get("selection_distance_atr")
    raw_index = facts.get("touch_bar_index")
    if (
        raw_distance in {None, "null"}
        or raw_index in {None, "null"}
        or event.causal_atr is None
        or event.causal_atr <= 0
    ):
        return None
    try:
        distance = Decimal(raw_distance)
        index = int(raw_index)
    except (TypeError, ValueError) as exc:
        raise MetricMatchingError(
            "touch matching facts are invalid"
        ) from exc
    if not distance.is_finite() or distance < 0 or index < 0:
        raise MetricMatchingError(
            "touch distance/index facts are invalid"
        )
    return distance, index


def _match(
    *,
    status: ResonanceMatchStatus,
    treatment: StructuralMetricEvent,
    treatment_distance: Decimal,
    treatment_index: int,
    control: StructuralMetricEvent | None,
    control_distance: Decimal | None,
    control_index: int | None,
    pair_value: Decimal | None,
    config: StructuralMetricConfig,
) -> ResonanceOutcomeMatch:
    if treatment.boundary_side is None:
        raise MetricMatchingError(
            "resonance treatment requires a boundary side"
        )
    gap = (
        None if control_distance is None
        else abs(treatment_distance - control_distance)
    )
    facts = make_facts(
        {
            "matching_policy": (
                "side_then_distance_atr_then_touch_index_then_event_id"
            ),
            "outcome_not_used_for_control_selection": True,
            "reaction_observation_bars": (
                config.reaction_observation_bars
            ),
            "without_replacement": True,
        }
    )
    payload = {
        "status": status.value,
        "treatment_event_id": treatment.metric_event_id,
        "control_event_id": (
            None if control is None else control.metric_event_id
        ),
        "boundary_side": treatment.boundary_side.value,
        "treatment_distance_atr": str(treatment_distance),
        "control_distance_atr": (
            None if control_distance is None else str(control_distance)
        ),
        "distance_atr_gap": None if gap is None else str(gap),
        "treatment_touch_bar_index": treatment_index,
        "control_touch_bar_index": control_index,
        "pair_value": None if pair_value is None else str(pair_value),
        "facts": list(facts),
        "schema_version": 1,
    }
    return ResonanceOutcomeMatch(
        resonance_match_id=semantic_id(
            "resonance-outcome-match-v1-", payload
        ),
        status=status,
        treatment_event_id=treatment.metric_event_id,
        control_event_id=(
            None if control is None else control.metric_event_id
        ),
        boundary_side=treatment.boundary_side,
        treatment_distance_atr=treatment_distance,
        control_distance_atr=control_distance,
        distance_atr_gap=gap,
        treatment_touch_bar_index=treatment_index,
        control_touch_bar_index=control_index,
        pair_value=pair_value,
        facts=facts,
    )


def _pair_observation(
    *,
    formula: MetricFormulaDefinition,
    treatment: StructuralMetricEvent,
    control: StructuralMetricEvent,
    treatment_observation: StructuralMetricObservation,
    control_observation: StructuralMetricObservation,
    match: ResonanceOutcomeMatch,
) -> StructuralMetricObservation:
    if match.pair_value is None:
        raise MetricMatchingError(
            "matched resonance pair requires pair_value"
        )
    observed_bar_ids = tuple(
        dict.fromkeys(
            (
                *treatment_observation.observed_bar_ids,
                *control_observation.observed_bar_ids,
            )
        )
    )
    start = min(
        treatment_observation.observation_start_time,
        control_observation.observation_start_time,
    )
    end = max(
        treatment_observation.observation_end_time,
        control_observation.observation_end_time,
    )
    facts = make_facts(
        {
            "control_event_id": control.metric_event_id,
            "match_id": match.resonance_match_id,
            "observation_window": (
                f"{start.isoformat()}|{end.isoformat()}"
            ),
            "observed_bar_ids_digest": digest(list(observed_bar_ids)),
            "treatment_event_id": treatment.metric_event_id,
        }
    )
    payload = {
        "metric_name": formula.metric_name.value,
        "metric_formula_id": formula.metric_formula_id,
        "metric_event_id": treatment.metric_event_id,
        "status": MetricObservationStatus.MATURED.value,
        "observation_start_time": start.isoformat(),
        "observation_end_time": end.isoformat(),
        "observed_bar_ids": list(observed_bar_ids),
        "value": str(match.pair_value),
        "numerator": str(match.pair_value),
        "denominator": "1",
        "facts": list(facts),
        "schema_version": 1,
    }
    return StructuralMetricObservation(
        metric_observation_id=semantic_id(
            "structural-metric-observation-v1-", payload
        ),
        metric_name=formula.metric_name,
        metric_formula_id=formula.metric_formula_id,
        metric_event_id=treatment.metric_event_id,
        status=MetricObservationStatus.MATURED,
        observation_start_time=start,
        observation_end_time=end,
        observed_bar_ids=observed_bar_ids,
        value=match.pair_value,
        numerator=match.pair_value,
        denominator=Decimal("1"),
        facts=facts,
    )


def match_resonance_outcomes(
    events: tuple[StructuralMetricEvent, ...],
    observations: tuple[StructuralMetricObservation, ...],
    formula: MetricFormulaDefinition,
    config: StructuralMetricConfig,
) -> tuple[
    tuple[ResonanceOutcomeMatch, ...],
    tuple[StructuralMetricObservation, ...],
]:
    """Match controls without replacement before reading outcome values."""

    if formula.metric_name is not ValidationMetricName.RESONANCE_LIFT:
        raise MetricMatchingError(
            "formula must be the frozen RESONANCE_LIFT definition"
        )
    reaction_observations = {
        item.metric_event_id: item
        for item in observations
        if item.metric_name
        is ValidationMetricName.FIRST_TOUCH_REACTION
        and item.status is MetricObservationStatus.MATURED
    }
    touch_events = tuple(
        item
        for item in events
        if item.metric_event_id in reaction_observations
        and item.boundary_side is not None
        and _event_distance(item) is not None
    )
    treatments = tuple(
        sorted(
            (
                item
                for item in touch_events
                if item.zone_class
                == ResonanceClass.MULTI_CONTEXT_RESONANCE.value
            ),
            key=lambda item: (
                item.event_confirm_time,
                item.metric_event_id,
            ),
        )
    )
    controls = tuple(
        item
        for item in touch_events
        if item.zone_class
        in {
            ResonanceClass.SINGLE.value,
            ResonanceClass.LOCAL_CLUSTER.value,
        }
    )
    used_controls: set[str] = set()
    matches: list[ResonanceOutcomeMatch] = []
    pair_observations: list[StructuralMetricObservation] = []
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        for treatment in treatments:
            treatment_facts = _event_distance(treatment)
            if treatment_facts is None:
                continue
            treatment_distance, treatment_index = treatment_facts
            candidates: list[
                tuple[
                    Decimal,
                    int,
                    str,
                    StructuralMetricEvent,
                    Decimal,
                    int,
                ]
            ] = []
            for control in controls:
                if (
                    control.metric_event_id in used_controls
                    or control.boundary_side is not treatment.boundary_side
                ):
                    continue
                control_facts = _event_distance(control)
                if control_facts is None:
                    continue
                control_distance, control_index = control_facts
                gap = abs(treatment_distance - control_distance)
                if gap > config.resonance_match_max_distance_atr:
                    continue
                candidates.append(
                    (
                        gap,
                        abs(treatment_index - control_index),
                        control.metric_event_id,
                        control,
                        control_distance,
                        control_index,
                    )
                )
            candidates.sort(key=lambda item: item[:3])
            if not candidates:
                matches.append(
                    _match(
                        status=ResonanceMatchStatus.NO_ELIGIBLE_CONTROL,
                        treatment=treatment,
                        treatment_distance=treatment_distance,
                        treatment_index=treatment_index,
                        control=None,
                        control_distance=None,
                        control_index=None,
                        pair_value=None,
                        config=config,
                    )
                )
                continue
            _, _, _, control, control_distance, control_index = candidates[0]
            used_controls.add(control.metric_event_id)
            treatment_observation = reaction_observations[
                treatment.metric_event_id
            ]
            control_observation = reaction_observations[
                control.metric_event_id
            ]
            if (
                treatment_observation.value is None
                or control_observation.value is None
            ):
                raise MetricMatchingError(
                    "MATURED reaction observation lacks value"
                )
            pair_value = (
                treatment_observation.value - control_observation.value
            )
            match = _match(
                status=ResonanceMatchStatus.MATCHED,
                treatment=treatment,
                treatment_distance=treatment_distance,
                treatment_index=treatment_index,
                control=control,
                control_distance=control_distance,
                control_index=control_index,
                pair_value=pair_value,
                config=config,
            )
            matches.append(match)
            pair_observations.append(
                _pair_observation(
                    formula=formula,
                    treatment=treatment,
                    control=control,
                    treatment_observation=treatment_observation,
                    control_observation=control_observation,
                    match=match,
                )
            )
    return tuple(matches), tuple(pair_observations)
