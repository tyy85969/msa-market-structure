from dataclasses import FrozenInstanceError, replace
from decimal import ROUND_DOWN, getcontext
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
    build_c008c_synthetic_dataset,
    build_synthetic_source_input,
    default_c008c_experiment_plan,
    write_c008c_authority_evidence,
)


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
    plan_id = default_c008c_experiment_plan().experiment_plan_id
    future_oos_bar = {"close": "999999", "available_time": "future"}
    future_metric_outcome = {"value": "999999"}
    assert future_oos_bar and future_metric_outcome
    assert default_c008c_experiment_plan().experiment_plan_id == plan_id


def test_partitions_variants_gates_and_increment_order_are_frozen() -> None:
    plan = default_c008c_experiment_plan()
    assert isinstance(plan.axes, tuple)
    assert isinstance(plan.variants, tuple)
    assert isinstance(plan.gate_definitions, tuple)
    assert isinstance(plan.increment_steps, tuple)
    with pytest.raises(FrozenInstanceError):
        plan.experiment_plan_id = "changed"  # type: ignore[misc]


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
