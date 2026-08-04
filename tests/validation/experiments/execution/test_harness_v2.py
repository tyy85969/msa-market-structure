from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, getcontext

import pytest

from msa.validation.experiments.execution import (
    C008CBV2ExecutionContract,
    DegenerationEvidenceScope,
    DeterminismEvidenceKind,
    ExperimentDegenerationSummaryV2,
    ExperimentGateResultV2,
    ExperimentGlobalDegenerationEvidenceV2,
    GateEvaluationStatus,
    build_c008c_b_v2_execution_contract,
)
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseStatus,
    ExperimentFailureStage,
)
from msa.validation.experiments.execution.degeneration import (
    evaluate_validation_degeneration_v2,
)
from msa.validation.experiments.execution.errors import (
    C008CBCaseError,
    C008CBGateError,
)
from msa.validation.experiments.execution.gate_evaluator import (
    evaluate_c008c_b_v2_gates,
)
from msa.validation.experiments.execution.runner import (
    _ExecutionArtifacts,
    _case_result,
    _determinism_v2,
    _execute_pair_v2,
)


def _altered_result(pair, variant):
    return _case_result(
        pair,
        variant,
        status=ExperimentCaseStatus.PIPELINE_FAILED,
        run=None,
        audit=None,
        metric_report=None,
        failure_stage=ExperimentFailureStage.PIPELINE,
        failure_error_type="Bv2AlteredDecimalSyntheticFailure",
    )


def _v2_comparisons(compact_components):
    variants = {
        item.variant_id: item for item in compact_components["plan"].variants
    }
    same = []
    decimal = []
    for pair, normal_result in zip(
        compact_components["manifest"].execution_pairs,
        compact_components["case_results"],
        strict=True,
    ):
        normal = _ExecutionArtifacts(normal_result, None, None, None)
        altered = _ExecutionArtifacts(
            _altered_result(pair, variants[pair.variant_id]),
            None,
            None,
            None,
        )
        same.append(
            _determinism_v2(
                pair,
                normal,
                normal,
                DeterminismEvidenceKind.SAME_CONTEXT_REPEAT,
            )
        )
        decimal.append(
            _determinism_v2(
                pair,
                normal,
                altered,
                DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION,
            )
        )
    return tuple(same), tuple(decimal)


def test_b_v2_contract_is_versioned_outcome_free_and_keeps_oos_deferred(
    compact_components,
) -> None:
    contract = build_c008c_b_v2_execution_contract(
        compact_components["manifest"]
    )
    assert contract.schema_version == 2
    assert contract.execution_semantics == "C-008C-B-v2"
    assert len(contract.executable_pair_ids) == 390
    assert len(contract.deferred_oos_pair_ids) == 130
    assert not set(contract.executable_pair_ids) & set(
        contract.deferred_oos_pair_ids
    )
    assert contract.execution_result_labels == (
        "NORMAL_A",
        "NORMAL_B",
        "ALTERED_DECIMAL_CONTEXT",
    )
    assert contract.outcome_execution_performed is False
    assert contract.formal_gate_recalculation_performed is False
    assert contract.oos_executed is False
    assert contract.historical_evidence_superseded is False
    assert C008CBV2ExecutionContract.from_dict(contract.to_dict()) == contract


def test_pair_v2_executes_normal_normal_and_altered_as_three_results(
    compact_components,
    monkeypatch,
) -> None:
    manifest = compact_components["manifest"]
    pair = manifest.execution_pairs[0]
    case = next(
        item
        for item in compact_components["dataset"].cases
        if item.dataset_case_id == pair.dataset_case_id
    )
    variant = next(
        item
        for item in compact_components["plan"].variants
        if item.variant_id == pair.variant_id
    )
    normal_result = compact_components["case_results"][0]
    altered_result = _altered_result(pair, variant)
    returned = iter(
        (
            _ExecutionArtifacts(normal_result, None, None, None),
            _ExecutionArtifacts(normal_result, None, None, None),
            _ExecutionArtifacts(altered_result, None, None, None),
        )
    )
    contexts = []

    def fake_execute(*_args):
        context = getcontext()
        contexts.append((context.prec, context.rounding))
        return next(returned)

    monkeypatch.setattr(
        "msa.validation.experiments.execution.runner._execute_pair",
        fake_execute,
    )
    result, same, decimal = _execute_pair_v2((pair, case, variant))
    assert result == normal_result
    assert contexts == [
        (28, ROUND_HALF_EVEN),
        (28, ROUND_HALF_EVEN),
        (7, ROUND_FLOOR),
    ]
    assert same.comparison_kind is DeterminismEvidenceKind.SAME_CONTEXT_REPEAT
    assert decimal.comparison_kind is (
        DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
    )
    assert same.determinism_comparison_id != decimal.determinism_comparison_id
    assert same.to_dict() != decimal.to_dict()


