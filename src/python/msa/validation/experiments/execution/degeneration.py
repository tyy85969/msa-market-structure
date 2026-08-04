"""Frozen ten-rule VALIDATION degeneration audit."""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from msa.validation.metrics import default_metric_formula_registry

from ..contracts import DatasetPartition
from ..identity import semantic_id
from .contracts import (
    ExperimentCaseResult,
    ExperimentCaseStatus,
    ExperimentDegenerationFinding,
    ExperimentDegenerationSummary,
    ExperimentFixedCutoffComparison,
    ExperimentMetricDeltaSummary,
    ExperimentReplayComparison,
    FixedCutoffStatus,
    DegenerationStatus,
    ReplayComparisonStatus,
)
from .contracts_v2 import (
    B_V2_EXECUTION_SEMANTICS,
    DegenerationEvidenceScope,
    ExperimentDegenerationFindingV2,
    ExperimentDegenerationSummaryV2,
    ExperimentGlobalDegenerationEvidenceV2,
    v2_payload_id,
)
from .errors import C008CBDegenerationError
from .manifest import load_c008c_b_authority


def _finding(
    *,
    variant_id: str,
    rule_code: str,
    triggered: bool,
    insufficient: bool,
    validation_case_ids: tuple[str, ...],
    facts: tuple[str, ...],
) -> ExperimentDegenerationFinding:
    status = (
        DegenerationStatus.DEGENERATED
        if triggered
        else DegenerationStatus.INSUFFICIENT_EVIDENCE
        if insufficient
        else DegenerationStatus.NOT_DEGENERATED
    )
    kwargs = {
        "variant_id": variant_id,
        "rule_code": rule_code,
        "triggered": triggered,
        "status": status,
        "validation_case_ids": validation_case_ids,
        "facts": facts,
        "schema_version": 1,
    }
    payload = {
        "variant_id": variant_id,
        "rule_code": rule_code,
        "triggered": triggered,
        "status": status.value,
        "validation_case_ids": list(validation_case_ids),
        "facts": list(facts),
        "schema_version": 1,
    }
    return ExperimentDegenerationFinding(
        degeneration_finding_id=semantic_id(
            ExperimentDegenerationFinding._PREFIX, payload
        ),
        **kwargs,
    )


def _summary(
    *,
    variant_id: str,
    findings: tuple[ExperimentDegenerationFinding, ...],
    non_zero_validation_delta_count: int,
) -> ExperimentDegenerationSummary:
    triggered = tuple(
        item.rule_code for item in findings if item.triggered
    )
    insufficient = any(
        item.status is DegenerationStatus.INSUFFICIENT_EVIDENCE
        for item in findings
    )
    status = (
        DegenerationStatus.DEGENERATED
        if triggered
        else DegenerationStatus.INSUFFICIENT_EVIDENCE
        if insufficient
        else DegenerationStatus.SENSITIVE
        if non_zero_validation_delta_count > 0
        else DegenerationStatus.NOT_DEGENERATED
    )
    kwargs = {
        "variant_id": variant_id,
        "status": status,
        "findings": findings,
        "triggered_rule_codes": triggered,
        "non_zero_validation_delta_count": (
            non_zero_validation_delta_count
        ),
        "schema_version": 1,
    }
    payload = {
        "variant_id": variant_id,
        "status": status.value,
        "findings": [item.to_dict() for item in findings],
        "triggered_rule_codes": list(triggered),
        "non_zero_validation_delta_count": (
            non_zero_validation_delta_count
        ),
        "schema_version": 1,
    }
    return ExperimentDegenerationSummary(
        degeneration_summary_id=semantic_id(
            ExperimentDegenerationSummary._PREFIX, payload
        ),
        **kwargs,
    )


def _coverage_counts(
    results: tuple[ExperimentCaseResult, ...],
) -> dict[object, tuple[int, int]] | None:
    formulas = default_metric_formula_registry()
    counts = {
        item.metric_name: [0, 0]
        for item in formulas
    }
    for result in results:
        if len(result.aggregates) != 10:
            return None
        for aggregate in result.aggregates:
            counts[aggregate.metric_name][0] += aggregate.eligible_count
            counts[aggregate.metric_name][1] += aggregate.matured_count
    return {
        key: (value[0], value[1]) for key, value in counts.items()
    }


