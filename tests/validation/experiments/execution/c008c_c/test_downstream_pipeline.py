from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from c008c_c import architecture
from c008c_c.contracts import (
    C008CCCaseResult,
    C008CCFixedCutoffComparison,
    C008CCMetricDeltaSummary,
    C008CCPartition,
    C008CCReplayComparison,
)
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseStatus,
    FixedCutoffStatus,
    MetricAggregateSnapshot,
    ReplayComparisonStatus,
)
from msa.validation.experiments.execution.contracts_v2 import (
    B_V2_EXECUTION_SEMANTICS,
    B_V2_SCHEMA_VERSION,
    DeterminismEvidenceKind,
    ExperimentDeterminismComparisonV2,
    v2_payload_id,
)
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)
from msa.validation.experiments.identity import canonical_json_bytes, semantic_id
from msa.validation.metrics import (
    MetricAggregateStatus,
    StructuralMetricAggregate,
    default_metric_formula_registry,
)


ROOT = Path(__file__).resolve().parents[5]


def _snapshot(metric_name: object, formula_id: str, value: Decimal) -> object:
    kwargs = {
        "metric_name": metric_name,
        "formula_id": formula_id,
        "aggregate_status": MetricAggregateStatus.AVAILABLE,
        "value": value,
        "eligible_count": 1,
        "matured_count": 1,
        "censored_count": 0,
        "unavailable_count": 0,
        "schema_version": 1,
    }
    payload = {
        "metric_name": metric_name.value,
        "formula_id": formula_id,
        "aggregate_status": MetricAggregateStatus.AVAILABLE.value,
        "value": str(value),
        "eligible_count": 1,
        "matured_count": 1,
        "censored_count": 0,
        "unavailable_count": 0,
        "schema_version": 1,
    }
    return MetricAggregateSnapshot(
        aggregate_snapshot_id=semantic_id(
            MetricAggregateSnapshot._PREFIX, payload
        ),
        **kwargs,
    )


def _case_result(pair: object, variant: object) -> C008CCCaseResult:
    value = Decimal(pair.schedule_index + 1)
    aggregates = tuple(
        _snapshot(
            formula.metric_name,
            formula.metric_formula_id,
            value,
        )
        for formula in default_metric_formula_registry()
    )
    return C008CCCaseResult.create(
        execution_pair_id=pair.execution_pair_id,
        dataset_case_id=pair.dataset_case_id,
        variant_id=pair.variant_id,
        experiment_kind=variant.experiment_kind,
        level=variant.level,
        partition=C008CCPartition.LOCKED_OOS,
        scenario=pair.scenario,
        seed=3,
        execution_status=ExperimentCaseStatus.PASSED,
        source_input_payload_digest=pair.source_input_payload_digest,
        core_config_payload_digest=pair.core_config_payload_digest,
        metric_config_payload_digest=pair.metric_config_payload_digest,
        run_id=f"mock-run-{pair.execution_pair_id}",
        run_payload_digest=f"mock-run-digest-{pair.execution_pair_id}",
        audit_report_id=f"mock-audit-{pair.execution_pair_id}",
        audit_payload_digest=f"mock-audit-digest-{pair.execution_pair_id}",
        audit_passed=True,
        metric_report_id=f"mock-metric-{pair.execution_pair_id}",
        metric_report_payload_digest=(
            f"mock-metric-digest-{pair.execution_pair_id}"
        ),
        aggregates=aggregates,
        event_count=1,
        box_episode_count=1,
        matured_count=10,
        censored_count=0,
        unavailable_count=0,
        failure_stage=None,
        failure_error_type=None,
        schema_version=1,
    )


