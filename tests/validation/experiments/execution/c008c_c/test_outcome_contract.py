from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from c008c_c import architecture
from c008c_c.contracts import C008CCCaseResult, C008CCPartition
from msa.validation.experiments.contracts import DatasetPartition
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseResult,
    ExperimentCaseStatus,
    ExperimentFailureStage,
)
from msa.validation.experiments.execution.errors import C008CBCaseError
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)


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