def _coverage_collapsed_metrics(
    baseline: dict[object, tuple[int, int]],
    variant: dict[object, tuple[int, int]],
) -> tuple[str, ...]:
    collapsed: list[str] = []
    context = Context(prec=50, rounding=ROUND_HALF_EVEN)
    with localcontext(context):
        for metric_name in baseline:
            baseline_eligible, baseline_matured = baseline[metric_name]
            variant_eligible, variant_matured = variant[metric_name]
            declines: list[Decimal] = []
            if baseline_eligible > 0:
                declines.append(
                    (
                        Decimal(baseline_eligible)
                        - Decimal(variant_eligible)
                    )
                    / Decimal(baseline_eligible)
                )
            if baseline_matured > 0:
                declines.append(
                    (
                        Decimal(baseline_matured)
                        - Decimal(variant_matured)
                    )
                    / Decimal(baseline_matured)
                )
            if any(item > Decimal("0.90") for item in declines):
                collapsed.append(metric_name.value)
    return tuple(collapsed)


def evaluate_validation_degeneration(
    case_results: tuple[ExperimentCaseResult, ...],
    metric_delta_summaries: tuple[ExperimentMetricDeltaSummary, ...],
    replay_comparisons: tuple[ExperimentReplayComparison, ...],
    fixed_cutoff_comparisons: tuple[
        ExperimentFixedCutoffComparison, ...
    ],
    root: Path | None = None,
) -> tuple[ExperimentDegenerationSummary, ...]:
    """Apply every frozen rule to every non-Baseline Variant."""

    if (
        len(case_results) != 390
        or len(metric_delta_summaries) != 50
        or len(replay_comparisons) != 140
        or len(fixed_cutoff_comparisons) != 15
    ):
        raise C008CBDegenerationError(
            "degeneration audit requires complete B-stage inputs"
        )
    _, dataset, gates, plan, _ = load_c008c_b_authority(root)
    gate = next(
        item
        for item in gates
        if item.code == "NO_NEIGHBORHOOD_DEGENERATION"
    )
    rules = gate.policy.degeneration_rules
    rule_codes = tuple(item.rule_code for item in rules)
    if len(rule_codes) != 10:
        raise C008CBDegenerationError(
            "frozen degeneration policy must contain ten rules"
        )
    validation_case_ids = tuple(
        item.dataset_case_id
        for item in dataset.cases
        if item.partition is DatasetPartition.VALIDATION
    )
    result_index = {
        (item.dataset_case_id, item.variant_id): item
        for item in case_results
    }
    baseline_id = plan.variants[0].variant_id
    baseline_results = tuple(
        result_index[(case_id, baseline_id)]
        for case_id in validation_case_ids
    )
    baseline_events = sum(
        item.event_count for item in baseline_results
    )
    baseline_boxes = sum(
        item.box_episode_count for item in baseline_results
    )
    baseline_coverage = _coverage_counts(baseline_results)
    replay_by_variant = {
        variant.variant_id: tuple(
            item
            for item in replay_comparisons
            if item.scope == "VARIANT"
            and item.variant_id == variant.variant_id
        )
        for variant in plan.variants[1:]
    }
    cutoff_rewrite = any(
        item.status is not FixedCutoffStatus.STABLE
        for item in fixed_cutoff_comparisons
    )
    delta_by_variant = {
        item.variant_id: item
        for item in metric_delta_summaries
        if item.partition is DatasetPartition.VALIDATION
    }
    summaries: list[ExperimentDegenerationSummary] = []
    for variant in plan.variants[1:]:
        results = tuple(
            result_index[(case_id, variant.variant_id)]
            for case_id in validation_case_ids
        )
        variant_events = sum(item.event_count for item in results)
        variant_boxes = sum(item.box_episode_count for item in results)
        variant_coverage = _coverage_counts(results)
        replay = replay_by_variant[variant.variant_id]
        collapsed_metrics = (
            ()
            if baseline_coverage is None or variant_coverage is None
            else _coverage_collapsed_metrics(
                baseline_coverage, variant_coverage
            )
        )
        facts_by_rule = {
            "PIPELINE_EXECUTION_FAILURE": (
                any(
                    item.status is ExperimentCaseStatus.PIPELINE_FAILED
                    for item in results
                ),
                False,
                (
                    f"pipeline_failures={sum(item.status is ExperimentCaseStatus.PIPELINE_FAILED for item in results)}",
                ),
            ),
            "CAUSAL_AUDIT_FAILURE": (
                any(
                    item.status
                    is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED
                    for item in results
                ),
                False,
                (
                    f"causal_audit_failures={sum(item.status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED for item in results)}",
                ),
            ),
            "METRIC_SOURCE_BIND_FAILURE": (
                any(
                    item.status
                    is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED
                    for item in results
                ),
                False,
                (
                    f"metric_source_bind_failures={sum(item.status is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED for item in results)}",
                ),
            ),
            "BATCH_REPLAY_MISMATCH": (
                any(
                    item.status is not ReplayComparisonStatus.MATCH
                    for item in replay
                ),
                len(replay) != 5,
                (
                    f"replay_samples={len(replay)}",
                    f"replay_non_matches={sum(item.status is not ReplayComparisonStatus.MATCH for item in replay)}",
                ),
            ),
            "FUTURE_PREFIX_REWRITE": (
                cutoff_rewrite,
                len(fixed_cutoff_comparisons) != 15,
                (
                    f"baseline_fixed_cutoff_cases={len(fixed_cutoff_comparisons)}",
                    f"baseline_cutoff_non_stable={sum(item.status is not FixedCutoffStatus.STABLE for item in fixed_cutoff_comparisons)}",
                ),
            ),
            "STRUCTURE_EVENT_COLLAPSE": (
                baseline_events >= 10 and variant_events == 0,
                False,
                (
                    f"baseline_structure_events={baseline_events}",
                    f"variant_structure_events={variant_events}",
                ),
            ),
            "BOX_EPISODE_COLLAPSE": (
                baseline_boxes >= 5 and variant_boxes == 0,
                False,
                (
                    f"baseline_box_episodes={baseline_boxes}",
                    f"variant_box_episodes={variant_boxes}",
                ),
            ),
            "MULTI_METRIC_COVERAGE_COLLAPSE": (
                len(collapsed_metrics) >= 5,
                baseline_coverage is None or variant_coverage is None,
                (
                    f"collapsed_metric_count={len(collapsed_metrics)}",
                    "collapsed_metrics="
                    + (
                        ",".join(collapsed_metrics)
                        if collapsed_metrics
                        else "none"
                    ),
                    "decline_fraction_operator=>0.90",
                ),
            ),
            "AGGREGATE_SET_INCOMPLETE": (
                any(len(item.aggregates) != 10 for item in results),
                False,
                (
                    f"incomplete_case_count={sum(len(item.aggregates) != 10 for item in results)}",
                ),
            ),
            "INVALID_OR_REPAIRED_CONFIG": (
                False,
                False,
                (
                    "formal_frozen_config_validated=true",
                    "automatic_repair_used=false",
                ),
            ),
        }
        findings = tuple(
            _finding(
                variant_id=variant.variant_id,
                rule_code=code,
                triggered=facts_by_rule[code][0],
                insufficient=facts_by_rule[code][1],
                validation_case_ids=validation_case_ids,
                facts=facts_by_rule[code][2],
            )
            for code in rule_codes
        )
        summaries.append(
            _summary(
                variant_id=variant.variant_id,
                findings=findings,
                non_zero_validation_delta_count=(
                    delta_by_variant[variant.variant_id].non_zero_count
                ),
            )
        )
    result = tuple(summaries)
    if len(result) != 25:
        raise C008CBDegenerationError(
            "degeneration audit must produce 25 Variant summaries"
        )
    return result


