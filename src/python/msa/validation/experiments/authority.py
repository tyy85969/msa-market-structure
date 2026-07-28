"""Source-bound validators for the unique frozen C-008C-A authorities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from .baseline import core_experiment_baseline
from .contracts import (
    CoreExperimentBaseline,
    ExperimentDatasetManifest,
    ExperimentGateDefinition,
    ExperimentPlan,
)
from .dataset import build_c008c_synthetic_dataset
from .errors import (
    ExperimentConfigurationError,
    ExperimentDatasetError,
    ExperimentGateError,
    ExperimentPlanError,
)
from .gates import default_c008c_gate_registry
from .plan import default_c008c_experiment_plan


AuthorityT = TypeVar(
    "AuthorityT",
    CoreExperimentBaseline,
    ExperimentDatasetManifest,
    ExperimentPlan,
)


def _validate_single_authority(
    value: object,
    *,
    expected_type: type[AuthorityT],
    factory: Callable[[], AuthorityT],
    error_type: type[ValueError],
    label: str,
) -> AuthorityT:
    if not isinstance(value, expected_type):
        raise error_type(f"{label} must have its formal contract type")
    try:
        original_payload = value.to_dict()
    except (
        AssertionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise error_type(f"{label} payload cannot be read") from exc
    if not isinstance(original_payload, Mapping):
        raise error_type(f"{label} payload must be a mapping")
    try:
        restored = expected_type.from_dict(original_payload)
        restored_payload = restored.to_dict()
        authority = factory()
        authority_payload = authority.to_dict()
    except (
        AssertionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise error_type(f"{label} formal validation failed") from exc
    if restored != value or restored_payload != original_payload:
        raise error_type(f"{label} does not round-trip exactly")
    if original_payload != authority_payload:
        raise error_type(f"{label} differs from the frozen source authority")
    return value


def validate_core_experiment_baseline(
    baseline: CoreExperimentBaseline,
) -> CoreExperimentBaseline:
    return _validate_single_authority(
        baseline,
        expected_type=CoreExperimentBaseline,
        factory=core_experiment_baseline,
        error_type=ExperimentConfigurationError,
        label="CoreExperimentBaseline",
    )


def validate_c008c_synthetic_dataset(
    dataset: ExperimentDatasetManifest,
) -> ExperimentDatasetManifest:
    return _validate_single_authority(
        dataset,
        expected_type=ExperimentDatasetManifest,
        factory=build_c008c_synthetic_dataset,
        error_type=ExperimentDatasetError,
        label="ExperimentDatasetManifest",
    )


def validate_c008c_gate_registry(
    registry: tuple[ExperimentGateDefinition, ...],
) -> tuple[ExperimentGateDefinition, ...]:
    if (
        not isinstance(registry, tuple)
        or len(registry) != 27
        or any(
            not isinstance(item, ExperimentGateDefinition)
            for item in registry
        )
    ):
        raise ExperimentGateError(
            "gate registry must contain 27 formal definitions"
        )
    try:
        original_payloads = tuple(item.to_dict() for item in registry)
    except (
        AssertionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentGateError("gate registry payload cannot be read") from exc
    try:
        restored = tuple(
            ExperimentGateDefinition.from_dict(item)
            for item in original_payloads
        )
        restored_payloads = tuple(item.to_dict() for item in restored)
        authority = default_c008c_gate_registry()
        authority_payloads = tuple(item.to_dict() for item in authority)
    except (
        AssertionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentGateError("gate registry validation failed") from exc
    if restored != registry or restored_payloads != original_payloads:
        raise ExperimentGateError("gate registry does not round-trip exactly")
    if original_payloads != authority_payloads:
        raise ExperimentGateError(
            "gate registry differs from the frozen source authority"
        )
    return registry


def validate_c008c_experiment_plan(plan: ExperimentPlan) -> ExperimentPlan:
    return _validate_single_authority(
        plan,
        expected_type=ExperimentPlan,
        factory=default_c008c_experiment_plan,
        error_type=ExperimentPlanError,
        label="ExperimentPlan",
    )


__all__ = [
    "validate_c008c_experiment_plan",
    "validate_c008c_gate_registry",
    "validate_c008c_synthetic_dataset",
    "validate_core_experiment_baseline",
]
