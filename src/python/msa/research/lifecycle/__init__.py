"""Public causal C-006A structure lifecycle event engine."""

from .contracts import (
    SCHEMA_VERSION,
    LifecycleConfig,
    LifecycleEvent,
    LifecycleEventType,
    LifecycleHistory,
    LifecycleInput,
    LifecycleReport,
    LifecycleSnapshot,
    LifecycleSubjectState,
    RetirementReason,
)
from .engine import LifecycleEngine
from .errors import (
    LifecycleConfigurationError,
    LifecycleEngineError,
    LifecycleInputError,
    LifecycleSerializationError,
)
from .replay import build_history, iter_replay_events, replay_history

__all__ = [
    "SCHEMA_VERSION", "LifecycleConfig", "LifecycleConfigurationError",
    "LifecycleEngine", "LifecycleEngineError", "LifecycleEvent",
    "LifecycleEventType", "LifecycleHistory", "LifecycleInput",
    "LifecycleInputError", "LifecycleReport", "LifecycleSerializationError",
    "LifecycleSnapshot", "LifecycleSubjectState", "RetirementReason",
    "build_history", "iter_replay_events", "replay_history",
]
