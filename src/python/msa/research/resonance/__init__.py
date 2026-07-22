"""Public causal C-007A multi-context resonance-frame framework."""

from .assembler import ResonanceFrameAssembler
from .contracts import (
    SCHEMA_VERSION,
    ReferencePriceField,
    ReferencePriceSnapshot,
    ResonanceContext,
    ResonanceContextState,
    ResonanceEvidence,
    ResonanceEvidencePolicy,
    ResonanceEvidenceTier,
    ResonanceFrame,
    ResonanceFrameConfig,
    ResonanceFrameHistory,
    ResonanceFrameInput,
    ResonanceFrameReport,
)
from .errors import (
    ResonanceFrameConfigurationError,
    ResonanceFrameEngineError,
    ResonanceFrameInputError,
    ResonanceFrameSerializationError,
)
from .replay import build_history, iter_replay_frames, replay_history

__all__ = [
    "SCHEMA_VERSION",
    "ReferencePriceField",
    "ReferencePriceSnapshot",
    "ResonanceContext",
    "ResonanceContextState",
    "ResonanceEvidence",
    "ResonanceEvidencePolicy",
    "ResonanceEvidenceTier",
    "ResonanceFrame",
    "ResonanceFrameAssembler",
    "ResonanceFrameConfig",
    "ResonanceFrameConfigurationError",
    "ResonanceFrameEngineError",
    "ResonanceFrameHistory",
    "ResonanceFrameInput",
    "ResonanceFrameInputError",
    "ResonanceFrameReport",
    "ResonanceFrameSerializationError",
    "build_history",
    "iter_replay_frames",
    "replay_history",
]
