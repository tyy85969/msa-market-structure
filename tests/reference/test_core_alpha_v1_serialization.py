import pytest

from msa.reference import (
    CoreBaselineProfile,
    ReferenceSerializationError,
    core_alpha_v1_profile,
)


def test_profile_strict_round_trip() -> None:
    profile = core_alpha_v1_profile()
    assert CoreBaselineProfile.from_dict(profile.to_dict()) == profile


@pytest.mark.parametrize("case", ("missing", "extra", "schema"))
def test_profile_rejects_non_exact_serialized_payload(case: str) -> None:
    payload = core_alpha_v1_profile().to_dict()
    if case == "missing":
        payload.pop("assumptions")
    elif case == "extra":
        payload["unexpected"] = "field"
    else:
        payload["schema_version"] = 2
    with pytest.raises(ReferenceSerializationError):
        CoreBaselineProfile.from_dict(payload)


def test_profile_serializes_tuples_as_ordered_lists() -> None:
    payload = core_alpha_v1_profile().to_dict()
    assert isinstance(payload["source_authority"], list)
    assert isinstance(payload["assumptions"], list)
