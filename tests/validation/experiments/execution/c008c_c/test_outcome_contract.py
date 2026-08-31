from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from c008c_c import architecture
from c008c_c.contracts import (
    C008CCCaseResult,
    C008CCFixedCutoffComparison,
    C008CCMetricDelta,
    C008CCMetricDeltaSummary,
    C008CCPartition,
    C008CCReplayComparison,
)
from msa.validation.experiments.contracts import DatasetPartition
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseResult,
    ExperimentCaseStatus,
    ExperimentFailureStage,
    ExperimentFixedCutoffComparison,
    ExperimentMetricDelta,
    ExperimentMetricDeltaSummary,
    ExperimentReplayComparison,
    FixedCutoffStatus,
    MetricDeltaStatus,
    ReplayComparisonStatus,
)
from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.experiments.execution.errors import (
    C008CBCaseError,
    C008CBComparisonError,
)
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)
from msa.validation.metrics import MetricAggregateStatus, default_metric_formula_registry


ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def locked_authority() -> tuple[object, object]:
    manifest = build_c008c_b_execution_manifest(ROOT)
    _, _, _, plan, _ = load_c008c_b_authority(ROOT)
    pair = manifest.deferred_oos_pairs[0]
    variant = next(
        item for item in plan.variants if item.variant_id == pair.variant_id
    )
    return pair, variant


def test_b_case_result_still_rejects_oos(
    locked_authority: tuple[object, object],
) -> None:
    pair, variant = locked_authority
    with pytest.raises(
        C008CBCaseError,
        match="C-008C-B CaseResult must never contain OOS outcome",
    ):
        ExperimentCaseResult(
            case_result_id="must-reject-before-identity-check",
            execution_pair_id=pair.execution_pair_id,
            dataset_case_id=pair.dataset_case_id,
            variant_id=pair.variant_id,
            experiment_kind=variant.experiment_kind,
            level=variant.level,
            partition=DatasetPartition.OOS,
            scenario=pair.scenario,
            seed=3,
            status=ExperimentCaseStatus.PIPELINE_FAILED,
            source_input_payload_digest=pair.source_input_payload_digest,
            core_config_payload_digest=pair.core_config_payload_digest,
            metric_config_payload_digest=pair.metric_config_payload_digest,
            run_id=None,
            run_payload_digest=None,
            audit_report_id=None,
            audit_payload_digest=None,
            audit_passed=None,
            metric_report_id=None,
            metric_report_payload_digest=None,
            aggregates=(),
            event_count=0,
            box_episode_count=0,
            matured_count=0,
            censored_count=0,
            unavailable_count=0,
            failure_stage=ExperimentFailureStage.PIPELINE,
            failure_error_type="SyntheticContractProbe",
        )


def test_c_case_result_accepts_only_locked_oos_seed_3(
    locked_authority: tuple[object, object],
) -> None:
    pair, variant = locked_authority
    result = C008CCCaseResult.create(
        execution_pair_id=pair.execution_pair_id,
        dataset_case_id=pair.dataset_case_id,
        variant_id=pair.variant_id,
        experiment_kind=variant.experiment_kind,
        level=variant.level,
        partition=C008CCPartition.LOCKED_OOS,
        scenario=pair.scenario,
        seed=3,
        execution_status=ExperimentCaseStatus.PIPELINE_FAILED,
        source_input_payload_digest=pair.source_input_payload_digest,
        core_config_payload_digest=pair.core_config_payload_digest,
        metric_config_payload_digest=pair.metric_config_payload_digest,
        run_id=None,
        run_payload_digest=None,
        audit_report_id=None,
        audit_payload_digest=None,
        audit_passed=None,
        metric_report_id=None,
        metric_report_payload_digest=None,
        aggregates=(),
        event_count=0,
        box_episode_count=0,
        matured_count=0,
        censored_count=0,
        unavailable_count=0,
        failure_stage=ExperimentFailureStage.PIPELINE,
        failure_error_type="SyntheticContractProbe",
        schema_version=1,
    )
    assert result.partition is C008CCPartition.LOCKED_OOS
    assert result.seed == 3
    assert result.execution_status is ExperimentCaseStatus.PIPELINE_FAILED
    assert result.case_result_id.startswith("c008c-c-case-result-v1-")
    assert C008CCCaseResult.from_dict(result.to_dict()) == result


