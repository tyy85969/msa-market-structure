"""Formal evaluation of all 27 frozen C-008C gates at B scope."""

from __future__ import annotations

from pathlib import Path

from .contracts import (
    C008CBExecutionManifest,
    ExperimentCaseResult,
    ExperimentCaseStatus,
    ExperimentDegenerationSummary,
    ExperimentDeterminismComparison,
    ExperimentFixedCutoffComparison,
    ExperimentGateResult,
    ExperimentReplayComparison,
    FixedCutoffStatus,
    GateEvaluationStatus,
    DegenerationStatus,
    ReplayComparisonStatus,
)
from .contracts_v2 import (
    B_V2_EXECUTION_SEMANTICS,
    DeterminismEvidenceKind,
    ExperimentDegenerationSummaryV2,
    ExperimentDeterminismComparisonV2,
    ExperimentGateResultV2,
    ExperimentGlobalDegenerationEvidenceV2,
    v2_payload_id,
)
from .errors import C008CBGateError
from .manifest import (
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)
from ..identity import digest, semantic_id


_STATIC_PASS = frozenset(
    {
        "BASE_COMMIT_MATCH",
        "CORE_PROFILE_AUTHORIZED",
        "PROTECTED_SOURCE_UNCHANGED",
        "DATASET_MANIFEST_VALID",
        "DATASET_PARTITIONS_DISJOINT",
        "ALL_SCENARIOS_PRESENT",
        "PLAN_PREDECLARED",
        "PLAN_OUTCOME_INDEPENDENT",
        "MODEL_VARIANTS_OAT",
        "METRIC_VARIANTS_OAT",
        "ABLATION_PUBLIC_CONFIG_ONLY",
        "INCREMENT_ENDS_AT_BASELINE",
        "NO_PARAMETER_OPTIMIZATION",
        "NO_TRADING_FIELDS",
        "EVIDENCE_REPRODUCIBLE",
    }
)


def _gate_result(
    definition: object,
    status: GateEvaluationStatus,
    evidence_ids: tuple[str, ...],
    evidence_payload: object,
    rationale: str,
) -> ExperimentGateResult:
    evidence_digest = digest(evidence_payload)
    kwargs = {
        "gate_definition_id": definition.gate_definition_id,
        "gate_code": definition.code,
        "status": status,
        "evidence_ids": evidence_ids,
        "evidence_payload_digest": evidence_digest,
        "rationale": rationale,
        "schema_version": 1,
    }
    payload = {
        "gate_definition_id": definition.gate_definition_id,
        "gate_code": definition.code,
        "status": status.value,
        "evidence_ids": list(evidence_ids),
        "evidence_payload_digest": evidence_digest,
        "rationale": rationale,
        "schema_version": 1,
    }
    return ExperimentGateResult(
        gate_result_id=semantic_id(
            ExperimentGateResult._PREFIX, payload
        ),
        **kwargs,
    )


def _gate_result_v2(
    definition: object,
    status: GateEvaluationStatus,
    evidence_kind: str,
    evidence_ids: tuple[str, ...],
    evidence_payload: object,
    rationale: str,
) -> ExperimentGateResultV2:
    evidence_digest = digest(evidence_payload)
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "gate_definition_id": definition.gate_definition_id,
        "gate_code": definition.code,
        "status": status,
        "evidence_kind": evidence_kind,
        "evidence_ids": evidence_ids,
        "evidence_payload_digest": evidence_digest,
        "rationale": rationale,
        "schema_version": 2,
    }
    payload = {
        **kwargs,
        "status": status.value,
        "evidence_ids": list(evidence_ids),
    }
    return ExperimentGateResultV2(
        gate_result_id=v2_payload_id(ExperimentGateResultV2._PREFIX, payload),
        **kwargs,
    )


