from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import ROUND_DOWN, getcontext
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from msa.reference import core_alpha_v1_config
from msa.research.msa_core import MSACorePipeline
from msa.research.msa_core.contracts import validate_source_input
from msa.validation import StructuralMetricEvaluator, SyntheticScenarioKind
from msa.validation.experiments import (
    ExperimentPlan,
    ExperimentPlanError,
    ExperimentDatasetManifest,
    ExperimentValidationError,
    build_c008c_synthetic_dataset,
    build_synthetic_source_input,
    core_experiment_baseline,
    default_c008c_experiment_plan,
    default_c008c_gate_registry,
    validate_c008c_experiment_plan,
    validate_c008c_gate_registry,
    validate_c008c_synthetic_dataset,
    validate_core_experiment_baseline,
    write_c008c_authority_evidence,
)
from msa.validation.experiments.identity import semantic_id


ROOT = Path(__file__).resolve().parents[2]


def _forbidden(*args: object, **kwargs: object) -> object:
    raise AssertionError("outcome-producing engine was called")


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            item
            for child in value.values()
            for item in _keys(child)
        }
    if isinstance(value, list):
        return {item for child in value for item in _keys(child)}
    return set()


def test_plan_build_runs_neither_core_nor_metric_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MSACorePipeline, "run", _forbidden)
    monkeypatch.setattr(StructuralMetricEvaluator, "evaluate", _forbidden)
    default_c008c_experiment_plan()


def test_plan_contains_no_metric_value_oos_outcome_or_selection() -> None:
    payload = default_c008c_experiment_plan().to_dict()
    keys = {item.lower() for item in _keys(payload)}
    for prohibited in (
        "metric_value",
        "aggregate_value",
        "oos_outcome",
        "winner",
        "leaderboard",
        "best_parameters",
    ):
        assert prohibited not in keys


def test_external_future_outcomes_cannot_change_plan_identity() -> None:
    assert not inspect.signature(default_c008c_experiment_plan).parameters
    plan_id = default_c008c_experiment_plan().experiment_plan_id
    external_outcome = {"oos": {"value": "1"}}
    external_outcome["oos"]["value"] = "999999"
    external_outcome["winner"] = "forged"
    assert default_c008c_experiment_plan().experiment_plan_id == plan_id


def test_partitions_variants_gates_and_increment_order_are_frozen() -> None:
    plan = default_c008c_experiment_plan()
    assert isinstance(plan.axes, tuple)
    assert isinstance(plan.variants, tuple)
    assert isinstance(plan.gate_definitions, tuple)
    assert isinstance(plan.increment_steps, tuple)
    with pytest.raises(FrozenInstanceError):
        plan.experiment_plan_id = "changed"  # type: ignore[misc]


def test_authority_validators_do_not_call_outcome_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = core_experiment_baseline()
    dataset = build_c008c_synthetic_dataset()
    gates = default_c008c_gate_registry()
    plan = default_c008c_experiment_plan()
    monkeypatch.setattr(MSACorePipeline, "run", _forbidden)
    monkeypatch.setattr(StructuralMetricEvaluator, "evaluate", _forbidden)
    validate_core_experiment_baseline(baseline)
    validate_c008c_synthetic_dataset(dataset)
    validate_c008c_gate_registry(gates)
    validate_c008c_experiment_plan(plan)


def test_complete_execution_replay_and_cutoff_scope_precedes_outcomes() -> None:
    plan = default_c008c_experiment_plan()
    assert plan.execution_scope_policy.expected_execution_pair_count == 520
    assert len(plan.execution_scope_policy.execution_pairs()) == 520
    assert plan.baseline_replay_policy.expected_sample_count == 20
    assert plan.variant_replay_policy.expected_sample_count == 125
    assert plan.fixed_cutoff_policy.cutoff_scope == (
        "EVERY_FORMAL_CAUSAL_ASOF"
    )
    assert (
        plan.execution_scope_policy.oos_all_variants_required is True
    )