def test_pair_v2_rejects_seed_3_before_calling_core_runner(
    compact_components,
    monkeypatch,
) -> None:
    pair = compact_components["manifest"].deferred_oos_pairs[0]
    case = next(
        item
        for item in compact_components["dataset"].cases
        if item.dataset_case_id == pair.dataset_case_id
    )
    variant = next(
        item
        for item in compact_components["plan"].variants
        if item.variant_id == pair.variant_id
    )

    def forbidden(*_args):
        raise AssertionError("Core runner must not be called for seed 3/OOS")

    monkeypatch.setattr(
        "msa.validation.experiments.execution.runner._execute_pair",
        forbidden,
    )
    with pytest.raises(C008CBCaseError, match="seed 3/OOS"):
        _execute_pair_v2((pair, case, variant))


def test_baseline_rewrite_is_global_not_25_variant_triggers(
    compact_components,
) -> None:
    summaries, global_evidence = evaluate_validation_degeneration_v2(
        compact_components["case_results"],
        compact_components["deltas"],
        compact_components["replay"],
        compact_components["cutoff"],
    )
    rewrite_findings = tuple(
        finding
        for summary in summaries
        for finding in summary.findings
        if finding.rule_code == "FUTURE_PREFIX_REWRITE"
    )
    assert len(rewrite_findings) == 25
    assert all(not item.triggered for item in rewrite_findings)
    assert all(
        item.evidence_scope
        is DegenerationEvidenceScope.VARIANT_EVIDENCE_UNAVAILABLE
        for item in rewrite_findings
    )
    assert all(
        item.evidence_subject_id == item.variant_id
        and not item.evidence_source_ids
        for item in rewrite_findings
    )
    assert all(
        "FUTURE_PREFIX_REWRITE" not in item.triggered_rule_codes
        for item in summaries
    )
    assert global_evidence.triggered
    assert global_evidence.evidence_scope is (
        DegenerationEvidenceScope.BASELINE_GLOBAL
    )
    assert global_evidence.evidence_subject_id == (
        compact_components["plan"].variants[0].variant_id
    )
    assert len(global_evidence.evidence_source_ids) == 15
    assert ExperimentDegenerationSummaryV2.from_dict(
        summaries[0].to_dict()
    ) == summaries[0]
    assert ExperimentGlobalDegenerationEvidenceV2.from_dict(
        global_evidence.to_dict()
    ) == global_evidence


def test_v2_gates_bind_independent_comparison_evidence(
    compact_components,
) -> None:
    same, decimal = _v2_comparisons(compact_components)
    degeneration, global_evidence = evaluate_validation_degeneration_v2(
        compact_components["case_results"],
        compact_components["deltas"],
        compact_components["replay"],
        compact_components["cutoff"],
    )
    gates = evaluate_c008c_b_v2_gates(
        compact_components["manifest"],
        compact_components["case_results"],
        same,
        decimal,
        compact_components["replay"],
        compact_components["cutoff"],
        degeneration,
        global_evidence,
    )
    by_code = {item.gate_code: item for item in gates}
    repeat = by_code["DETERMINISTIC_REPEAT"]
    decimal_gate = by_code["DECIMAL_CONTEXT_INDEPENDENCE"]
    assert repeat.status is GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
    assert decimal_gate.status is GateEvaluationStatus.FAIL
    assert repeat.evidence_kind == "SAME_CONTEXT_REPEAT"
    assert decimal_gate.evidence_kind == "DECIMAL_CONTEXT_PERTURBATION"
    assert repeat.evidence_ids == tuple(
        item.determinism_comparison_id for item in same
    )
    assert decimal_gate.evidence_ids == tuple(
        item.determinism_comparison_id for item in decimal
    )
    assert not set(repeat.evidence_ids) & set(decimal_gate.evidence_ids)
    assert repeat.evidence_payload_digest != (
        decimal_gate.evidence_payload_digest
    )
    degeneration_gate = by_code["NO_NEIGHBORHOOD_DEGENERATION"]
    assert global_evidence.global_evidence_id not in (
        degeneration_gate.evidence_ids
    )
    assert ExperimentGateResultV2.from_dict(repeat.to_dict()) == repeat


def test_one_comparison_collection_cannot_bind_both_gates(
    compact_components,
) -> None:
    same, _ = _v2_comparisons(compact_components)
    degeneration, global_evidence = evaluate_validation_degeneration_v2(
        compact_components["case_results"],
        compact_components["deltas"],
        compact_components["replay"],
        compact_components["cutoff"],
    )
    with pytest.raises(C008CBGateError, match="Decimal perturbation"):
        evaluate_c008c_b_v2_gates(
            compact_components["manifest"],
            compact_components["case_results"],
            same,
            same,
            compact_components["replay"],
            compact_components["cutoff"],
            degeneration,
            global_evidence,
        )
