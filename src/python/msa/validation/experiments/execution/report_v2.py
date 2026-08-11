"""Formal, append-only C-008C-B-v2 orchestration and report validation."""

from __future__ import annotations

from pathlib import Path

from ..contracts import DatasetPartition
from ..protected_source import build_protected_source_manifest
from .contracts import (
    C008CBExecutionManifest,
    C008CBStageStatus,
    GateEvaluationStatus,
)
from .contracts_v2 import (
    B_V2_EXECUTION_SEMANTICS,
    B_V2_SCHEMA_VERSION,
    C008CBV2ExecutionContract,
    C008CBV2ExecutionSourceManifest,
    C008CBV2RunReport,
    build_c008c_b_v2_execution_contract,
    v2_payload_id,
)
from .cutoff import run_fixed_cutoff_comparisons
from .degeneration import evaluate_validation_degeneration_v2
from .deltas import calculate_metric_deltas
from .errors import C008CBManifestError, C008CBReportError
from .gate_evaluator import (
    evaluate_c008c_b_v2_gates,
    validate_c008c_b_v2_gate_results,
)
from .manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)
from .replay import run_replay_comparisons
from .report import _partition_summaries
from .runner import run_primary_execution_v2
from .source_authority_v2 import (
    validate_c008c_b_v2_execution_source_authority,
    validate_c008c_b_v2_execution_source_stability,
)


_DEFERRED_GATE_CODES = frozenset(
    {
        "ALL_CASES_MUST_EXECUTE",
        "OOS_SAMPLE_COVERAGE",
        "FREEZE_SOURCE_BOUND",
    }
)
_PARTIAL_GATE_CODES = frozenset(
    {
        "ALL_CORE_RUNS_MUST_AUDIT",
        "ALL_METRIC_REPORTS_MUST_SOURCE_BIND",
        "BASELINE_BATCH_REPLAY_PARITY",
        "FIXED_CUTOFF_STABILITY",
        "DETERMINISTIC_REPEAT",
        "DECIMAL_CONTEXT_INDEPENDENCE",
        "TEN_AGGREGATES_ALWAYS_PRESENT",
    }
)


def validate_c008c_b_v2_execution_contract(
    contract: C008CBV2ExecutionContract,
    manifest: C008CBExecutionManifest,
) -> C008CBV2ExecutionContract:
    """Bind the outcome-free v2 contract to the exact historical schedule."""

    if not isinstance(contract, C008CBV2ExecutionContract):
        raise C008CBManifestError("B-v2 execution contract is required")
    expected = build_c008c_b_v2_execution_contract(manifest)
    if contract.to_dict() != expected.to_dict():
        raise C008CBManifestError(
            "B-v2 execution contract differs from historical manifest"
        )
    return contract


def validate_c008c_b_v2_execution_schedule(
    manifest: C008CBExecutionManifest,
    contract: C008CBV2ExecutionContract,
    root: Path | None = None,
) -> None:
    """Reject any OOS/deferred pair before a formal executor is called."""

    if (
        not isinstance(manifest, C008CBExecutionManifest)
        or len(manifest.execution_pairs) != 390
        or any(
            item.seed == 3
            or item.partition is DatasetPartition.OOS
            or item.deferred_to_c008c_c
            for item in manifest.execution_pairs
        )
    ):
        raise C008CBManifestError(
            "B-v2 executable schedule contains OOS, seed 3, or deferred pair"
        )
    validate_c008c_b_execution_manifest(manifest, root)
    validate_c008c_b_v2_execution_contract(contract, manifest)
    if (
        len(manifest.deferred_oos_pairs) != 130
        or any(
            item.seed != 3
            or item.partition is not DatasetPartition.OOS
            or not item.deferred_to_c008c_c
            for item in manifest.deferred_oos_pairs
        )
    ):
        raise C008CBManifestError(
            "B-v2 deferred OOS schedule differs from frozen authority"
        )


