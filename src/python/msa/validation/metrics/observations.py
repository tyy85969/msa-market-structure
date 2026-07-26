"""Causal observation windows and aggregate construction for C-008B."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from msa.data import CanonicalBar
from msa.domain import BoundarySide, Direction, MarketRole
from msa.research.msa_core import MSACoreRun
from msa.validation import (
    CausalAuditor,
    MSAValidationError,
    ValidationMetricName,
)

from .bars import (
    bars_after,
    canonical_bar_id,
    last_bar_at_or_before,
    validate_reference_bars,
)
from .contracts import (
    BreakResolution,
    MetricAggregateStatus,
    MetricEventKind,
    MetricFormulaDefinition,
    MetricObservationStatus,
    StructuralMetricAggregate,
    StructuralMetricConfig,
    StructuralMetricEvent,
    StructuralMetricObservation,
    TurnResolution,
    fact_mapping,
    make_facts,
    resolve_metric_config,
)
from .errors import MetricInputError, MetricObservationError
from .events import (
    _context_key,
    _extract_events,
    resolve_evaluation_as_of,
)
from .formula_registry import default_metric_formula_registry
from .identity import (
    DECIMAL_PRECISION,
    decimal_divide,
    digest,
    semantic_id,
)


def _fact_time(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise MetricObservationError(
            f"{field_name} event fact must be an ISO datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MetricObservationError(
            f"{field_name} event fact must be timezone-aware"
        )
    return parsed


def _fact_decimal(value: str, field_name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (TypeError, ValueError) as exc:
        raise MetricObservationError(
            f"{field_name} event fact must be Decimal text"
        ) from exc
    if not parsed.is_finite():
        raise MetricObservationError(
            f"{field_name} event fact must be finite"
        )
    return parsed


def _bar_ids(bars: tuple[CanonicalBar, ...]) -> tuple[str, ...]:
    return tuple(canonical_bar_id(item) for item in bars)


def _observation(
    *,
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    status: MetricObservationStatus,
    start: datetime,
    end: datetime,
    bars: tuple[CanonicalBar, ...],
    value: Decimal | None,
    numerator: Decimal | None,
    denominator: Decimal | None,
    facts: dict[str, object],
) -> StructuralMetricObservation:
    bar_ids = _bar_ids(bars)
    bound_facts = {
        **facts,
        "observation_window": f"{start.isoformat()}|{end.isoformat()}",
        "observed_bar_ids_digest": digest(list(bar_ids)),
    }
    encoded = make_facts(bound_facts)
    payload = {
        "metric_name": formula.metric_name.value,
        "metric_formula_id": formula.metric_formula_id,
        "metric_event_id": event.metric_event_id,
        "status": status.value,
        "observation_start_time": start.isoformat(),
        "observation_end_time": end.isoformat(),
        "observed_bar_ids": list(bar_ids),
        "value": None if value is None else str(value),
        "numerator": None if numerator is None else str(numerator),
        "denominator": (
            None if denominator is None else str(denominator)
        ),
        "facts": list(encoded),
        "schema_version": 1,
    }
    return StructuralMetricObservation(
        metric_observation_id=semantic_id(
            "structural-metric-observation-v1-", payload
        ),
        metric_name=formula.metric_name,
        metric_formula_id=formula.metric_formula_id,
        metric_event_id=event.metric_event_id,
        status=status,
        observation_start_time=start,
        observation_end_time=end,
        observed_bar_ids=bar_ids,
        value=value,
        numerator=numerator,
        denominator=denominator,
        facts=encoded,
    )


def _confirmation_delay_bars(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    bars: tuple[CanonicalBar, ...],
) -> StructuralMetricObservation:
    facts = fact_mapping(event.facts, error_type=MetricObservationError)
    origin = _fact_time(facts["origin_time"], "origin_time")
    counted = tuple(
        item
        for item in bars
        if origin < item.available_time <= event.event_confirm_time
    )
    if origin < bars[0].timestamp:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.UNAVAILABLE_INPUT,
            start=origin,
            end=event.event_confirm_time,
            bars=counted,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "origin_predates_reference_history"},
        )
    value = Decimal(len(counted))
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=origin,
        end=event.event_confirm_time,
        bars=counted,
        value=value,
        numerator=value,
        denominator=None,
        facts={"counted_bar_count": len(counted)},
    )


def _confirmation_delay_atr(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    bars: tuple[CanonicalBar, ...],
) -> StructuralMetricObservation:
    facts = fact_mapping(event.facts, error_type=MetricObservationError)
    origin = _fact_time(facts["origin_time"], "origin_time")
    anchor = event.anchor_price
    confirm_bar = last_bar_at_or_before(bars, event.event_confirm_time)
    observed = () if confirm_bar is None else (confirm_bar,)
    if (
        anchor is None
        or confirm_bar is None
        or event.causal_atr is None
        or event.causal_atr <= 0
    ):
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.UNAVAILABLE_INPUT,
            start=origin,
            end=event.event_confirm_time,
            bars=observed,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "anchor_or_causal_atr_unavailable"},
        )
    numerator = abs(confirm_bar.close - anchor)
    value = decimal_divide(numerator, event.causal_atr)
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=origin,
        end=event.event_confirm_time,
        bars=observed,
        value=value,
        numerator=numerator,
        denominator=event.causal_atr,
        facts={
            "confirm_anchor": confirm_bar.close,
            "origin_anchor": anchor,
        },
    )


def _history_by_context(run: MSACoreRun) -> dict[str, object]:
    result: dict[str, object] = {}
    for history in run.source_input.timeframe_state_histories:
        key = _context_key(
            history.config_snapshot.target_timeframe,
            history.config_snapshot.target_scale,
        )
        if key in result:
            raise MetricObservationError(
                "TimeframeState histories repeat a context"
            )
        result[key] = history
    return result


def _false_turn(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    run: MSACoreRun,
    config: StructuralMetricConfig,
    bars: tuple[CanonicalBar, ...],
    cutoff: datetime,
) -> StructuralMetricObservation:
    history = _history_by_context(run).get(event.context_key or "")
    if history is None:
        raise MetricObservationError(
            "TURN_CANDIDATE context history is unavailable"
        )
    event_facts = fact_mapping(
        event.facts, error_type=MetricObservationError
    )
    try:
        prior = Direction(event_facts["prior_stable_direction"])
    except (KeyError, ValueError) as exc:
        raise MetricObservationError(
            "TURN_CANDIDATE prior direction is invalid"
        ) from exc
    future_bars = bars_after(bars, event.event_confirm_time, cutoff)
    window = future_bars[: config.turn_resolution_bars]
    stable = {Direction.UP, Direction.DOWN}
    resolved_state = None
    for snapshot in history.snapshots:
        state = snapshot.state
        if (
            state.confirm_time <= event.event_confirm_time
            or state.confirm_time > cutoff
            or state.direction not in stable
        ):
            continue
        bars_to_resolution = tuple(
            item
            for item in future_bars
            if item.available_time <= state.confirm_time
        )
        if len(bars_to_resolution) <= config.turn_resolution_bars:
            resolved_state = state
            window = bars_to_resolution
            break
    if resolved_state is None:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.CENSORED_RIGHT,
            start=event.event_confirm_time,
            end=(
                window[-1].available_time if window else cutoff
            ),
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "turn_not_resolved_within_causal_window"},
        )
    resumed = resolved_state.direction is prior
    resolution = (
        TurnResolution.PRIOR_DIRECTION_RESUMED
        if resumed
        else TurnResolution.OPPOSITE_CONFIRMED
    )
    numerator = Decimal("1") if resumed else Decimal("0")
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=event.event_confirm_time,
        end=resolved_state.confirm_time,
        bars=window,
        value=numerator,
        numerator=numerator,
        denominator=Decimal("1"),
        facts={
            "resolution": resolution,
            "resolved_direction": resolved_state.direction,
            "resolved_state_id": resolved_state.state_id,
        },
    )


def _continued_break(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    config: StructuralMetricConfig,
    bars: tuple[CanonicalBar, ...],
    cutoff: datetime,
) -> StructuralMetricObservation:
    future = bars_after(bars, event.event_confirm_time, cutoff)
    window = future[: config.break_observation_bars]
    end = window[-1].available_time if window else cutoff
    if len(window) < config.break_observation_bars:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.CENSORED_RIGHT,
            start=event.event_confirm_time,
            end=end,
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "break_window_incomplete"},
        )
    if event.causal_atr is None:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.UNAVAILABLE_INPUT,
            start=event.event_confirm_time,
            end=end,
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "causal_atr_unavailable"},
        )
    event_facts = fact_mapping(
        event.facts, error_type=MetricObservationError
    )
    boundary_high = _fact_decimal(
        event_facts["boundary_high"], "boundary_high"
    )
    boundary_low = _fact_decimal(
        event_facts["boundary_low"], "boundary_low"
    )
    if event.boundary_side is BoundarySide.UPPER:
        favorable = max(item.high for item in window) - boundary_high
    elif event.boundary_side is BoundarySide.LOWER:
        favorable = boundary_low - min(item.low for item in window)
    else:
        raise MetricObservationError(
            "BREAK_CONFIRMATION requires a boundary side"
        )
    threshold = config.break_continuation_atr * event.causal_atr
    continued = favorable >= threshold
    resolution = (
        BreakResolution.CONTINUED
        if continued
        else BreakResolution.NOT_CONTINUED
    )
    numerator = Decimal("1") if continued else Decimal("0")
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=event.event_confirm_time,
        end=end,
        bars=window,
        value=numerator,
        numerator=numerator,
        denominator=Decimal("1"),
        facts={
            "favorable_continuation": favorable,
            "required_continuation": threshold,
            "resolution": resolution,
        },
    )


def _trend_capture(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    run: MSACoreRun,
    config: StructuralMetricConfig,
    bars: tuple[CanonicalBar, ...],
    cutoff: datetime,
) -> StructuralMetricObservation:
    history = _history_by_context(run).get(event.context_key or "")
    if history is None:
        raise MetricObservationError(
            "DIRECTION_EPISODE context history is unavailable"
        )
    event_facts = fact_mapping(
        event.facts, error_type=MetricObservationError
    )
    try:
        direction = Direction(event_facts["direction"])
    except (KeyError, ValueError) as exc:
        raise MetricObservationError(
            "DIRECTION_EPISODE direction is invalid"
        ) from exc
    opposite = Direction.DOWN if direction is Direction.UP else Direction.UP
    future = bars_after(bars, event.event_confirm_time, cutoff)
    horizon_end = (
        future[config.trend_capture_bars - 1].available_time
        if len(future) >= config.trend_capture_bars
        else None
    )
    opposite_time = None
    for snapshot in history.snapshots:
        state = snapshot.state
        if (
            state.confirm_time > event.event_confirm_time
            and state.confirm_time <= cutoff
            and state.direction is opposite
        ):
            opposite_time = state.confirm_time
            break
    end_candidates = tuple(
        item for item in (opposite_time, horizon_end) if item is not None
    )
    if not end_candidates:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.CENSORED_RIGHT,
            start=event.event_confirm_time,
            end=(future[-1].available_time if future else cutoff),
            bars=future,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "trend_episode_end_not_observable"},
        )
    episode_end = min(end_candidates)
    window = tuple(
        item for item in future if item.available_time <= episode_end
    )
    origin_time = _fact_time(
        event_facts["origin_time"], "origin_time"
    )
    origin_bar = last_bar_at_or_before(bars, origin_time)
    confirm_bar = last_bar_at_or_before(bars, event.event_confirm_time)
    if origin_bar is None or confirm_bar is None or not window:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.UNAVAILABLE_INPUT,
            start=event.event_confirm_time,
            end=episode_end,
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "trend_anchor_or_window_unavailable"},
        )
    if direction is Direction.UP:
        terminal = max(item.high for item in window)
        full = terminal - origin_bar.close
        remaining = terminal - confirm_bar.close
    else:
        terminal = min(item.low for item in window)
        full = origin_bar.close - terminal
        remaining = confirm_bar.close - terminal
    if full <= 0:
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.UNAVAILABLE_INPUT,
            start=event.event_confirm_time,
            end=episode_end,
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "full_opportunity_not_positive"},
        )
    clamped = min(max(remaining, Decimal("0")), full)
    value = decimal_divide(clamped, full)
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=event.event_confirm_time,
        end=episode_end,
        bars=window,
        value=value,
        numerator=clamped,
        denominator=full,
        facts={
            "confirm_anchor": confirm_bar.close,
            "direction": direction,
            "episode_end_reason": (
                "opposite_direction"
                if opposite_time == episode_end
                else "bar_horizon"
            ),
            "origin_anchor": origin_bar.close,
            "terminal_extreme": terminal,
        },
    )


def _touch_excursions(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    config: StructuralMetricConfig,
    bars: tuple[CanonicalBar, ...],
    cutoff: datetime,
) -> tuple[
    StructuralMetricObservation,
    Decimal | None,
    Decimal | None,
    tuple[CanonicalBar, ...],
]:
    future = bars_after(bars, event.event_confirm_time, cutoff)
    window = future[: config.reaction_observation_bars]
    end = window[-1].available_time if window else cutoff
    if len(window) < config.reaction_observation_bars:
        return (
            _observation(
                formula=formula,
                event=event,
                status=MetricObservationStatus.CENSORED_RIGHT,
                start=event.event_confirm_time,
                end=end,
                bars=window,
                value=None,
                numerator=None,
                denominator=None,
                facts={"reason": "post_touch_window_incomplete"},
            ),
            None,
            None,
            window,
        )
    if event.anchor_price is None:
        return (
            _observation(
                formula=formula,
                event=event,
                status=MetricObservationStatus.UNAVAILABLE_INPUT,
                start=event.event_confirm_time,
                end=end,
                bars=window,
                value=None,
                numerator=None,
                denominator=None,
                facts={"reason": "touch_anchor_unavailable"},
            ),
            None,
            None,
            window,
        )
    anchor = event.anchor_price
    if event.market_role is MarketRole.SUPPORT:
        mfe = max(
            max(item.high for item in window) - anchor,
            Decimal("0"),
        )
        mae = max(
            anchor - min(item.low for item in window),
            Decimal("0"),
        )
    elif event.market_role is MarketRole.RESISTANCE:
        mfe = max(
            anchor - min(item.low for item in window),
            Decimal("0"),
        )
        mae = max(
            max(item.high for item in window) - anchor,
            Decimal("0"),
        )
    else:
        raise MetricObservationError(
            "BOUNDARY_FIRST_TOUCH requires SUPPORT or RESISTANCE"
        )
    value = mfe if formula.metric_name is ValidationMetricName.MFE else mae
    return (
        _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.MATURED,
            start=event.event_confirm_time,
            end=end,
            bars=window,
            value=value,
            numerator=value,
            denominator=None,
            facts={"mae": mae, "mfe": mfe, "touch_anchor": anchor},
        ),
        mfe,
        mae,
        window,
    )


def _touch_reaction(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    config: StructuralMetricConfig,
    bars: tuple[CanonicalBar, ...],
    cutoff: datetime,
) -> StructuralMetricObservation:
    mfe_formula = next(
        item
        for item in default_metric_formula_registry()
        if item.metric_name is ValidationMetricName.MFE
    )
    base, mfe, mae, window = _touch_excursions(
        mfe_formula, event, config, bars, cutoff
    )
    if base.status is not MetricObservationStatus.MATURED:
        return _observation(
            formula=formula,
            event=event,
            status=base.status,
            start=base.observation_start_time,
            end=base.observation_end_time,
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={
                "reason": fact_mapping(
                    base.facts, error_type=MetricObservationError
                ).get("reason", "post_touch_input_unavailable")
            },
        )
    if (
        mfe is None
        or mae is None
        or event.causal_atr is None
        or event.causal_atr <= 0
    ):
        return _observation(
            formula=formula,
            event=event,
            status=MetricObservationStatus.UNAVAILABLE_INPUT,
            start=base.observation_start_time,
            end=base.observation_end_time,
            bars=window,
            value=None,
            numerator=None,
            denominator=None,
            facts={"reason": "causal_atr_unavailable"},
        )
    numerator = mfe - mae
    value = decimal_divide(numerator, event.causal_atr)
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=base.observation_start_time,
        end=base.observation_end_time,
        bars=window,
        value=value,
        numerator=numerator,
        denominator=event.causal_atr,
        facts={"mae": mae, "mfe": mfe},
    )


def _box_churn(
    formula: MetricFormulaDefinition,
    event: StructuralMetricEvent,
    created_index: int,
) -> StructuralMetricObservation:
    value = Decimal("0") if created_index == 0 else Decimal("1")
    return _observation(
        formula=formula,
        event=event,
        status=MetricObservationStatus.MATURED,
        start=event.event_confirm_time,
        end=event.event_confirm_time,
        bars=(),
        value=value,
        numerator=value,
        denominator=None,
        facts={
            "created_episode_index": created_index,
            "is_churn_increment": created_index > 0,
        },
    )


def _observations(
    run: MSACoreRun,
    events: tuple[StructuralMetricEvent, ...],
    config: StructuralMetricConfig,
    cutoff: datetime,
) -> tuple[StructuralMetricObservation, ...]:
    bars = validate_reference_bars(run)
    formulas = default_metric_formula_registry()
    events_by_kind = {
        kind: tuple(item for item in events if item.kind is kind)
        for kind in MetricEventKind
    }
    output: list[StructuralMetricObservation] = []
    for formula in formulas:
        matching_events = events_by_kind[formula.event_kind]
        for index, event in enumerate(matching_events):
            name = formula.metric_name
            if name is ValidationMetricName.CONFIRMATION_DELAY_BARS:
                item = _confirmation_delay_bars(formula, event, bars)
            elif name is ValidationMetricName.CONFIRMATION_DELAY_ATR:
                item = _confirmation_delay_atr(formula, event, bars)
            elif name is ValidationMetricName.FALSE_TURN_RATE:
                item = _false_turn(
                    formula, event, run, config, bars, cutoff
                )
            elif name is ValidationMetricName.CONTINUED_BREAK_RATE:
                item = _continued_break(
                    formula, event, config, bars, cutoff
                )
            elif name is ValidationMetricName.TREND_CAPTURE_RATIO:
                item = _trend_capture(
                    formula, event, run, config, bars, cutoff
                )
            elif name in {
                ValidationMetricName.MFE,
                ValidationMetricName.MAE,
            }:
                item = _touch_excursions(
                    formula, event, config, bars, cutoff
                )[0]
            elif name is ValidationMetricName.BOX_CHURN:
                item = _box_churn(formula, event, index)
            elif name is ValidationMetricName.FIRST_TOUCH_REACTION:
                item = _touch_reaction(
                    formula, event, config, bars, cutoff
                )
            elif name is ValidationMetricName.RESONANCE_LIFT:
                continue
            else:
                raise MetricObservationError(
                    f"unsupported frozen metric {name.value}"
                )
            output.append(item)
    return tuple(output)


def iter_structural_metric_observations(
    run: MSACoreRun,
    events: tuple[StructuralMetricEvent, ...] | None = None,
    config: StructuralMetricConfig | None = None,
    evaluation_as_of_time: datetime | None = None,
):
    """Yield deterministic observations in frozen formula/event order."""

    if not isinstance(run, MSACoreRun):
        raise MetricInputError("run must be an MSACoreRun")
    resolved = resolve_metric_config(config)
    cutoff = resolve_evaluation_as_of(run, evaluation_as_of_time)
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        try:
            audit = CausalAuditor().audit_run(run)
        except MSAValidationError as exc:
            raise MetricInputError(
                "MSACoreRun could not be audited safely"
            ) from exc
        if not audit.passed:
            raise MetricInputError(
                "MSACoreRun failed the independent CausalAuditor"
            )
        context.prec = DECIMAL_PRECISION
        selected_events = (
            _extract_events(run, resolved, cutoff)
            if events is None
            else events
        )
        if not isinstance(selected_events, tuple) or any(
            not isinstance(item, StructuralMetricEvent)
            for item in selected_events
        ):
            raise MetricInputError(
                "events must be a StructuralMetricEvent tuple"
            )
        yield from _observations(
            run, selected_events, resolved, cutoff
        )


def build_metric_aggregates(
    formulas: tuple[MetricFormulaDefinition, ...],
    observations: tuple[StructuralMetricObservation, ...],
    config: StructuralMetricConfig,
) -> tuple[StructuralMetricAggregate, ...]:
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        return _build_metric_aggregates(formulas, observations, config)


def _build_metric_aggregates(
    formulas: tuple[MetricFormulaDefinition, ...],
    observations: tuple[StructuralMetricObservation, ...],
    config: StructuralMetricConfig,
) -> tuple[StructuralMetricAggregate, ...]:
    """Recompute all ten aggregates from their exact observation streams."""

    output: list[StructuralMetricAggregate] = []
    for formula in formulas:
        selected = tuple(
            item
            for item in observations
            if item.metric_formula_id == formula.metric_formula_id
        )
        matured = tuple(
            item
            for item in selected
            if item.status is MetricObservationStatus.MATURED
        )
        censored_count = sum(
            item.status is MetricObservationStatus.CENSORED_RIGHT
            for item in selected
        )
        unavailable_count = sum(
            item.status is MetricObservationStatus.UNAVAILABLE_INPUT
            for item in selected
        )
        value: Decimal | None = None
        numerator: Decimal | None = None
        denominator: Decimal | None = None
        if (
            formula.metric_name is ValidationMetricName.RESONANCE_LIFT
            and len(matured) < config.resonance_min_pair_count
        ):
            status = MetricAggregateStatus.INSUFFICIENT_SAMPLE
        elif not selected:
            status = MetricAggregateStatus.NO_ELIGIBLE_EVENTS
        elif not matured:
            status = MetricAggregateStatus.NO_MATURED_OBSERVATIONS
        else:
            status = MetricAggregateStatus.AVAILABLE
            values = tuple(item.value for item in matured)
            if any(item is None for item in values):
                raise MetricObservationError(
                    "MATURED observations must contain values"
                )
            numerator = sum(
                (item for item in values if item is not None),
                Decimal("0"),
            )
            if formula.aggregation_rule == "SUM_MATURED":
                value = numerator
            else:
                denominator = Decimal(len(matured))
                value = decimal_divide(numerator, denominator)
        payload = {
            "metric_name": formula.metric_name.value,
            "formula_id": formula.metric_formula_id,
            "status": status.value,
            "value": None if value is None else str(value),
            "eligible_count": len(selected),
            "matured_count": len(matured),
            "censored_count": censored_count,
            "unavailable_count": unavailable_count,
            "numerator": (
                None if numerator is None else str(numerator)
            ),
            "denominator": (
                None if denominator is None else str(denominator)
            ),
            "source_observation_ids": [
                item.metric_observation_id for item in selected
            ],
            "schema_version": 1,
        }
        output.append(
            StructuralMetricAggregate(
                metric_aggregate_id=semantic_id(
                    "structural-metric-aggregate-v1-", payload
                ),
                metric_name=formula.metric_name,
                formula_id=formula.metric_formula_id,
                status=status,
                value=value,
                eligible_count=len(selected),
                matured_count=len(matured),
                censored_count=censored_count,
                unavailable_count=unavailable_count,
                numerator=numerator,
                denominator=denominator,
                source_observation_ids=tuple(
                    item.metric_observation_id for item in selected
                ),
            )
        )
    return tuple(output)
