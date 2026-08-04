"""Frozen Baseline and Variant replay execution for C-008C-B."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from msa.research.msa_core import (
    MSACorePipeline,
    replay_msa_core_run,
)
from msa.research.msa_core.errors import MSACoreError
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
    ExperimentReplayComparison,
    ReplayComparisonStatus,
)
from .errors import C008CBComparisonError
from .manifest import (
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)


_FORMAL_MAX_WORKERS = 12


def _comparison(
    *,
    replay_sample_id: str,
    scope: str,
    case: object,
    variant: object,
    status: ReplayComparisonStatus,
    batch_run: object | None,
    replay_run: object | None,
    comparison_audit: object | None,
    batch_metric: object | None,
    replay_metric: object | None,
    run_equal: bool,
    metric_equal: bool,
    failure_error_type: str | None,
) -> ExperimentReplayComparison:
    kwargs = {
        "replay_sample_id": replay_sample_id,
        "scope": scope,
        "dataset_case_id": case.dataset_case_id,
        "variant_id": variant.variant_id,
        "partition": case.partition,
        "scenario": case.scenario_kind,
        "seed": case.seed,
        "status": status,
        "batch_run_id": (
            None if batch_run is None else batch_run.run_id
        ),
        "batch_run_payload_digest": (
            None if batch_run is None else digest(batch_run.to_dict())
        ),
        "replay_run_id": (
            None if replay_run is None else replay_run.run_id
        ),
        "replay_run_payload_digest": (
            None if replay_run is None else digest(replay_run.to_dict())
        ),
        "comparison_audit_id": (
            None
            if comparison_audit is None
            else comparison_audit.audit_report_id
        ),
        "comparison_audit_payload_digest": (
            None
            if comparison_audit is None
            else digest(comparison_audit.to_dict())
        ),
        "batch_metric_report_id": (
            None
            if batch_metric is None
            else batch_metric.metric_report_id
        ),
        "batch_metric_payload_digest": (
            None
            if batch_metric is None
            else digest(batch_metric.to_dict())
        ),
        "replay_metric_report_id": (
            None
            if replay_metric is None
            else replay_metric.metric_report_id
        ),
        "replay_metric_payload_digest": (
            None
            if replay_metric is None
            else digest(replay_metric.to_dict())
        ),
        "full_run_payload_equal": run_equal,
        "full_metric_payload_equal": metric_equal,
        "failure_error_type": failure_error_type,
        "schema_version": 1,
    }
    payload = {
        "replay_sample_id": replay_sample_id,
        "scope": scope,
        "dataset_case_id": case.dataset_case_id,
        "variant_id": variant.variant_id,
        "partition": case.partition.value,
        "scenario": case.scenario_kind.value,
        "seed": case.seed,
        "status": status.value,
        **{
            key: value
            for key, value in kwargs.items()
            if key
            not in (
                "replay_sample_id",
                "scope",
                "dataset_case_id",
                "variant_id",
                "partition",
                "scenario",
                "seed",
                "status",
            )
        },
    }
    return ExperimentReplayComparison(
        replay_comparison_id=semantic_id(
            ExperimentReplayComparison._PREFIX, payload
        ),
        **kwargs,
    )


def _execute_sample(
    replay_sample_id: str,
    scope: str,
    case: object,
    variant: object,
) -> ExperimentReplayComparison:
    if (
        case.partition is DatasetPartition.OOS
        or case.seed == 3
        or scope not in ("BASELINE", "VARIANT")
    ):
        raise C008CBComparisonError(
            "OOS or invalid replay sample reached execution"
        )
    batch_run = None
    replay_run = None
    comparison_audit = None
    batch_metric = None
    replay_metric = None
    try:
        pipeline = MSACorePipeline(variant.core_config_snapshot)
        batch_run = pipeline.run(case.source_input)
        replay_run = replay_msa_core_run(pipeline, case.source_input)
        comparison_audit = CausalAuditor().compare_batch_replay(
            batch_run, replay_run
        )
        evaluator = StructuralMetricEvaluator(
            variant.metric_config_snapshot
        )
        batch_metric = evaluator.evaluate(batch_run)
        validate_metric_evaluation_report(batch_run, batch_metric)
        replay_metric = evaluator.evaluate(replay_run)
        validate_metric_evaluation_report(replay_run, replay_metric)
    except (MSACoreError, MSAValidationError, StructuralMetricError) as exc:
        return _comparison(
            replay_sample_id=replay_sample_id,
            scope=scope,
            case=case,
            variant=variant,
            status=ReplayComparisonStatus.EXECUTION_FAILED,
            batch_run=batch_run,
            replay_run=replay_run,
            comparison_audit=comparison_audit,
            batch_metric=batch_metric,
            replay_metric=replay_metric,
            run_equal=False,
            metric_equal=False,
            failure_error_type=type(exc).__name__,
        )
    run_equal = batch_run.to_dict() == replay_run.to_dict()
    metric_equal = batch_metric.to_dict() == replay_metric.to_dict()
    status = (
        ReplayComparisonStatus.MATCH
        if comparison_audit.passed and run_equal and metric_equal
        else ReplayComparisonStatus.MISMATCH
    )
    return _comparison(
        replay_sample_id=replay_sample_id,
        scope=scope,
        case=case,
        variant=variant,
        status=status,
        batch_run=batch_run,
        replay_run=replay_run,
        comparison_audit=comparison_audit,
        batch_metric=batch_metric,
        replay_metric=replay_metric,
        run_equal=run_equal,
        metric_equal=metric_equal,
        failure_error_type=None,
    )


def _execute_scheduled_sample(
    item: tuple[str, str, object, object],
) -> ExperimentReplayComparison:
    return _execute_sample(*item)


def run_replay_comparisons(
    manifest: C008CBExecutionManifest,
    root: Path | None = None,
    *,
    progress_every: int = 10,
) -> tuple[ExperimentReplayComparison, ...]:
    """Execute exactly 15 Baseline and 125 frozen Variant replay samples."""

    validate_c008c_b_execution_manifest(manifest, root)
    _, dataset, _, plan, _ = load_c008c_b_authority(root)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    baseline = plan.variants[0]
    scheduled: list[tuple[str, str, object, object]] = []
    baseline_cases = tuple(
        cases[item] for item in manifest.executable_case_ids
    )
    scheduled.extend(
        (
            sample_id,
            "BASELINE",
            case,
            baseline,
        )
        for sample_id, case in zip(
            manifest.baseline_replay_sample_ids,
            baseline_cases,
            strict=True,
        )
    )
    variant_cases = tuple(
        cases[item] for item in plan.variant_replay_policy.dataset_case_ids
    )
    variant_schedule = tuple(
        (case, variant)
        for variant in plan.variants[1:]
        for case in variant_cases
    )
    scheduled.extend(
        (
            sample_id,
            "VARIANT",
            case,
            variant,
        )
        for sample_id, (case, variant) in zip(
            manifest.variant_replay_sample_ids,
            variant_schedule,
            strict=True,
        )
    )
    if len(scheduled) != 140:
        raise C008CBComparisonError(
            "replay schedule must contain exactly 140 B samples"
        )
    if type(progress_every) is not int or progress_every < 1:
        raise C008CBComparisonError(
            "progress_every must be positive integer"
        )
    results: list[ExperimentReplayComparison] = []
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, result in enumerate(
            executor.map(_execute_scheduled_sample, tuple(scheduled)),
            start=1,
        ):
            results.append(result)
            if index % progress_every == 0 or index == len(scheduled):
                print(
                    f"C-008C-B replay progress {index}/{len(scheduled)}",
                    flush=True,
                )
    return tuple(results)


__all__ = ["run_replay_comparisons"]