def derive_c008c_b_v2_stage(
    gate_results: tuple,
    root: Path | None = None,
) -> C008CBStageStatus:
    """Apply the frozen pre-OOS decision policy to an exact 27-Gate set."""

    _, _, definitions, _, _ = load_c008c_b_authority(root)
    expected_codes = tuple(item.code for item in definitions)
    actual_codes = tuple(
        getattr(item, "gate_code", None) for item in gate_results
    )
    if actual_codes != expected_codes or len(set(actual_codes)) != 27:
        raise C008CBReportError(
            "B-v2 stage requires the exact ordered frozen Gate set"
        )
    if any(
        item.status is GateEvaluationStatus.FAIL for item in gate_results
    ):
        return C008CBStageStatus.BLOCKED_BEFORE_OOS
    for item in gate_results:
        expected = (
            GateEvaluationStatus.DEFERRED_TO_C008C_C
            if item.gate_code in _DEFERRED_GATE_CODES
            else GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
            if item.gate_code in _PARTIAL_GATE_CODES
            else GateEvaluationStatus.PASS
        )
        if item.status is not expected:
            raise C008CBReportError(
                f"Gate status is invalid for pre-OOS stage: {item.gate_code}"
            )
    return C008CBStageStatus.READY_FOR_LOCKED_OOS


def _same_payloads(actual: tuple, expected: tuple) -> bool:
    return tuple(item.to_dict() for item in actual) == tuple(
        item.to_dict() for item in expected
    )


def _validate_report_schedule(
    report: C008CBV2RunReport,
    manifest: C008CBExecutionManifest,
) -> None:
    pair_ids = tuple(
        item.execution_pair_id for item in manifest.execution_pairs
    )
    if tuple(item.execution_pair_id for item in report.case_results) != pair_ids:
        raise C008CBReportError(
            "B-v2 case results are missing, duplicated, or reordered"
        )
    if tuple(
        item.execution_pair_id for item in report.same_context_comparisons
    ) != pair_ids:
        raise C008CBReportError("same-context comparison order mismatch")
    if tuple(
        item.execution_pair_id for item in report.decimal_context_comparisons
    ) != pair_ids:
        raise C008CBReportError("Decimal-context comparison order mismatch")
    expected_replay_ids = (
        manifest.baseline_replay_sample_ids
        + manifest.variant_replay_sample_ids
    )
    if tuple(
        item.replay_sample_id for item in report.replay_comparisons
    ) != expected_replay_ids:
        raise C008CBReportError("B-v2 Replay evidence order mismatch")
    if tuple(
        item.dataset_case_id for item in report.fixed_cutoff_comparisons
    ) != manifest.fixed_cutoff_case_ids:
        raise C008CBReportError("B-v2 fixed-cutoff evidence order mismatch")
    if tuple(
        item.variant_id for item in report.degeneration_summaries
    ) != manifest.variant_ids[1:]:
        raise C008CBReportError("B-v2 degeneration evidence order mismatch")
    if any(
        item.seed == 3 or item.partition is DatasetPartition.OOS
        for item in (
            *report.case_results,
            *report.replay_comparisons,
            *report.fixed_cutoff_comparisons,
        )
    ):
        raise C008CBReportError("B-v2 report contains forbidden OOS outcome")


