"""Explicit source-bound attribution for the ten frozen degeneration rules."""

from __future__ import annotations

from ...identity import semantic_id
from ..contracts import C008CBRunReport
from .contracts import (
    DegenerationEvidenceKind,
    DegenerationRuleAttribution,
    VariantDegenerationAttribution,
)
from .errors import C008CBRCAReportError


_VARIANT_DIRECT_RULES = frozenset(
    {
        "PIPELINE_EXECUTION_FAILURE",
        "CAUSAL_AUDIT_FAILURE",
        "METRIC_SOURCE_BIND_FAILURE",
        "BATCH_REPLAY_MISMATCH",
        "STRUCTURE_EVENT_COLLAPSE",
        "BOX_EPISODE_COLLAPSE",
        "MULTI_METRIC_COVERAGE_COLLAPSE",
        "AGGREGATE_SET_INCOMPLETE",
    }
)


def _classification(finding: object) -> DegenerationEvidenceKind:
    if finding.status.value == "INSUFFICIENT_EVIDENCE":
        return DegenerationEvidenceKind.INSUFFICIENT_EVIDENCE
    if finding.rule_code == "FUTURE_PREFIX_REWRITE":
        return DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
    if finding.rule_code == "INVALID_OR_REPAIRED_CONFIG":
        return DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE
    if finding.rule_code in _VARIANT_DIRECT_RULES:
        return DegenerationEvidenceKind.VARIANT_DIRECT
    raise C008CBRCAReportError(
        f"unrecognized degeneration rule: {finding.rule_code}"
    )


def attribute_degeneration(report: C008CBRunReport):
    results = []
    cutoff_ids = tuple(
        item.fixed_cutoff_comparison_id
        for item in report.fixed_cutoff_comparisons
    )
    for summary in report.degeneration_summaries:
        attributions = []
        for finding in summary.findings:
            kind = _classification(finding)
            if kind is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION:
                subject = "BASELINE_FIXED_CUTOFF_AGGREGATE"
                source_ids = cutoff_ids
                flags = (False, True, True)
            elif kind is DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE:
                subject = "FROZEN_EXECUTION_MANIFEST_CONFIG_AUTHORITY"
                source_ids = (report.execution_manifest_id,)
                flags = (False, False, False)
            elif kind is DegenerationEvidenceKind.INSUFFICIENT_EVIDENCE:
                subject = "INSUFFICIENT_VARIANT_EVIDENCE"
                source_ids = (finding.degeneration_finding_id,)
                flags = (False, False, False)
            else:
                subject = summary.variant_id
                source_ids = (finding.degeneration_finding_id,)
                flags = (True, False, False)
            kwargs = {
                "variant_id": summary.variant_id,
                "rule_code": finding.rule_code,
                "triggered": finding.triggered,
                "finding_status": finding.status.value,
                "evidence_kind": kind,
                "evidence_direct_subject": subject,
                "evidence_source_ids": source_ids,
                "variant_specific": flags[0],
                "shared_baseline_evidence": flags[1],
                "derived_from_failed_gate": flags[2],
                "schema_version": 1,
            }
            payload = {
                **kwargs,
                "evidence_kind": kind.value,
                "evidence_source_ids": list(source_ids),
            }
            attributions.append(
                DegenerationRuleAttribution(
                    rule_attribution_id=semantic_id(
                        DegenerationRuleAttribution._PREFIX, payload
                    ),
                    **kwargs,
                )
            )
        direct = tuple(
            item.rule_code
            for item in attributions
            if item.triggered
            and item.evidence_kind is DegenerationEvidenceKind.VARIANT_DIRECT
        )
        propagated = tuple(
            item.rule_code
            for item in attributions
            if item.triggered
            and item.evidence_kind
            is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
        )
        non_global_problem = any(
            item.triggered
            and item.evidence_kind
            in (
                DegenerationEvidenceKind.VARIANT_DIRECT,
                DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE,
            )
            for item in attributions
        )
        insufficient = any(
            item.evidence_kind is DegenerationEvidenceKind.INSUFFICIENT_EVIDENCE
            for item in attributions
        )
        descriptive = (
            "DEGENERATED"
            if non_global_problem
            else "INSUFFICIENT_EVIDENCE"
            if insufficient
            else "SENSITIVE"
            if summary.non_zero_validation_delta_count
            else "NOT_DEGENERATED"
        )
        kwargs = {
            "variant_id": summary.variant_id,
            "formal_status": summary.status.value,
            "attributions": tuple(attributions),
            "direct_triggered_rule_codes": direct,
            "global_propagated_rule_codes": propagated,
            "descriptive_status_without_global_propagation": descriptive,
            "schema_version": 1,
        }
        payload = {
            **kwargs,
            "attributions": [item.to_dict() for item in attributions],
            "direct_triggered_rule_codes": list(direct),
            "global_propagated_rule_codes": list(propagated),
        }
        results.append(
            VariantDegenerationAttribution(
                variant_attribution_id=semantic_id(
                    VariantDegenerationAttribution._PREFIX, payload
                ),
                **kwargs,
            )
        )
    return tuple(results)


__all__ = ["attribute_degeneration"]