def test_b_metric_delta_contracts_still_reject_oos(
    locked_authority: tuple[object, object],
) -> None:
    pair, _ = locked_authority
    formula = default_metric_formula_registry()[0]
    with pytest.raises(
        C008CBComparisonError,
        match="metric delta partition must be DEVELOPMENT/VALIDATION",
    ):
        ExperimentMetricDelta(
            metric_delta_id="must-reject-before-identity-check",
            dataset_case_id=pair.dataset_case_id,
            partition=DatasetPartition.OOS,
            scenario=pair.scenario,
            variant_id="variant-id",
            baseline_variant_id="baseline-id",
            metric_name=formula.metric_name,
            formula_id=formula.metric_formula_id,
            baseline_aggregate_status=MetricAggregateStatus.AVAILABLE,
            variant_aggregate_status=MetricAggregateStatus.AVAILABLE,
            baseline_value=Decimal("1"),
            variant_value=Decimal("2"),
            absolute_delta=Decimal("1"),
            delta_status=MetricDeltaStatus.COMPARABLE,
        )
    with pytest.raises(
        C008CBComparisonError,
        match="delta summary partition must be B-stage partition",
    ):
        ExperimentMetricDeltaSummary(
            metric_delta_summary_id="must-reject-before-identity-check",
            partition=DatasetPartition.OOS,
            variant_id="variant-id",
            baseline_variant_id="baseline-id",
            metric_deltas=(),
            comparable_count=0,
            equal_count=0,
            non_zero_count=0,
            unavailable_count=0,
        )


def _c_metric_delta(
    *,
    case_id: str,
    scenario: object,
    variant_id: str,
    baseline_id: str,
    metric_name: object,
    formula_id: str,
) -> C008CCMetricDelta:
    return C008CCMetricDelta.create(
        dataset_case_id=case_id,
        partition=C008CCPartition.LOCKED_OOS,
        scenario=scenario,
        variant_id=variant_id,
        baseline_variant_id=baseline_id,
        metric_name=metric_name,
        formula_id=formula_id,
        baseline_aggregate_status=MetricAggregateStatus.AVAILABLE,
        variant_aggregate_status=MetricAggregateStatus.AVAILABLE,
        baseline_value=Decimal("1"),
        variant_value=Decimal("2"),
        absolute_delta=Decimal("1"),
        delta_status=MetricDeltaStatus.COMPARABLE,
        schema_version=1,
    )


def test_c_metric_delta_contracts_accept_only_locked_oos() -> None:
    formulas = default_metric_formula_registry()
    deltas = tuple(
        _c_metric_delta(
            case_id=f"case-{case_index}",
            scenario=next(iter(SyntheticScenarioKind)),
            variant_id="variant-id",
            baseline_id="baseline-id",
            metric_name=formula.metric_name,
            formula_id=formula.metric_formula_id,
        )
        for case_index in range(5)
        for formula in formulas
    )
    summary = C008CCMetricDeltaSummary.create(
        partition=C008CCPartition.LOCKED_OOS,
        variant_id="variant-id",
        baseline_variant_id="baseline-id",
        metric_deltas=deltas,
        comparable_count=50,
        equal_count=0,
        non_zero_count=50,
        unavailable_count=0,
        schema_version=1,
    )
    assert len(deltas) == 50
    assert C008CCMetricDelta.from_dict(deltas[0].to_dict()) == deltas[0]
    assert C008CCMetricDeltaSummary.from_dict(summary.to_dict()) == summary


