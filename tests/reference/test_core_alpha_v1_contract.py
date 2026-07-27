from dataclasses import FrozenInstanceError, replace

import pytest

from msa.reference import (
    CORE_ALPHA_V1_PROFILE_ID,
    CORE_ALPHA_V1_PROFILE_VERSION,
    CORE_ALPHA_V1_REFERENCE_COMMIT_SHA,
    CORE_ALPHA_V1_SOURCE_AUTHORITY,
    CoreBaselineProfile,
    ReferenceAuthorityError,
    core_alpha_v1_config,
    core_alpha_v1_profile,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)


def test_public_constants_and_factories_are_exact() -> None:
    assert CORE_ALPHA_V1_PROFILE_ID == "msa-core-alpha-v1"
    assert CORE_ALPHA_V1_PROFILE_VERSION == "1.0.0"
    assert (
        CORE_ALPHA_V1_REFERENCE_COMMIT_SHA
        == "d72c18f7994afd506e6ecf044571ccffbc695631"
    )
    assert len(CORE_ALPHA_V1_SOURCE_AUTHORITY) == 6
    assert core_alpha_v1_config().to_dict() == (
        core_alpha_v1_profile().core_config.to_dict()
    )


def test_profile_is_frozen_slotted_and_formally_valid() -> None:
    profile = core_alpha_v1_profile()
    assert isinstance(profile, CoreBaselineProfile)
    assert not hasattr(profile, "__dict__")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        profile.profile_id = "changed"  # type: ignore[misc]
    assert validate_core_alpha_v1_profile(profile) is profile
    assert validate_core_alpha_v1_config(profile.core_config) is profile.core_config


def test_direct_replace_cannot_change_authority() -> None:
    with pytest.raises(ReferenceAuthorityError):
        replace(core_alpha_v1_profile(), profile_version="1.0.1")