def evaluate_c008c_b_gates(
    manifest: C008CBExecutionManifest,
    case_results: tuple[ExperimentCaseResult, ...],
    determinism_comparisons: tuple[
        ExperimentDeterminismComparison, ...
    ],
    replay_comparisons: tuple[ExperimentReplayComparison, ...],
    fixed_cutoff_comparisons: tuple[
        ExperimentFixedCutoffComparison, ...
    ],
    degeneration_summaries: tuple[
        ExperimentDegenerationSummary, ...
    ],
    root: Path | None = None,
) -> tuple[ExperimentGateResult, ...]:
    """Evaluate B evidence without converting deferred full-scope gates to PASS."""

    validate_c008c_b_execution_manifest(manifest, root)
    _, _, gates, _, _ = load_c008c_b_authority(root)
    if (
        len(case_results) != 390
        or len(determinism_comparisons) != 390
        or len(replay_comparisons) != 140
        or len(fixed_cutoff_comparisons) != 15
        or len(degeneration_summaries) != 25
    ):
        raise C008CBGateError(
            "gate evaluation requires complete B-stage evidence"
        )
    passed_cases = sum(
        item.status is ExperimentCaseStatus.PASSED
        for item in case_results
    )
    audits_ok = all(
        item.status is ExperimentCaseStatus.PASSED
        for item in case_results
    )
    metric_bind_ok = all(
        item.status is ExperimentCaseStatus.PASSED
        for item in case_results
    )
    ten_aggregates_ok = all(
        len(item.aggregates) == 10 for item in case_results
    )
    repeat_ok = all(
        item.status is ReplayComparisonStatus.MATCH
        for item in determinism_comparisons
    )
    variant_replay = tuple(
        item for item in replay_comparisons if item.scope == "VARIANT"
    )
    baseline_replay = tuple(
        item for item in replay_comparisons if item.scope == "BASELINE"
    )
    variant_replay_ok = (
        len(variant_replay) == 125
        and all(
            item.status is ReplayComparisonStatus.MATCH
            for item in variant_replay
        )
    )
    baseline_replay_ok = (
        len(baseline_replay) == 15
        and all(
            item.status is ReplayComparisonStatus.MATCH
            for item in baseline_replay
        )
    )
    cutoff_ok = all(
        item.status is FixedCutoffStatus.STABLE
        for item in fixed_cutoff_comparisons
    )
    degeneration_ok = all(
        item.status is not DegenerationStatus.DEGENERATED
        and item.status is not DegenerationStatus.INSUFFICIENT_EVIDENCE
        for item in degeneration_summaries
    )
    ids = {
        "manifest": (manifest.execution_manifest_id,),
        "cases": tuple(item.case_result_id for item in case_results),
        "repeat": tuple(
            item.determinism_comparison_id
            for item in determinism_comparisons
        ),
        "replay": tuple(
            item.replay_comparison_id for item in replay_comparisons
        ),
        "cutoff": tuple(
            item.fixed_cutoff_comparison_id
            for item in fixed_cutoff_comparisons
        ),
        "degeneration": tuple(
            item.degeneration_summary_id
            for item in degeneration_summaries
        ),
    }
    payloads = {
        "manifest": manifest.to_dict(),
        "cases": [item.to_dict() for item in case_results],
        "repeat": [
            item.to_dict() for item in determinism_comparisons
        ],
        "replay": [item.to_dict() for item in replay_comparisons],
        "cutoff": [
            item.to_dict() for item in fixed_cutoff_comparisons
        ],
        "degeneration": [
            item.to_dict() for item in degeneration_summaries
        ],
    }
    results: list[ExperimentGateResult] = []
    for gate in gates:
        code = gate.code
        if code in _STATIC_PASS:
            status = GateEvaluationStatus.PASS
            evidence_ids = ids["manifest"]
            evidence_payload = payloads["manifest"]
            rationale = "Frozen authority and outcome-independent B policy validate"
        elif code == "ALL_CASES_MUST_EXECUTE":
            status = (
                GateEvaluationStatus.DEFERRED_TO_C008C_C
                if len(case_results) == 390
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = (
                "390 of 520 frozen pairs executed; 130 OOS pairs remain deferred"
            )
        elif code == "ALL_CORE_RUNS_MUST_AUDIT":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if audits_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = (
                f"{passed_cases}/390 B-scope Runs passed complete causal audit"
            )
        elif code == "ALL_METRIC_REPORTS_MUST_SOURCE_BIND":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if metric_bind_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = (
                f"{passed_cases}/390 B-scope Metric Reports source-bind"
            )
        elif code == "BASELINE_BATCH_REPLAY_PARITY":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if baseline_replay_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = tuple(
                item.replay_comparison_id for item in baseline_replay
            )
            evidence_payload = [
                item.to_dict() for item in baseline_replay
            ]
            rationale = "15/20 Baseline replay samples executed; five OOS deferred"
        elif code == "VARIANT_REPLAY_SAMPLE_PARITY":
            status = (
                GateEvaluationStatus.PASS
                if variant_replay_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = tuple(
                item.replay_comparison_id for item in variant_replay
            )
            evidence_payload = [
                item.to_dict() for item in variant_replay
            ]
            rationale = "All 125 frozen seed-2 Variant replay samples evaluated"
        elif code == "FIXED_CUTOFF_STABILITY":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if cutoff_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["cutoff"]
            evidence_payload = payloads["cutoff"]
            rationale = "15/20 Baseline cases evaluated at every formal causal AsOf"
        elif code in (
            "DETERMINISTIC_REPEAT",
            "DECIMAL_CONTEXT_INDEPENDENCE",
        ):
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if repeat_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["repeat"]
            evidence_payload = payloads["repeat"]
            rationale = "All 390 B pairs repeated under altered Decimal context"
        elif code == "TEN_AGGREGATES_ALWAYS_PRESENT":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if ten_aggregates_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = "Every successful B Metric Report must retain ten aggregates"
        elif code == "OOS_SAMPLE_COVERAGE":
            status = GateEvaluationStatus.DEFERRED_TO_C008C_C
            evidence_ids = ids["manifest"]
            evidence_payload = payloads["manifest"]
            rationale = "No OOS metric outcome is readable in C-008C-B"
        elif code == "NO_NEIGHBORHOOD_DEGENERATION":
            status = (
                GateEvaluationStatus.PASS
                if degeneration_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_ids = ids["degeneration"]
            evidence_payload = payloads["degeneration"]
            rationale = "All 25 non-Baseline Variants consumed all ten frozen rules"
        elif code == "FREEZE_SOURCE_BOUND":
            status = GateEvaluationStatus.DEFERRED_TO_C008C_C
            evidence_ids = ids["manifest"]
            evidence_payload = payloads["manifest"]
            rationale = "C-008C-B cannot create a Core Freeze Candidate"
        else:
            raise C008CBGateError(f"unsupported frozen gate code: {code}")
        results.append(
            _gate_result(
                gate,
                status,
                evidence_ids,
                evidence_payload,
                rationale,
            )
        )
    result = tuple(results)
    if len(result) != 27:
        raise C008CBGateError("exactly 27 GateResults are required")
    return result


def evaluate_c008c_b_v2_gates(
    manifest: C008CBExecutionManifest,
    case_results: tuple[ExperimentCaseResult, ...],
    same_context_comparisons: tuple[ExperimentDeterminismComparisonV2, ...],
    decimal_context_comparisons: tuple[ExperimentDeterminismComparisonV2, ...],
    replay_comparisons: tuple[ExperimentReplayComparison, ...],
    fixed_cutoff_comparisons: tuple[ExperimentFixedCutoffComparison, ...],
    degeneration_summaries: tuple[ExperimentDegenerationSummaryV2, ...],
    global_degeneration_evidence: ExperimentGlobalDegenerationEvidenceV2,
    root: Path | None = None,
) -> tuple[ExperimentGateResultV2, ...]:
    """Derive future B-v2 Gates without reading or rewriting v1 Gate evidence."""

    validate_c008c_b_execution_manifest(manifest, root)
    _, _, gates, _, _ = load_c008c_b_authority(root)
    if (
        len(case_results) != 390
        or len(same_context_comparisons) != 390
        or len(decimal_context_comparisons) != 390
        or len(replay_comparisons) != 140
        or len(fixed_cutoff_comparisons) != 15
        or len(degeneration_summaries) != 25
        or not isinstance(
            global_degeneration_evidence,
            ExperimentGlobalDegenerationEvidenceV2,
        )
    ):
        raise C008CBGateError("Gate derivation requires complete B-v2 evidence")
    expected_pair_ids = tuple(
        item.execution_pair_id for item in manifest.execution_pairs
    )
    if (
        tuple(item.execution_pair_id for item in case_results) != expected_pair_ids
        or tuple(
            item.execution_pair_id for item in same_context_comparisons
        )
        != expected_pair_ids
        or tuple(
            item.execution_pair_id for item in decimal_context_comparisons
        )
        != expected_pair_ids
    ):
        raise C008CBGateError("B-v2 evidence differs from the frozen pair schedule")
    for result, same, decimal in zip(
        case_results,
        same_context_comparisons,
        decimal_context_comparisons,
        strict=True,
    ):
        expected_source = (
            result.execution_pair_id,
            result.dataset_case_id,
            result.variant_id,
            result.case_result_id,
            digest(result.to_dict()),
        )
        if (
            (
                same.execution_pair_id,
                same.dataset_case_id,
                same.variant_id,
                same.normal_a_case_result_id,
                same.normal_a_payload_digest,
            )
            != expected_source
            or (
                decimal.execution_pair_id,
                decimal.dataset_case_id,
                decimal.variant_id,
                decimal.normal_a_case_result_id,
                decimal.normal_a_payload_digest,
            )
            != expected_source
        ):
            raise C008CBGateError(
                "B-v2 comparison does not bind its normal-A source result"
            )
    if any(
        item.comparison_kind
        is not DeterminismEvidenceKind.SAME_CONTEXT_REPEAT
        or item.decimal_context_changed
        for item in same_context_comparisons
    ):
        raise C008CBGateError(
            "DETERMINISTIC_REPEAT requires only SAME_CONTEXT_REPEAT evidence"
        )
    if any(
        item.comparison_kind
        is not DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
        or not item.decimal_context_changed
        for item in decimal_context_comparisons
    ):
        raise C008CBGateError(
            "DECIMAL_CONTEXT_INDEPENDENCE requires only Decimal perturbation evidence"
        )
    same_ids = tuple(
        item.determinism_comparison_id for item in same_context_comparisons
    )
    decimal_ids = tuple(
        item.determinism_comparison_id for item in decimal_context_comparisons
    )
    same_payload = [item.to_dict() for item in same_context_comparisons]
    decimal_payload = [item.to_dict() for item in decimal_context_comparisons]
    if set(same_ids) & set(decimal_ids):
        raise C008CBGateError("one comparison cannot bind both B-v2 Gates")
    if digest(same_payload) == digest(decimal_payload):
        raise C008CBGateError("B-v2 Gate evidence payload digests must differ")

    passed_cases = sum(
        item.status is ExperimentCaseStatus.PASSED for item in case_results
    )
    audits_ok = all(
        item.status is ExperimentCaseStatus.PASSED for item in case_results
    )
    metric_bind_ok = all(
        item.status is ExperimentCaseStatus.PASSED for item in case_results
    )
    ten_aggregates_ok = all(len(item.aggregates) == 10 for item in case_results)
    same_context_ok = all(
        item.status is ReplayComparisonStatus.MATCH
        for item in same_context_comparisons
    )
    decimal_context_ok = all(
        item.status is ReplayComparisonStatus.MATCH
        for item in decimal_context_comparisons
    )
    variant_replay = tuple(
        item for item in replay_comparisons if item.scope == "VARIANT"
    )
    baseline_replay = tuple(
        item for item in replay_comparisons if item.scope == "BASELINE"
    )
    variant_replay_ok = len(variant_replay) == 125 and all(
        item.status is ReplayComparisonStatus.MATCH for item in variant_replay
    )
    baseline_replay_ok = len(baseline_replay) == 15 and all(
        item.status is ReplayComparisonStatus.MATCH for item in baseline_replay
    )
    cutoff_ok = all(
        item.status is FixedCutoffStatus.STABLE
        for item in fixed_cutoff_comparisons
    )
    degeneration_ok = all(
        item.status
        not in (
            DegenerationStatus.DEGENERATED,
            DegenerationStatus.INSUFFICIENT_EVIDENCE,
        )
        for item in degeneration_summaries
    )
    ids = {
        "manifest": (manifest.execution_manifest_id,),
        "cases": tuple(item.case_result_id for item in case_results),
        "same": same_ids,
        "decimal": decimal_ids,
        "cutoff": tuple(
            item.fixed_cutoff_comparison_id
            for item in fixed_cutoff_comparisons
        ),
        "degeneration": tuple(
            item.degeneration_summary_id for item in degeneration_summaries
        ),
    }
    payloads = {
        "manifest": manifest.to_dict(),
        "cases": [item.to_dict() for item in case_results],
        "same": same_payload,
        "decimal": decimal_payload,
        "cutoff": [item.to_dict() for item in fixed_cutoff_comparisons],
        "degeneration": [item.to_dict() for item in degeneration_summaries],
    }
    results: list[ExperimentGateResultV2] = []
    for gate in gates:
        code = gate.code
        if code in _STATIC_PASS:
            status = GateEvaluationStatus.PASS
            evidence_kind = "FROZEN_AUTHORITY"
            evidence_ids = ids["manifest"]
            evidence_payload = payloads["manifest"]
            rationale = "Frozen authority validates under B-v2 semantics"
        elif code == "ALL_CASES_MUST_EXECUTE":
            status = GateEvaluationStatus.DEFERRED_TO_C008C_C
            evidence_kind = "CASE_RESULTS"
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = "390 B-stage pairs present; 130 OOS pairs remain deferred"
        elif code == "ALL_CORE_RUNS_MUST_AUDIT":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if audits_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "CASE_RESULTS"
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = f"{passed_cases}/390 B-scope Runs passed causal audit"
        elif code == "ALL_METRIC_REPORTS_MUST_SOURCE_BIND":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if metric_bind_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "CASE_RESULTS"
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = f"{passed_cases}/390 B-scope Metric Reports source-bind"
        elif code == "BASELINE_BATCH_REPLAY_PARITY":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if baseline_replay_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "BASELINE_REPLAY"
            evidence_ids = tuple(
                item.replay_comparison_id for item in baseline_replay
            )
            evidence_payload = [item.to_dict() for item in baseline_replay]
            rationale = "15 Baseline replay samples; five OOS deferred"
        elif code == "VARIANT_REPLAY_SAMPLE_PARITY":
            status = (
                GateEvaluationStatus.PASS
                if variant_replay_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "VARIANT_REPLAY"
            evidence_ids = tuple(
                item.replay_comparison_id for item in variant_replay
            )
            evidence_payload = [item.to_dict() for item in variant_replay]
            rationale = "125 frozen seed-2 Variant replay samples evaluated"
        elif code == "FIXED_CUTOFF_STABILITY":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if cutoff_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "BASELINE_FIXED_CUTOFF"
            evidence_ids = ids["cutoff"]
            evidence_payload = payloads["cutoff"]
            rationale = "15 Baseline cases evaluated at formal causal AsOf"
        elif code == "DETERMINISTIC_REPEAT":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if same_context_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = DeterminismEvidenceKind.SAME_CONTEXT_REPEAT.value
            evidence_ids = ids["same"]
            evidence_payload = payloads["same"]
            rationale = "normal A compared only with independent normal B"
        elif code == "DECIMAL_CONTEXT_INDEPENDENCE":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if decimal_context_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = (
                DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION.value
            )
            evidence_ids = ids["decimal"]
            evidence_payload = payloads["decimal"]
            rationale = "normal A compared only with altered Decimal context"
        elif code == "TEN_AGGREGATES_ALWAYS_PRESENT":
            status = (
                GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
                if ten_aggregates_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "CASE_RESULTS"
            evidence_ids = ids["cases"]
            evidence_payload = payloads["cases"]
            rationale = "Successful B-v2 Metric Reports retain ten aggregates"
        elif code == "OOS_SAMPLE_COVERAGE":
            status = GateEvaluationStatus.DEFERRED_TO_C008C_C
            evidence_kind = "FROZEN_AUTHORITY"
            evidence_ids = ids["manifest"]
            evidence_payload = payloads["manifest"]
            rationale = "No OOS outcome is readable in C-008C-B-v2"
        elif code == "NO_NEIGHBORHOOD_DEGENERATION":
            status = (
                GateEvaluationStatus.PASS
                if degeneration_ok
                else GateEvaluationStatus.FAIL
            )
            evidence_kind = "VARIANT_SUBJECT_DEGENERATION"
            evidence_ids = ids["degeneration"]
            evidence_payload = payloads["degeneration"]
            rationale = (
                "Variant findings bind Variant subjects; Baseline rewrite is "
                "separate global evidence "
                f"{global_degeneration_evidence.global_evidence_id}"
            )
        elif code == "FREEZE_SOURCE_BOUND":
            status = GateEvaluationStatus.DEFERRED_TO_C008C_C
            evidence_kind = "FROZEN_AUTHORITY"
            evidence_ids = ids["manifest"]
            evidence_payload = payloads["manifest"]
            rationale = "C-008C-B-v2 cannot create a Core Freeze Candidate"
        else:
            raise C008CBGateError(f"unsupported frozen gate code: {code}")
        results.append(
            _gate_result_v2(
                gate,
                status,
                evidence_kind,
                evidence_ids,
                evidence_payload,
                rationale,
            )
        )
    if len(results) != 27:
        raise C008CBGateError("exactly 27 B-v2 GateResults are required")
    result_index = {item.gate_code: item for item in results}
    same_gate = result_index["DETERMINISTIC_REPEAT"]
    decimal_gate = result_index["DECIMAL_CONTEXT_INDEPENDENCE"]
    if (
        same_gate.evidence_ids == decimal_gate.evidence_ids
        or same_gate.evidence_payload_digest
        == decimal_gate.evidence_payload_digest
    ):
        raise C008CBGateError("B-v2 determinism Gates remain conflated")
    return tuple(results)


__all__ = ["evaluate_c008c_b_gates", "evaluate_c008c_b_v2_gates"]
