from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, getcontext

import pytest

from msa.validation.experiments.execution import (
    C008CBV2ExecutionContract,
    DegenerationStatus,
    DegenerationEvidenceScope,
    DeterminismEvidenceKind,
    ExperimentDegenerationFindingV2,
    ExperimentDegenerationSummaryV2,
    ExperimentFixedCutoffComparison,
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
    C008CBDegenerationError,
    C008CBGateError,
)
from msa.validation.experiments.execution.gate_evaluator import (
    evaluate_c008c_b_v2_gates,
    validate_c008c_b_v2_gate_results,
)
from msa.validation.experiments.identity import digest, semantic_id
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


def _resign(cls, id_field: str, payload: dict):
    signed = dict(payload)
    signed[id_field] = semantic_id(
        cls._PREFIX,
        {key: value for key, value in signed.items() if key != id_field},
    )
    return cls.from_dict(signed)


def _replace_finding(finding, **changes):
    payload = finding.to_dict()
    payload.update(changes)
    return _resign(
        ExperimentDegenerationFindingV2,
        "degeneration_finding_id",
        payload,
    )


def _replace_summary(summary, findings, **changes):
    payload = summary.to_dict()
    payload.update(
        {
            "findings": [item.to_dict() for item in findings],
            "triggered_rule_codes": [
                item.rule_code for item in findings if item.triggered
            ],
            **changes,
        }
    )
    return _resign(
        ExperimentDegenerationSummaryV2,
        "degeneration_summary_id",
        payload,
    )


def _clean_summaries(summaries):
    cleaned = []
    for summary in summaries:
        findings = tuple(
            finding
            if finding.rule_code == "FUTURE_PREFIX_REWRITE"
            else _replace_finding(
                finding,
                evidence_scope=DegenerationEvidenceScope.VARIANT_DIRECT.value,
                triggered=False,
                status=DegenerationStatus.NOT_DEGENERATED.value,
                facts=[
                    fact
                    for fact in finding.facts
                    if fact != "applicable_variant_evidence_missing=true"
                ],
            )
            for finding in summary.findings
        )
        cleaned.append(
            _replace_summary(
                summary,
                findings,
                status=DegenerationStatus.NOT_DEGENERATED.value,
                non_zero_validation_delta_count=0,
            )
        )
    return tuple(cleaned)


def _stable_global(global_evidence, **changes):
    payload = global_evidence.to_dict()
    payload.update(
        {
            "triggered": False,
            "status": DegenerationStatus.NOT_DEGENERATED.value,
            **changes,
        }
    )
    return _resign(
        ExperimentGlobalDegenerationEvidenceV2,
        "global_evidence_id",
        payload,
    )


def _with_direct_trigger(summaries):
    summaries = list(summaries)
    summary = summaries[0]
    findings = list(summary.findings)
    index = next(
        index
        for index, finding in enumerate(findings)
        if finding.rule_code != "FUTURE_PREFIX_REWRITE"
    )
    findings[index] = _replace_finding(
        findings[index],
        evidence_scope=DegenerationEvidenceScope.VARIANT_DIRECT.value,
        triggered=True,
        status=DegenerationStatus.DEGENERATED.value,
    )
    summaries[0] = _replace_summary(
        summary,
        tuple(findings),
        status=DegenerationStatus.DEGENERATED.value,
    )
    return tuple(summaries)


def _with_true_insufficient(summaries):
    summaries = list(summaries)
    summary = summaries[0]
    findings = list(summary.findings)
    index = next(
        index
        for index, finding in enumerate(findings)
        if finding.rule_code != "FUTURE_PREFIX_REWRITE"
    )
    facts = tuple(findings[index].facts) + (
        "applicable_variant_evidence_missing=true",
    )
    findings[index] = _replace_finding(
        findings[index],
        evidence_scope=(
            DegenerationEvidenceScope.TRUE_INSUFFICIENT_EVIDENCE.value
        ),
        triggered=False,
        status=DegenerationStatus.INSUFFICIENT_EVIDENCE.value,
        facts=list(facts),
    )
    summaries[0] = _replace_summary(
        summary,
        tuple(findings),
        status=DegenerationStatus.INSUFFICIENT_EVIDENCE.value,
    )
    return tuple(summaries)


@pytest.fixture(scope="session")
def b_v2_harness_inputs(compact_components):
    same, decimal = _v2_comparisons(compact_components)
    summaries, triggered_global = evaluate_validation_degeneration_v2(
        compact_components["case_results"],
        compact_components["deltas"],
        compact_components["replay"],
        compact_components["cutoff"],
    )
    return {
        "same": same,
        "decimal": decimal,
        "raw_summaries": summaries,
        "clean_summaries": _clean_summaries(summaries),
        "triggered_global": triggered_global,
        "stable_global": _stable_global(triggered_global),
    }


