"""Public C-007C causal Active Box contract API."""

from .contracts import (
    ActiveBoxEvent,
    ActiveBoxEventReason,
    ActiveBoxEventType,
    ActiveBoxReplacementDistanceMode,
    ActiveBoxSelectionConfig,
    ActiveBoxSelectionFrame,
    ActiveBoxSelectionHistory,
    ActiveBoxSelectionKey,
    ActiveBoxSelectionPolicy,
    ActiveBoxSelectionReport,
    ActiveBoxSideAction,
    ActiveBoxSideDecision,
    ActiveBoxSnapshot,
    ActiveBoxZoneProjection,
    ZoneEligibility,
    ZoneEligibilityReason,
    build_active_box_event,
    build_selection_frame,
    create_active_box_snapshot,
    freeze_active_box_snapshot,
    observe_active_box_snapshot,
)
from .errors import (
    ActiveBoxConfigurationError,
    ActiveBoxContractError,
    ActiveBoxEngineError,
    ActiveBoxInputError,
    ActiveBoxProjectionError,
    ActiveBoxReplayError,
    ActiveBoxSerializationError,
)
from .engine import ActiveBoxSelector, build_active_box_history
from .policy import build_side_decision, evaluate_zone, selection_key
from .projection import project_zone
from .replay import iter_replay_active_box_frames, replay_active_box_history

__all__ = [
    "ActiveBoxConfigurationError", "ActiveBoxContractError", "ActiveBoxEngineError",
    "ActiveBoxEvent",
    "ActiveBoxEventReason", "ActiveBoxEventType", "ActiveBoxInputError",
    "ActiveBoxProjectionError", "ActiveBoxReplayError",
    "ActiveBoxReplacementDistanceMode",
    "ActiveBoxSelectionConfig", "ActiveBoxSelectionFrame",
    "ActiveBoxSelectionHistory", "ActiveBoxSelectionKey",
    "ActiveBoxSelectionPolicy", "ActiveBoxSelectionReport",
    "ActiveBoxSerializationError", "ActiveBoxSideAction",
    "ActiveBoxSelector", "ActiveBoxSideDecision", "ActiveBoxSnapshot",
    "ActiveBoxZoneProjection",
    "ZoneEligibility", "ZoneEligibilityReason", "build_active_box_event",
    "build_active_box_history", "build_selection_frame", "build_side_decision",
    "create_active_box_snapshot", "evaluate_zone",
    "freeze_active_box_snapshot", "iter_replay_active_box_frames",
    "observe_active_box_snapshot", "project_zone", "replay_active_box_history",
    "selection_key",
]
