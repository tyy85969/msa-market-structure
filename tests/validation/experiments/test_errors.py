from dataclasses import replace

import pytest

from msa.validation import SyntheticScenarioKind
from msa.validation.experiments import (
    ExperimentConfigurationError,
    ExperimentDatasetError,
    ExperimentEvidenceError,
    ExperimentGateError,
    ExperimentInputError,
    ExperimentPlanError,
    ExperimentProtectedSourceError,
    ExperimentSerializationError,
    ExperimentValidationError,
    build_protected_source_manifest,
    build_synthetic_source_input,
    core_experiment_baseline,
    default_c008c_experiment_plan,
    validate_protected_source_manifest,
    write_c008c_authority_evidence,
)


def test_error_hierarchy_is_public_and_finite() -> None:
    for error in (
        ExperimentConfigurationError,
        ExperimentInputError,
        ExperimentDatasetError,
        ExperimentPlanError,
        ExperimentGateError,
        ExperimentProtectedSourceError,
        ExperimentEvidenceError,
        ExperimentSerializationError,
    ):
        assert issubclass(error, ExperimentValidationError)


def test_axis_direct_construction_fails_closed() -> None:
    axis = default_c008c_experiment_plan().axes[0]
    with pytest.raises(ExperimentConfigurationError):
        replace(axis, values=(object(), object(), object()))


def test_ablation_direct_construction_fails_closed() -> None:
    ablation = default_c008c_experiment_plan().ablations[0]
    with pytest.raises(ExperimentPlanError):
        replace(ablation, baseline_values=[])


@pytest.mark.parametrize("field", ("increment_steps", "gate_definitions"))
def test_plan_nested_direct_construction_fails_closed(field: str) -> None:
    plan = default_c008c_experiment_plan()
    with pytest.raises(ExperimentPlanError):
        replace(plan, **{field: (object(),)})


def test_baseline_direct_construction_fails_closed() -> None:
    baseline = core_experiment_baseline()
    with pytest.raises(ExperimentConfigurationError):
        replace(baseline, metric_config_snapshot=object())


@pytest.mark.parametrize(
    ("kind", "seed"),
    (
        ("SINGLE_TREND", 0),
        (SyntheticScenarioKind.SINGLE_TREND, 0.0),
        (SyntheticScenarioKind.SINGLE_TREND, 4),
    ),
)
def test_synthetic_builder_invalid_inputs_use_domain_error(
    kind: object, seed: object
) -> None:
    with pytest.raises(ExperimentInputError):
        build_synthetic_source_input(kind, seed)  # type: ignore[arg-type]


def test_protected_source_invalid_roots_use_domain_errors() -> None:
    manifest = build_protected_source_manifest()
    with pytest.raises(ExperimentProtectedSourceError):
        build_protected_source_manifest("bad-root")  # type: ignore[arg-type]
    with pytest.raises(ExperimentProtectedSourceError):
        validate_protected_source_manifest(
            manifest, "bad-root"  # type: ignore[arg-type]
        )
    with pytest.raises(ExperimentEvidenceError):
        write_c008c_authority_evidence(
            "bad-root", check=True  # type: ignore[arg-type]
        )


def test_protected_source_read_failure_uses_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("denied")

    monkeypatch.setattr(Path, "rglob", fail)
    with pytest.raises(ExperimentProtectedSourceError):
        build_protected_source_manifest()