def _finding_v2(
    *,
    variant_id: str,
    evidence_scope: DegenerationEvidenceScope,
    evidence_source_ids: tuple[str, ...],
    rule_code: str,
    triggered: bool,
    insufficient: bool,
    validation_case_ids: tuple[str, ...],
    facts: tuple[str, ...],
) -> ExperimentDegenerationFindingV2:
    if insufficient and "applicable_variant_evidence_missing=true" not in facts:
        facts = facts + ("applicable_variant_evidence_missing=true",)
    status = (
        DegenerationStatus.DEGENERATED
        if triggered
        else DegenerationStatus.INSUFFICIENT_EVIDENCE
        if insufficient
        else DegenerationStatus.NOT_DEGENERATED
    )
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "variant_id": variant_id,
        "evidence_subject_id": variant_id,
        "evidence_scope": evidence_scope,
        "evidence_source_ids": evidence_source_ids,
        "rule_code": rule_code,
        "triggered": triggered,
        "status": status,
        "validation_case_ids": validation_case_ids,
        "facts": facts,
        "schema_version": 2,
    }
    payload = {
        **kwargs,
        "evidence_scope": evidence_scope.value,
        "evidence_source_ids": list(evidence_source_ids),
        "status": status.value,
        "validation_case_ids": list(validation_case_ids),
        "facts": list(facts),
    }
    return ExperimentDegenerationFindingV2(
        degeneration_finding_id=v2_payload_id(
            ExperimentDegenerationFindingV2._PREFIX, payload
        ),
        **kwargs,
    )


