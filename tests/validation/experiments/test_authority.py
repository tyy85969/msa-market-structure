from copy import deepcopy
from decimal import Decimal
from typing import Any, Callable

import pytest

from msa.validation.experiments import (
    CoreExperimentBaseline,
    ExperimentConfigurationError,
    ExperimentDatasetError,
    ExperimentDatasetManifest,
    ExperimentGateDefinition,
    ExperimentGateError,
    ExperimentPlan,
    ExperimentPlanError,
    ExperimentProtectedSourceError,
    ProtectedSourceManifest,
    build_c008c_synthetic_dataset,
    build_protected_source_manifest,
    core_experiment_baseline,
    default_c008c_experiment_plan,
    default_c008c_gate_registry,
    validate_c008c_experiment_plan,
    validate_c008c_gate_registry,
    validate_c008c_synthetic_dataset,
    validate_core_experiment_baseline,
    validate_protected_source_manifest,
)
from msa.validation.experiments.identity import digest

from .resigning import resign_authority_payload


def _resign_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_case(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_axis(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_variant(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_gate(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_plan(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _resign_protected(payload: dict[str, Any]) -> dict[str, Any]:
    return resign_authority_payload(payload)


def _replace_variant_id(
    plan: dict[str, Any], index: int, variant: dict[str, Any]
) -> None:
    old_id = plan["variants"][index]["variant_id"]
    new_id = variant["variant_id"]
    plan["variants"][index] = variant
    scope_ids = plan["execution_scope_policy"]["variant_ids"]
    scope_ids[scope_ids.index(old_id)] = new_id
    replay_ids = plan["variant_replay_policy"]["variant_ids"]
    if old_id in replay_ids:
        replay_ids[replay_ids.index(old_id)] = new_id


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload["assumptions"].append("Forged assumption"),
        lambda payload: payload["provenance"].append("Forged provenance"),
        lambda payload: payload["assumptions"].reverse(),
        lambda payload: payload["provenance"].reverse(),
    ),
)
def test_fully_resigned_baseline_metadata_is_not_authority(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload = deepcopy(core_experiment_baseline().to_dict())
    mutate(payload)
    forged = CoreExperimentBaseline.from_dict(_resign_baseline(payload))
    with pytest.raises(ExperimentConfigurationError):
        validate_core_experiment_baseline(forged)


def test_fully_resigned_dataset_source_swap_is_not_authority() -> None:
    payload = deepcopy(build_c008c_synthetic_dataset().to_dict())
    for left, right in ((0, 4),):
        payload["cases"][left]["source_input"], payload["cases"][right][
            "source_input"
        ] = (
            payload["cases"][right]["source_input"],
            payload["cases"][left]["source_input"],
        )
        for index in (left, right):
            case = payload["cases"][index]
            case["source_input_payload_digest"] = digest(case["source_input"])
            payload["cases"][index] = _resign_case(case)
    forged = ExperimentDatasetManifest.from_dict(_resign_dataset(payload))
    with pytest.raises(ExperimentDatasetError):
        validate_c008c_synthetic_dataset(forged)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload["cases"][0]["assumptions"].append(
            "Forged case assumption"
        ),
        lambda payload: payload["cases"][0][
            "expected_causal_properties"
        ].append("Forged causal property"),
    ),
)
def test_fully_resigned_dataset_case_metadata_is_not_authority(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload = deepcopy(build_c008c_synthetic_dataset().to_dict())
    mutate(payload)
    payload["cases"][0] = _resign_case(payload["cases"][0])
    forged = ExperimentDatasetManifest.from_dict(_resign_dataset(payload))
    with pytest.raises(ExperimentDatasetError):
        validate_c008c_synthetic_dataset(forged)


@pytest.mark.parametrize(
    "field",
    ("seed_partition_rules", "assumptions"),
)
def test_fully_resigned_dataset_manifest_metadata_is_not_authority(
    field: str,
) -> None:
    payload = deepcopy(build_c008c_synthetic_dataset().to_dict())
    payload[field].append(f"Forged {field}")
    forged = ExperimentDatasetManifest.from_dict(_resign_dataset(payload))
    with pytest.raises(ExperimentDatasetError):
        validate_c008c_synthetic_dataset(forged)


def test_rebuilt_bar_and_all_associated_objects_are_not_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msa.validation.experiments import synthetic_suite

    prices = dict(synthetic_suite._BASE_PRICES)
    changed = list(prices[next(iter(prices))])
    changed[0] = str(Decimal(changed[0]) + Decimal("0.125"))
    prices[next(iter(prices))] = tuple(changed)
    with monkeypatch.context() as context:
        context.setattr(synthetic_suite, "_BASE_PRICES", prices)
        forged = build_c008c_synthetic_dataset()
    ExperimentDatasetManifest.from_dict(forged.to_dict())
    with pytest.raises(ExperimentDatasetError):
        validate_c008c_synthetic_dataset(forged)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("baseline_id", "fully-resigned-other-baseline"),
        ("dataset_manifest_id", "fully-resigned-other-dataset"),
    ),
)
def test_fully_resigned_plan_authority_ids_are_rejected(
    field: str, value: str
) -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    payload[field] = value
    forged = ExperimentPlan.from_dict(_resign_plan(payload))
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)