def validate_c008c_b_v2_report(
    report: C008CBV2RunReport,
    contract: C008CBV2ExecutionContract,
    manifest: C008CBExecutionManifest,
    root: Path | None = None,
) -> C008CBV2RunReport:
    """Recompute every derived binding without executing an outcome."""

    if not isinstance(report, C008CBV2RunReport):
        raise C008CBReportError("report must be C008CBV2RunReport")
    validate_c008c_b_v2_execution_schedule(manifest, contract, root)
    if (
        report.execution_contract_id != contract.execution_contract_id
        or report.historical_execution_manifest_id
        != manifest.execution_manifest_id
    ):
        raise C008CBReportError(
            "B-v2 report authority identifiers are inconsistent"
        )
    reviewed_source = build_protected_source_manifest(root)
    if report.reviewed_protected_source_manifest_id != (
        reviewed_source.protected_source_manifest_id
    ):
        raise C008CBReportError(
            "B-v2 report reviewed source authority mismatch"
        )
    execution_source = validate_c008c_b_v2_execution_source_authority(root)
    if report.execution_source_manifest_id != (
        execution_source.source_manifest_id
    ):
        raise C008CBReportError(
            "B-v2 report execution source authority mismatch"
        )
    _validate_report_schedule(report, manifest)
    expected_stage = derive_c008c_b_v2_stage(report.gate_results, root)
    if report.stage_status is not expected_stage:
        raise C008CBReportError(
            "B-v2 stage decision contradicts Gate evidence"
        )
    expected_deltas = calculate_metric_deltas(report.case_results, root)
    if not _same_payloads(report.metric_delta_summaries, expected_deltas):
        raise C008CBReportError("B-v2 Metric deltas are not source-derived")
    expected_degeneration = evaluate_validation_degeneration_v2(
        report.case_results,
        expected_deltas,
        report.replay_comparisons,
        report.fixed_cutoff_comparisons,
        root,
    )
    expected_summaries, expected_global = expected_degeneration
    if (
        not _same_payloads(report.degeneration_summaries, expected_summaries)
        or report.global_degeneration_evidence.to_dict()
        != expected_global.to_dict()
    ):
        raise C008CBReportError(
            "B-v2 degeneration evidence is not source-derived"
        )
    validate_c008c_b_v2_gate_results(
        report.gate_results,
        manifest,
        report.case_results,
        report.same_context_comparisons,
        report.decimal_context_comparisons,
        report.replay_comparisons,
        report.fixed_cutoff_comparisons,
        report.degeneration_summaries,
        report.global_degeneration_evidence,
        root,
    )
    expected_partitions = _partition_summaries(
        report.case_results,
        expected_deltas,
        report.replay_comparisons,
        report.degeneration_summaries,
        root,
    )
    if not _same_payloads(report.partition_summaries, expected_partitions):
        raise C008CBReportError(
            "B-v2 partition summaries are not source-derived"
        )
    if report.executed_pair_count != len(manifest.execution_pairs) or (
        report.deferred_oos_pair_count != len(manifest.deferred_oos_pairs)
    ):
        raise C008CBReportError("B-v2 report schedule counts mismatch")
    return report


