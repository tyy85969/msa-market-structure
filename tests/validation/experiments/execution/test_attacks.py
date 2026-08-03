from __future__ import annotations

from copy import deepcopy

import pytest

from msa.validation.experiments.execution import (
    C008CBExecutionManifest,
    C008CBManifestError,
    C008CBReportError,
    C008CBRunReport,
    ExperimentCaseResult,
    ExperimentDegenerationFinding,
    ExperimentDegenerationSummary,
    ExperimentFixedCutoffCheckpoint,
    ExperimentFixedCutoffComparison,
    ExperimentGateResult,
    ExperimentMetricDelta,
    ExperimentMetricDeltaSummary,
    ExperimentReplayComparison,
    MetricAggregateSnapshot,
    validate_c008c_b_execution_manifest,
    verify_c008c_b_report,
)
from msa.validation.experiments.execution.errors import C008CBExecutionError
from msa.validation.experiments.identity import digest, semantic_id
from msa.validation.metrics import (
    MetricAggregateStatus,
    default_metric_formula_registry,
)


def _resign(payload, contract_type, identity_field):
    identity = {
        key: value
        for key, value in payload.items()
        if key != identity_field
    }
    payload[identity_field] = semantic_id(
        contract_type._PREFIX, identity
    )
    return payload


def _resign_manifest(payload):
    return _resign(
        payload,
        C008CBExecutionManifest,
        "execution_manifest_id",
    )


def _resign_report(payload):
    return _resign(payload, C008CBRunReport, "run_report_id")


def _replace_first_case_with_formal_pass(payload):
    case = payload["case_results"][0]
    aggregates = []
    for formula in default_metric_formula_registry():
        aggregate = {
            "aggregate_snapshot_id": "",
            "metric_name": formula.metric_name.value,
            "formula_id": formula.metric_formula_id,
            "aggregate_status": (
                MetricAggregateStatus.NO_ELIGIBLE_EVENTS.value
            ),
            "value": None,
            "eligible_count": 0,
            "matured_count": 0,
            "censored_count": 0,
            "unavailable_count": 0,
            "schema_version": 1,
        }
        aggregates.append(
            _resign(
                aggregate,
                MetricAggregateSnapshot,
                "aggregate_snapshot_id",
            )
        )
    case.update(
        {
            "status": "PASSED",
            "run_id": "forged-run",
            "run_payload_digest": "1" * 64,
            "audit_report_id": "forged-audit",
            "audit_payload_digest": "2" * 64,
            "audit_passed": True,
            "metric_report_id": "forged-metric",
            "metric_report_payload_digest": "3" * 64,
            "aggregates": aggregates,
            "event_count": 0,
            "box_episode_count": 0,
            "matured_count": 0,
            "censored_count": 0,
            "unavailable_count": 0,
            "failure_stage": None,
            "failure_error_type": None,
        }
    )
    _resign(case, ExperimentCaseResult, "case_result_id")
    payload["passed_case_count"] = 1
    payload["failed_case_count"] = 389
    _resign_report(payload)
    return payload


def _replace_first_replay_with_formal_mismatch(payload):
    replay = payload["replay_comparisons"][0]
    replay.update(
        {
            "status": "MISMATCH",
            "batch_run_id": "forged-batch-run",
            "batch_run_payload_digest": "1" * 64,
            "replay_run_id": "forged-replay-run",
            "replay_run_payload_digest": "2" * 64,
            "comparison_audit_id": "forged-comparison-audit",
            "comparison_audit_payload_digest": "3" * 64,
            "batch_metric_report_id": "forged-batch-metric",
            "batch_metric_payload_digest": "4" * 64,
            "replay_metric_report_id": "forged-replay-metric",
            "replay_metric_payload_digest": "5" * 64,
            "full_run_payload_equal": False,
            "full_metric_payload_equal": True,
            "failure_error_type": None,
        }
    )
    _resign(
        replay,
        ExperimentReplayComparison,
        "replay_comparison_id",
    )
    _resign_report(payload)
    return payload