def _determinism(
    result: C008CCCaseResult,
    kind: DeterminismEvidenceKind,
) -> ExperimentDeterminismComparisonV2:
    payload_digest = f"mock-case-digest-{result.execution_pair_id}"
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "comparison_kind": kind,
        "execution_pair_id": result.execution_pair_id,
        "dataset_case_id": result.dataset_case_id,
        "variant_id": result.variant_id,
        "status": ReplayComparisonStatus.MATCH,
        "normal_a_case_result_id": result.case_result_id,
        "compared_case_result_id": result.case_result_id,
        "normal_a_payload_digest": payload_digest,
        "compared_payload_digest": payload_digest,
        "run_payload_equal": True,
        "audit_payload_equal": True,
        "metric_payload_equal": True,
        "case_result_payload_equal": True,
        "decimal_context_changed": (
            kind is DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
        ),
        "schema_version": B_V2_SCHEMA_VERSION,
    }
    payload = {
        key: value.value if hasattr(value, "value") else value
        for key, value in kwargs.items()
    }
    return ExperimentDeterminismComparisonV2(
        determinism_comparison_id=v2_payload_id(
            ExperimentDeterminismComparisonV2._PREFIX, payload
        ),
        **kwargs,
    )


def _coverage_aggregate(
    case_id: str,
    metric_name: object,
    formula_id: str,
) -> StructuralMetricAggregate:
    observation_id = f"mock-observation-{case_id}-{metric_name.value}"
    kwargs = {
        "metric_name": metric_name,
        "formula_id": formula_id,
        "status": MetricAggregateStatus.AVAILABLE,
        "value": Decimal("1"),
        "eligible_count": 1,
        "matured_count": 1,
        "censored_count": 0,
        "unavailable_count": 0,
        "numerator": Decimal("1"),
        "denominator": None,
        "source_observation_ids": (observation_id,),
        "schema_version": 1,
    }
    payload = {
        "metric_name": metric_name.value,
        "formula_id": formula_id,
        "status": MetricAggregateStatus.AVAILABLE.value,
        "value": "1",
        "eligible_count": 1,
        "matured_count": 1,
        "censored_count": 0,
        "unavailable_count": 0,
        "numerator": "1",
        "denominator": None,
        "source_observation_ids": [observation_id],
        "schema_version": 1,
    }
    return StructuralMetricAggregate(
        metric_aggregate_id=semantic_id(
            "structural-metric-aggregate-v1-", payload
        ),
        **kwargs,
    )


def _coverage_sources(
    case_results: tuple[C008CCCaseResult, ...],
    baseline_id: str,
) -> list[dict[str, object]]:
    return [
        {
            "case_result_id": result.case_result_id,
            "dataset_case_id": result.dataset_case_id,
            "metric_report_id": result.metric_report_id,
            "aggregates": [
                _coverage_aggregate(
                    result.dataset_case_id,
                    formula.metric_name,
                    formula.metric_formula_id,
                ).to_dict()
                for formula in default_metric_formula_registry()
            ],
        }
        for result in case_results
        if result.variant_id == baseline_id
    ]


def _replays_and_cutoffs(
    case_results: tuple[C008CCCaseResult, ...],
    baseline_id: str,
    checkpoint: object,
) -> tuple[
    tuple[C008CCReplayComparison, ...],
    tuple[C008CCFixedCutoffComparison, ...],
]:
    baseline_results = tuple(
        result for result in case_results if result.variant_id == baseline_id
    )
    replays = tuple(
        C008CCReplayComparison.create(
            replay_sample_id=f"mock-replay-{result.dataset_case_id}",
            scope="BASELINE",
            dataset_case_id=result.dataset_case_id,
            variant_id=baseline_id,
            partition=C008CCPartition.LOCKED_OOS,
            scenario=result.scenario,
            seed=3,
            status=ReplayComparisonStatus.MATCH,
            batch_run_id=f"batch-{result.dataset_case_id}",
            batch_run_payload_digest=f"batch-digest-{result.dataset_case_id}",
            replay_run_id=f"replay-{result.dataset_case_id}",
            replay_run_payload_digest=f"replay-digest-{result.dataset_case_id}",
            comparison_audit_id=f"audit-{result.dataset_case_id}",
            comparison_audit_payload_digest=f"audit-digest-{result.dataset_case_id}",
            batch_metric_report_id=f"batch-metric-{result.dataset_case_id}",
            batch_metric_payload_digest=f"metric-digest-{result.dataset_case_id}",
            replay_metric_report_id=f"replay-metric-{result.dataset_case_id}",
            replay_metric_payload_digest=f"metric-digest-{result.dataset_case_id}",
            full_run_payload_equal=True,
            full_metric_payload_equal=True,
            failure_error_type=None,
            schema_version=1,
        )
        for result in baseline_results
    )
    cutoffs = tuple(
        C008CCFixedCutoffComparison.create(
            dataset_case_id=result.dataset_case_id,
            baseline_variant_id=baseline_id,
            partition=C008CCPartition.LOCKED_OOS,
            scenario=result.scenario,
            seed=3,
            status=FixedCutoffStatus.STABLE,
            checkpoints=(checkpoint,),
            stable_checkpoint_count=1,
            rewrite_count=0,
            failure_error_type=None,
            schema_version=1,
        )
        for result in baseline_results
    )
    return replays, cutoffs