def test_c_runner_has_no_b_case_result_constructor_dependency(
    locked_authority: tuple[object, object],
) -> None:
    pair, variant = locked_authority
    module_source = inspect.getsource(architecture)
    runner_source = inspect.getsource(architecture._execute_oos_pair)
    assert "ExperimentCaseResult" not in module_source
    assert "_case_result" not in architecture.__dict__
    assert "_c_case_result(" in runner_source

    result = architecture._c_case_result(
        pair,
        variant,
        status=ExperimentCaseStatus.PIPELINE_FAILED,
        run=None,
        audit=None,
        metric_report=None,
        failure_stage=ExperimentFailureStage.PIPELINE,
        failure_error_type="SyntheticContractProbe",
    )
    assert type(result) is C008CCCaseResult
    assert result.partition is C008CCPartition.LOCKED_OOS
    assert result.seed == 3


def test_b_replay_comparison_still_rejects_oos(
    locked_authority: tuple[object, object],
) -> None:
    pair, variant = locked_authority
    with pytest.raises(
        C008CBComparisonError,
        match="replay comparison cannot contain OOS outcome",
    ):
        ExperimentReplayComparison(
            replay_comparison_id="must-reject-before-identity-check",
            replay_sample_id="synthetic-replay-sample",
            scope="BASELINE",
            dataset_case_id=pair.dataset_case_id,
            variant_id=variant.variant_id,
            partition=DatasetPartition.OOS,
            scenario=pair.scenario,
            seed=3,
            status=ReplayComparisonStatus.EXECUTION_FAILED,
            batch_run_id=None,
            batch_run_payload_digest=None,
            replay_run_id=None,
            replay_run_payload_digest=None,
            comparison_audit_id=None,
            comparison_audit_payload_digest=None,
            batch_metric_report_id=None,
            batch_metric_payload_digest=None,
            replay_metric_report_id=None,
            replay_metric_payload_digest=None,
            full_run_payload_equal=False,
            full_metric_payload_equal=False,
            failure_error_type="SyntheticContractProbe",
        )


def _c_replay(
    pair: object,
    variant: object,
) -> C008CCReplayComparison:
    return C008CCReplayComparison.create(
        replay_sample_id="synthetic-replay-sample",
        scope="BASELINE",
        dataset_case_id=pair.dataset_case_id,
        variant_id=variant.variant_id,
        partition=C008CCPartition.LOCKED_OOS,
        scenario=pair.scenario,
        seed=3,
        status=ReplayComparisonStatus.EXECUTION_FAILED,
        batch_run_id=None,
        batch_run_payload_digest=None,
        replay_run_id=None,
        replay_run_payload_digest=None,
        comparison_audit_id=None,
        comparison_audit_payload_digest=None,
        batch_metric_report_id=None,
        batch_metric_payload_digest=None,
        replay_metric_report_id=None,
        replay_metric_payload_digest=None,
        full_run_payload_equal=False,
        full_metric_payload_equal=False,
        failure_error_type="SyntheticContractProbe",
        schema_version=1,
    )


def test_c_replay_comparison_accepts_locked_oos_seed_3(
    locked_authority: tuple[object, object],
) -> None:
    result = _c_replay(*locked_authority)
    assert result.partition is C008CCPartition.LOCKED_OOS
    assert result.seed == 3
    assert C008CCReplayComparison.from_dict(result.to_dict()) == result


def test_b_fixed_cutoff_comparison_still_rejects_oos(
    locked_authority: tuple[object, object],
) -> None:
    pair, variant = locked_authority
    with pytest.raises(
        C008CBComparisonError,
        match="fixed cutoff comparison cannot contain OOS",
    ):
        ExperimentFixedCutoffComparison(
            fixed_cutoff_comparison_id="must-reject-before-identity-check",
            dataset_case_id=pair.dataset_case_id,
            baseline_variant_id=variant.variant_id,
            partition=DatasetPartition.OOS,
            scenario=pair.scenario,
            seed=3,
            status=FixedCutoffStatus.EXECUTION_FAILED,
            checkpoints=(),
            stable_checkpoint_count=0,
            rewrite_count=0,
            failure_error_type="SyntheticContractProbe",
        )


