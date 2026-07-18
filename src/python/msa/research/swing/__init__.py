"""Public C-003A Swing experiment protocol and Pivot baseline."""

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

__all__ = [
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
    "TiePolicy",
    "canonical_bar_key",
    "iter_replay_events",
    "replay_events",
]
