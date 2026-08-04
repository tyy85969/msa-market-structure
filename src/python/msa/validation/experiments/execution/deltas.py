"""Descriptive same-case Baseline metric deltas for C-008C-B."""

from __future__ import annotations

from decimal import Decimal

from msa.validation.metrics import (
    MetricAggregateStatus,
    default_metric_formula_registry,
)

from ..contracts import DatasetPartition
from ..identity import semantic_id
from .contracts import (
    ExperimentCaseResult,
    ExperimentMetricDelta,
    ExperimentMetricDeltaSummary,
    MetricAggregateSnapshot,
    MetricDeltaStatus,
)
from .errors import C008CBComparisonError
from .manifest import load_c008c_b_authority


def _aggregate_index(
    result: ExperimentCaseResult,
) -> dict[object, MetricAggregateSnapshot]:
    return {item.metric_name: item for item in result.aggregates}


def _delta(
    baseline: ExperimentCaseResult,
    variant: ExperimentCaseResult,
    metric_name: object,
    formula_id: str,
) -> ExperimentMetricDelta:
    baseline_aggregate = _aggregate_index(baseline).get(metric_name)
    variant_aggregate = _aggregate_index(variant).get(metric_name)
    baseline_status = (
        None
        if baseline_aggregate is None
        else baseline_aggregate.aggregate_status
    )
    variant_status = (
        None
        if variant_aggregate is None
        else variant_aggregate.aggregate_status
    )
    baseline_value = (
        None if baseline_aggregate is None else baseline_aggregate.value
    )
    variant_value = (
        None if variant_aggregate is None else variant_aggregate.value
    )
    baseline_available = (
        baseline_status is MetricAggregateStatus.AVAILABLE
        and baseline_value is not None
    )
    variant_available = (
        variant_status is MetricAggregateStatus.AVAILABLE
        and variant_value is not None
    )
    status = (
        MetricDeltaStatus.COMPARABLE
        if baseline_available and variant_available
        else MetricDeltaStatus.BASELINE_UNAVAILABLE
        if not baseline_available and variant_available
        else MetricDeltaStatus.VARIANT_UNAVAILABLE
        if baseline_available and not variant_available
        else MetricDeltaStatus.BOTH_UNAVAILABLE
    )
    absolute_delta = (
        variant_value - baseline_value
        if status is MetricDeltaStatus.COMPARABLE
        else None
    )
    kwargs = {
        "dataset_case_id": baseline.dataset_case_id,
        "partition": baseline.partition,
        "scenario": baseline.scenario,
        "variant_id": variant.variant_id,
        "baseline_variant_id": baseline.variant_id,
        "metric_name": metric_name,
        "formula_id": formula_id,
        "baseline_aggregate_status": baseline_status,
        "variant_aggregate_status": variant_status,
        "baseline_value": baseline_value,
        "variant_value": variant_value,
        "absolute_delta": absolute_delta,
        "delta_status": status,
        "schema_version": 1,
    }
    payload = {
        "dataset_case_id": baseline.dataset_case_id,
        "partition": baseline.partition.value,
        "scenario": baseline.scenario.value,
        "variant_id": variant.variant_id,
        "baseline_variant_id": baseline.variant_id,
        "metric_name": metric_name.value,
        "formula_id": formula_id,
        "baseline_aggregate_status": (
            None if baseline_status is None else baseline_status.value
        ),
        "variant_aggregate_status": (
            None if variant_status is None else variant_status.value
        ),
        "baseline_value": (
            None if baseline_value is None else str(baseline_value)
        ),
        "variant_value": (
            None if variant_value is None else str(variant_value)
        ),
        "absolute_delta": (
            None if absolute_delta is None else str(absolute_delta)
        ),
        "delta_status": status.value,
        "schema_version": 1,
    }
    return ExperimentMetricDelta(
        metric_delta_id=semantic_id(
            ExperimentMetricDelta._PREFIX, payload
        ),
        **kwargs,
    )


def _summary(
    partition: DatasetPartition,
    variant_id: str,
    baseline_variant_id: str,
    deltas: tuple[ExperimentMetricDelta, ...],
) -> ExperimentMetricDeltaSummary:
    comparable = tuple(
        item
        for item in deltas
        if item.delta_status is MetricDeltaStatus.COMPARABLE
    )
    kwargs = {
        "partition": partition,
        "variant_id": variant_id,
        "baseline_variant_id": baseline_variant_id,
        "metric_deltas": deltas,
        "comparable_count": len(comparable),
        "equal_count": sum(
            item.absolute_delta == Decimal("0") for item in comparable
        ),
        "non_zero_count": sum(
            item.absolute_delta != Decimal("0") for item in comparable
        ),
        "unavailable_count": len(deltas) - len(comparable),
        "schema_version": 1,
    }
    payload = {
        "partition": partition.value,
        "variant_id": variant_id,
        "baseline_variant_id": baseline_variant_id,
        "metric_deltas": [item.to_dict() for item in deltas],
        "comparable_count": kwargs["comparable_count"],
        "equal_count": kwargs["equal_count"],
        "non_zero_count": kwargs["non_zero_count"],
        "unavailable_count": kwargs["unavailable_count"],
        "schema_version": 1,
    }
    return ExperimentMetricDeltaSummary(
        metric_delta_summary_id=semantic_id(
            ExperimentMetricDeltaSummary._PREFIX, payload
        ),
        **kwargs,
    )


def calculate_metric_deltas(
    case_results: tuple[ExperimentCaseResult, ...],
    root: object = None,
) -> tuple[ExperimentMetricDeltaSummary, ...]:
    """Calculate all 3,750 descriptive deltas without interpreting sign."""

    if (
        not isinstance(case_results, tuple)
        or len(case_results) != 390
        or any(
            not isinstance(item, ExperimentCaseResult)
            for item in case_results
        )
    ):
        raise C008CBComparisonError(
            "metric deltas require all 390 formal CaseResults"
        )
    _, dataset, _, plan, _ = load_c008c_b_authority(root)
    result_by_pair = {
        (item.dataset_case_id, item.variant_id): item
        for item in case_results
    }
    if len(result_by_pair) != 390:
        raise C008CBComparisonError(
            "CaseResults must bind 390 unique case/variant pairs"
        )
    baseline_variant_id = plan.variants[0].variant_id
    non_baseline_variant_ids = tuple(
        item.variant_id for item in plan.variants[1:]
    )
    formulas = default_metric_formula_registry()
    summaries: list[ExperimentMetricDeltaSummary] = []
    for partition in (
        DatasetPartition.DEVELOPMENT,
        DatasetPartition.VALIDATION,
    ):
        case_ids = tuple(
            item.dataset_case_id
            for item in dataset.cases
            if item.partition is partition
        )
        for variant_id in non_baseline_variant_ids:
            deltas = tuple(
                _delta(
                    result_by_pair[(case_id, baseline_variant_id)],
                    result_by_pair[(case_id, variant_id)],
                    formula.metric_name,
                    formula.metric_formula_id,
                )
                for case_id in case_ids
                for formula in formulas
            )
            summaries.append(
                _summary(
                    partition,
                    variant_id,
                    baseline_variant_id,
                    deltas,
                )
            )
    result = tuple(summaries)
    if len(result) != 50 or sum(
        len(item.metric_deltas) for item in result
    ) != 3750:
        raise C008CBComparisonError(
            "metric delta schedule must be exactly 3,750 comparisons"
        )
    return result


__all__ = ["calculate_metric_deltas"]