def _replace_first_cutoff_with_formal_rewrite(payload):
    cutoff = payload["fixed_cutoff_comparisons"][0]
    checkpoint = {
        "cutoff_checkpoint_id": "",
        "cutoff_as_of_time": "2025-01-01T00:00:00+00:00",
        "prefix_run_payload_digest": "1" * 64,
        "extended_run_payload_digest": "2" * 64,
        "comparison_audit_id": "forged-cutoff-audit",
        "comparison_audit_payload_digest": "3" * 64,
        "prefix_metric_payload_digest": "4" * 64,
        "extended_metric_payload_digest": "5" * 64,
        "stable": False,
        "schema_version": 1,
    }
    _resign(
        checkpoint,
        ExperimentFixedCutoffCheckpoint,
        "cutoff_checkpoint_id",
    )
    cutoff.update(
        {
            "status": "REWRITE_DETECTED",
            "checkpoints": [checkpoint],
            "stable_checkpoint_count": 0,
            "rewrite_count": 1,
            "failure_error_type": None,
        }
    )
    _resign(
        cutoff,
        ExperimentFixedCutoffComparison,
        "fixed_cutoff_comparison_id",
    )
    _resign_report(payload)
    return payload


def _report_attack_is_rejected(payload, expected, monkeypatch):
    try:
        candidate = C008CBRunReport.from_dict(payload)
    except (C008CBExecutionError, ValueError):
        return
    monkeypatch.setattr(
        "msa.validation.experiments.execution.evidence."
        "run_c008c_b_dev_validation",
        lambda root=None: expected,
    )
    with pytest.raises(C008CBReportError):
        verify_c008c_b_report(candidate)


@pytest.mark.parametrize(
    "attack",
    (
        "01_delete_b_pair",
        "02_add_b_pair",
        "03_duplicate_pair",
        "04_oos_in_executable",
        "05_delete_deferred_oos_pair",
        "06_change_execution_order",
        "07_change_plan_id",
        "08_change_dataset_id",
        "09_change_repository_base",
        "10_change_frozen_execution_base",
    ),
)
def test_all_ten_resigned_manifest_attacks_fail_closed(
    compact_components,
    attack,
) -> None:
    payload = deepcopy(compact_components["manifest"].to_dict())
    if attack == "01_delete_b_pair":
        payload["execution_pairs"].pop()
    elif attack == "02_add_b_pair":
        payload["execution_pairs"].append(
            deepcopy(payload["execution_pairs"][-1])
        )
    elif attack == "03_duplicate_pair":
        payload["execution_pairs"][-1] = deepcopy(
            payload["execution_pairs"][0]
        )
        payload["execution_pairs"][-1]["schedule_index"] = 389
        _resign(
            payload["execution_pairs"][-1],
            type(compact_components["manifest"].execution_pairs[0]),
            "execution_pair_id",
        )
    elif attack == "04_oos_in_executable":
        payload["execution_pairs"][0] = deepcopy(
            payload["deferred_oos_pairs"][0]
        )
        payload["execution_pairs"][0]["schedule_index"] = 0
        _resign(
            payload["execution_pairs"][0],
            type(compact_components["manifest"].execution_pairs[0]),
            "execution_pair_id",
        )
    elif attack == "05_delete_deferred_oos_pair":
        payload["deferred_oos_pairs"].pop()
    elif attack == "06_change_execution_order":
        payload["execution_pairs"][0:2] = reversed(
            payload["execution_pairs"][0:2]
        )
    elif attack == "07_change_plan_id":
        payload["experiment_plan_id"] = "forged-plan"
    elif attack == "08_change_dataset_id":
        payload["dataset_manifest_id"] = "forged-dataset"
    elif attack == "09_change_repository_base":
        payload["repository_base_commit"] = "0" * 40
    elif attack == "10_change_frozen_execution_base":
        payload["frozen_execution_base_commit"] = "0" * 40
    payload["execution_schedule_digest"] = digest(
        payload["execution_pairs"]
    )
    _resign_manifest(payload)
    with pytest.raises(C008CBManifestError):
        manifest = C008CBExecutionManifest.from_dict(payload)
        validate_c008c_b_execution_manifest(manifest)


