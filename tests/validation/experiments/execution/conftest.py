from __future__ import annotations

import pytest

from msa.validation.experiments.execution.contracts import (
    ExperimentCaseStatus,
    ExperimentFailureStage,
    FixedCutoffStatus,
    ReplayComparisonStatus,
)
from msa.validation.experiments.execution.cutoff import _comparison as cutoff_result
from msa.validation.experiments.execution.degeneration import (
    evaluate_validation_degeneration,
)
from msa.validation.experiments.execution.deltas import calculate_metric_deltas
from msa.validation.experiments.execution.gate_evaluator import (
    evaluate_c008c_b_gates,
)
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)
from msa.validation.experiments.execution.replay import (
    _comparison as replay_result,
)
from msa.validation.experiments.execution.report import (
    _partition_summaries,
    build_c008c_b_report,
    validate_c008c_b_report,
)
from msa.validation.experiments.execution.runner import (
    _ExecutionArtifacts,
    _case_result,
    _determinism,
)


@pytest.fixture(scope="session")
def compact_components():
    manifest = build_c008c_b_execution_manifest()
    _, dataset, _, plan, _ = load_c008c_b_authority()
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    case_results = tuple(
        _case_result(
            pair,
            variants[pair.variant_id],
            status=ExperimentCaseStatus.PIPELINE_FAILED,
            run=None,
            audit=None,
            metric_report=None,
            failure_stage=ExperimentFailureStage.PIPELINE,
            failure_error_type="MSACoreInputError",
        )
        for pair in manifest.execution_pairs
    )
    determinism = tuple(
        _determinism(
            pair,
            _ExecutionArtifacts(result, None, None, None),
            _ExecutionArtifacts(result, None, None, None),
        )
        for pair, result in zip(
            manifest.execution_pairs, case_results, strict=True
        )
    )
    deltas = calculate_metric_deltas(case_results)
    baseline = plan.variants[0]
    baseline_cases = tuple(
        cases[item] for item in manifest.executable_case_ids
    )
    replays = [
        replay_result(
            replay_sample_id=sample_id,
            scope="BASELINE",
            case=case,
            variant=baseline,
            status=ReplayComparisonStatus.EXECUTION_FAILED,
            batch_run=None,
            replay_run=None,
            comparison_audit=None,
            batch_metric=None,
            replay_metric=None,
            run_equal=False,
            metric_equal=False,
            failure_error_type="MSACoreReplayError",
        )
        for sample_id, case in zip(
            manifest.baseline_replay_sample_ids,
            baseline_cases,
            strict=True,
        )
    ]
    validation_cases = tuple(
        cases[item] for item in plan.variant_replay_policy.dataset_case_ids
    )
    variant_schedule = tuple(
        (case, variant)
        for variant in plan.variants[1:]
        for case in validation_cases
    )
    replays.extend(
        replay_result(
            replay_sample_id=sample_id,
            scope="VARIANT",
            case=case,
            variant=variant,
            status=ReplayComparisonStatus.EXECUTION_FAILED,
            batch_run=None,
            replay_run=None,
            comparison_audit=None,
            batch_metric=None,
            replay_metric=None,
            run_equal=False,
            metric_equal=False,
            failure_error_type="MSACoreReplayError",
        )
        for sample_id, (case, variant) in zip(
            manifest.variant_replay_sample_ids,
            variant_schedule,
            strict=True,
        )
    )
    replay = tuple(replays)
    cutoff = tuple(
        cutoff_result(
            case=case,
            baseline_variant_id=baseline.variant_id,
            status=FixedCutoffStatus.EXECUTION_FAILED,
            checkpoints=(),
            failure_error_type="MSACoreReplayError",
        )
        for case in baseline_cases
    )
    degeneration = evaluate_validation_degeneration(
        case_results,
        deltas,
        replay,
        cutoff,
    )
    gates = evaluate_c008c_b_gates(
        manifest,
        case_results,
        determinism,
        replay,
        cutoff,
        degeneration,
    )
    partitions = _partition_summaries(
        case_results,
        deltas,
        replay,
        degeneration,
        None,
    )
    report = build_c008c_b_report(
        manifest,
        case_results,
        determinism,
        deltas,
        partitions,
        replay,
        cutoff,
        degeneration,
        gates,
    )
    validate_c008c_b_report(report, manifest)
    return {
        "manifest": manifest,
        "case_results": case_results,
        "determinism": determinism,
        "deltas": deltas,
        "replay": replay,
        "cutoff": cutoff,
        "degeneration": degeneration,
        "gates": gates,
        "partitions": partitions,
        "report": report,
        "dataset": dataset,
        "plan": plan,
    }
