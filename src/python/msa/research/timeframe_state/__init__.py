"""Public causal C-006B per-timeframe structure state engine."""

from .contracts import (
    CROSSED_PAIR_OLDER_SIDE,
    SCHEMA_VERSION,
    BoundarySelectionExplanation,
    BoundarySelectionKey,
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateEvent,
    TimeframeStateEventType,
    TimeframeStateHistory,
    TimeframeStateInput,
    TimeframeStateReport,
    TimeframeStateSnapshot,
)
from .engine import TimeframeStateEngine
from .errors import (
    TimeframeStateConfigurationError,
    TimeframeStateEngineError,
    TimeframeStateInputError,
    TimeframeStateSerializationError,
)
from .replay import build_history, iter_replay_events, replay_history

__all__ = [
    "BoundarySelectionExplanation",
    "BoundarySelectionKey",
    "CROSSED_PAIR_OLDER_SIDE",
    "SCHEMA_VERSION",
    "TimeframeSelectionPolicy",
    "TimeframeStateConfig",
    "TimeframeStateConfigurationError",
    "TimeframeStateEngine",
    "TimeframeStateEngineError",
    "TimeframeStateEvent",
    "TimeframeStateEventType",
    "TimeframeStateHistory",
    "TimeframeStateInput",
    "TimeframeStateInputError",
    "TimeframeStateReport",
    "TimeframeStateSerializationError",
    "TimeframeStateSnapshot",
    "build_history",
    "iter_replay_events",
    "replay_history",
]
