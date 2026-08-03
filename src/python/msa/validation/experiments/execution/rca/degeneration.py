"""Direct versus global-propagation attribution for frozen degeneration rules."""

from __future__ import annotations

from ...identity import semantic_id
from ..contracts import C008CBRunReport
from .contracts import (
    DegenerationEvidenceKind,
    DegenerationRuleAttribution,
    VariantDegenerationAttribution,
)


def attribute_degeneration(report: C008CBRunReport):
    results = []
    cutoff_ids = tuple(
        item.fixed_cutoff_comparison_id for item in report.fixed_cutoff_comparisons
    )
    for summary in report.degeneration_summaries:
        attributions = []
        for finding in summary.findings:
            global_rule = finding.rule_code == "FUTURE_PREFIX_REWRITE"
            kind = (
                DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
                if global_rule
                else DegenerationEvidenceKind.VARIANT_DIRECT
            )
            source_ids = cutoff_ids if global_rule else (finding.degeneration_finding_id,)
            kwargs = {
                "variant_id": summary.variant_id,
                "rule_code": finding.rule_code,
                "triggered": finding.triggered,
                "evidence_kind": kind,
                "evidence_direct_subject": "BASELINE_FIXED_CUTOFF_AGGREGATE" if global_rule else summary.variant_id,
                "evidence_source_ids": source_ids,
                "variant_specific": not global_rule,
                "shared_baseline_evidence": global_rule,
                "derived_from_failed_gate": global_rule,
                "schema_version": 1,
            }
            payload = {**kwargs, "evidence_kind": kind.value, "evidence_source_ids": list(source_ids)}
            attributions.append(DegenerationRuleAttribution(
                rule_attribution_id=semantic_id(DegenerationRuleAttribution._PREFIX, payload), **kwargs
            ))
        direct = tuple(x.rule_code for x in attributions if x.triggered and x.evidence_kind is DegenerationEvidenceKind.VARIANT_DIRECT)
        propagated = tuple(x.rule_code for x in attributions if x.triggered and x.evidence_kind is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION)
        descriptive = "DEGENERATED" if direct else "SENSITIVE" if summary.non_zero_validation_delta_count else "NOT_DEGENERATED"
        kwargs = {
            "variant_id": summary.variant_id,
            "formal_status": summary.status.value,
            "attributions": tuple(attributions),
            "direct_triggered_rule_codes": direct,
            "global_propagated_rule_codes": propagated,
            "descriptive_status_without_global_propagation": descriptive,
            "schema_version": 1,
        }
        payload = {**kwargs, "attributions": [x.to_dict() for x in attributions], "direct_triggered_rule_codes": list(direct), "global_propagated_rule_codes": list(propagated)}
        results.append(VariantDegenerationAttribution(
            variant_attribution_id=semantic_id(VariantDegenerationAttribution._PREFIX, payload), **kwargs
        ))
    return tuple(results)


__all__ = ["attribute_degeneration"]
