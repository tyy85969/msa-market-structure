"""Public C-004 periodic-extreme and historical-reaction baselines."""

from .contracts import (
    HistoricalReactionConfig,
    LevelGenerationEvent,
    LevelGenerationInput,
    LevelGenerationReport,
    LevelGenerationResult,
    LevelGenerator,
    LevelGeneratorConfig,
    PeriodicExtremeConfig,
)
from .errors import (
    LevelConfigurationError,
    LevelGenerationError,
    LevelInputError,
)
from .periodic import PeriodicExtremeGenerator
from .reaction import HistoricalReactionGenerator
from .replay import iter_replay_events, replay_events

__all__ = [
    "HistoricalReactionConfig",
    "HistoricalReactionGenerator",
    "LevelConfigurationError",
    "LevelGenerationError",
    "LevelGenerationEvent",
    "LevelGenerationInput",
    "LevelGenerationReport",
    "LevelGenerationResult",
    "LevelGenerator",
    "LevelGeneratorConfig",
    "LevelInputError",
    "PeriodicExtremeConfig",
    "PeriodicExtremeGenerator",
    "iter_replay_events",
    "replay_events",
]
