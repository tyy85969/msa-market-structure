from dataclasses import replace

import pytest

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
    core_experiment_baseline,
    default_c008c_experiment_plan,
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