def _summary_v2(
    *,
    variant_id: str,
    findings: tuple[ExperimentDegenerationFindingV2, ...],
    non_zero_validation_delta_count: int,
) -> ExperimentDegenerationSummaryV2:
    triggered = tuple(item.rule_code for item in findings if item.triggered)
    insufficient = any(
        item.evidence_scope
        is DegenerationEvidenceScope.TRUE_INSUFFICIENT_EVIDENCE
        for item in findings
    )
    status = (
        DegenerationStatus.DEGENERATED
        if triggered
        else DegenerationStatus.INSUFFICIENT_EVIDENCE
        if insufficient
        else DegenerationStatus.SENSITIVE
        if non_zero_validation_delta_count
        else DegenerationStatus.NOT_DEGENERATED
    )
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "variant_id": variant_id,
        "status": status,
        "findings": findings,
        "triggered_rule_codes": triggered,
        "non_zero_validation_delta_count": non_zero_validation_delta_count,
        "schema_version": 2,
    }
    payload = {
        **kwargs,
        "status": status.value,
        "findings": [item.to_dict() for item in findings],
        "triggered_rule_codes": list(triggered),
    }
    return ExperimentDegenerationSummaryV2(
        degeneration_summary_id=v2_payload_id(
            ExperimentDegenerationSummaryV2._PREFIX, payload
        ),
        **kwargs,
    )


def _global_rewrite_evidence_v2(
    baseline_variant_id: str,
    fixed_cutoff_comparisons: tuple[ExperimentFixedCutoffComparison, ...],
) -> ExperimentGlobalDegenerationEvidenceV2:
    triggered = any(
        item.status is not FixedCutoffStatus.STABLE
        for item in fixed_cutoff_comparisons
    )
    source_ids = tuple(
        item.fixed_cutoff_comparison_id for item in fixed_cutoff_comparisons
    )
    status = (
        DegenerationStatus.DEGENERATED
        if triggered
        else DegenerationStatus.NOT_DEGENERATED
    )
    facts = (
        f"baseline_fixed_cutoff_cases={len(fixed_cutoff_comparisons)}",
        "baseline_cutoff_non_stable="
        + str(
            sum(
                item.status is not FixedCutoffStatus.STABLE
                for item in fixed_cutoff_comparisons
            )
        ),
        "variant_propagation=false",
    )
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "baseline_variant_id": baseline_variant_id,
        "evidence_subject_id": baseline_variant_id,
        "evidence_scope": DegenerationEvidenceScope.BASELINE_GLOBAL,
        "evidence_source_ids": source_ids,
        "rule_code": "FUTURE_PREFIX_REWRITE",
        "triggered": triggered,
        "status": status,
        "facts": facts,
        "schema_version": 2,
    }
    payload = {
        **kwargs,
        "evidence_scope": DegenerationEvidenceScope.BASELINE_GLOBAL.value,
        "evidence_source_ids": list(source_ids),
        "status": status.value,
        "facts": list(facts),
    }
    return ExperimentGlobalDegenerationEvidenceV2(
        global_evidence_id=v2_payload_id(
            ExperimentGlobalDegenerationEvidenceV2._PREFIX, payload
        ),
        **kwargs,
    )


