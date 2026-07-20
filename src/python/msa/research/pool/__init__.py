"""Public deterministic C-005 Level Pool and price clustering baseline."""

from .clustering import CLUSTER_FAMILY, LevelPoolClusterer
from .contracts import (
    SCHEMA_VERSION,
    ClusterExplanation,
    ClusterFormationEvent,
    DependencyFamilyAssignment,
    DependencyGroup,
    LevelPoolConfig,
    LevelPoolHistory,
    LevelPoolInput,
    LevelPoolReport,
    LevelPoolSnapshot,
    LinkageMode,
    ToleranceMode,
)
from .distance import range_gap
from .errors import (
    LevelPoolClusteringError,
    LevelPoolConfigurationError,
    LevelPoolInputError,
    LevelPoolSerializationError,
)
from .replay import build_history, iter_replay_events, replay_history

__all__ = [
    "CLUSTER_FAMILY",
    "SCHEMA_VERSION",
    "ClusterExplanation",
    "ClusterFormationEvent",
    "DependencyFamilyAssignment",
    "DependencyGroup",
    "LevelPoolClusterer",
    "LevelPoolClusteringError",
    "LevelPoolConfig",
    "LevelPoolConfigurationError",
    "LevelPoolHistory",
    "LevelPoolInput",
    "LevelPoolInputError",
    "LevelPoolReport",
    "LevelPoolSerializationError",
    "LevelPoolSnapshot",
    "LinkageMode",
    "ToleranceMode",
    "build_history",
    "iter_replay_events",
    "range_gap",
    "replay_history",
]