def _c_cutoff(
    pair: object,
    variant: object,
) -> C008CCFixedCutoffComparison:
    return C008CCFixedCutoffComparison.create(
        dataset_case_id=pair.dataset_case_id,
        baseline_variant_id=variant.variant_id,
        partition=C008CCPartition.LOCKED_OOS,
        scenario=pair.scenario,
        seed=3,
        status=FixedCutoffStatus.EXECUTION_FAILED,
        checkpoints=(),
        stable_checkpoint_count=0,
        rewrite_count=0,
        failure_error_type="SyntheticContractProbe",
        schema_version=1,
    )


def test_c_fixed_cutoff_comparison_accepts_locked_oos_seed_3(
    locked_authority: tuple[object, object],
) -> None:
    result = _c_cutoff(*locked_authority)
    assert result.partition is C008CCPartition.LOCKED_OOS
    assert result.seed == 3
    assert C008CCFixedCutoffComparison.from_dict(result.to_dict()) == result


def test_c_runner_and_report_use_only_c_owned_oos_containers() -> None:
    replay_source = inspect.getsource(architecture._execute_oos_replay)
    cutoff_source = inspect.getsource(architecture._execute_oos_cutoff)
    report_source = inspect.getsource(architecture._objects_from_report)
    assert "_c_replay_comparison(" in replay_source
    assert "return _replay_comparison(" not in replay_source
    assert "_c_cutoff_comparison(" in cutoff_source
    assert "return _cutoff_comparison(" not in cutoff_source
    assert "C008CCReplayComparison.from_dict" in report_source
    assert "ExperimentReplayComparison.from_dict" not in report_source
    assert "C008CCFixedCutoffComparison.from_dict" in report_source
    assert "ExperimentFixedCutoffComparison.from_dict" not in report_source
    assert "C008CCMetricDeltaSummary.from_dict" in report_source
    assert "ExperimentMetricDeltaSummary.from_dict" not in report_source


def test_mock_c_flow_assembles_and_deserializes_without_b_oos_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    locked_authority: tuple[object, object],
) -> None:
    pair, variant = locked_authority
    case_result = architecture._c_case_result(
        pair,
        variant,
        status=ExperimentCaseStatus.PIPELINE_FAILED,
        run=None,
        audit=None,
        metric_report=None,
        failure_stage=ExperimentFailureStage.PIPELINE,
        failure_error_type="SyntheticContractProbe",
    )
    replay = _c_replay(pair, variant)
    cutoff = _c_cutoff(pair, variant)
    monkeypatch.setattr(
        architecture,
        "_gate_results",
        lambda *args, **kwargs: [{"gate_code": "MOCK", "status": "FAIL"}],
    )
    contract = {
        "execution_contract_id": "contract-id",
        "b_v2_execution_contract_id": "b-contract-id",
        "historical_execution_manifest_id": "manifest-id",
        "dataset_manifest_id": "dataset-id",
        "experiment_plan_id": "plan-id",
        "reviewed_protected_source_manifest_id": "source-id",
        "scenarios": [pair.scenario.value],
        "oos_case_ids": [pair.dataset_case_id],
        "variant_ids": [variant.variant_id],
        "validation_exposure_status": "POST_EXPOSURE",
        "prior_primary_execution_count": 2,
        "prior_primary_completed_pair_count": 260,
        "prior_replay_execution_count": 1,
        "prior_replay_completed_case_count": 5,
        "prior_fixed_cutoff_execution_count": 1,
        "prior_fixed_cutoff_completed_case_count": 5,
        "pristine_locked_holdout": False,
    }
    b_report = SimpleNamespace(
        run_report_id="b-report-id",
        execution_source_manifest_id="b-source-id",
    )
    report = architecture._build_report(
        ROOT,
        contract,
        {"attempt_id": "attempt-id"},
        b_report,
        (case_result,),
        (),
        (),
        (),
        [],
        [],
        (replay,),
        (cutoff,),
        [],
        {"status": "NOT_DEGENERATED"},
    )
    parsed = architecture._objects_from_report(report)
    assert parsed[0] == (case_result,)
    assert parsed[4] == (replay,)
    assert parsed[5] == (cutoff,)
    assert report["validation_exposure_status"] == "POST_EXPOSURE"
    assert report["pristine_locked_holdout"] is False
