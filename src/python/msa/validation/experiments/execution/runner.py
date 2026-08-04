"""Formal DEV/VALIDATION pair execution and deterministic repeat."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from enum import Enum
from pathlib import Path

from msa.research.msa_core import MSACorePipeline, MSACoreRun
from msa.research.msa_core.errors import MSACoreError
from msa.validation.causal_audit import CausalAuditor
from msa.validation.contracts import CausalAuditReport
from msa.validation.errors import MSAValidationError
from msa.validation.metrics import (
    MetricEvaluationReport,
    StructuralMetricAggregate,
    StructuralMetricError,
    StructuralMetricEvaluator,
    validate_metric_evaluation_report,
)

from ..contracts import DatasetPartition, ExperimentDatasetCase, ExperimentVariant
from ..identity import digest, semantic_id
from .contracts import (
    C008CBExecutionManifest,
    C008CBExecutionPair,
    ExperimentCaseResult,
    ExperimentCaseStatus,
    ExperimentDeterminismComparison,
    ExperimentFailureStage,
    MetricAggregateSnapshot,
    ReplayComparisonStatus,
)
from .contracts_v2 import (
    B_V2_EXECUTION_SEMANTICS,
    DeterminismEvidenceKind,
    ExperimentDeterminismComparisonV2,
    v2_payload_id,
)
from .errors import (
    C008CBCaseError,
    C008CBCausalAuditFailure,
    C008CBComparisonError,
)
from .manifest import (
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)


_FORMAL_MAX_WORKERS = 12


@dataclass(frozen=True, slots=True)
class _ExecutionArtifacts:
    result: ExperimentCaseResult
    run: MSACoreRun | None
    audit: CausalAuditReport | None
    metric_report: MetricEvaluationReport | None


@dataclass(frozen=True, slots=True)
class C008CBPrimaryExecution:
    case_results: tuple[ExperimentCaseResult, ...]
    determinism_comparisons: tuple[
        ExperimentDeterminismComparison, ...
    ]


@dataclass(frozen=True, slots=True)
class C008CBV2PrimaryExecution:
    """Three-run B-v2 result set; it is not a historical v1 report."""

    case_results: tuple[ExperimentCaseResult, ...]
    same_context_comparisons: tuple[ExperimentDeterminismComparisonV2, ...]
    decimal_context_comparisons: tuple[ExperimentDeterminismComparisonV2, ...]


def _snapshot(
    aggregate: StructuralMetricAggregate,
) -> MetricAggregateSnapshot:
    kwargs = {
        "metric_name": aggregate.metric_name,
        "formula_id": aggregate.formula_id,
        "aggregate_status": aggregate.status,
        "value": aggregate.value,
        "eligible_count": aggregate.eligible_count,
        "matured_count": aggregate.matured_count,
        "censored_count": aggregate.censored_count,
        "unavailable_count": aggregate.unavailable_count,
        "schema_version": 1,
    }
    payload = {
        "metric_name": aggregate.metric_name.value,
        "formula_id": aggregate.formula_id,
        "aggregate_status": aggregate.status.value,
        "value": (
            None if aggregate.value is None else str(aggregate.value)
        ),
        "eligible_count": aggregate.eligible_count,
        "matured_count": aggregate.matured_count,
        "censored_count": aggregate.censored_count,
        "unavailable_count": aggregate.unavailable_count,
        "schema_version": 1,
    }
    return MetricAggregateSnapshot(
        aggregate_snapshot_id=semantic_id(
            MetricAggregateSnapshot._PREFIX, payload
        ),
        **kwargs,
    )


def _case_result(
    pair: C008CBExecutionPair,
    variant: ExperimentVariant,
    *,
    status: ExperimentCaseStatus,
    run: MSACoreRun | None,
    audit: CausalAuditReport | None,
    metric_report: MetricEvaluationReport | None,
    failure_stage: ExperimentFailureStage | None,
    failure_error_type: str | None,
) -> ExperimentCaseResult:
    aggregate_snapshots = (
        ()
        if metric_report is None
        or status is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED
        else tuple(_snapshot(item) for item in metric_report.aggregates)
    )
    run_payload = None if run is None else run.to_dict()
    audit_payload = None if audit is None else audit.to_dict()
    metric_payload = (
        None if metric_report is None else metric_report.to_dict()
    )
    kwargs = {
        "execution_pair_id": pair.execution_pair_id,
        "dataset_case_id": pair.dataset_case_id,
        "variant_id": pair.variant_id,
        "experiment_kind": variant.experiment_kind,
        "level": variant.level,
        "partition": pair.partition,
        "scenario": pair.scenario,
        "seed": pair.seed,
        "status": status,
        "source_input_payload_digest": pair.source_input_payload_digest,
        "core_config_payload_digest": pair.core_config_payload_digest,
        "metric_config_payload_digest": pair.metric_config_payload_digest,
        "run_id": None if run is None else run.run_id,
        "run_payload_digest": (
            None if run_payload is None else digest(run_payload)
        ),
        "audit_report_id": (
            None if audit is None else audit.audit_report_id
        ),
        "audit_payload_digest": (
            None if audit_payload is None else digest(audit_payload)
        ),
        "audit_passed": None if audit is None else audit.passed,
        "metric_report_id": (
            None
            if metric_report is None
            else metric_report.metric_report_id
        ),
        "metric_report_payload_digest": (
            None if metric_payload is None else digest(metric_payload)
        ),
        "aggregates": aggregate_snapshots,
        "event_count": (
            0 if metric_report is None else metric_report.event_count
        ),
        "box_episode_count": (
            0 if run is None else run.report.created_event_count
        ),
        "matured_count": (
            0
            if metric_report is None
            else metric_report.matured_observation_count
        ),
        "censored_count": (
            0
            if metric_report is None
            else metric_report.censored_observation_count
        ),
        "unavailable_count": (
            0
            if metric_report is None
            else metric_report.unavailable_observation_count
        ),
        "failure_stage": failure_stage,
        "failure_error_type": failure_error_type,
        "schema_version": 1,
    }
    payload = {
        "execution_pair_id": pair.execution_pair_id,
        "dataset_case_id": pair.dataset_case_id,
        "variant_id": pair.variant_id,
        "experiment_kind": variant.experiment_kind.value,
        "level": variant.level.value,
        "partition": pair.partition.value,
        "scenario": pair.scenario.value,
        "seed": pair.seed,
        "status": status.value,
        "source_input_payload_digest": pair.source_input_payload_digest,
        "core_config_payload_digest": pair.core_config_payload_digest,
        "metric_config_payload_digest": pair.metric_config_payload_digest,
        "run_id": kwargs["run_id"],
        "run_payload_digest": kwargs["run_payload_digest"],
        "audit_report_id": kwargs["audit_report_id"],
        "audit_payload_digest": kwargs["audit_payload_digest"],
        "audit_passed": kwargs["audit_passed"],
        "metric_report_id": kwargs["metric_report_id"],
        "metric_report_payload_digest": kwargs[
            "metric_report_payload_digest"
        ],
        "aggregates": [item.to_dict() for item in aggregate_snapshots],
        "event_count": kwargs["event_count"],
        "box_episode_count": kwargs["box_episode_count"],
        "matured_count": kwargs["matured_count"],
        "censored_count": kwargs["censored_count"],
        "unavailable_count": kwargs["unavailable_count"],
        "failure_stage": (
            None if failure_stage is None else failure_stage.value
        ),
        "failure_error_type": failure_error_type,
        "schema_version": 1,
    }
    return ExperimentCaseResult(
        case_result_id=semantic_id(
            ExperimentCaseResult._PREFIX, payload
        ),
        **kwargs,
    )


def _execute_pair(
    pair: C008CBExecutionPair,
    case: ExperimentDatasetCase,
    variant: ExperimentVariant,
) -> _ExecutionArtifacts:
    if (
        pair.dataset_case_id != case.dataset_case_id
        or pair.variant_id != variant.variant_id
        or pair.seed == 3
        or pair.deferred_to_c008c_c
    ):
        raise C008CBCaseError(
            "execution pair does not bind an executable B-stage authority"
        )
    try:
        pipeline = MSACorePipeline(variant.core_config_snapshot)
        run = pipeline.run(case.source_input)
    except MSACoreError as exc:
        return _ExecutionArtifacts(
            result=_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.PIPELINE_FAILED,
                run=None,
                audit=None,
                metric_report=None,
                failure_stage=ExperimentFailureStage.PIPELINE,
                failure_error_type=type(exc).__name__,
            ),
            run=None,
            audit=None,
            metric_report=None,
        )
    try:
        audit = CausalAuditor().audit_run(run)
    except MSAValidationError as exc:
        # A formal audit entrypoint failure is recorded without retry.
        return _ExecutionArtifacts(
            result=_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.CAUSAL_AUDIT_FAILED,
                run=run,
                audit=None,
                metric_report=None,
                failure_stage=ExperimentFailureStage.CAUSAL_AUDIT,
                failure_error_type=type(exc).__name__,
            ),
            run=run,
            audit=None,
            metric_report=None,
        )
    if not audit.passed:
        return _ExecutionArtifacts(
            result=_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.CAUSAL_AUDIT_FAILED,
                run=run,
                audit=audit,
                metric_report=None,
                failure_stage=ExperimentFailureStage.CAUSAL_AUDIT,
                failure_error_type=C008CBCausalAuditFailure.__name__,
            ),
            run=run,
            audit=audit,
            metric_report=None,
        )
    try:
        metric_report = StructuralMetricEvaluator(
            variant.metric_config_snapshot
        ).evaluate(run)
    except StructuralMetricError as exc:
        return _ExecutionArtifacts(
            result=_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.METRIC_EVALUATION_FAILED,
                run=run,
                audit=audit,
                metric_report=None,
                failure_stage=ExperimentFailureStage.METRIC_EVALUATION,
                failure_error_type=type(exc).__name__,
            ),
            run=run,
            audit=audit,
            metric_report=None,
        )
    try:
        validate_metric_evaluation_report(run, metric_report)
    except StructuralMetricError as exc:
        return _ExecutionArtifacts(
            result=_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED,
                run=run,
                audit=audit,
                metric_report=metric_report,
                failure_stage=ExperimentFailureStage.METRIC_SOURCE_BIND,
                failure_error_type=type(exc).__name__,
            ),
            run=run,
            audit=audit,
            metric_report=metric_report,
        )
    return _ExecutionArtifacts(
        result=_case_result(
            pair,
            variant,
            status=ExperimentCaseStatus.PASSED,
            run=run,
            audit=audit,
            metric_report=metric_report,
            failure_stage=None,
            failure_error_type=None,
        ),
        run=run,
        audit=audit,
        metric_report=metric_report,
    )


def _payload_equal(
    left: object | None,
    right: object | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return left.to_dict() == right.to_dict()


def _determinism(
    pair: C008CBExecutionPair,
    first: _ExecutionArtifacts,
    second: _ExecutionArtifacts,
) -> ExperimentDeterminismComparison:
    run_equal = _payload_equal(first.run, second.run)
    audit_equal = _payload_equal(first.audit, second.audit)
    metric_equal = _payload_equal(
        first.metric_report, second.metric_report
    )
    first_payload = first.result.to_dict()
    second_payload = second.result.to_dict()
    case_equal = first_payload == second_payload
    all_equal = run_equal and audit_equal and metric_equal and case_equal
    status = (
        ReplayComparisonStatus.MATCH
        if all_equal
        else ReplayComparisonStatus.MISMATCH
    )
    kwargs = {
        "execution_pair_id": pair.execution_pair_id,
        "dataset_case_id": pair.dataset_case_id,
        "variant_id": pair.variant_id,
        "status": status,
        "first_case_result_id": first.result.case_result_id,
        "second_case_result_id": second.result.case_result_id,
        "first_case_payload_digest": digest(first_payload),
        "second_case_payload_digest": digest(second_payload),
        "run_payload_equal": run_equal,
        "audit_payload_equal": audit_equal,
        "metric_payload_equal": metric_equal,
        "case_result_payload_equal": case_equal,
        "decimal_context_changed": True,
        "failure_error_type": None,
        "schema_version": 1,
    }
    payload = {
        key: value.value if isinstance(value, ReplayComparisonStatus) else value
        for key, value in kwargs.items()
    }
    return ExperimentDeterminismComparison(
        determinism_comparison_id=semantic_id(
            ExperimentDeterminismComparison._PREFIX, payload
        ),
        **kwargs,
    )


def _determinism_v2(
    pair: C008CBExecutionPair,
    normal_a: _ExecutionArtifacts,
    compared: _ExecutionArtifacts,
    comparison_kind: DeterminismEvidenceKind,
) -> ExperimentDeterminismComparisonV2:
    """Build one comparison whose kind is part of its identity and digest."""

    if not isinstance(comparison_kind, DeterminismEvidenceKind):
        raise C008CBCaseError(
            "B-v2 comparison_kind must be DeterminismEvidenceKind"
        )
    run_equal = _payload_equal(normal_a.run, compared.run)
    audit_equal = _payload_equal(normal_a.audit, compared.audit)
    metric_equal = _payload_equal(
        normal_a.metric_report, compared.metric_report
    )
    normal_payload = normal_a.result.to_dict()
    compared_payload = compared.result.to_dict()
    case_equal = normal_payload == compared_payload
    all_equal = run_equal and audit_equal and metric_equal and case_equal
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "comparison_kind": comparison_kind,
        "execution_pair_id": pair.execution_pair_id,
        "dataset_case_id": pair.dataset_case_id,
        "variant_id": pair.variant_id,
        "status": (
            ReplayComparisonStatus.MATCH
            if all_equal
            else ReplayComparisonStatus.MISMATCH
        ),
        "normal_a_case_result_id": normal_a.result.case_result_id,
        "compared_case_result_id": compared.result.case_result_id,
        "normal_a_payload_digest": digest(normal_payload),
        "compared_payload_digest": digest(compared_payload),
        "run_payload_equal": run_equal,
        "audit_payload_equal": audit_equal,
        "metric_payload_equal": metric_equal,
        "case_result_payload_equal": case_equal,
        "decimal_context_changed": (
            comparison_kind
            is DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
        ),
        "schema_version": 2,
    }
    payload = {
        key: value.value if isinstance(value, Enum) else value
        for key, value in kwargs.items()
    }
    return ExperimentDeterminismComparisonV2(
        determinism_comparison_id=v2_payload_id(
            ExperimentDeterminismComparisonV2._PREFIX, payload
        ),
        **kwargs,
    )


def _execute_pair_v2(
    item: tuple[C008CBExecutionPair, ExperimentDatasetCase, ExperimentVariant],
) -> tuple[
    ExperimentCaseResult,
    ExperimentDeterminismComparisonV2,
    ExperimentDeterminismComparisonV2,
]:
    """Run normal A, normal B, and altered Decimal as independent outcomes."""

    pair, case, variant = item
    if (
        pair.deferred_to_c008c_c
        or pair.seed == 3
        or pair.partition is DatasetPartition.OOS
        or case.seed == 3
        or case.partition is DatasetPartition.OOS
    ):
        raise C008CBCaseError("B-v2 primary execution forbids seed 3/OOS")
    with localcontext() as normal_context_a:
        normal_context_a.prec = 28
        normal_context_a.rounding = ROUND_HALF_EVEN
        normal_a = _execute_pair(pair, case, variant)
    with localcontext() as normal_context_b:
        normal_context_b.prec = 28
        normal_context_b.rounding = ROUND_HALF_EVEN
        normal_b = _execute_pair(pair, case, variant)
    with localcontext() as altered_context:
        altered_context.prec = 7
        altered_context.rounding = ROUND_FLOOR
        altered = _execute_pair(pair, case, variant)
    same_context = _determinism_v2(
        pair,
        normal_a,
        normal_b,
        DeterminismEvidenceKind.SAME_CONTEXT_REPEAT,
    )
    decimal_context = _determinism_v2(
        pair,
        normal_a,
        altered,
        DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION,
    )
    if (
        same_context.determinism_comparison_id
        == decimal_context.determinism_comparison_id
        or digest(same_context.to_dict()) == digest(decimal_context.to_dict())
    ):
        raise C008CBComparisonError(
            "B-v2 comparison evidence must have distinct identity and digest"
        )
    return normal_a.result, same_context, decimal_context


def _execute_pair_repeat(
    item: tuple[C008CBExecutionPair, ExperimentDatasetCase, ExperimentVariant],
) -> tuple[ExperimentCaseResult, ExperimentDeterminismComparison]:
    pair, case, variant = item
    first = _execute_pair(pair, case, variant)
    with localcontext() as altered:
        altered.prec = 7
        altered.rounding = ROUND_FLOOR
        second = _execute_pair(pair, case, variant)
    return first.result, _determinism(pair, first, second)


def run_primary_execution(
    manifest: C008CBExecutionManifest,
    root: Path | None = None,
    *,
    progress_every: int = 20,
) -> C008CBPrimaryExecution:
    """Execute all 390 frozen pairs twice without selective omission."""

    validate_c008c_b_execution_manifest(manifest, root)
    _, dataset, _, plan, _ = load_c008c_b_authority(root)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    results: list[ExperimentCaseResult] = []
    repeats: list[ExperimentDeterminismComparison] = []
    if type(progress_every) is not int or progress_every < 1:
        raise C008CBCaseError("progress_every must be positive integer")
    scheduled = tuple(
        (
            pair,
            cases[pair.dataset_case_id],
            variants[pair.variant_id],
        )
        for pair in manifest.execution_pairs
    )
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, (result, repeat) in enumerate(
            executor.map(_execute_pair_repeat, scheduled), start=1
        ):
            results.append(result)
            repeats.append(repeat)
            if index % progress_every == 0 or index == len(
                manifest.execution_pairs
            ):
                print(
                    f"C-008C-B primary progress {index}/"
                    f"{len(manifest.execution_pairs)}",
                    flush=True,
                )
    if tuple(item.execution_pair_id for item in results) != tuple(
        item.execution_pair_id for item in manifest.execution_pairs
    ):
        raise C008CBCaseError(
            "primary execution omitted or reordered a frozen pair"
        )
    return C008CBPrimaryExecution(tuple(results), tuple(repeats))


def run_primary_execution_v2(
    manifest: C008CBExecutionManifest,
    root: Path | None = None,
    *,
    progress_every: int = 20,
) -> C008CBV2PrimaryExecution:
    """Execute the corrected B-v2 primary triad; never schedules OOS."""

    validate_c008c_b_execution_manifest(manifest, root)
    _, dataset, _, plan, _ = load_c008c_b_authority(root)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    if type(progress_every) is not int or progress_every < 1:
        raise C008CBCaseError("progress_every must be positive integer")
    if any(
        item.deferred_to_c008c_c
        or item.seed == 3
        or item.partition is DatasetPartition.OOS
        for item in manifest.execution_pairs
    ):
        raise C008CBCaseError("B-v2 executable schedule contains seed 3/OOS")
    scheduled = tuple(
        (
            pair,
            cases[pair.dataset_case_id],
            variants[pair.variant_id],
        )
        for pair in manifest.execution_pairs
    )
    results: list[ExperimentCaseResult] = []
    same_context: list[ExperimentDeterminismComparisonV2] = []
    decimal_context: list[ExperimentDeterminismComparisonV2] = []
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, (result, same, decimal) in enumerate(
            executor.map(_execute_pair_v2, scheduled), start=1
        ):
            results.append(result)
            same_context.append(same)
            decimal_context.append(decimal)
            if index % progress_every == 0 or index == len(scheduled):
                print(
                    f"C-008C-B-v2 primary progress {index}/{len(scheduled)}",
                    flush=True,
                )
    expected_ids = tuple(item.execution_pair_id for item in manifest.execution_pairs)
    if (
        tuple(item.execution_pair_id for item in results) != expected_ids
        or tuple(item.execution_pair_id for item in same_context) != expected_ids
        or tuple(item.execution_pair_id for item in decimal_context) != expected_ids
    ):
        raise C008CBCaseError("B-v2 primary execution omitted or reordered a pair")
    return C008CBV2PrimaryExecution(
        tuple(results), tuple(same_context), tuple(decimal_context)
    )


__all__ = [
    "C008CBPrimaryExecution",
    "C008CBV2PrimaryExecution",
    "run_primary_execution",
    "run_primary_execution_v2",
]