@pytest.mark.parametrize(
    ("gate_code", "policy_list", "field", "value"),
    (
        (
            "OOS_SAMPLE_COVERAGE",
            "sample_coverage_rules",
            "minimum_count",
            1,
        ),
        (
            "NO_NEIGHBORHOOD_DEGENERATION",
            "degeneration_rules",
            "description",
            "Outcome-adjusted degeneration",
        ),
    ),
)
def test_fully_resigned_outcome_adjusted_gate_plan_is_rejected(
    gate_code: str,
    policy_list: str,
    field: str,
    value: object,
) -> None:
    payload = deepcopy(default_c008c_experiment_plan().to_dict())
    index = next(
        index
        for index, item in enumerate(payload["gate_definitions"])
        if item["code"] == gate_code
    )
    gate = payload["gate_definitions"][index]
    gate["policy"][policy_list][0][field] = value
    gate["gate_definition_id"] = semantic_id(
        "c008c-gate-definition-v1-",
        {
            key: item
            for key, item in gate.items()
            if key != "gate_definition_id"
        },
    )
    payload["gate_definitions"][index] = gate
    payload["experiment_plan_id"] = semantic_id(
        "c008c-experiment-plan-v1-",
        {
            key: item
            for key, item in payload.items()
            if key != "experiment_plan_id"
        },
    )
    forged = ExperimentPlan.from_dict(payload)
    with pytest.raises(ExperimentPlanError):
        validate_c008c_experiment_plan(forged)


def test_outcomes_cannot_remove_oos_cases_or_variants() -> None:
    dataset = deepcopy(build_c008c_synthetic_dataset().to_dict())
    dataset["cases"] = [
        item for item in dataset["cases"] if item["partition"] != "OOS"
    ]
    dataset["dataset_manifest_id"] = semantic_id(
        "c008c-dataset-manifest-v1-",
        {
            key: item
            for key, item in dataset.items()
            if key != "dataset_manifest_id"
        },
    )
    with pytest.raises(ExperimentValidationError):
        ExperimentDatasetManifest.from_dict(dataset)

    plan = deepcopy(default_c008c_experiment_plan().to_dict())
    plan["variants"].pop()
    plan["experiment_plan_id"] = semantic_id(
        "c008c-experiment-plan-v1-",
        {
            key: item
            for key, item in plan.items()
            if key != "experiment_plan_id"
        },
    )
    with pytest.raises(ExperimentValidationError):
        ExperimentPlan.from_dict(plan)


def test_context_tuple_permutation_canonicalizes_to_same_formal_input() -> None:
    source = build_synthetic_source_input(
        SyntheticScenarioKind.SINGLE_TREND, 0
    )
    permuted = replace(
        source,
        timeframe_state_histories=tuple(
            reversed(source.timeframe_state_histories)
        ),
    )
    assert validate_source_input(
        source, core_alpha_v1_config()
    ).to_dict() == validate_source_input(
        permuted, core_alpha_v1_config()
    ).to_dict()


def test_decimal_context_does_not_change_plan_payload() -> None:
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        first = default_c008c_experiment_plan().to_dict()
        getcontext().prec = 6
        getcontext().rounding = ROUND_DOWN
        assert default_c008c_experiment_plan().to_dict() == first
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding


def test_python_hash_seed_does_not_change_plan_id() -> None:
    command = (
        "from msa.validation.experiments import "
        "default_c008c_experiment_plan as f; "
        "print(f().experiment_plan_id)"
    )
    values = []
    for seed in ("1", "999"):
        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = str(ROOT / "src/python")
        result = subprocess.run(
            [sys.executable, "-B", "-c", command],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        values.append(result.stdout.strip())
    assert values[0] == values[1]


def test_repeated_complete_payload_is_identical() -> None:
    assert (
        default_c008c_experiment_plan().to_dict()
        == default_c008c_experiment_plan().to_dict()
    )
    assert (
        build_c008c_synthetic_dataset().to_dict()
        == build_c008c_synthetic_dataset().to_dict()
    )


def test_source_inputs_are_not_reused_across_partitions() -> None:
    cases = build_c008c_synthetic_dataset().cases
    assert len(
        {item.source_input_payload_digest for item in cases}
    ) == len(cases)


def test_origin_time_is_provenance_not_execution_or_outcome_rule() -> None:
    plan = default_c008c_experiment_plan()
    assert all("origin" not in item.lower() for item in plan.execution_order)
    assert all(
        "origintime grants visibility" not in item.pass_rule.lower()
        for item in plan.gate_definitions
    )


def test_no_incomplete_bar_enters_synthetic_input() -> None:
    for case in build_c008c_synthetic_dataset().cases:
        assert all(
            bar.is_complete
            for bar in case.source_input.reference_price_data.bars
        )


def test_evidence_bytes_are_deterministic_and_outcome_free() -> None:
    paths = write_c008c_authority_evidence(check=True)
    first = tuple(path.read_bytes() for path in paths)
    second = tuple(path.read_bytes() for path in paths)
    assert first == second
    keys = {
        key.lower()
        for item in first
        for key in _keys(json.loads(item))
    }
    assert not {
        "winner",
        "leaderboard",
        "best_parameters",
        "outcome",
    } & keys
