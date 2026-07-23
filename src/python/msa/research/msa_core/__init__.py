"""Public C-007D causal MSA Core Alpha integration API."""

from .contracts import (
    SCHEMA_VERSION,
    MSACoreConfig,
    MSACoreFrameBundle,
    MSACoreRun,
    MSACoreRunReport,
)
from .errors import (
    MSACoreConfigurationError,
    MSACoreError,
    MSACoreInputError,
    MSACoreIntegrationError,
    MSACoreReplayError,
    MSACoreSerializationError,
)
from .pipeline import (
    MSACorePipeline,
    build_msa_core_run,
    iter_msa_core_frame_bundles,
)
from .replay import (
    iter_replay_msa_core_frame_bundles,
    replay_msa_core_run,
)

__all__ = [
    "SCHEMA_VERSION",
    "MSACoreConfig",
    "MSACoreConfigurationError",
    "MSACoreError",
    "MSACoreFrameBundle",
    "MSACoreInputError",
    "MSACoreIntegrationError",
    "MSACorePipeline",
    "MSACoreReplayError",
    "MSACoreRun",
    "MSACoreRunReport",
    "MSACoreSerializationError",
    "build_msa_core_run",
    "iter_msa_core_frame_bundles",
    "iter_replay_msa_core_frame_bundles",
    "replay_msa_core_run",
]