def _evaluate(compact_components, inputs, summaries, global_evidence, *, cutoff=None):
    return evaluate_c008c_b_v2_gates(
        compact_components["manifest"],
        compact_components["case_results"],
        inputs["same"],
        inputs["decimal"],
        compact_components["replay"],
        compact_components["cutoff"] if cutoff is None else cutoff,
        summaries,
        global_evidence,
    )


def _gate(gates, code):
    return next(item for item in gates if item.gate_code == code)


def _replace_gate(gate, **changes):
    payload = gate.to_dict()
    payload.update(changes)
    return _resign(ExperimentGateResultV2, "gate_result_id", payload)


def _validate(
    compact_components,
    inputs,
    gates,
    summaries,
    global_evidence,
    *,
    cutoff=None,
):
    return validate_c008c_b_v2_gate_results(
        gates,
        compact_components["manifest"],
        compact_components["case_results"],
        inputs["same"],
        inputs["decimal"],
        compact_components["replay"],
        compact_components["cutoff"] if cutoff is None else cutoff,
        summaries,
        global_evidence,
    )


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
    b_v2_harness_inputs,
) -> None:
    summaries = b_v2_harness_inputs["raw_summaries"]
    global_evidence = b_v2_harness_inputs["triggered_global"]
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
        is DegenerationEvidenceScope.NOT_APPLICABLE_GLOBAL_RULE
        for item in rewrite_findings
    )
    assert all(
        item.status is DegenerationStatus.NOT_DEGENERATED
        and set(item.facts)
        == {
            "rule_applicability=baseline_global",
            "variant_trigger=false",
            "global_evidence_evaluated_separately=true",
        }
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
    b_v2_harness_inputs,
) -> None:
    same = b_v2_harness_inputs["same"]
    decimal = b_v2_harness_inputs["decimal"]
    degeneration = b_v2_harness_inputs["clean_summaries"]
    global_evidence = b_v2_harness_inputs["stable_global"]
    gates = _evaluate(
        compact_components,
        b_v2_harness_inputs,
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
    assert degeneration_gate.status is GateEvaluationStatus.PASS
    assert degeneration_gate.evidence_ids == tuple(
        item.degeneration_summary_id for item in degeneration
    ) + (global_evidence.global_evidence_id,)
    assert degeneration_gate.evidence_payload_digest == digest(
        {
            "variant_summaries": [item.to_dict() for item in degeneration],
            "global_rewrite_evidence": global_evidence.to_dict(),
        }
    )
    assert ExperimentGateResultV2.from_dict(repeat.to_dict()) == repeat


def test_one_comparison_collection_cannot_bind_both_gates(
    compact_components,
    b_v2_harness_inputs,
) -> None:
    same = b_v2_harness_inputs["same"]
    degeneration = b_v2_harness_inputs["clean_summaries"]
    global_evidence = b_v2_harness_inputs["stable_global"]
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


def test_global_trigger_direct_trigger_and_true_insufficient_each_fail_gate(
    compact_components,
    b_v2_harness_inputs,
) -> None:
    clean = b_v2_harness_inputs["clean_summaries"]
    stable = b_v2_harness_inputs["stable_global"]
    cases = (
        (clean, b_v2_harness_inputs["triggered_global"]),
        (_with_direct_trigger(clean), stable),
        (_with_true_insufficient(clean), stable),
    )
    for summaries, global_evidence in cases:
        gate = _gate(
            _evaluate(
                compact_components,
                b_v2_harness_inputs,
                summaries,
                global_evidence,
            ),
            "NO_NEIGHBORHOOD_DEGENERATION",
        )
        assert gate.status is GateEvaluationStatus.FAIL


def test_global_rule_not_applicable_is_not_variant_insufficient(
    b_v2_harness_inputs,
) -> None:
    for summary in b_v2_harness_inputs["clean_summaries"]:
        finding = next(
            item
            for item in summary.findings
            if item.rule_code == "FUTURE_PREFIX_REWRITE"
        )
        assert finding.evidence_scope is (
            DegenerationEvidenceScope.NOT_APPLICABLE_GLOBAL_RULE
        )
        assert finding.status is DegenerationStatus.NOT_DEGENERATED
        assert summary.status is DegenerationStatus.NOT_DEGENERATED


def test_global_mutations_resign_no_neighborhood_gate(
    compact_components,
    b_v2_harness_inputs,
) -> None:
    clean = b_v2_harness_inputs["clean_summaries"]
    stable = b_v2_harness_inputs["stable_global"]
    base_gate = _gate(
        _evaluate(
            compact_components,
            b_v2_harness_inputs,
            clean,
            stable,
        ),
        "NO_NEIGHBORHOOD_DEGENERATION",
    )
    triggered_gate = _gate(
        _evaluate(
            compact_components,
            b_v2_harness_inputs,
            clean,
            b_v2_harness_inputs["triggered_global"],
        ),
        "NO_NEIGHBORHOOD_DEGENERATION",
    )
    changed_facts = _stable_global(
        stable,
        facts=list(stable.facts) + ["mutation_probe=true"],
    )
    facts_gate = _gate(
        _evaluate(
            compact_components,
            b_v2_harness_inputs,
            clean,
            changed_facts,
        ),
        "NO_NEIGHBORHOOD_DEGENERATION",
    )

    cutoff = list(compact_components["cutoff"])
    cutoff_payload = cutoff[0].to_dict()
    cutoff_payload["failure_error_type"] = (
        f"{cutoff_payload['failure_error_type']}SourceMutation"
    )
    cutoff[0] = _resign(
        ExperimentFixedCutoffComparison,
        "fixed_cutoff_comparison_id",
        cutoff_payload,
    )
    cutoff = tuple(cutoff)
    changed_sources = _stable_global(
        stable,
        evidence_source_ids=[
            item.fixed_cutoff_comparison_id for item in cutoff
        ],
    )
    sources_gate = _gate(
        _evaluate(
            compact_components,
            b_v2_harness_inputs,
            clean,
            changed_sources,
            cutoff=cutoff,
        ),
        "NO_NEIGHBORHOOD_DEGENERATION",
    )

    gate_ids = {
        item.gate_result_id
        for item in (base_gate, triggered_gate, facts_gate, sources_gate)
    }
    payload_digests = {
        item.evidence_payload_digest
        for item in (base_gate, triggered_gate, facts_gate, sources_gate)
    }
    assert len(gate_ids) == 4
    assert len(payload_digests) == 4


def test_variant_and_global_scope_contract_attacks_are_rejected(
    compact_components,
    b_v2_harness_inputs,
) -> None:
    rewrite = next(
        item
        for item in b_v2_harness_inputs["clean_summaries"][0].findings
        if item.rule_code == "FUTURE_PREFIX_REWRITE"
    )
    with pytest.raises(C008CBDegenerationError):
        _replace_finding(
            rewrite,
            triggered=True,
            status=DegenerationStatus.DEGENERATED.value,
        )
    with pytest.raises(C008CBDegenerationError):
        _replace_finding(
            rewrite,
            status=DegenerationStatus.INSUFFICIENT_EVIDENCE.value,
        )
    with pytest.raises(C008CBDegenerationError):
        _replace_finding(
            rewrite,
            evidence_scope=DegenerationEvidenceScope.BASELINE_GLOBAL.value,
        )

    variant_id = compact_components["manifest"].variant_ids[1]
    forged_global = _stable_global(
        b_v2_harness_inputs["stable_global"],
        baseline_variant_id=variant_id,
        evidence_subject_id=variant_id,
    )
    with pytest.raises(C008CBGateError, match="bind Baseline"):
        _evaluate(
            compact_components,
            b_v2_harness_inputs,
            b_v2_harness_inputs["clean_summaries"],
            forged_global,
        )


def test_gate_verifier_rejects_missing_or_unhashed_global_evidence(
    compact_components,
    b_v2_harness_inputs,
) -> None:
    summaries = b_v2_harness_inputs["clean_summaries"]
    global_evidence = b_v2_harness_inputs["stable_global"]
    gates = _evaluate(
        compact_components,
        b_v2_harness_inputs,
        summaries,
        global_evidence,
    )
    gate_index = next(
        index
        for index, item in enumerate(gates)
        if item.gate_code == "NO_NEIGHBORHOOD_DEGENERATION"
    )
    degeneration_gate = gates[gate_index]

    missing_global = list(gates)
    missing_global[gate_index] = _replace_gate(
        degeneration_gate,
        evidence_ids=list(degeneration_gate.evidence_ids[:-1]),
    )
    with pytest.raises(C008CBGateError, match="recomputed"):
        _validate(
            compact_components,
            b_v2_harness_inputs,
            tuple(missing_global),
            summaries,
            global_evidence,
        )

    unhashed_global = list(gates)
    unhashed_global[gate_index] = _replace_gate(
        degeneration_gate,
        evidence_payload_digest=digest(
            [item.to_dict() for item in summaries]
        ),
    )
    with pytest.raises(C008CBGateError, match="recomputed"):
        _validate(
            compact_components,
            b_v2_harness_inputs,
            tuple(unhashed_global),
            summaries,
            global_evidence,
        )


def test_gate_verifier_rejects_reused_gate_after_global_change(
    compact_components,
    b_v2_harness_inputs,
) -> None:
    summaries = b_v2_harness_inputs["clean_summaries"]
    stable = b_v2_harness_inputs["stable_global"]
    gates = _evaluate(
        compact_components,
        b_v2_harness_inputs,
        summaries,
        stable,
    )
    assert _validate(
        compact_components,
        b_v2_harness_inputs,
        gates,
        summaries,
        stable,
    ) == gates
    changed = _stable_global(
        stable,
        facts=list(stable.facts) + ["reused_gate_attack=true"],
    )
    with pytest.raises(C008CBGateError, match="recomputed"):
        _validate(
            compact_components,
            b_v2_harness_inputs,
            gates,
            summaries,
            changed,
        )