@pytest.mark.parametrize(
    "attack",
    tuple(f"{number:02d}" for number in range(11, 51)),
)
def test_all_forty_report_and_evidence_attacks_fail_closed(
    compact_components,
    monkeypatch,
    attack,
) -> None:
    expected = compact_components["report"]
    payload = deepcopy(expected.to_dict())

    if attack in {"15", "16", "17", "18", "19", "20", "21"}:
        _replace_first_case_with_formal_pass(payload)
    if attack == "28":
        _replace_first_replay_with_formal_mismatch(payload)
    if attack in {"32", "33", "34"}:
        _replace_first_cutoff_with_formal_rewrite(payload)

    if attack == "11":
        payload["case_results"][0]["dataset_case_id"] = "forged-case"
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "12":
        payload["case_results"][0]["variant_id"] = "forged-variant"
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "13":
        payload["case_results"][0]["partition"] = "VALIDATION"
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "14":
        payload["case_results"][0]["partition"] = "OOS"
        payload["case_results"][0]["seed"] = 3
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "15":
        payload["case_results"][0]["run_payload_digest"] = "4" * 64
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "16":
        payload["case_results"][0]["audit_payload_digest"] = "4" * 64
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "17":
        payload["case_results"][0]["audit_passed"] = False
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "18":
        payload["case_results"][0][
            "metric_report_payload_digest"
        ] = "4" * 64
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "19":
        aggregate = payload["case_results"][0]["aggregates"][0]
        aggregate["aggregate_status"] = "AVAILABLE"
        aggregate["value"] = "1"
        _resign(
            aggregate,
            MetricAggregateSnapshot,
            "aggregate_snapshot_id",
        )
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "20":
        payload["case_results"][0]["aggregates"].pop()
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "21":
        payload["case_results"][0]["aggregates"][-1] = deepcopy(
            payload["case_results"][0]["aggregates"][0]
        )
        _resign(
            payload["case_results"][0],
            ExperimentCaseResult,
            "case_result_id",
        )
    elif attack == "22":
        case = payload["case_results"][0]
        case["metric_report_id"] = "forged-metric"
        case["metric_report_payload_digest"] = "4" * 64
        _resign(case, ExperimentCaseResult, "case_result_id")
    elif attack == "23":
        delta = payload["metric_delta_summaries"][0][
            "metric_deltas"
        ][0]
        delta["absolute_delta"] = "0"
        _resign(delta, ExperimentMetricDelta, "metric_delta_id")
        _resign(
            payload["metric_delta_summaries"][0],
            ExperimentMetricDeltaSummary,
            "metric_delta_summary_id",
        )
    elif attack == "24":
        delta = payload["metric_delta_summaries"][0][
            "metric_deltas"
        ][0]
        delta["baseline_dataset_case_id"] = "different-case"
    elif attack == "25":
        summary = payload["metric_delta_summaries"][0]
        summary["baseline_variant_id"] = "forged-baseline"
        for delta in summary["metric_deltas"]:
            delta["baseline_variant_id"] = "forged-baseline"
            _resign(delta, ExperimentMetricDelta, "metric_delta_id")
        _resign(
            summary,
            ExperimentMetricDeltaSummary,
            "metric_delta_summary_id",
        )
    elif attack == "26":
        delta = payload["metric_delta_summaries"][0][
            "metric_deltas"
        ][0]
        delta.update(
            {
                "baseline_aggregate_status": "AVAILABLE",
                "variant_aggregate_status": "AVAILABLE",
                "baseline_value": "1",
                "variant_value": "2",
                "absolute_delta": "9",
                "delta_status": "COMPARABLE",
            }
        )
        _resign(delta, ExperimentMetricDelta, "metric_delta_id")
    elif attack == "27":
        payload["metric_delta_summaries"][0][
            "metric_deltas"
        ][0]["better"] = True
    elif attack == "28":
        replay = payload["replay_comparisons"][0]
        replay["status"] = "MATCH"
        _resign(
            replay,
            ExperimentReplayComparison,
            "replay_comparison_id",
        )
    elif attack == "29":
        payload["replay_comparisons"].pop()
    elif attack == "30":
        replay = next(
            item
            for item in payload["replay_comparisons"]
            if item["scope"] == "VARIANT"
        )
        replay["partition"] = "DEVELOPMENT"
        _resign(
            replay,
            ExperimentReplayComparison,
            "replay_comparison_id",
        )
    elif attack == "31":
        replay = next(
            item
            for item in payload["replay_comparisons"]
            if item["scope"] == "VARIANT"
        )
        replay["variant_id"] = compact_components["plan"].variants[
            0
        ].variant_id
        _resign(
            replay,
            ExperimentReplayComparison,
            "replay_comparison_id",
        )
    elif attack == "32":
        cutoff = payload["fixed_cutoff_comparisons"][0]
        cutoff["checkpoints"].pop()
        _resign(
            cutoff,
            ExperimentFixedCutoffComparison,
            "fixed_cutoff_comparison_id",
        )
    elif attack == "33":
        cutoff = payload["fixed_cutoff_comparisons"][0]
        cutoff["status"] = "STABLE"
        _resign(
            cutoff,
            ExperimentFixedCutoffComparison,
            "fixed_cutoff_comparison_id",
        )
    elif attack == "34":
        cutoff = payload["fixed_cutoff_comparisons"][0]
        checkpoint = cutoff["checkpoints"][0]
        checkpoint[
            "cutoff_as_of_time"
        ] = "2000-01-01T00:00:00+00:00"
        _resign(
            checkpoint,
            ExperimentFixedCutoffCheckpoint,
            "cutoff_checkpoint_id",
        )
        _resign(
            cutoff,
            ExperimentFixedCutoffComparison,
            "fixed_cutoff_comparison_id",
        )
    elif attack == "35":
        cutoff = payload["fixed_cutoff_comparisons"][0]
        cutoff["partition"] = "OOS"
        cutoff["seed"] = 3
        _resign(
            cutoff,
            ExperimentFixedCutoffComparison,
            "fixed_cutoff_comparison_id",
        )
    elif attack == "36":
        summary = payload["degeneration_summaries"][0]
        summary["findings"].pop()
        _resign(
            summary,
            ExperimentDegenerationSummary,
            "degeneration_summary_id",
        )
    elif attack == "37":
        summary = payload["degeneration_summaries"][0]
        finding = next(
            item
            for item in summary["findings"]
            if item["rule_code"] == "MULTI_METRIC_COVERAGE_COLLAPSE"
        )
        finding["facts"][-1] = "decline_fraction_operator=>=0.90"
        _resign(
            finding,
            ExperimentDegenerationFinding,
            "degeneration_finding_id",
        )
        _resign(
            summary,
            ExperimentDegenerationSummary,
            "degeneration_summary_id",
        )
    elif attack == "38":
        summary = payload["degeneration_summaries"][0]
        summary["status"] = "SENSITIVE"
        _resign(
            summary,
            ExperimentDegenerationSummary,
            "degeneration_summary_id",
        )
    elif attack == "39":
        payload["degeneration_summaries"].pop()
    elif attack == "40":
        summary = payload["degeneration_summaries"][0]
        finding = summary["findings"][0]
        finding["validation_case_ids"].pop()
        _resign(
            finding,
            ExperimentDegenerationFinding,
            "degeneration_finding_id",
        )
        _resign(
            summary,
            ExperimentDegenerationSummary,
            "degeneration_summary_id",
        )
    elif attack in {"41", "42", "43", "44", "45"}:
        if attack == "41":
            gate = next(
                item
                for item in payload["gate_results"]
                if item["status"] == "FAIL"
            )
        elif attack == "42":
            gate = next(
                item
                for item in payload["gate_results"]
                if item["status"] == "DEFERRED_TO_C008C_C"
            )
        else:
            codes = {
                "43": "OOS_SAMPLE_COVERAGE",
                "44": "FREEZE_SOURCE_BOUND",
                "45": "ALL_CASES_MUST_EXECUTE",
            }
            gate = next(
                item
                for item in payload["gate_results"]
                if item["gate_code"] == codes[attack]
            )
        gate["status"] = "PASS"
        _resign(gate, ExperimentGateResult, "gate_result_id")
    elif attack in {"46", "47", "48", "49"}:
        forbidden_fields = {
            "46": ("winner", "forbidden"),
            "47": ("leaderboard", []),
            "48": ("recommended_parameter", "forbidden"),
            "49": ("trading_signal", "BUY"),
        }
        field, value = forbidden_fields[attack]
        payload[field] = value
    elif attack == "50":
        payload["stage_status"] = "READY_FOR_LOCKED_OOS"

    _resign_report(payload)
    _report_attack_is_rejected(payload, expected, monkeypatch)
