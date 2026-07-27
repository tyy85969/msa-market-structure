"""Public formal reference-profile API."""

from .contracts import (
    CORE_ALPHA_V1_PROFILE_ID,
    CORE_ALPHA_V1_PROFILE_VERSION,
    CORE_ALPHA_V1_REFERENCE_COMMIT_SHA,
    CORE_ALPHA_V1_SOURCE_AUTHORITY,
    CoreBaselineProfile,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)
from .core_alpha_v1 import core_alpha_v1_config, core_alpha_v1_profile
from .errors import (
    MSAReferenceError,
    ReferenceAuthorityError,
    ReferenceConfigurationError,
    ReferenceInputError,
    ReferenceSerializationError,
)

__all__ = [
    "CORE_ALPHA_V1_PROFILE_ID",
    "CORE_ALPHA_V1_PROFILE_VERSION",
    "CORE_ALPHA_V1_REFERENCE_COMMIT_SHA",
    "CORE_ALPHA_V1_SOURCE_AUTHORITY",
    "CoreBaselineProfile",
    "MSAReferenceError",
    "ReferenceAuthorityError",
    "ReferenceConfigurationError",
    "ReferenceInputError",
    "ReferenceSerializationError",
    "core_alpha_v1_config",
    "core_alpha_v1_profile",
    "validate_core_alpha_v1_config",
    "validate_core_alpha_v1_profile",
]