def evaluate_validation_degeneration_v2(
    case_results: tuple[ExperimentCaseResult, ...],
    metric_delta_summaries: tuple[ExperimentMetricDeltaSummary, ...],
    replay_comparisons: tuple[ExperimentReplayComparison, ...],
    fixed_cutoff_comparisons: tuple[ExperimentFixedCutoffComparison, ...],
    root: Path | None = None,
) -> tuple[
    tuple[ExperimentDegenerationSummaryV2, ...],
    ExperimentGlobalDegenerationEvidenceV2,
]:
    """Derive subject-bound Variant findings and separate Baseline evidence."""

    if (
        len(case_results) != 390
        or len(metric_delta_summaries) != 50
        or len(replay_comparisons) != 140
        or len(fixed_cutoff_comparisons) != 15
    ):
        raise C008CBDegenerationError(
            "B-v2 degeneration requires complete non-OOS B-stage evidence"
        )
    if any(
        item.seed == 3 or item.partition is DatasetPartition.OOS
        for item in case_results
    ):
        raise C008CBDegenerationError("B-v2 degeneration forbids OOS outcomes")
    _, dataset, gates, plan, _ = load_c008c_b_authority(root)
    gate = next(
        item for item in gates if item.code == "NO_NEIGHBORHOOD_DEGENERATION"
    )
    rule_codes = tuple(item.rule_code for item in gate.policy.degeneration_rules)
    if len(rule_codes) != 10:
        raise C008CBDegenerationError("B-v2 requires ten frozen rules")
    validation_case_ids = tuple(
        item.dataset_case_id
        for item in dataset.cases
        if item.partition is DatasetPartition.VALIDATION
    )
    result_index = {
        (item.dataset_case_id, item.variant_id): item for item in case_results
    }
    baseline_id = plan.variants[0].variant_id
    baseline_results = tuple(
        result_index[(case_id, baseline_id)] for case_id in validation_case_ids
    )
    baseline_events = sum(item.event_count for item in baseline_results)
    baseline_boxes = sum(item.box_episode_count for item in baseline_results)
    baseline_coverage = _coverage_counts(baseline_results)
    replay_by_variant = {
        variant.variant_id: tuple(
            item
            for item in replay_comparisons
            if item.scope == "VARIANT" and item.variant_id == variant.variant_id
        )
        for variant in plan.variants[1:]
    }
    delta_by_variant = {
        item.variant_id: item
        for item in metric_delta_summaries
        if item.partition is DatasetPartition.VALIDATION
    }
    summaries: list[ExperimentDegenerationSummaryV2] = []
    for variant in plan.variants[1:]:
        results = tuple(
            result_index[(case_id, variant.variant_id)]
            for case_id in validation_case_ids
        )
        result_ids = tuple(item.case_result_id for item in results)
        replay = replay_by_variant[variant.variant_id]
        replay_ids = tuple(item.replay_comparison_id for item in replay)
        variant_events = sum(item.event_count for item in results)
        variant_boxes = sum(item.box_episode_count for item in results)
        variant_coverage = _coverage_counts(results)
        collapsed_metrics = (
            ()
            if baseline_coverage is None or variant_coverage is None
            else _coverage_collapsed_metrics(baseline_coverage, variant_coverage)
        )
        facts_by_rule = {
            "PIPELINE_EXECUTION_FAILURE": (
                any(
                    item.status is ExperimentCaseStatus.PIPELINE_FAILED
                    for item in results
                ),
                False,
                result_ids,
                (
                    "pipeline_failures="
                    + str(
                        sum(
                            item.status
                            is ExperimentCaseStatus.PIPELINE_FAILED
                            for item in results
                        )
                    ),
                ),
            ),
            "CAUSAL_AUDIT_FAILURE": (
                any(
                    item.status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED
                    for item in results
                ),
                False,
                result_ids,
                (
                    "causal_audit_failures="
                    + str(
                        sum(
                            item.status
                            is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED
                            for item in results
                        )
                    ),
                ),
            ),
            "METRIC_SOURCE_BIND_FAILURE": (
                any(
                    item.status
                    is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED
                    for item in results
                ),
                False,
                result_ids,
                (
                    "metric_source_bind_failures="
                    + str(
                        sum(
                            item.status
                            is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED
                            for item in results
                        )
                    ),
                ),
            ),
            "BATCH_REPLAY_MISMATCH": (
                any(
                    item.status is not ReplayComparisonStatus.MATCH
                    for item in replay
                ),
                len(replay) != 5,
                replay_ids,
                (
                    f"replay_samples={len(replay)}",
                    "replay_non_matches="
                    + str(
                        sum(
                            item.status is not ReplayComparisonStatus.MATCH
                            for item in replay
                        )
                    ),
                ),
            ),
            "FUTURE_PREFIX_REWRITE": (
                False,
                False,
                (),
                (
                    "rule_applicability=baseline_global",
                    "variant_trigger=false",
                    "global_evidence_evaluated_separately=true",
                ),
            ),
            "STRUCTURE_EVENT_COLLAPSE": (
                baseline_events >= 10 and variant_events == 0,
                False,
                result_ids,
                (
                    f"baseline_structure_events={baseline_events}",
                    f"variant_structure_events={variant_events}",
                ),
            ),
            "BOX_EPISODE_COLLAPSE": (
                baseline_boxes >= 5 and variant_boxes == 0,
                False,
                result_ids,
                (
                    f"baseline_box_episodes={baseline_boxes}",
                    f"variant_box_episodes={variant_boxes}",
                ),
            ),
            "MULTI_METRIC_COVERAGE_COLLAPSE": (
                len(collapsed_metrics) >= 5,
                baseline_coverage is None or variant_coverage is None,
                result_ids,
                (
                    f"collapsed_metric_count={len(collapsed_metrics)}",
                    "collapsed_metrics="
                    + (
                        ",".join(collapsed_metrics)
                        if collapsed_metrics
                        else "none"
                    ),
                    "decline_fraction_operator=>0.90",
                ),
            ),
            "AGGREGATE_SET_INCOMPLETE": (
                any(len(item.aggregates) != 10 for item in results),
                False,
                result_ids,
                (
                    "incomplete_case_count="
                    + str(
                        sum(len(item.aggregates) != 10 for item in results)
                    ),
                ),
            ),
            "INVALID_OR_REPAIRED_CONFIG": (
                False,
                False,
                result_ids,
                (
                    "formal_frozen_config_validated=true",
                    "automatic_repair_used=false",
                ),
            ),
        }
        findings = tuple(
            _finding_v2(
                variant_id=variant.variant_id,
                evidence_scope=(
                    DegenerationEvidenceScope.NOT_APPLICABLE_GLOBAL_RULE
                    if code == "FUTURE_PREFIX_REWRITE"
                    else DegenerationEvidenceScope.TRUE_INSUFFICIENT_EVIDENCE
                    if facts_by_rule[code][1]
                    else DegenerationEvidenceScope.VARIANT_DIRECT
                ),
                evidence_source_ids=facts_by_rule[code][2],
                rule_code=code,
                triggered=facts_by_rule[code][0],
                insufficient=facts_by_rule[code][1],
                validation_case_ids=validation_case_ids,
                facts=facts_by_rule[code][3],
            )
            for code in rule_codes
        )
        summaries.append(
            _summary_v2(
                variant_id=variant.variant_id,
                findings=findings,
                non_zero_validation_delta_count=(
                    delta_by_variant[variant.variant_id].non_zero_count
                ),
            )
        )
    if len(summaries) != 25:
        raise C008CBDegenerationError("B-v2 requires 25 Variant summaries")
    return tuple(summaries), _global_rewrite_evidence_v2(
        baseline_id, fixed_cutoff_comparisons
    )


__all__ = [
    "evaluate_validation_degeneration",
    "evaluate_validation_degeneration_v2",
]
