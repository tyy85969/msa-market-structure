"""Stateless causal C-007C Active Box selector engine."""

from __future__ import annotations

from dataclasses import dataclass

from msa.domain import ActiveBox, ActiveBoxStatus, BoundarySide
from msa.research.resonance import (
    ResonanceScoreFrame,
    ResonanceScoreHistory,
    ResonanceZone,
)

from .contracts import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
    ActiveBoxSelectionConfig,
    ActiveBoxSelectionFrame,
    ActiveBoxSelectionHistory,
    ActiveBoxSideDecision,
    ActiveBoxSnapshot,
    build_active_box_event,
    build_selection_frame,
    create_active_box_snapshot,
    freeze_active_box_snapshot,
    observe_active_box_snapshot,
)
from .errors import ActiveBoxEngineError
from .policy import build_side_decision
from .projection import project_zone


def _symbol(frame: ResonanceScoreFrame) -> str:
    return frame.source_frame.config_snapshot.symbol


def _validate_score_frame(
    frame: object,
    config: ActiveBoxSelectionConfig,
) -> ResonanceScoreFrame:
    if not isinstance(frame, ResonanceScoreFrame):
        raise ActiveBoxEngineError(
            "source_score_frame must be a ResonanceScoreFrame"
        )
    try:
        restored = ResonanceScoreFrame.from_dict(frame.to_dict())
    except (
        AttributeError,
        KeyError,
        AssertionError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise ActiveBoxEngineError(
            "source_score_frame is not a formally valid ResonanceScoreFrame"
        ) from exc
    if restored != frame:
        raise ActiveBoxEngineError(
            "source_score_frame payload is not formally self-consistent"
        )
    if _symbol(frame) != config.symbol:
        raise ActiveBoxEngineError(
            "selector config symbol conflicts with source ScoreFrame"
        )
    return frame


def _validate_previous(
    previous: object,
    frame: ResonanceScoreFrame,
    config: ActiveBoxSelectionConfig,
) -> ActiveBoxSnapshot | None:
    if previous is None:
        return None
    if not isinstance(previous, ActiveBoxSnapshot):
        raise ActiveBoxEngineError(
            "previous_active must be None or an ActiveBoxSnapshot"
        )
    if (
        not isinstance(previous.active_box, ActiveBox)
        or not isinstance(previous.config_snapshot, ActiveBoxSelectionConfig)
        or not isinstance(previous.observed_lower_zone_key_id, str)
        or not isinstance(previous.observed_upper_zone_key_id, str)
    ):
        raise ActiveBoxEngineError(
            "previous_active nested state is not formally typed"
        )
    if previous.active_box.status is not ActiveBoxStatus.ACTIVE:
        raise ActiveBoxEngineError("previous_active must have ACTIVE status")
    if previous.config_snapshot != config:
        raise ActiveBoxEngineError(
            "previous_active config must equal selector config"
        )
    if (
        previous.active_box.symbol != config.symbol
        or previous.active_box.timeframe is not config.output_timeframe
        or previous.active_box.scale != config.output_scale
    ):
        raise ActiveBoxEngineError(
            "previous_active output context conflicts with selector config"
        )
    if previous.active_box.as_of_time >= frame.as_of_time:
        raise ActiveBoxEngineError(
            "previous_active AsOf must be strictly earlier than current Frame"
        )
    if (
        not previous.observed_lower_zone_key_id.strip()
        or not previous.observed_upper_zone_key_id.strip()
    ):
        raise ActiveBoxEngineError(
            "previous_active stable Zone keys must be non-empty"
        )
    try:
        restored = ActiveBoxSnapshot.from_dict(previous.to_dict())
    except (
        AttributeError,
        KeyError,
        AssertionError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise ActiveBoxEngineError(
            "previous_active is not a formally valid ActiveBoxSnapshot"
        ) from exc
    if restored != previous:
        raise ActiveBoxEngineError(
            "previous_active payload is not formally self-consistent"
        )
    return previous


def _resolve_selected_zone(
    source_score_frame: ResonanceScoreFrame,
    decision: ActiveBoxSideDecision,
) -> ResonanceZone | None:
    key = decision.selected_zone_key_id
    snapshot = decision.selected_zone_snapshot_id
    if (key is None) != (snapshot is None):
        raise ActiveBoxEngineError(
            "selected Zone key and snapshot must be both present or absent"
        )
    if key is None:
        return None
    side_zones = (
        source_score_frame.lower_zones
        if decision.side is BoundarySide.LOWER
        else source_score_frame.upper_zones
    )
    key_matches = tuple(zone for zone in side_zones if zone.zone_key_id == key)
    if len(key_matches) != 1:
        raise ActiveBoxEngineError(
            "selected stable Zone key must resolve exactly once on its side"
        )
    exact_matches = tuple(
        zone
        for zone in key_matches
        if zone.zone_snapshot_id == snapshot and zone.side is decision.side
    )
    if len(exact_matches) != 1:
        raise ActiveBoxEngineError(
            "selected Zone key/snapshot/side must resolve exactly once"
        )
    if exact_matches[0] not in source_score_frame.zones:
        raise ActiveBoxEngineError(
            "selected Zone must belong to the current source ScoreFrame"
        )
    return exact_matches[0]


def _create_snapshot(
    frame: ResonanceScoreFrame,
    lower_zone: ResonanceZone,
    upper_zone: ResonanceZone,
    config: ActiveBoxSelectionConfig,
) -> ActiveBoxSnapshot:
    lower_projection = project_zone(
        frame, lower_zone, config, frame.as_of_time
    )
    upper_projection = project_zone(
        frame, upper_zone, config, frame.as_of_time
    )
    if lower_projection.boundary.boundary_side is not BoundarySide.LOWER:
        raise ActiveBoxEngineError("lower Projection side must be LOWER")
    if upper_projection.boundary.boundary_side is not BoundarySide.UPPER:
        raise ActiveBoxEngineError("upper Projection side must be UPPER")
    return create_active_box_snapshot(
        frame, lower_projection, upper_projection, config
    )


@dataclass(frozen=True, slots=True)
class ActiveBoxSelector:
    """Execute the frozen C-007C policy without retaining mutable state."""

    config: ActiveBoxSelectionConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, ActiveBoxSelectionConfig):
            raise ActiveBoxEngineError(
                "config must be an ActiveBoxSelectionConfig"
            )

    def select_frame(
        self,
        source_score_frame: ResonanceScoreFrame,
        previous_active: ActiveBoxSnapshot | None = None,
    ) -> ActiveBoxSelectionFrame:
        frame = _validate_score_frame(source_score_frame, self.config)
        previous = _validate_previous(previous_active, frame, self.config)
        current_lower = (
            None if previous is None else previous.observed_lower_zone_key_id
        )
        current_upper = (
            None if previous is None else previous.observed_upper_zone_key_id
        )
        lower_decision = build_side_decision(
            frame, self.config, BoundarySide.LOWER, current_lower
        )
        upper_decision = build_side_decision(
            frame, self.config, BoundarySide.UPPER, current_upper
        )
        lower_zone = _resolve_selected_zone(frame, lower_decision)
        upper_zone = _resolve_selected_zone(frame, upper_decision)
        complete = lower_zone is not None and upper_zone is not None

        active: ActiveBoxSnapshot | None
        events = ()
        if previous is None:
            if complete:
                active = _create_snapshot(
                    frame, lower_zone, upper_zone, self.config
                )
                events = (
                    build_active_box_event(
                        event_type=ActiveBoxEventType.CREATED,
                        event_reason=ActiveBoxEventReason.INITIAL_PAIR,
                        resulting_snapshot=active,
                    ),
                )
            else:
                active = None
        elif not complete:
            frozen = freeze_active_box_snapshot(frame, previous)
            active = None
            events = (
                build_active_box_event(
                    event_type=ActiveBoxEventType.FROZEN,
                    event_reason=ActiveBoxEventReason.PAIR_UNAVAILABLE,
                    previous_snapshot=previous,
                    resulting_snapshot=frozen,
                ),
            )
        else:
            previous_pair = (
                previous.observed_lower_zone_key_id,
                previous.observed_upper_zone_key_id,
            )
            selected_pair = (
                lower_decision.selected_zone_key_id,
                upper_decision.selected_zone_key_id,
            )
            if selected_pair == previous_pair:
                active = observe_active_box_snapshot(
                    frame,
                    previous,
                    lower_decision.selected_zone_snapshot_id,
                    upper_decision.selected_zone_snapshot_id,
                )
            else:
                frozen = freeze_active_box_snapshot(frame, previous)
                active = _create_snapshot(
                    frame, lower_zone, upper_zone, self.config
                )
                events = (
                    build_active_box_event(
                        event_type=ActiveBoxEventType.FROZEN,
                        event_reason=ActiveBoxEventReason.PAIR_CHANGED,
                        previous_snapshot=previous,
                        resulting_snapshot=frozen,
                    ),
                    build_active_box_event(
                        event_type=ActiveBoxEventType.CREATED,
                        event_reason=ActiveBoxEventReason.PAIR_CHANGED,
                        resulting_snapshot=active,
                    ),
                )
        return build_selection_frame(
            source_score_frame=frame,
            lower_decision=lower_decision,
            upper_decision=upper_decision,
            active_box_snapshot=active,
            emitted_events=events,
            config=self.config,
        )

    def build_batch(
        self,
        source_score_history: ResonanceScoreHistory,
    ) -> ActiveBoxSelectionHistory:
        if not isinstance(source_score_history, ResonanceScoreHistory):
            raise ActiveBoxEngineError(
                "source_score_history must be a ResonanceScoreHistory"
            )
        if not source_score_history.frames:
            raise ActiveBoxEngineError(
                "source_score_history.frames must not be empty"
            )
        if _symbol(source_score_history.frames[0]) != self.config.symbol:
            raise ActiveBoxEngineError(
                "selector config symbol conflicts with source ScoreHistory"
            )
        frames: list[ActiveBoxSelectionFrame] = []
        previous: ActiveBoxSnapshot | None = None
        for score_frame in source_score_history.frames:
            selected = self.select_frame(score_frame, previous)
            frames.append(selected)
            previous = selected.active_box_snapshot
        result = tuple(frames)
        events = tuple(
            event for frame in result for event in frame.emitted_events
        )
        frozen = tuple(
            event.resulting_box_snapshot
            for event in events
            if event.event_type is ActiveBoxEventType.FROZEN
        )
        return ActiveBoxSelectionHistory(
            frames=result,
            final_frame=result[-1],
            events=events,
            frozen_boxes=frozen,
            source_score_history=source_score_history,
            config_snapshot=self.config,
        )


def build_active_box_history(
    selector: ActiveBoxSelector,
    source_score_history: ResonanceScoreHistory,
) -> ActiveBoxSelectionHistory:
    if not isinstance(selector, ActiveBoxSelector):
        raise ActiveBoxEngineError("selector must be an ActiveBoxSelector")
    return selector.build_batch(source_score_history)
