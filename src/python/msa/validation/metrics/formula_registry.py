"""Frozen C-008B formulas bound to the authoritative C-008A registry."""

from __future__ import annotations

from msa.validation import ValidationMetricName, default_metric_registry

from .contracts import (
    FORMULA_STATUS_FROZEN,
    MetricEventKind,
    MetricFormulaDefinition,
)
from .identity import semantic_id


def _formula(
    *,
    definition_id: str,
    metric_name: ValidationMetricName,
    event_kind: MetricEventKind,
    expression: str,
    aggregation: str,
    censoring: str,
    required_fields: tuple[str, ...],
    parameters: tuple[str, ...] = (),
) -> MetricFormulaDefinition:
    payload = {
        "metric_definition_id": definition_id,
        "metric_name": metric_name.value,
        "formula_version": "C008B_V1",
        "formula_status": FORMULA_STATUS_FROZEN,
        "event_kind": event_kind.value,
        "formula_expression": expression,
        "aggregation_rule": aggregation,
        "censoring_rule": censoring,
        "required_fields": list(required_fields),
        "parameters": list(parameters),
        "schema_version": 1,
    }
    return MetricFormulaDefinition(
        metric_formula_id=semantic_id(
            "structural-metric-formula-v1-", payload
        ),
        metric_definition_id=definition_id,
        metric_name=metric_name,
        formula_version="C008B_V1",
        formula_status=FORMULA_STATUS_FROZEN,
        event_kind=event_kind,
        formula_expression=expression,
        aggregation_rule=aggregation,
        censoring_rule=censoring,
        required_fields=required_fields,
        parameters=parameters,
    )


