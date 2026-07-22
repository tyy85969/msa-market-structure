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
    ActiveBoxInputError,
    ActiveBoxProjectionError,
    ActiveBoxSerializationError,
)
from .policy import build_side_decision, evaluate_zone, selection_key
from .projection import project_zone

__all__ = [
    "ActiveBoxConfigurationError", "ActiveBoxContractError", "ActiveBoxEvent",
    "ActiveBoxEventReason", "ActiveBoxEventType", "ActiveBoxInputError",
    "ActiveBoxProjectionError", "ActiveBoxReplacementDistanceMode",
    "ActiveBoxSelectionConfig", "ActiveBoxSelectionFrame",
    "ActiveBoxSelectionHistory", "ActiveBoxSelectionKey",
    "ActiveBoxSelectionPolicy", "ActiveBoxSelectionReport",
    "ActiveBoxSerializationError", "ActiveBoxSideAction",
    "ActiveBoxSideDecision", "ActiveBoxSnapshot", "ActiveBoxZoneProjection",
    "ZoneEligibility", "ZoneEligibilityReason", "build_active_box_event",
    "build_selection_frame", "build_side_decision", "create_active_box_snapshot", "evaluate_zone",
    "freeze_active_box_snapshot", "observe_active_box_snapshot", "project_zone",
    "selection_key",
]
