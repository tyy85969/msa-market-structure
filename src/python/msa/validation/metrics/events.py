"""Deterministic causal event extraction from public MSA Core contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from msa.domain import (
    BoundarySide,
    Direction,
    MarketRole,
)
from msa.research.active_box import ActiveBoxEventType
from msa.research.lifecycle import LifecycleEventType
from msa.research.msa_core import MSACoreRun
from msa.validation import CausalAuditor, MSAValidationError

from .bars import (
    canonical_bar_id,
    causal_atr_at_or_before,
    validate_reference_bars,
)
from .contracts import (
    MetricEventKind,
    StructuralMetricConfig,
    StructuralMetricEvent,
    fact_mapping,
    make_facts,
    resolve_metric_config,
)
from .errors import MetricEventError, MetricInputError
from .identity import (
    DECIMAL_PRECISION,
    decimal_divide,
    digest,
    semantic_id,
)


def resolve_evaluation_as_of(
    run: MSACoreRun, value: datetime | None
) -> datetime:
    if not isinstance(run, MSACoreRun):
        raise MetricInputError("run must be an MSACoreRun")
    if value is None:
        return run.processing_times[-1]
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise MetricInputError(
            "evaluation_as_of_time must be an aware UTC datetime"
        )
    cutoff = value.astimezone(timezone.utc)
    if cutoff < run.processing_times[0]:
        raise MetricInputError(
            "evaluation_as_of_time cannot precede Run start AsOf"
        )
    if cutoff > run.processing_times[-1]:
        raise MetricInputError(
            "evaluation_as_of_time cannot follow Run final AsOf"
        )
    return cutoff


def _context_key(timeframe: object, scale: object) -> str:
    timeframe_value = getattr(timeframe, "value", None)
    scale_to_dict = getattr(scale, "to_dict", None)
    if not isinstance(timeframe_value, str) or not callable(scale_to_dict):
        raise MetricEventError("context lacks public timeframe/scale facts")
    return semantic_id(
        "structural-metric-context-v1-",
        {
            "timeframe": timeframe_value,
            "scale": scale_to_dict(),
            "schema_version": 1,
        },
    )


def _event(
    *,
    kind: MetricEventKind,
    event_confirm_time: datetime,
    first_observed_as_of_time: datetime,
    symbol: str,
    reference_timeframe: str,
    source_object_ids: tuple[str, ...],
    facts: tuple[str, ...],
    boundary_side: BoundarySide | None = None,
    market_role: MarketRole | None = None,
    context_key: str | None = None,
    box_key_id: str | None = None,
    zone_key: str | None = None,
    zone_snapshot_id: str | None = None,
    zone_class: str | None = None,
    anchor_price: Decimal | None = None,
    causal_atr: Decimal | None = None,
) -> StructuralMetricEvent:
    source_ids = tuple(sorted(set(source_object_ids)))
    fact_values = fact_mapping(facts, error_type=MetricEventError)
    fact_values.update(
        {
            "event_confirm_time": event_confirm_time.isoformat(),
            "source_object_ids_digest": digest(list(source_ids)),
        }
    )
    bound_facts = make_facts(fact_values)
    payload = {
        "kind": kind.value,
        "event_confirm_time": event_confirm_time.isoformat(),
        "first_observed_as_of_time": first_observed_as_of_time.isoformat(),
        "symbol": symbol,
        "reference_timeframe": reference_timeframe,
        "source_object_ids": list(source_ids),
        "boundary_side": (
            None if boundary_side is None else boundary_side.value
        ),
        "market_role": None if market_role is None else market_role.value,
        "context_key": context_key,
        "box_key_id": box_key_id,
        "zone_key": zone_key,
        "zone_snapshot_id": zone_snapshot_id,
        "zone_class": zone_class,
        "anchor_price": (
            None if anchor_price is None else str(anchor_price)
        ),
        "causal_atr": None if causal_atr is None else str(causal_atr),
        "facts": list(bound_facts),
        "schema_version": 1,
    }
    return StructuralMetricEvent(
        metric_event_id=semantic_id(
            "structural-metric-event-v1-", payload
        ),
        kind=kind,
        event_confirm_time=event_confirm_time,
        first_observed_as_of_time=first_observed_as_of_time,
        symbol=symbol,
        reference_timeframe=reference_timeframe,
        source_object_ids=source_ids,
        boundary_side=boundary_side,
        market_role=market_role,
        context_key=context_key,
        box_key_id=box_key_id,
        zone_key=zone_key,
        zone_snapshot_id=zone_snapshot_id,
        zone_class=zone_class,
        anchor_price=anchor_price,
        causal_atr=causal_atr,
        facts=bound_facts,
    )


def _structure_events(
    run: MSACoreRun,
    config: StructuralMetricConfig,
    cutoff: datetime,
    bars: tuple[object, ...],
) -> list[StructuralMetricEvent]:
    output: list[StructuralMetricEvent] = []
    seen_subjects: set[str] = set()
    symbol = run.config_snapshot.frame_config.symbol
    reference_timeframe = (
        run.config_snapshot.frame_config.reference_price_timeframe.value
    )
    for frame in run.resonance_history.frames:
        if frame.as_of_time > cutoff:
            break
        for evidence in frame.evidence:
            if evidence.subject_id in seen_subjects:
                continue
            seen_subjects.add(evidence.subject_id)
            boundary = evidence.boundary
            with localcontext() as context:
                context.prec = DECIMAL_PRECISION
                context.rounding = ROUND_HALF_EVEN
                midpoint = +(
                    (boundary.price_range.low + boundary.price_range.high)
                    / Decimal("2")
                )
            event_time = evidence.state_confirm_time
            if event_time > cutoff:
                continue
            output.append(
                _event(
                    kind=MetricEventKind.STRUCTURE_CONFIRMATION,
                    event_confirm_time=event_time,
                    first_observed_as_of_time=frame.as_of_time,
                    symbol=symbol,
                    reference_timeframe=reference_timeframe,
                    source_object_ids=(
                        evidence.subject_id,
                        evidence.lifecycle_state_id,
                        evidence.lifecycle_event_id,
                        evidence.evidence_id,
                        boundary.object_id,
                        frame.frame_id,
                    ),
                    boundary_side=boundary.boundary_side,
                    market_role=boundary.market_role,
                    context_key=_context_key(
                        evidence.context.timeframe,
                        evidence.context.scale,
                    ),
                    anchor_price=midpoint,
                    causal_atr=causal_atr_at_or_before(
                        bars, config, event_time
                    ),
                    facts=make_facts(
                        {
                            "boundary_high": boundary.price_range.high,
                            "boundary_low": boundary.price_range.low,
                            "evidence_id": evidence.evidence_id,
                            "lifecycle_state_id": (
                                evidence.lifecycle_state_id
                            ),
                            "origin_anchor": midpoint,
                            "origin_time": boundary.origin_time,
                            "subject_id": evidence.subject_id,
                        }
                    ),
                )
            )
    return output


def _timeframe_events(
    run: MSACoreRun,
    config: StructuralMetricConfig,
    cutoff: datetime,
    bars: tuple[object, ...],
) -> list[StructuralMetricEvent]:
    output: list[StructuralMetricEvent] = []
    symbol = run.config_snapshot.frame_config.symbol
    reference_timeframe = (
        run.config_snapshot.frame_config.reference_price_timeframe.value
    )
    stable = {Direction.UP, Direction.DOWN}
    histories = tuple(
        sorted(
            run.source_input.timeframe_state_histories,
            key=lambda item: (
                item.config_snapshot.target_timeframe.value,
                str(item.config_snapshot.target_scale.to_dict()),
            ),
        )
    )
    for history in histories:
        key = _context_key(
            history.config_snapshot.target_timeframe,
            history.config_snapshot.target_scale,
        )
        previous_direction: Direction | None = None
        for snapshot in history.snapshots:
            if snapshot.as_of_time > cutoff:
                break
            state = snapshot.state
            direction = state.direction
            source_ids = (
                snapshot.snapshot_id,
                state.state_id,
                snapshot.events[-1].event_id,
                snapshot.source_lifecycle_snapshot_id,
            )
            event_time = state.confirm_time
            if (
                direction is Direction.TURNING
                and previous_direction in stable
            ):
                output.append(
                    _event(
                        kind=MetricEventKind.TURN_CANDIDATE,
                        event_confirm_time=event_time,
                        first_observed_as_of_time=snapshot.as_of_time,
                        symbol=symbol,
                        reference_timeframe=reference_timeframe,
                        source_object_ids=source_ids,
                        context_key=key,
                        causal_atr=causal_atr_at_or_before(
                            bars, config, event_time
                        ),
                        facts=make_facts(
                            {
                                "prior_stable_direction": (
                                    previous_direction
                                ),
                                "state_id": state.state_id,
                                "turn_origin_time": state.origin_time,
                            }
                        ),
                    )
                )
            if direction in stable and direction is not previous_direction:
                output.append(
                    _event(
                        kind=MetricEventKind.DIRECTION_EPISODE,
                        event_confirm_time=event_time,
                        first_observed_as_of_time=snapshot.as_of_time,
                        symbol=symbol,
                        reference_timeframe=reference_timeframe,
                        source_object_ids=source_ids,
                        context_key=key,
                        causal_atr=causal_atr_at_or_before(
                            bars, config, event_time
                        ),
                        facts=make_facts(
                            {
                                "direction": direction,
                                "origin_time": state.origin_time,
                                "state_id": state.state_id,
                            }
                        ),
                    )
                )
            previous_direction = direction
    return output


def _break_events(
    run: MSACoreRun,
    config: StructuralMetricConfig,
    cutoff: datetime,
    bars: tuple[object, ...],
) -> list[StructuralMetricEvent]:
    history = run.source_input.lifecycle_history
    first_observed: dict[str, datetime] = {}
    state_at_first_observation: dict[str, object] = {}
    for snapshot in history.snapshots:
        if snapshot.as_of_time > cutoff:
            break
        for event in snapshot.events:
            if event.event_id in first_observed:
                continue
            first_observed[event.event_id] = snapshot.as_of_time
            matching_states = tuple(
                item
                for item in snapshot.states
                if item.subject_ref.object_id == event.subject_id
            )
            if len(matching_states) != 1:
                raise MetricEventError(
                    "Lifecycle event must resolve one state at first observation"
                )
            state_at_first_observation[event.event_id] = (
                matching_states[0]
            )
    symbol = run.config_snapshot.frame_config.symbol
    reference_timeframe = (
        run.config_snapshot.frame_config.reference_price_timeframe.value
    )
    output: list[StructuralMetricEvent] = []
    for event in history.events:
        if (
            event.event_type is not LifecycleEventType.BROKEN
            or event.event_confirm_time > cutoff
        ):
            continue
        state = state_at_first_observation.get(event.event_id)
        if state is None:
            continue
        boundary = state.subject_ref
        side = event.effective_boundary_side
        anchor = (
            boundary.price_range.high
            if side is BoundarySide.UPPER
            else boundary.price_range.low
        )
        output.append(
            _event(
                kind=MetricEventKind.BREAK_CONFIRMATION,
                event_confirm_time=event.event_confirm_time,
                first_observed_as_of_time=first_observed[event.event_id],
                symbol=symbol,
                reference_timeframe=reference_timeframe,
                source_object_ids=(
                    event.event_id,
                    event.subject_id,
                    boundary.object_id,
                    state.state_id,
                ),
                boundary_side=side,
                market_role=event.effective_market_role,
                context_key=_context_key(
                    boundary.timeframe, boundary.scale
                ),
                anchor_price=anchor,
                causal_atr=causal_atr_at_or_before(
                    bars, config, event.event_confirm_time
                ),
                facts=make_facts(
                    {
                        "boundary_high": boundary.price_range.high,
                        "boundary_low": boundary.price_range.low,
                        "lifecycle_break_event_id": event.event_id,
                        "origin_time": boundary.origin_time,
                        "subject_id": event.subject_id,
                    }
                ),
            )
        )
    return output


def _zone_for_projection(score_frame: object, projection: object) -> object:
    zones = getattr(score_frame, "zones", None)
    side = getattr(getattr(projection, "boundary", None), "boundary_side", None)
    key = getattr(projection, "source_zone_key_id", None)
    snapshot_id = getattr(projection, "source_zone_snapshot_id", None)
    if not isinstance(zones, tuple):
        raise MetricEventError("source ScoreFrame zones are unavailable")
    matches = tuple(
        item
        for item in zones
        if item.side is side
        and item.zone_key_id == key
        and item.zone_snapshot_id == snapshot_id
    )
    if len(matches) != 1:
        raise MetricEventError(
            "Active Box projection must resolve exactly one current Zone"
        )
    return matches[0]


def _active_box_events(
    run: MSACoreRun,
    config: StructuralMetricConfig,
    cutoff: datetime,
    bars: tuple[object, ...],
) -> list[StructuralMetricEvent]:
    history = run.active_box_history
    score_by_id = {
        item.score_frame_id: item for item in run.score_history.frames
    }
    frozen_time_by_box = {
        item.box_key_id: item.event_confirm_time
        for item in history.events
        if item.event_type is ActiveBoxEventType.FROZEN
    }
    indexed_bars = tuple(enumerate(bars))
    symbol = run.config_snapshot.frame_config.symbol
    reference_timeframe = (
        run.config_snapshot.frame_config.reference_price_timeframe.value
    )
    output: list[StructuralMetricEvent] = []
    created_box_keys: set[str] = set()
    for active_event in history.events:
        if (
            active_event.event_type is not ActiveBoxEventType.CREATED
            or active_event.event_confirm_time > cutoff
        ):
            continue
        snapshot = active_event.resulting_box_snapshot
        if snapshot.box_key_id in created_box_keys:
            raise MetricEventError(
                "Active Box creation ledger repeats a box_key_id"
            )
        created_box_keys.add(snapshot.box_key_id)
        score_frame = score_by_id.get(active_event.source_score_frame_id)
        if score_frame is None:
            raise MetricEventError(
                "CREATED event source ScoreFrame is unavailable"
            )
        lower_zone = _zone_for_projection(
            score_frame, snapshot.lower_projection
        )
        upper_zone = _zone_for_projection(
            score_frame, snapshot.upper_projection
        )
        creation_atr = causal_atr_at_or_before(
            bars, config, snapshot.created_time
        )
        output.append(
            _event(
                kind=MetricEventKind.BOX_EPISODE_CREATED,
                event_confirm_time=snapshot.created_time,
                first_observed_as_of_time=active_event.event_confirm_time,
                symbol=symbol,
                reference_timeframe=reference_timeframe,
                source_object_ids=(
                    active_event.event_id,
                    snapshot.box_key_id,
                    snapshot.box_snapshot_id,
                    score_frame.score_frame_id,
                    snapshot.lower_projection.projection_id,
                    snapshot.upper_projection.projection_id,
                    lower_zone.zone_snapshot_id,
                    upper_zone.zone_snapshot_id,
                ),
                box_key_id=snapshot.box_key_id,
                anchor_price=snapshot.active_box.selection_price,
                causal_atr=creation_atr,
                facts=make_facts(
                    {
                        "active_box_created_event_id": (
                            active_event.event_id
                        ),
                        "lower_zone_class": lower_zone.resonance_class,
                        "lower_zone_key": lower_zone.zone_key_id,
                        "lower_zone_snapshot_id": (
                            lower_zone.zone_snapshot_id
                        ),
                        "selection_price": (
                            snapshot.active_box.selection_price
                        ),
                        "upper_zone_class": upper_zone.resonance_class,
                        "upper_zone_key": upper_zone.zone_key_id,
                        "upper_zone_snapshot_id": (
                            upper_zone.zone_snapshot_id
                        ),
                    }
                ),
            )
        )
        freeze_time = frozen_time_by_box.get(snapshot.box_key_id)
        for projection, zone in (
            (snapshot.lower_projection, lower_zone),
            (snapshot.upper_projection, upper_zone),
        ):
            boundary = projection.boundary
            side = boundary.boundary_side
            role = boundary.market_role
            candidates = tuple(
                (index, bar)
                for index, bar in indexed_bars
                if bar.available_time > snapshot.created_time
                and bar.available_time <= cutoff
                and (
                    freeze_time is None
                    or bar.available_time < freeze_time
                )
            )
            touch: tuple[int, object] | None = None
            for index, bar in candidates:
                if (
                    bar.low <= boundary.price_range.high
                    and bar.high >= boundary.price_range.low
                ):
                    touch = (index, bar)
                    break
            if touch is None:
                continue
            touch_index, touch_bar = touch
            touch_anchor = (
                boundary.price_range.high
                if role is MarketRole.SUPPORT
                else boundary.price_range.low
            )
            touch_atr = causal_atr_at_or_before(
                bars, config, touch_bar.available_time
            )
            selection_distance_atr: Decimal | None = None
            if creation_atr is not None and creation_atr > 0:
                selection_distance_atr = decimal_divide(
                    zone.distance, creation_atr
                )
            touch_bar_id = canonical_bar_id(touch_bar)
            output.append(
                _event(
                    kind=MetricEventKind.BOUNDARY_FIRST_TOUCH,
                    event_confirm_time=touch_bar.available_time,
                    first_observed_as_of_time=touch_bar.available_time,
                    symbol=symbol,
                    reference_timeframe=reference_timeframe,
                    source_object_ids=(
                        active_event.event_id,
                        snapshot.box_key_id,
                        projection.projection_id,
                        zone.zone_key_id,
                        zone.zone_snapshot_id,
                        touch_bar_id,
                    ),
                    boundary_side=side,
                    market_role=role,
                    box_key_id=snapshot.box_key_id,
                    zone_key=zone.zone_key_id,
                    zone_snapshot_id=zone.zone_snapshot_id,
                    zone_class=zone.resonance_class.value,
                    anchor_price=touch_anchor,
                    causal_atr=touch_atr,
                    facts=make_facts(
                        {
                            "active_box_created_event_id": (
                                active_event.event_id
                            ),
                            "box_created_time": snapshot.created_time,
                            "creation_causal_atr": creation_atr,
                            "selection_distance": zone.distance,
                            "selection_distance_atr": (
                                selection_distance_atr
                            ),
                            "touch_bar_id": touch_bar_id,
                            "touch_bar_index": touch_index,
                            "zone_context_count": (
                                zone.distinct_context_count
                            ),
                            "zone_quality_score": zone.quality_score,
                            "zone_selection_score": zone.selection_score,
                            "zone_source_type_count": (
                                zone.distinct_source_type_count
                            ),
                        }
                    ),
                )
            )
    return output


def _extract_events(
    run: MSACoreRun,
    config: StructuralMetricConfig,
    cutoff: datetime,
) -> tuple[StructuralMetricEvent, ...]:
    bars = validate_reference_bars(run)
    events = [
        *_structure_events(run, config, cutoff, bars),
        *_timeframe_events(run, config, cutoff, bars),
        *_break_events(run, config, cutoff, bars),
        *_active_box_events(run, config, cutoff, bars),
    ]
    events.sort(
        key=lambda item: (
            item.event_confirm_time,
            item.kind.value,
            item.metric_event_id,
        )
    )
    if len({item.metric_event_id for item in events}) != len(events):
        raise MetricEventError("metric event identities must be unique")
    return tuple(events)


def extract_structural_metric_events(
    run: MSACoreRun,
    config: StructuralMetricConfig | None = None,
    evaluation_as_of_time: datetime | None = None,
) -> tuple[StructuralMetricEvent, ...]:
    """Audit a Run, then extract only events visible by the cutoff."""

    if not isinstance(run, MSACoreRun):
        raise MetricInputError("run must be an MSACoreRun")
    resolved = resolve_metric_config(config)
    cutoff = resolve_evaluation_as_of(run, evaluation_as_of_time)
    try:
        with localcontext() as context:
            context.prec = 28
            context.rounding = ROUND_HALF_EVEN
            report = CausalAuditor().audit_run(run)
    except MSAValidationError as exc:
        raise MetricInputError(
            "MSACoreRun could not be audited safely"
        ) from exc
    if not report.passed:
        raise MetricInputError(
            "MSACoreRun failed the independent CausalAuditor"
        )
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        return _extract_events(run, resolved, cutoff)
