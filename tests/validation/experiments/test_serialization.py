import pytest

from msa.validation.experiments import (
    ExperimentSerializationError,
    build_c008c_synthetic_dataset,
    build_protected_source_manifest,
    core_experiment_baseline,
    default_c008c_experiment_plan,
)


@pytest.mark.parametrize(
    "value",
    [
        core_experiment_baseline(),
        build_c008c_synthetic_dataset(),
        default_c008c_experiment_plan(),
        build_protected_source_manifest(),
    ],
)
def test_authority_contracts_strictly_round_trip(value: object) -> None:
    payload = value.to_dict()  # type: ignore[attr-defined]
    assert type(value).from_dict(payload) == value
    unknown = dict(payload)
    unknown["unknown"] = True
    with pytest.raises(ExperimentSerializationError):
        type(value).from_dict(unknown)
    wrong_schema = dict(payload)
    wrong_schema["schema_version"] = 2
    with pytest.raises(ExperimentSerializationError):
        type(value).from_dict(wrong_schema)
