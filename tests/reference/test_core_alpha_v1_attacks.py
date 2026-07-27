import copy

import pytest

from msa.reference import (
    CoreBaselineProfile,
    MSAReferenceError,
    core_alpha_v1_config,
    core_alpha_v1_profile,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)
from msa.reference.identity import semantic_id


def _resign(payload: dict[str, object]) -> dict[str, object]:
    identity = {
        key: value
        for key, value in payload.items()
        if key != "profile_semantic_id"
    }
    payload["profile_semantic_id"] = semantic_id(
        "core-baseline-profile-v1-", identity
    )
    return payload


def _attack_payload(case: str) -> dict[str, object]:
    payload = copy.deepcopy(core_alpha_v1_profile().to_dict())
    config = payload["core_config"]
    assert isinstance(config, dict)
    if case == "profile_id":
        payload["profile_id"] = "msa-core-alpha-v2"
    elif case == "profile_version":
        payload["profile_version"] = "1.0.1"
    elif case == "reference_commit":
        payload["reference_commit_sha"] = "0" * 40
    elif case == "authority_delete":
        payload["source_authority"] = payload["source_authority"][:-1]  # type: ignore[index]
    elif case == "authority_reorder":
        payload["source_authority"] = list(
            reversed(payload["source_authority"])  # type: ignore[arg-type]
        )
    elif case == "assumptions":
        payload["assumptions"] = ["forged assumption"]
    elif case == "engine_id":
        config["engine_id"] = "forged-core"
    elif case == "engine_version":
        config["engine_version"] = "9.9.9"
    elif case == "policy_id":
        config["policy_id"] = "forged-policy"
    elif case == "frame_nested":
        config["frame_config"]["engine_id"] = "forged-frame"  # type: ignore[index]
    elif case == "scoring_nested":
        config["scoring_config"]["dependency_repeat_credit"] = "0.26"  # type: ignore[index]
    elif case == "active_nested":
        config["active_box_config"]["minimum_selection_score"] = "0.26"  # type: ignore[index]
    elif case == "strict_false":
        config["strict"] = False
    elif case == "digest":
        payload["core_config_payload_digest"] = "0" * 64
    elif case == "digest_mismatch":
        payload["core_config_payload_digest"] = "f" * 64
    elif case == "resigned_non_authoritative":
        config["active_box_config"]["minimum_quality_score"] = "0.1"  # type: ignore[index]
    elif case == "config_missing":
        config.pop("policy_id")
    elif case == "config_extra":
        config["unexpected"] = "field"
    elif case == "config_schema":
        config["schema_version"] = 2
    else:
        raise AssertionError(f"unknown attack: {case}")
    return _resign(payload)


@pytest.mark.parametrize(
    "case",
    (
        "profile_id",
        "profile_version",
        "reference_commit",
        "authority_delete",
        "authority_reorder",
        "assumptions",
        "engine_id",
        "engine_version",
        "policy_id",
        "frame_nested",
        "scoring_nested",
        "active_nested",
        "strict_false",
        "digest",
        "digest_mismatch",
        "resigned_non_authoritative",
        "config_missing",
        "config_extra",
        "config_schema",
    ),
)
def test_complete_resigned_attacks_fail_closed(case: str) -> None:
    with pytest.raises(MSAReferenceError):
        CoreBaselineProfile.from_dict(_attack_payload(case))


def test_non_profile_and_non_config_inputs_fail_closed() -> None:
    with pytest.raises(MSAReferenceError):
        validate_core_alpha_v1_profile(object())
    with pytest.raises(MSAReferenceError):
        validate_core_alpha_v1_config(object())


def test_mutated_formal_objects_cannot_bypass_authority() -> None:
    profile = core_alpha_v1_profile()
    object.__setattr__(profile, "profile_semantic_id", "0" * 64)
    with pytest.raises(MSAReferenceError):
        validate_core_alpha_v1_profile(profile)

    config = core_alpha_v1_config()
    object.__setattr__(config, "engine_id", "forged-core")
    with pytest.raises(MSAReferenceError):
        validate_core_alpha_v1_config(config)


@pytest.mark.parametrize(
    ("field_name", "corrupted_value"),
    (
        ("core_config", object()),
        ("core_config", None),
        ("source_authority", object()),
        ("source_authority", None),
        ("assumptions", object()),
        ("assumptions", None),
        ("profile_semantic_id", []),
    ),
)
def test_post_construction_corrupted_profile_fields_fail_closed(
    field_name: str, corrupted_value: object
) -> None:
    profile = core_alpha_v1_profile()
    object.__setattr__(profile, field_name, corrupted_value)

    with pytest.raises(MSAReferenceError) as caught:
        validate_core_alpha_v1_profile(profile)

    assert not isinstance(
        caught.value, (AttributeError, KeyError, TypeError, AssertionError)
    )


@pytest.mark.parametrize(
    "child_field",
    ("frame_config", "scoring_config", "active_box_config"),
)
def test_post_construction_corrupted_profile_child_configs_fail_closed(
    child_field: str,
) -> None:
    profile = core_alpha_v1_profile()
    object.__setattr__(profile.core_config, child_field, object())

    with pytest.raises(MSAReferenceError) as caught:
        validate_core_alpha_v1_profile(profile)

    assert not isinstance(
        caught.value, (AttributeError, KeyError, TypeError, AssertionError)
    )


@pytest.mark.parametrize(
    ("target", "field_name", "corrupted_value"),
    (
        ("config", "engine_id", object()),
        ("config", "frame_config", object()),
        ("config", "scoring_config", object()),
        ("config", "active_box_config", object()),
        ("frame", "contexts", (object(),)),
        ("scoring", "context_weights", (object(),)),
        ("active", "allowed_resonance_classes", (object(),)),
    ),
)
def test_post_construction_corrupted_configs_fail_closed(
    target: str, field_name: str, corrupted_value: object
) -> None:
    config = core_alpha_v1_config()
    subjects = {
        "config": config,
        "frame": config.frame_config,
        "scoring": config.scoring_config,
        "active": config.active_box_config,
    }
    object.__setattr__(subjects[target], field_name, corrupted_value)

    with pytest.raises(MSAReferenceError) as caught:
        validate_core_alpha_v1_config(config)

    assert not isinstance(
        caught.value, (AttributeError, KeyError, TypeError, AssertionError)
    )
