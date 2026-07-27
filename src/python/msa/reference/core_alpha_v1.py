"""Factories for the explicitly selected Core Alpha v1 reference profile."""

from __future__ import annotations

from msa.research.msa_core import MSACoreConfig, MSACoreError

from .contracts import (
    CoreBaselineProfile,
    _authorized_core_config_payload,
    _build_core_alpha_v1_profile,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)
from .errors import ReferenceConfigurationError


def core_alpha_v1_config() -> MSACoreConfig:
    """Return a fresh formal config with the exact owner-authorized payload."""

    try:
        config = MSACoreConfig.from_dict(_authorized_core_config_payload())
    except (MSACoreError, AttributeError, KeyError, TypeError) as exc:
        raise ReferenceConfigurationError(
            "frozen Core Alpha v1 config cannot be constructed"
        ) from exc
    return validate_core_alpha_v1_config(config)


def core_alpha_v1_profile() -> CoreBaselineProfile:
    """Return a fresh immutable authority-bound Core Alpha v1 profile."""

    profile = _build_core_alpha_v1_profile(core_alpha_v1_config())
    return validate_core_alpha_v1_profile(profile)
