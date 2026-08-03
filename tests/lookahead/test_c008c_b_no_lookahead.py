from dataclasses import FrozenInstanceError, fields
from decimal import ROUND_UP, localcontext
from functools import lru_cache

import pytest

from msa.validation.experiments import DatasetPartition
from msa.validation.experiments.execution import (
    C008CBRunReport,
    C008CBStageStatus,
    ExperimentCaseStatus,
    ExperimentFailureStage,
    build_c008c_b_execution_manifest,
)
from msa.validation.experiments.execution.gate_evaluator import _STATIC_PASS
from msa.validation.experiments.execution.cutoff import _execute_case
from msa.validation.experiments.execution.errors import (
    C008CBCaseError,
    C008CBComparisonError,
)
from msa.validation.experiments.execution.manifest import (
    load_c008c_b_authority,
)
from msa.validation.experiments.execution.replay import _execute_sample
from msa.validation.experiments.execution.runner import (
    _case_result,
    _execute_pair,
)


@lru_cache(maxsize=1)
def _authorities():
    manifest = build_c008c_b_execution_manifest()
    _, dataset, _, plan, _ = load_c008c_b_authority()
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    return manifest, dataset, plan, cases, variants


def _failed_result(pair, variant):
    return _case_result(
        pair,
        variant,
        status=ExperimentCaseStatus.PIPELINE_FAILED,
        run=None,
        audit=None,
        metric_report=None,
        failure_stage=ExperimentFailureStage.PIPELINE,
        failure_error_type="MSACoreInputError",
    )