def default_metric_formula_registry() -> tuple[
    MetricFormulaDefinition, ...
]:
    """Return the exact ten frozen formulas in C-008A registry order."""

    definitions = default_metric_registry()
    by_name = {item.name: item for item in definitions}
    formulas = {
        ValidationMetricName.CONFIRMATION_DELAY_BARS: _formula(
            definition_id=by_name[
                ValidationMetricName.CONFIRMATION_DELAY_BARS
            ].metric_definition_id,
            metric_name=ValidationMetricName.CONFIRMATION_DELAY_BARS,
            event_kind=MetricEventKind.STRUCTURE_CONFIRMATION,
            expression=(
                "count(reference_bar where origin_time < "
                "bar.available_time <= confirm_time)"
            ),
            aggregation="ARITHMETIC_MEAN_MATURED",
            censoring=(
                "UNAVAILABLE_INPUT when OriginTime predates reference "
                "bar history coverage"
            ),
            required_fields=(
                "origin_time",
                "event_confirm_time",
                "reference_bar.available_time",
            ),
        ),
        ValidationMetricName.CONFIRMATION_DELAY_ATR: _formula(
            definition_id=by_name[
                ValidationMetricName.CONFIRMATION_DELAY_ATR
            ].metric_definition_id,
            metric_name=ValidationMetricName.CONFIRMATION_DELAY_ATR,
            event_kind=MetricEventKind.STRUCTURE_CONFIRMATION,
            expression=(
                "abs(confirm_close - boundary_midpoint) / "
                "causal_atr_at_confirm"
            ),
            aggregation="ARITHMETIC_MEAN_MATURED",
            censoring="UNAVAILABLE_INPUT when anchor or causal ATR is absent",
            required_fields=(
                "boundary_midpoint",
                "confirm_close",
                "causal_atr_at_confirm",
            ),
            parameters=("atr_period",),
        ),
        ValidationMetricName.FALSE_TURN_RATE: _formula(
            definition_id=by_name[
                ValidationMetricName.FALSE_TURN_RATE
            ].metric_definition_id,
            metric_name=ValidationMetricName.FALSE_TURN_RATE,
            event_kind=MetricEventKind.TURN_CANDIDATE,
            expression=(
                "prior_direction_resumed_count / resolved_turn_count"
            ),
            aggregation="RATIO_SUM_MATURED",
            censoring=(
                "CENSORED_RIGHT when the causal bar window is incomplete "
                "or no stable direction resolves"
            ),
            required_fields=(
                "prior_stable_direction",
                "first_subsequent_stable_direction",
            ),
            parameters=("turn_resolution_bars",),
        ),
        ValidationMetricName.CONTINUED_BREAK_RATE: _formula(
            definition_id=by_name[
                ValidationMetricName.CONTINUED_BREAK_RATE
            ].metric_definition_id,
            metric_name=ValidationMetricName.CONTINUED_BREAK_RATE,
            event_kind=MetricEventKind.BREAK_CONFIRMATION,
            expression=(
                "continued_break_count / matured_break_count; "
                "continued iff favorable_continuation >= "
                "break_continuation_atr * causal_atr_at_break"
            ),
            aggregation="RATIO_SUM_MATURED",
            censoring=(
                "CENSORED_RIGHT when the post-confirmation bar window "
                "is incomplete"
            ),
            required_fields=(
                "boundary_envelope",
                "post_confirm_bars",
                "causal_atr_at_break",
            ),
            parameters=(
                "break_observation_bars",
                "break_continuation_atr",
            ),
        ),
        ValidationMetricName.TREND_CAPTURE_RATIO: _formula(
            definition_id=by_name[
                ValidationMetricName.TREND_CAPTURE_RATIO
            ].metric_definition_id,
            metric_name=ValidationMetricName.TREND_CAPTURE_RATIO,
            event_kind=MetricEventKind.DIRECTION_EPISODE,
            expression=(
                "clamp(remaining_opportunity, 0, full_opportunity) / "
                "full_opportunity"
            ),
            aggregation="ARITHMETIC_MEAN_MATURED",
            censoring=(
                "CENSORED_RIGHT until an opposite stable direction or "
                "the configured bar horizon is observable"
            ),
            required_fields=(
                "direction",
                "origin_close",
                "confirm_close",
                "terminal_extreme",
            ),
            parameters=("trend_capture_bars",),
        ),
        ValidationMetricName.MFE: _formula(
            definition_id=by_name[
                ValidationMetricName.MFE
            ].metric_definition_id,
            metric_name=ValidationMetricName.MFE,
            event_kind=MetricEventKind.BOUNDARY_FIRST_TOUCH,
            expression=(
                "support: max(future_high)-touch_anchor; "
                "resistance: touch_anchor-min(future_low); floor at 0"
            ),
            aggregation="ARITHMETIC_MEAN_MATURED",
            censoring=(
                "CENSORED_RIGHT until the complete post-touch window exists"
            ),
            required_fields=(
                "boundary_side",
                "touch_anchor",
                "post_touch_bars",
            ),
            parameters=("reaction_observation_bars",),
        ),
        ValidationMetricName.MAE: _formula(
            definition_id=by_name[
                ValidationMetricName.MAE
            ].metric_definition_id,
            metric_name=ValidationMetricName.MAE,
            event_kind=MetricEventKind.BOUNDARY_FIRST_TOUCH,
            expression=(
                "support: touch_anchor-min(future_low); "
                "resistance: max(future_high)-touch_anchor; floor at 0"
            ),
            aggregation="ARITHMETIC_MEAN_MATURED",
            censoring=(
                "CENSORED_RIGHT until the complete post-touch window exists"
            ),
            required_fields=(
                "boundary_side",
                "touch_anchor",
                "post_touch_bars",
            ),
            parameters=("reaction_observation_bars",),
        ),
        ValidationMetricName.BOX_CHURN: _formula(
            definition_id=by_name[
                ValidationMetricName.BOX_CHURN
            ].metric_definition_id,
            metric_name=ValidationMetricName.BOX_CHURN,
            event_kind=MetricEventKind.BOX_EPISODE_CREATED,
            expression="max(created_episode_count - 1, 0)",
            aggregation="SUM_MATURED",
            censoring="Box creation events are immediate and not right-censored",
            required_fields=("unique_box_key_id", "created_event_order"),
        ),
        ValidationMetricName.FIRST_TOUCH_REACTION: _formula(
            definition_id=by_name[
                ValidationMetricName.FIRST_TOUCH_REACTION
            ].metric_definition_id,
            metric_name=ValidationMetricName.FIRST_TOUCH_REACTION,
            event_kind=MetricEventKind.BOUNDARY_FIRST_TOUCH,
            expression="(MFE - MAE) / causal_atr_at_touch",
            aggregation="ARITHMETIC_MEAN_MATURED",
            censoring=(
                "CENSORED_RIGHT for an incomplete window; "
                "UNAVAILABLE_INPUT when causal ATR is absent"
            ),
            required_fields=("mfe", "mae", "causal_atr_at_touch"),
            parameters=("reaction_observation_bars", "atr_period"),
        ),
        ValidationMetricName.RESONANCE_LIFT: _formula(
            definition_id=by_name[
                ValidationMetricName.RESONANCE_LIFT
            ].metric_definition_id,
            metric_name=ValidationMetricName.RESONANCE_LIFT,
            event_kind=MetricEventKind.BOUNDARY_FIRST_TOUCH,
            expression=(
                "mean(treatment_first_touch_reaction - "
                "matched_control_first_touch_reaction)"
            ),
            aggregation="ARITHMETIC_MEAN_MATCHED_PAIRS",
            censoring=(
                "INSUFFICIENT_SAMPLE when matched pair count is below "
                "resonance_min_pair_count"
            ),
            required_fields=(
                "zone_class",
                "boundary_side",
                "selection_distance_atr",
                "touch_bar_index",
                "first_touch_reaction",
            ),
            parameters=(
                "reaction_observation_bars",
                "resonance_match_max_distance_atr",
                "resonance_min_pair_count",
            ),
        ),
    }
    ordered = tuple(formulas[item.name] for item in definitions)
    if tuple(item.metric_definition_id for item in ordered) != tuple(
        item.metric_definition_id for item in definitions
    ):
        raise RuntimeError(
            "C-008B formula registry lost C-008A definition authority"
        )
    return ordered
