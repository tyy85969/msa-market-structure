"""Baseline fixed-cutoff and future-append stability for C-008C-B."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta
from pathlib import Path

from msa.data import LoadResult, validate_bar_sequence
from msa.research.lifecycle import LifecycleHistory
from msa.research.msa_core import (
    MSACorePipeline,
)
from msa.research.msa_core.errors import MSACoreError
from msa.research.resonance import ResonanceFrameInput
from msa.research.timeframe_state import TimeframeStateHistory
from msa.validation.causal_audit import CausalAuditor
from msa.validation.errors import MSAValidationError
from msa.validation.metrics import (
    StructuralMetricError,
    StructuralMetricEvaluator,
    validate_metric_evaluation_report,
)

from ..contracts import DatasetPartition
from ..identity import digest, semantic_id
from .contracts import (
    C008CBExecutionManifest,
    ExperimentFixedCutoffCheckpoint,
    ExperimentFixedCutoffComparison,
    FixedCutoffStatus,
)
from .errors import C008CBComparisonError
from .manifest import (
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)


_FORMAL_MAX_WORKERS = 12


def _metric_cutoff_projection(report: object) -> dict[str, object]:
    """Compare complete causal outcomes while excluding source-run bindings."""

    payload = report.to_dict()
    return {
        key: value
        for key, value in payload.items()
        if key not in ("metric_report_id", "source_run_id", "provenance")
    }


def _truncate_source(
    source: ResonanceFrameInput,
    cutoff: object,
) -> ResonanceFrameInput:
    """Build a formal prefix from facts available no later than cutoff."""

    lifecycle_snapshots = tuple(
        item
        for item in source.lifecycle_history.snapshots
        if item.as_of_time <= cutoff
    )
    if not lifecycle_snapshots:
        raise C008CBComparisonError(
            "cutoff precedes every lifecycle snapshot"
        )
    lifecycle = LifecycleHistory(
        events=lifecycle_snapshots[-1].events,
        snapshots=lifecycle_snapshots,
        final_snapshot=lifecycle_snapshots[-1],
    )
    timeframe_histories = []
    for history in source.timeframe_state_histories:
        snapshots = tuple(
            item
            for item in history.snapshots
            if item.as_of_time <= cutoff
        )
        if not snapshots:
            raise C008CBComparisonError(
                "cutoff precedes a configured TimeframeState history"
            )
        timeframe_histories.append(
            TimeframeStateHistory(
                events=snapshots[-1].events,
                snapshots=snapshots,
                final_snapshot=snapshots[-1],
                config_snapshot=history.config_snapshot,
            )
        )
    bars = tuple(
        item
        for item in source.reference_price_data.bars
        if item.available_time <= cutoff
    )
    if not bars:
        raise C008CBComparisonError(
            "cutoff precedes every available reference bar"
        )
    original = source.reference_price_data
    quality = validate_bar_sequence(
        bars,
        source=original.source_config.source,
        timeframe=original.source_config.timeframe,
    )
    reference = LoadResult(
        bars=bars,
        quality_report=quality,
        source_config=original.source_config,
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )
    return ResonanceFrameInput(
        lifecycle,
        tuple(timeframe_histories),
        reference,
    )


def _checkpoint(
    *,
    cutoff: object,
    prefix_run: object,
    extended_run: object,
    comparison_audit: object,
    prefix_metric: object,
    extended_metric: object,
    stable: bool,
) -> ExperimentFixedCutoffCheckpoint:
    kwargs = {
        "cutoff_as_of_time": cutoff,
        "prefix_run_payload_digest": digest(prefix_run.to_dict()),
        "extended_run_payload_digest": digest(extended_run.to_dict()),
        "comparison_audit_id": comparison_audit.audit_report_id,
        "comparison_audit_payload_digest": digest(
            comparison_audit.to_dict()
        ),
        "prefix_metric_payload_digest": digest(prefix_metric.to_dict()),
        "extended_metric_payload_digest": digest(
            extended_metric.to_dict()
        ),
        "stable": stable,
        "schema_version": 1,
    }
    payload = {
        "cutoff_as_of_time": cutoff.isoformat(),
        **kwargs,
    }
    payload["cutoff_as_of_time"] = cutoff.isoformat()
    return ExperimentFixedCutoffCheckpoint(
        cutoff_checkpoint_id=semantic_id(
            ExperimentFixedCutoffCheckpoint._PREFIX, payload
        ),
        **kwargs,
    )


def _comparison(
    *,
    case: object,
    baseline_variant_id: str,
    status: FixedCutoffStatus,
    checkpoints: tuple[ExperimentFixedCutoffCheckpoint, ...],
    failure_error_type: str | None,
) -> ExperimentFixedCutoffComparison:
    kwargs = {
        "dataset_case_id": case.dataset_case_id,
        "baseline_variant_id": baseline_variant_id,
        "partition": case.partition,
        "scenario": case.scenario_kind,
        "seed": case.seed,
        "status": status,
        "checkpoints": checkpoints,
        "stable_checkpoint_count": sum(
            item.stable for item in checkpoints
        ),
        "rewrite_count": sum(not item.stable for item in checkpoints),
        "failure_error_type": failure_error_type,
        "schema_version": 1,
    }
    payload = {
        "dataset_case_id": case.dataset_case_id,
        "baseline_variant_id": baseline_variant_id,
        "partition": case.partition.value,
        "scenario": case.scenario_kind.value,
        "seed": case.seed,
        "status": status.value,
        "checkpoints": [item.to_dict() for item in checkpoints],
        "stable_checkpoint_count": kwargs["stable_checkpoint_count"],
        "rewrite_count": kwargs["rewrite_count"],
        "failure_error_type": failure_error_type,
        "schema_version": 1,
    }
    return ExperimentFixedCutoffComparison(
        fixed_cutoff_comparison_id=semantic_id(
            ExperimentFixedCutoffComparison._PREFIX, payload
        ),
        **kwargs,
    )


def _execute_case(
    case: object,
    baseline: object,
) -> ExperimentFixedCutoffComparison:
    if case.seed == 3 or case.partition is DatasetPartition.OOS:
        raise C008CBComparisonError(
            "OOS case reached fixed-cutoff execution"
        )
    checkpoints: list[ExperimentFixedCutoffCheckpoint] = []
    try:
        pipeline = MSACorePipeline(baseline.core_config_snapshot)
        extended_run = pipeline.run(case.source_input)
        schedule = extended_run.processing_times
        auditor = CausalAuditor()
        evaluator = StructuralMetricEvaluator(
            baseline.metric_config_snapshot
        )
        for index, cutoff in enumerate(schedule):
            prefix_source = _truncate_source(case.source_input, cutoff)
            prefix_run = pipeline.run(prefix_source)
            comparison_audit = auditor.compare_shared_asof(
                prefix_run,
                extended_run,
                cutoff + timedelta(microseconds=1),
            )
            prefix_stable = True
            if index + 1 < len(schedule):
                prefix_stable = auditor.compare_prefix(
                    prefix_run, extended_run
                ).passed
            prefix_metric = evaluator.evaluate(prefix_run)
            validate_metric_evaluation_report(prefix_run, prefix_metric)
            extended_metric = evaluator.evaluate(extended_run, cutoff)
            validate_metric_evaluation_report(
                extended_run, extended_metric
            )
            metric_stable = (
                _metric_cutoff_projection(prefix_metric)
                == _metric_cutoff_projection(extended_metric)
            )
            stable = (
                comparison_audit.passed
                and prefix_stable
                and metric_stable
            )
            checkpoints.append(
                _checkpoint(
                    cutoff=cutoff,
                    prefix_run=prefix_run,
                    extended_run=extended_run,
                    comparison_audit=comparison_audit,
                    prefix_metric=prefix_metric,
                    extended_metric=extended_metric,
                    stable=stable,
                )
            )
    except (
        C008CBComparisonError,
        MSACoreError,
        MSAValidationError,
        StructuralMetricError,
    ) as exc:
        return _comparison(
            case=case,
            baseline_variant_id=baseline.variant_id,
            status=FixedCutoffStatus.EXECUTION_FAILED,
            checkpoints=tuple(checkpoints),
            failure_error_type=type(exc).__name__,
        )
    frozen = tuple(checkpoints)
    status = (
        FixedCutoffStatus.STABLE
        if all(item.stable for item in frozen)
        else FixedCutoffStatus.REWRITE_DETECTED
    )
    return _comparison(
        case=case,
        baseline_variant_id=baseline.variant_id,
        status=status,
        checkpoints=frozen,
        failure_error_type=None,
    )


def run_fixed_cutoff_comparisons(
    manifest: C008CBExecutionManifest,
    root: Path | None = None,
) -> tuple[ExperimentFixedCutoffComparison, ...]:
    """Execute every formal causal AsOf for 15 Baseline B-stage cases."""

    validate_c008c_b_execution_manifest(manifest, root)
    _, dataset, _, plan, _ = load_c008c_b_authority(root)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    baseline = plan.variants[0]
    results: list[ExperimentFixedCutoffComparison] = []
    scheduled = tuple(
        (cases[case_id], baseline)
        for case_id in manifest.fixed_cutoff_case_ids
    )
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, result in enumerate(
            executor.map(_execute_cutoff_case, scheduled), start=1
        ):
            results.append(result)
            print(
                f"C-008C-B fixed-cutoff progress {index}/"
                f"{len(manifest.fixed_cutoff_case_ids)}",
                flush=True,
            )
    return tuple(results)


def _execute_cutoff_case(
    item: tuple[object, object],
) -> ExperimentFixedCutoffComparison:
    return _execute_case(*item)


__all__ = ["run_fixed_cutoff_comparisons"]