def test_complete_schedule_exists_before_any_outcome(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("outcome entrypoint called before manifest")

    monkeypatch.setattr(
        "msa.research.msa_core.MSACorePipeline.run", forbidden
    )
    monkeypatch.setattr(
        "msa.validation.causal_audit.CausalAuditor.audit_run",
        forbidden,
    )
    monkeypatch.setattr(
        "msa.validation.metrics.StructuralMetricEvaluator.evaluate",
        forbidden,
    )
    manifest = build_c008c_b_execution_manifest()
    assert tuple(item.schedule_index for item in manifest.execution_pairs) == (
        tuple(range(390))
    )


def test_dev_outcome_cannot_change_validation_set_or_variant_order() -> None:
    manifest, _, _, _, variants = _authorities()
    validation_before = tuple(
        item.execution_pair_id
        for item in manifest.execution_pairs
        if item.partition is DatasetPartition.VALIDATION
    )
    variant_order_before = tuple(
        item.variant_id for item in manifest.execution_pairs
    )
    pair = next(
        item
        for item in manifest.execution_pairs
        if item.partition is DatasetPartition.DEVELOPMENT
    )
    result = _failed_result(pair, variants[pair.variant_id])
    rebuilt = build_c008c_b_execution_manifest()
    assert result.status is ExperimentCaseStatus.PIPELINE_FAILED
    assert tuple(
        item.execution_pair_id
        for item in rebuilt.execution_pairs
        if item.partition is DatasetPartition.VALIDATION
    ) == validation_before
    assert tuple(
        item.variant_id for item in rebuilt.execution_pairs
    ) == variant_order_before


def test_validation_outcome_cannot_change_frozen_plan() -> None:
    manifest, _, plan, _, variants = _authorities()
    before = plan.to_dict()
    pair = next(
        item
        for item in manifest.execution_pairs
        if item.partition is DatasetPartition.VALIDATION
    )
    result = _failed_result(pair, variants[pair.variant_id])
    assert result.partition is DatasetPartition.VALIDATION
    assert load_c008c_b_authority()[3].to_dict() == before


def test_dev_and_validation_scope_cannot_include_seed_three() -> None:
    manifest = build_c008c_b_execution_manifest()
    assert len(manifest.execution_pairs) == 390
    assert all(
        item.partition
        in (DatasetPartition.DEVELOPMENT, DatasetPartition.VALIDATION)
        and item.seed != 3
        for item in manifest.execution_pairs
    )
    assert all(
        item.partition is DatasetPartition.OOS and item.seed == 3
        for item in manifest.deferred_oos_pairs
    )


def test_oos_metadata_is_readable_but_core_is_not_called(
    monkeypatch,
) -> None:
    manifest, _, _, cases, variants = _authorities()
    pair = manifest.deferred_oos_pairs[0]
    calls = {"core": 0, "audit": 0, "metric": 0}

    def core_forbidden(*args, **kwargs):
        calls["core"] += 1

    def audit_forbidden(*args, **kwargs):
        calls["audit"] += 1

    def metric_forbidden(*args, **kwargs):
        calls["metric"] += 1

    monkeypatch.setattr(
        "msa.research.msa_core.MSACorePipeline.run", core_forbidden
    )
    monkeypatch.setattr(
        "msa.validation.causal_audit.CausalAuditor.audit_run",
        audit_forbidden,
    )
    monkeypatch.setattr(
        "msa.validation.metrics.StructuralMetricEvaluator.evaluate",
        metric_forbidden,
    )
    assert pair.seed == 3
    assert pair.source_input_payload_digest
    with pytest.raises(C008CBCaseError):
        _execute_pair(
            pair,
            cases[pair.dataset_case_id],
            variants[pair.variant_id],
        )
    assert calls == {"core": 0, "audit": 0, "metric": 0}


def test_oos_never_enters_replay() -> None:
    manifest, _, plan, cases, variants = _authorities()
    pair = manifest.deferred_oos_pairs[0]
    case = cases[pair.dataset_case_id]
    variant = variants[pair.variant_id]
    with pytest.raises(C008CBComparisonError):
        _execute_sample("forbidden-oos", "VARIANT", case, variant)


def test_oos_never_enters_fixed_cutoff() -> None:
    manifest, _, plan, cases, _ = _authorities()
    pair = manifest.deferred_oos_pairs[0]
    case = cases[pair.dataset_case_id]
    with pytest.raises(C008CBComparisonError):
        _execute_case(case, plan.variants[0])


def test_oos_outcome_gates_can_never_use_static_pass_path() -> None:
    assert "OOS_SAMPLE_COVERAGE" not in _STATIC_PASS
    assert "FREEZE_SOURCE_BOUND" not in _STATIC_PASS
    assert "ALL_CASES_MUST_EXECUTE" not in _STATIC_PASS


def test_all_frozen_dataset_bars_are_complete() -> None:
    _, dataset, _, _, _ = _authorities()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "is_complete":
                    yield item
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    flags = tuple(
        flag
        for case in dataset.cases
        for flag in walk(case.source_input.to_dict())
    )
    assert flags
    assert all(flag is True for flag in flags)


def test_decimal_context_cannot_change_manifest_or_pair_order() -> None:
    expected = build_c008c_b_execution_manifest().to_dict()
    with localcontext() as context:
        context.prec = 5
        context.rounding = ROUND_UP
        actual = build_c008c_b_execution_manifest().to_dict()
    assert actual == expected


def test_failure_cannot_remove_remaining_schedule() -> None:
    manifest = build_c008c_b_execution_manifest()
    first_variant = manifest.execution_pairs[0].variant_id
    scheduled = tuple(
        item
        for item in manifest.execution_pairs
        if item.variant_id == first_variant
    )
    assert len(scheduled) == 15
    assert scheduled[-1].schedule_index > scheduled[0].schedule_index


def test_delta_gate_and_stage_objects_cannot_mutate_frozen_authority() -> None:
    manifest, _, plan, _, _ = _authorities()
    before_manifest = manifest.to_dict()
    before_plan = plan.to_dict()
    stage = C008CBStageStatus.BLOCKED_BEFORE_OOS
    assert stage.value == "BLOCKED_BEFORE_OOS"
    assert build_c008c_b_execution_manifest().to_dict() == before_manifest
    assert load_c008c_b_authority()[3].to_dict() == before_plan
    with pytest.raises(FrozenInstanceError):
        plan.schema_version = 2


def test_cutoff_contract_exposes_confirmed_asof_not_origin_time() -> None:
    from msa.validation.experiments.execution import (
        ExperimentFixedCutoffCheckpoint,
    )

    names = {item.name for item in fields(ExperimentFixedCutoffCheckpoint)}
    assert "cutoff_as_of_time" in names
    assert "origin_time" not in names


def test_report_contract_has_no_selection_or_trading_surface() -> None:
    names = {item.name for item in fields(C008CBRunReport)}
    forbidden = {
        "winner",
        "leaderboard",
        "recommendation",
        "recommended_parameter",
        "score",
        "trading_signal",
        "entry",
        "exit",
    }
    assert names.isdisjoint(forbidden)
