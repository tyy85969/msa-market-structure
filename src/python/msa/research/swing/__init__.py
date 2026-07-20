"""Public causal Swing experiment protocols and C-003 baselines."""

from .atr_reversal import AtrReversalDetector, AtrReversalDetectorConfig
from .combined import (
    AtrStructureBreakDetector,
    AtrStructureBreakDetectorConfig,
)

from .contracts import (
    PivotDetectorConfig,
    SwingDetectionEvent,
    SwingDetectionReport,
    SwingDetectionResult,
    SwingDetector,
    SwingDetectorConfig,
    TiePolicy,
)
from .errors import (
    SwingConfigurationError,
    SwingDetectionError,
    SwingInputError,
)
from .pivot import PivotDetector, canonical_bar_key
from .replay import iter_replay_events, replay_events
from .structure_break import (
    BreakBasis,
    PendingReplacementPolicy,
    StructureBreakDetector,
    StructureBreakDetectorConfig,
)

__all__ = [
    "AtrReversalDetector",
    "AtrReversalDetectorConfig",
    "AtrStructureBreakDetector",
    "AtrStructureBreakDetectorConfig",
    "BreakBasis",
    "PendingReplacementPolicy",
    "PivotDetector",
    "PivotDetectorConfig",
    "SwingConfigurationError",
    "SwingDetectionError",
    "SwingDetectionEvent",
    "SwingDetectionReport",
    "SwingDetectionResult",
    "SwingDetector",
    "SwingDetectorConfig",
    "SwingInputError",
    "StructureBreakDetector",
    "StructureBreakDetectorConfig",
    "TiePolicy",
    "canonical_bar_key",
    "iter_replay_events",
    "replay_events",
]
