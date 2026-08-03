"""C-008C-B orchestration, compact summaries, and report validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from msa.validation.metrics import default_metric_formula_registry

from ..contracts import DatasetPartition
from ..identity import semantic_id
from .contracts import (
    REPOSITORY_BASE_COMMIT,
    C008CBExecutionManifest,
    C008CBRunReport,
    C008CBStageStatus,
    DegenerationStatus,
    ExperimentCaseResult,
    ExperimentCaseStatus,
    ExperimentDegenerationSummary,
    ExperimentMetricDeltaSummary,
    ExperimentPartitionSummary,
    ExperimentReplayComparison,
    ExperimentVariantSummary,
    GateEvaluationStatus,
    MetricDeltaCountSnapshot,
    ReplayComparisonStatus,
)
from .cutoff import run_fixed_cutoff_comparisons
from .degeneration import evaluate_validation_degeneration
from .deltas import calculate_metric_deltas
from .errors import C008CBReportError
from .gate_evaluator import evaluate_c008c_b_gates
from .manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)
from .replay import run_replay_comparisons
from .runner import run_primary_execution


_REPORT_ASSUMPTIONS = (
    "Report contains structural validation evidence only and has no trading interpretation",
    "Metric delta signs do not encode better worse reward score rank or recommendation",
    "All seed 3 OOS outcome execution remains deferred to locked C-008C-C",
    "READY_FOR_LOCKED_OOS means permission for synthetic OOS only not Core Freeze production or C-009 readiness",
    "No Variant Dataset parameter Gate threshold or execution order changed after outcome access",
    "Synthetic results do not establish profitability external validity or real-market performance",
)


def _metric_count(
    metric_name: object,
    *,
    comparable: int,
    equal: int,
    non_zero: int,
    unavailable: int,
) -> MetricDeltaCountSnapshot:
    kwargs = {
        "metric_name": metric_name,
        "comparable_count": comparable,
        "equal_count": equal,
        "non_zero_count": non_zero,
        "unavailable_count": unavailable,
        "schema_version": 1,
    }
    payload = {
        "metric_name": metric_name.value,
        "comparable_count": comparable,
        "equal_count": equal,
        "non_zero_count": non_zero,
        "unavailable_count": unavailable,
        "schema_version": 1,
    }
    return MetricDeltaCountSnapshot(
        metric_delta_count_id=semantic_id(
            MetricDeltaCountSnapshot._PREFIX, payload
        ),
        **kwargs,
    )


def _variant_summary(
    *,
    partition: DatasetPartition,
    variant: object,
    results: tuple[ExperimentCaseResult, ...],
    delta_summary: ExperimentMetricDeltaSummary | None,
    replay_status: ReplayComparisonStatus,
    degeneration_status: DegenerationStatus,
) -> ExperimentVariantSummary:
    formulas = default_metric_formula_registry()
    metric_counts: list[MetricDeltaCountSnapshot] = []
    for formula in formulas:
        deltas = (
            ()
            if delta_summary is None
            else tuple(
                item
                for item in delta_summary.metric_deltas
                if item.metric_name is formula.metric_name
            )
        )
        comparable = tuple(
            item for item in deltas if item.absolute_delta is not None
        )
        metric_counts.append(
            _metric_count(
                formula.metric_name,
                comparable=len(comparable),
                equal=sum(
                    item.absolute_delta == 0 for item in comparable
                ),
                non_zero=sum(
                    item.absolute_delta != 0 for item in comparable
                ),
                unavailable=(
                    len(results) - len(comparable)
                    if delta_summary is None
                    else len(deltas) - len(comparable)
                ),
            )
        )
    kwargs = {
        "partition": partition,
        "variant_id": variant.variant_id,
        "executed_case_count": len(results),
        "passed_count": sum(
            item.status is ExperimentCaseStatus.PASSED
            for item in results
        ),
        "failed_count": sum(
            item.status is not ExperimentCaseStatus.PASSED
            for item in results
        ),
        "audit_failure_count": sum(
            item.status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED
            for item in results
        ),
        "metric_failure_count": sum(
            item.status is ExperimentCaseStatus.METRIC_EVALUATION_FAILED
            for item in results
        ),
        "metric_source_bind_failure_count": sum(
            item.status is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED
            for item in results
        ),
        "metric_counts": tuple(metric_counts),
        "structure_event_count": sum(
            item.event_count for item in results
        ),
        "box_episode_count": sum(
            item.box_episode_count for item in results
        ),
        "aggregate_complete_count": sum(
            len(item.aggregates) == 10 for item in results
        ),
        "replay_status": replay_status,
        "degeneration_status": degeneration_status,
        "schema_version": 1,
    }
    payload = {
        "partition": partition.value,
        "variant_id": variant.variant_id,
        "executed_case_count": kwargs["executed_case_count"],
        "passed_count": kwargs["passed_count"],
        "failed_count": kwargs["failed_count"],
        "audit_failure_count": kwargs["audit_failure_count"],
        "metric_failure_count": kwargs["metric_failure_count"],
        "metric_source_bind_failure_count": kwargs[
            "metric_source_bind_failure_count"
        ],
        "metric_counts": [item.to_dict() for item in metric_counts],
        "structure_event_count": kwargs["structure_event_count"],
        "box_episode_count": kwargs["box_episode_count"],
        "aggregate_complete_count": kwargs["aggregate_complete_count"],
        "replay_status": replay_status.value,
        "degeneration_status": degeneration_status.value,
        "schema_version": 1,
    }
    return ExperimentVariantSummary(
        variant_summary_id=semantic_id(
            ExperimentVariantSummary._PREFIX, payload
        ),
        **kwargs,
    )


def _partition_summaries(
    case_results: tuple[ExperimentCaseResult, ...],
    delta_summaries: tuple[ExperimentMetricDeltaSummary, ...],
    replay_comparisons: tuple[ExperimentReplayComparison, ...],
    degeneration_summaries: tuple[
        ExperimentDegenerationSummary, ...
    ],
    root: Path | None,
) -> tuple[ExperimentPartitionSummary, ...]:
    _, _, _, plan, _ = load_c008c_b_authority(root)
    delta_index = {
        (item.partition, item.variant_id): item
        for item in delta_summaries
    }
    degeneration_index = {
        item.variant_id: item.status
        for item in degeneration_summaries
    }
    replay_index = {
        variant.variant_id: (
            ReplayComparisonStatus.MATCH
            if all(
                item.status is ReplayComparisonStatus.MATCH
                for item in replay_comparisons
                if item.variant_id == variant.variant_id
            )
            else ReplayComparisonStatus.MISMATCH
        )
        for variant in plan.variants
    }
    summaries: list[ExperimentPartitionSummary] = []
    for partition in (
        DatasetPartition.DEVELOPMENT,
        DatasetPartition.VALIDATION,
    ):
        partition_results = tuple(
            item
            for item in case_results
            if item.partition is partition
        )
        variants = tuple(
            _variant_summary(
                partition=partition,
                variant=variant,
                results=tuple(
                    item
                    for item in partition_results
                    if item.variant_id == variant.variant_id
                ),
                delta_summary=delta_index.get(
                    (partition, variant.variant_id)
                ),
                replay_status=replay_index[variant.variant_id],
                degeneration_status=degeneration_index.get(
                    variant.variant_id,
                    DegenerationStatus.NOT_DEGENERATED,
                ),
            )
            for variant in plan.variants
        )
        kwargs = {
            "partition": partition,
            "variant_summaries": variants,
            "execution_pair_count": len(partition_results),
            "passed_case_count": sum(
                item.status is ExperimentCaseStatus.PASSED
                for item in partition_results
            ),
            "failed_case_count": sum(
                item.status is not ExperimentCaseStatus.PASSED
                for item in partition_results
            ),
            "metric_delta_count": sum(
                len(item.metric_deltas)
                for item in delta_summaries
                if item.partition is partition
            ),
            "schema_version": 1,
        }
        payload = {
            "partition": partition.value,
            "variant_summaries": [item.to_dict() for item in variants],
            "execution_pair_count": kwargs["execution_pair_count"],
            "passed_case_count": kwargs["passed_case_count"],
            "failed_case_count": kwargs["failed_case_count"],
            "metric_delta_count": kwargs["metric_delta_count"],
            "schema_version": 1,
        }
        summaries.append(
            ExperimentPartitionSummary(
                partition_summary_id=semantic_id(
                    ExperimentPartitionSummary._PREFIX, payload
                ),
                **kwargs,
            )
        )
    return tuple(summaries)


def build_c008c_b_report(
    manifest: C008CBExecutionManifest,
    case_results: tuple[ExperimentCaseResult, ...],
    determinism_comparisons: tuple,
    metric_delta_summaries: tuple[ExperimentMetricDeltaSummary, ...],
    partition_summaries: tuple[ExperimentPartitionSummary, ...],
    replay_comparisons: tuple[ExperimentReplayComparison, ...],
    fixed_cutoff_comparisons: tuple,
    degeneration_summaries: tuple[ExperimentDegenerationSummary, ...],
    gate_results: tuple,
) -> C008CBRunReport:
    """Build the compact report after every predeclared B execution."""

    stage_status = (
        C008CBStageStatus.BLOCKED_BEFORE_OOS
        if any(
            item.status is GateEvaluationStatus.FAIL
            for item in gate_results
        )
        else C008CBStageStatus.READY_FOR_LOCKED_OOS
    )
    kwargs = {
        "execution_manifest_id": manifest.execution_manifest_id,
        "repository_base_commit": REPOSITORY_BASE_COMMIT,
        "case_results": case_results,
        "determinism_comparisons": determinism_comparisons,
        "metric_delta_summaries": metric_delta_summaries,
        "partition_summaries": partition_summaries,
        "replay_comparisons": replay_comparisons,
        "fixed_cutoff_comparisons": fixed_cutoff_comparisons,
        "degeneration_summaries": degeneration_summaries,
        "gate_results": gate_results,
        "stage_status": stage_status,
        "executed_pair_count": len(case_results),
        "deferred_oos_pair_count": len(manifest.deferred_oos_pairs),
        "passed_case_count": sum(
            item.status is ExperimentCaseStatus.PASSED
            for item in case_results
        ),
        "failed_case_count": sum(
            item.status is not ExperimentCaseStatus.PASSED
            for item in case_results
        ),
        "deterministic_match_count": sum(
            item.status is ReplayComparisonStatus.MATCH
            for item in determinism_comparisons
        ),
        "deterministic_mismatch_count": sum(
            item.status is ReplayComparisonStatus.MISMATCH
            for item in determinism_comparisons
        ),
        "variant_replay_match_count": sum(
            item.scope == "VARIANT"
            and item.status is ReplayComparisonStatus.MATCH
            for item in replay_comparisons
        ),
        "baseline_replay_match_count": sum(
            item.scope == "BASELINE"
            and item.status is ReplayComparisonStatus.MATCH
            for item in replay_comparisons
        ),
        "cutoff_stable_case_count": sum(
            item.status.value == "STABLE"
            for item in fixed_cutoff_comparisons
        ),
        "assumptions": _REPORT_ASSUMPTIONS,
        "schema_version": 1,
    }
    payload = {
        "execution_manifest_id": manifest.execution_manifest_id,
        "repository_base_commit": REPOSITORY_BASE_COMMIT,
        "case_results": [item.to_dict() for item in case_results],
        "determinism_comparisons": [
            item.to_dict() for item in determinism_comparisons
        ],
        "metric_delta_summaries": [
            item.to_dict() for item in metric_delta_summaries
        ],
        "partition_summaries": [
            item.to_dict() for item in partition_summaries
        ],
        "replay_comparisons": [
            item.to_dict() for item in replay_comparisons
        ],
        "fixed_cutoff_comparisons": [
            item.to_dict() for item in fixed_cutoff_comparisons
        ],
        "degeneration_summaries": [
            item.to_dict() for item in degeneration_summaries
        ],
        "gate_results": [item.to_dict() for item in gate_results],
        "stage_status": stage_status.value,
        "executed_pair_count": kwargs["executed_pair_count"],
        "deferred_oos_pair_count": kwargs["deferred_oos_pair_count"],
        "passed_case_count": kwargs["passed_case_count"],
        "failed_case_count": kwargs["failed_case_count"],
        "deterministic_match_count": kwargs[
            "deterministic_match_count"
        ],
        "deterministic_mismatch_count": kwargs[
            "deterministic_mismatch_count"
        ],
        "variant_replay_match_count": kwargs[
            "variant_replay_match_count"
        ],
        "baseline_replay_match_count": kwargs[
            "baseline_replay_match_count"
        ],
        "cutoff_stable_case_count": kwargs[
            "cutoff_stable_case_count"
        ],
        "assumptions": list(_REPORT_ASSUMPTIONS),
        "schema_version": 1,
    }
    return C008CBRunReport(
        run_report_id=semantic_id(C008CBRunReport._PREFIX, payload),
        **kwargs,
    )


def validate_c008c_b_report(
    report: C008CBRunReport,
    manifest: C008CBExecutionManifest | None = None,
    root: Path | None = None,
) -> C008CBRunReport:
    """Validate strict contract, identity, authority binding, and coverage."""

    if not isinstance(report, C008CBRunReport):
        raise C008CBReportError("report must be C008CBRunReport")
    expected_manifest = (
        build_c008c_b_execution_manifest(root)
        if manifest is None
        else validate_c008c_b_execution_manifest(manifest, root)
    )
    try:
        payload = report.to_dict()
        restored = C008CBRunReport.from_dict(payload)
    except (
        AssertionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise C008CBReportError(
            "C-008C-B report formal validation failed"
        ) from exc
    if restored != report or restored.to_dict() != payload:
        raise C008CBReportError("C-008C-B report round-trip mismatch")
    if report.execution_manifest_id != expected_manifest.execution_manifest_id:
        raise C008CBReportError("report does not bind frozen B manifest")
    if tuple(
        item.execution_pair_id for item in report.case_results
    ) != tuple(
        item.execution_pair_id for item in expected_manifest.execution_pairs
    ):
        raise C008CBReportError(
            "report CaseResults omit or reorder frozen execution pairs"
        )
    _, _, gates, _, _ = load_c008c_b_authority(root)
    if tuple(item.gate_code for item in report.gate_results) != tuple(
        item.code for item in gates
    ):
        raise C008CBReportError(
            "report GateResults do not preserve frozen gate order"
        )
    return report


@dataclass(frozen=True, slots=True)
class C008CExperimentRunner:
    """Stateless source-bound C-008C-B runner."""

    root: Path | None = None

    def run(self) -> C008CBRunReport:
        manifest = build_c008c_b_execution_manifest(self.root)
        primary = run_primary_execution(manifest, self.root)
        deltas = calculate_metric_deltas(
            primary.case_results, self.root
        )
        replay = run_replay_comparisons(manifest, self.root)
        cutoff = run_fixed_cutoff_comparisons(manifest, self.root)
        degeneration = evaluate_validation_degeneration(
            primary.case_results,
            deltas,
            replay,
            cutoff,
            self.root,
        )
        gates = evaluate_c008c_b_gates(
            manifest,
            primary.case_results,
            primary.determinism_comparisons,
            replay,
            cutoff,
            degeneration,
            self.root,
        )
        partitions = _partition_summaries(
            primary.case_results,
            deltas,
            replay,
            degeneration,
            self.root,
        )
        report = build_c008c_b_report(
            manifest,
            primary.case_results,
            primary.determinism_comparisons,
            deltas,
            partitions,
            replay,
            cutoff,
            degeneration,
            gates,
        )
        return validate_c008c_b_report(report, manifest, self.root)


def run_c008c_b_dev_validation(
    root: Path | None = None,
) -> C008CBRunReport:
    return C008CExperimentRunner(root).run()


__all__ = [
    "C008CExperimentRunner",
    "build_c008c_b_report",
    "run_c008c_b_dev_validation",
    "validate_c008c_b_report",
]