def test_fully_resigned_gate_policy_and_plan_are_rejected() -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    gate = payload["gate_definitions"][0]
    condition = "Forged complete authority comparison passes"
    gate["policy"]["pass_condition"] = condition
    gate["pass_rule"] = condition
    payload["gate_definitions"][0] = _resign_gate(gate)
    resigned = _resign_plan(payload)
    forged = ExperimentPlan.from_dict(resigned)
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)
    with pytest.raises(ExperimentGateError):
        validate_c008c_gate_registry(forged.gate_definitions)


def test_fully_resigned_gate_evidence_and_plan_are_rejected() -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    gate = payload["gate_definitions"][0]
    gate["required_evidence_kinds"] = ["experiment_report"]
    payload["gate_definitions"][0] = _resign_gate(gate)
    forged = ExperimentPlan.from_dict(_resign_plan(payload))
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)
    with pytest.raises(ExperimentGateError):
        validate_c008c_gate_registry(forged.gate_definitions)


def test_fully_resigned_axis_variant_and_plan_are_rejected() -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    axis = payload["axes"][0]
    axis["values"][0]["value"] = "0.05"
    axis = _resign_axis(axis)
    payload["axes"][0] = axis
    variant = payload["variants"][1]
    variant["axis_id"] = axis["axis_id"]
    variant["core_config_snapshot"]["scoring_config"][
        "dependency_repeat_credit"
    ] = "0.05"
    variant = _resign_variant(variant)
    _replace_variant_id(payload, 1, variant)
    high_variant = payload["variants"][2]
    high_variant["axis_id"] = axis["axis_id"]
    high_variant = _resign_variant(high_variant)
    _replace_variant_id(payload, 2, high_variant)
    forged = ExperimentPlan.from_dict(_resign_plan(payload))
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)


def test_fully_resigned_variant_config_and_plan_are_rejected() -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    index = 17
    variant = payload["variants"][index]
    variant["core_config_snapshot"]["scoring_config"][
        "dependency_repeat_credit"
    ] = "0.125"
    variant = _resign_variant(variant)
    _replace_variant_id(payload, index, variant)
    forged = ExperimentPlan.from_dict(_resign_plan(payload))
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)


@pytest.mark.parametrize(
    "field",
    ("partition_rules", "execution_order", "assumptions"),
)
def test_fully_resigned_plan_protocol_is_rejected(field: str) -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    payload[field].append(f"Forged {field}")
    forged = ExperimentPlan.from_dict(_resign_plan(payload))
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)


@pytest.mark.parametrize("field", ("sha256", "category"))
def test_fully_resigned_protected_source_is_rejected(field: str) -> None:
    payload = deepcopy(build_protected_source_manifest().to_dict())
    payload["files"][0][field] = (
        "0" * 64 if field == "sha256" else "FORGED_CATEGORY"
    )
    forged = ProtectedSourceManifest.from_dict(_resign_protected(payload))
    with pytest.raises(ExperimentProtectedSourceError):
        validate_protected_source_manifest(forged)


def test_normal_authorities_validate_exactly() -> None:
    baseline = core_experiment_baseline()
    dataset = build_c008c_synthetic_dataset()
    gates = default_c008c_gate_registry()
    plan = default_c008c_experiment_plan()
    assert validate_core_experiment_baseline(baseline) is baseline
    assert validate_c008c_synthetic_dataset(dataset) is dataset
    assert validate_c008c_gate_registry(gates) is gates
    assert validate_c008c_experiment_plan(plan) is plan


def test_validators_read_each_caller_payload_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = core_experiment_baseline()
    dataset = build_c008c_synthetic_dataset()
    gates = default_c008c_gate_registry()
    plan = default_c008c_experiment_plan()

    baseline_calls = 0
    baseline_to_dict = CoreExperimentBaseline.to_dict

    def baseline_payload(self: CoreExperimentBaseline) -> dict[str, object]:
        nonlocal baseline_calls
        if self is baseline:
            baseline_calls += 1
        return baseline_to_dict(self)

    dataset_calls = 0
    dataset_to_dict = ExperimentDatasetManifest.to_dict

    def dataset_payload(
        self: ExperimentDatasetManifest,
    ) -> dict[str, object]:
        nonlocal dataset_calls
        if self is dataset:
            dataset_calls += 1
        return dataset_to_dict(self)

    plan_calls = 0
    plan_to_dict = ExperimentPlan.to_dict

    def plan_payload(self: ExperimentPlan) -> dict[str, object]:
        nonlocal plan_calls
        if self is plan:
            plan_calls += 1
        return plan_to_dict(self)

    gate_calls = {id(item): 0 for item in gates}
    gate_to_dict = ExperimentGateDefinition.to_dict

    def gate_payload(
        self: ExperimentGateDefinition,
    ) -> dict[str, object]:
        if id(self) in gate_calls:
            gate_calls[id(self)] += 1
        return gate_to_dict(self)

    monkeypatch.setattr(
        CoreExperimentBaseline, "to_dict", baseline_payload
    )
    monkeypatch.setattr(
        ExperimentDatasetManifest, "to_dict", dataset_payload
    )
    monkeypatch.setattr(ExperimentPlan, "to_dict", plan_payload)
    monkeypatch.setattr(ExperimentGateDefinition, "to_dict", gate_payload)
    validate_core_experiment_baseline(baseline)
    validate_c008c_synthetic_dataset(dataset)
    validate_c008c_gate_registry(gates)
    validate_c008c_experiment_plan(plan)
    assert baseline_calls == 1
    assert dataset_calls == 1
    assert plan_calls == 1
    assert set(gate_calls.values()) == {1}
