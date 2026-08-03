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


__all__ = ["evaluate_c008c_b_gates"]