def test_complete_mock_downstream_pipeline_is_c_oos_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_c008c_b_execution_manifest(ROOT)
    _, _, _, plan, _ = load_c008c_b_authority(ROOT)
    variants = {item.variant_id: item for item in plan.variants}
    case_results = tuple(
        _case_result(pair, variants[pair.variant_id])
        for pair in manifest.deferred_oos_pairs
    )
    same = tuple(
        _determinism(item, DeterminismEvidenceKind.SAME_CONTEXT_REPEAT)
        for item in case_results
    )
    decimal = tuple(
        _determinism(
            item,
            DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION,
        )
        for item in case_results
    )
    _, b_report = architecture._load_b_v2_prerequisite(ROOT)
    replay, cutoff = _replays_and_cutoffs(
        case_results,
        plan.variants[0].variant_id,
        b_report.fixed_cutoff_comparisons[0].checkpoints[0],
    )
    coverage_sources = _coverage_sources(
        case_results, plan.variants[0].variant_id
    )

    metric_deltas = architecture._oos_metric_deltas(ROOT, case_results)
    assert len(metric_deltas) == 25
    assert all(
        isinstance(item, C008CCMetricDeltaSummary)
        and item.partition is C008CCPartition.LOCKED_OOS
        and len(item.metric_deltas) == 50
        for item in metric_deltas
    )
    assert sum(len(item.metric_deltas) for item in metric_deltas) == 1250
    coverage = architecture._coverage_summaries(
        ROOT, case_results, coverage_sources
    )
    degeneration, global_degeneration = architecture._degeneration_summaries(
        ROOT,
        b_report,
        case_results,
        metric_deltas,
        cutoff,
    )
    contract = architecture.build_c008c_c_execution_contract(ROOT)
    attempt = architecture._attempt_payload(contract)
    report = architecture._build_report(
        ROOT,
        contract,
        attempt,
        b_report,
        case_results,
        same,
        decimal,
        metric_deltas,
        coverage_sources,
        coverage,
        replay,
        cutoff,
        degeneration,
        global_degeneration,
    )
    parsed = architecture._objects_from_report(report)
    assert parsed[0] == case_results
    assert parsed[3] == metric_deltas
    assert parsed[4] == replay
    assert parsed[5] == cutoff

    actual_canonical_payload = architecture._canonical_payload

    def _canonical_payload(path: Path, label: str) -> tuple[bytes, dict]:
        if path.resolve() == (ROOT / architecture.ATTEMPT_PATH).resolve():
            return canonical_json_bytes(attempt), attempt
        return actual_canonical_payload(path, label)

    monkeypatch.setattr(
        architecture,
        "load_committed_c008c_c_execution_contract",
        lambda root: contract,
    )
    monkeypatch.setattr(architecture, "_canonical_payload", _canonical_payload)
    validated = architecture.validate_c008c_c_report(report, ROOT)
    assert validated == report
