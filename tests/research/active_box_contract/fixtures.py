from __future__ import annotations

from decimal import Decimal

from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
    ActiveBoxReplacementDistanceMode,
    ActiveBoxSelectionConfig,
    ActiveBoxSelectionHistory,
    ActiveBoxSelectionPolicy,
    build_active_box_event,
    build_selection_frame,
    build_side_decision,
    create_active_box_snapshot,
    observe_active_box_snapshot,
    project_zone,
)
from msa.research.resonance import ResonanceClass
from tests.research.resonance.fixtures import H4_PRIMARY, T1
from tests.research.resonance_scoring.fixtures import (
    score_frame as upstream_score_frame,
    scorer,
    source_history,
)


def config(**overrides: object) -> ActiveBoxSelectionConfig:
    values: dict[str, object] = {
        "engine_id": "c007c-active-box-contract",
        "engine_version": "1.0.0",
        "policy_id": "nearest-qualified-hysteresis-v1",
        "symbol": "XAUUSD",
        "output_timeframe": H4_PRIMARY.timeframe,
        "output_scale": H4_PRIMARY.scale,
        "selection_policy": ActiveBoxSelectionPolicy.NEAREST_QUALIFIED_WITH_HYSTERESIS,
        "minimum_quality_score": Decimal("0"),
        "minimum_selection_score": Decimal("0"),
        "allowed_resonance_classes": tuple(sorted(ResonanceClass, key=lambda item: item.value)),
        "replacement_distance_mode": ActiveBoxReplacementDistanceMode.ABSOLUTE,
        "absolute_replacement_distance_margin": Decimal("1"),
        "reference_replacement_distance_fraction": None,
        "minimum_replacement_selection_score_improvement": Decimal("0.1"),
        "require_expected_side": True,
        "require_positive_distance_factor": True,
        "strict": True,
    }
    values.update(overrides)
    return ActiveBoxSelectionConfig(**values)  # type: ignore[arg-type]


def score_frame(*, at=T1):
    return upstream_score_frame(at=at)


def initial_frame(*, at=T1):
    frame = score_frame(at=at)
    cfg = config()
    lower = build_side_decision(frame, cfg, frame.lower_zones[0].side)
    upper = build_side_decision(frame, cfg, frame.upper_zones[0].side)
    lower_zone = next(item for item in frame.lower_zones if item.zone_key_id == lower.selected_zone_key_id)
    upper_zone = next(item for item in frame.upper_zones if item.zone_key_id == upper.selected_zone_key_id)
    lower_projection = project_zone(frame, lower_zone, cfg, frame.as_of_time)
    upper_projection = project_zone(frame, upper_zone, cfg, frame.as_of_time)
    box = create_active_box_snapshot(frame, lower_projection, upper_projection, cfg)
    created = build_active_box_event(
        event_type=ActiveBoxEventType.CREATED,
        event_reason=ActiveBoxEventReason.INITIAL_PAIR,
        resulting_snapshot=box,
    )
    return build_selection_frame(
        source_score_frame=frame, lower_decision=lower, upper_decision=upper,
        active_box_snapshot=box, emitted_events=(created,), config=cfg,
    )


def selection_history() -> ActiveBoxSelectionHistory:
    score_history = scorer().build_batch(source_history())
    cfg = config()
    frames = []
    previous = None
    for score in score_history.frames:
        lower = build_side_decision(score, cfg, score.lower_zones[0].side, None if previous is None else previous.observed_lower_zone_key_id)
        upper = build_side_decision(score, cfg, score.upper_zones[0].side, None if previous is None else previous.observed_upper_zone_key_id)
        if previous is None:
            lower_zone = next(item for item in score.lower_zones if item.zone_key_id == lower.selected_zone_key_id)
            upper_zone = next(item for item in score.upper_zones if item.zone_key_id == upper.selected_zone_key_id)
            box = create_active_box_snapshot(
                score, project_zone(score, lower_zone, cfg, score.as_of_time),
                project_zone(score, upper_zone, cfg, score.as_of_time), cfg,
            )
            events = (build_active_box_event(event_type=ActiveBoxEventType.CREATED,event_reason=ActiveBoxEventReason.INITIAL_PAIR,resulting_snapshot=box),)
        else:
            box = observe_active_box_snapshot(score, previous, lower.selected_zone_snapshot_id, upper.selected_zone_snapshot_id)
            events = ()
        frames.append(build_selection_frame(source_score_frame=score,lower_decision=lower,upper_decision=upper,active_box_snapshot=box,emitted_events=events,config=cfg))
        previous = box
    result = tuple(frames)
    return ActiveBoxSelectionHistory(frames=result,final_frame=result[-1],events=tuple(event for frame in result for event in frame.emitted_events),
        frozen_boxes=(),source_score_history=score_history,config_snapshot=cfg)