def build_c008c_b_v2_report(
    manifest: C008CBExecutionManifest,
    contract: C008CBV2ExecutionContract,
    case_results: tuple,
    same_context_comparisons: tuple,
    decimal_context_comparisons: tuple,
    metric_delta_summaries: tuple,
    partition_summaries: tuple,
    replay_comparisons: tuple,
    fixed_cutoff_comparisons: tuple,
    degeneration_summaries: tuple,
    global_degeneration_evidence: object,
    gate_results: tuple,
    root: Path | None = None,
    *,
    execution_source_manifest: C008CBV2ExecutionSourceManifest | None = None,
) -> C008CBV2RunReport:
    """Assemble a canonical v2 report from already-produced formal evidence."""

    validate_c008c_b_v2_execution_schedule(manifest, contract, root)
    reviewed_source = build_protected_source_manifest(root)
    if execution_source_manifest is None:
        execution_source_manifest = (
            validate_c008c_b_v2_execution_source_authority(root)
        )
    if not isinstance(
        execution_source_manifest, C008CBV2ExecutionSourceManifest
    ):
        raise C008CBReportError("B-v2 execution source manifest is required")
    stage = derive_c008c_b_v2_stage(gate_results, root)
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "execution_contract_id": contract.execution_contract_id,
        "historical_execution_manifest_id": manifest.execution_manifest_id,
        "reviewed_protected_source_manifest_id": (
            reviewed_source.protected_source_manifest_id
        ),
        "execution_source_manifest_id": (
            execution_source_manifest.source_manifest_id
        ),
        "case_results": case_results,
        "same_context_comparisons": same_context_comparisons,
        "decimal_context_comparisons": decimal_context_comparisons,
        "metric_delta_summaries": metric_delta_summaries,
        "partition_summaries": partition_summaries,
        "replay_comparisons": replay_comparisons,
        "fixed_cutoff_comparisons": fixed_cutoff_comparisons,
        "degeneration_summaries": degeneration_summaries,
        "global_degeneration_evidence": global_degeneration_evidence,
        "gate_results": gate_results,
        "stage_status": stage,
        "executed_pair_count": len(case_results),
        "deferred_oos_pair_count": len(manifest.deferred_oos_pairs),
        "oos_executed": False,
        "schema_version": B_V2_SCHEMA_VERSION,
    }
    payload = {
        "execution_semantics": kwargs["execution_semantics"],
        "execution_contract_id": kwargs["execution_contract_id"],
        "historical_execution_manifest_id": kwargs[
            "historical_execution_manifest_id"
        ],
        "reviewed_protected_source_manifest_id": kwargs[
            "reviewed_protected_source_manifest_id"
        ],
        "execution_source_manifest_id": kwargs[
            "execution_source_manifest_id"
        ],
        "case_results": [item.to_dict() for item in case_results],
        "same_context_comparisons": [
            item.to_dict() for item in same_context_comparisons
        ],
        "decimal_context_comparisons": [
            item.to_dict() for item in decimal_context_comparisons
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
        "global_degeneration_evidence": (
            global_degeneration_evidence.to_dict()
        ),
        "gate_results": [item.to_dict() for item in gate_results],
        "stage_status": stage.value,
        "executed_pair_count": kwargs["executed_pair_count"],
        "deferred_oos_pair_count": kwargs["deferred_oos_pair_count"],
        "oos_executed": False,
        "schema_version": B_V2_SCHEMA_VERSION,
    }
    report = C008CBV2RunReport(
        run_report_id=v2_payload_id(C008CBV2RunReport._PREFIX, payload),
        **kwargs,
    )
    return report


def run_c008c_b_v2_dev_validation(
    root: Path | None = None,
) -> C008CBV2RunReport:
    """Run the one formal DEV+VALIDATION B-v2 orchestration; never OOS."""

    source_before = validate_c008c_b_v2_execution_source_authority(root)
    manifest = build_c008c_b_execution_manifest(root)
    contract = build_c008c_b_v2_execution_contract(manifest)
    validate_c008c_b_v2_execution_schedule(manifest, contract, root)
    primary = run_primary_execution_v2(manifest, root)
    replay = run_replay_comparisons(manifest, root)
    cutoff = run_fixed_cutoff_comparisons(manifest, root)
    deltas = calculate_metric_deltas(primary.case_results, root)
    degeneration, global_evidence = evaluate_validation_degeneration_v2(
        primary.case_results,
        deltas,
        replay,
        cutoff,
        root,
    )
    gates = evaluate_c008c_b_v2_gates(
        manifest,
        primary.case_results,
        primary.same_context_comparisons,
        primary.decimal_context_comparisons,
        replay,
        cutoff,
        degeneration,
        global_evidence,
        root,
    )
    partitions = _partition_summaries(
        primary.case_results,
        deltas,
        replay,
        degeneration,
        root,
    )
    report = build_c008c_b_v2_report(
        manifest,
        contract,
        primary.case_results,
        primary.same_context_comparisons,
        primary.decimal_context_comparisons,
        deltas,
        partitions,
        replay,
        cutoff,
        degeneration,
        global_evidence,
        gates,
        root,
        execution_source_manifest=source_before,
    )
    source_after = validate_c008c_b_v2_execution_source_authority(root)
    validate_c008c_b_v2_execution_source_stability(
        source_before, source_after
    )
    return validate_c008c_b_v2_report(report, contract, manifest, root)


__all__ = [
    "build_c008c_b_v2_report",
    "derive_c008c_b_v2_stage",
    "run_c008c_b_v2_dev_validation",
    "validate_c008c_b_v2_execution_contract",
    "validate_c008c_b_v2_execution_schedule",
    "validate_c008c_b_v2_report",
]
