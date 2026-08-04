"""Derive the immutable RCA report from nested diagnostics and frozen B facts."""

from __future__ import annotations

from ...identity import semantic_id
from .contracts import (
    C008CBRootCauseReport,
    CutoffRewriteLayer,
    DegenerationEvidenceKind,
    DeterminismDiagnosticKind,
    RootCauseDisposition,
    RootCauseSubject,
)
from .degeneration import attribute_degeneration


_GAP_BY_SUBJECT = {
    RootCauseSubject.DETERMINISM_GATE_CONFLATION: (
        "The frozen DETERMINISTIC_REPEAT and DECIMAL_CONTEXT_INDEPENDENCE Gates bind the same altered-Decimal comparison evidence",
    ),
    RootCauseSubject.DEGENERATION_GLOBAL_PROPAGATION: (
        "FUTURE_PREFIX_REWRITE is a global Baseline fixed-cutoff aggregate propagated to every Variant rather than direct per-Variant evidence",
    ),
    RootCauseSubject.PREFIX_HARNESS_ERROR: (
        "At least one selected prefix/comparison diagnostic could not establish a valid harness boundary",
    ),
}

_RECOMMENDATION_BY_SUBJECT = {
    RootCauseSubject.DETERMINISM_GATE_CONFLATION: (
        "Use a separately authorized change to split formal same-context and Decimal-context Gate evidence",
    ),
    RootCauseSubject.DEGENERATION_GLOBAL_PROPAGATION: (
        "Use a separately authorized change to make degeneration evidence subject-bound instead of globally propagated",
    ),
    RootCauseSubject.CORE_DECIMAL_CONTEXT_DEPENDENCE: (
        "Independently diagnose and remediate protected Core Decimal arithmetic context dependence under separate authorization",
    ),
    RootCauseSubject.METRIC_FIXED_CUTOFF_SEMANTICS: (
        "Independently diagnose and remediate protected Metric fixed-cutoff semantic divergence under separate authorization",
    ),
    RootCauseSubject.SAME_CONTEXT_NONDETERMINISM: (
        "Independently diagnose same-context nondeterminism before recalculating any formal Gate",
    ),
    RootCauseSubject.FRAME_OR_LEDGER_FUTURE_REWRITE: (
        "Independently diagnose protected Frame or Active Box Ledger prefix rewrite under separate authorization",
    ),
    RootCauseSubject.PREFIX_HARNESS_ERROR: (
        "Correct the bounded prefix/comparator harness under separate authorization before relying on its attribution",
    ),
}

_FROZEN_BOUNDARY_RECOMMENDATION = (
    "Do not recalculate formal Gates or change BLOCKED_BEFORE_OOS until the project owner reviews this RCA"
)


def _gate_conflated(b_report: object) -> bool:
    gates = {item.gate_code: item for item in b_report.gate_results}
    repeat = gates.get("DETERMINISTIC_REPEAT")
    decimal = gates.get("DECIMAL_CONTEXT_INDEPENDENCE")
    return bool(
        repeat is not None
        and decimal is not None
        and repeat.evidence_ids == decimal.evidence_ids
        and repeat.evidence_payload_digest == decimal.evidence_payload_digest
        and b_report.determinism_comparisons
        and all(
            item.decimal_context_changed
            for item in b_report.determinism_comparisons
        )
    )


def derive_root_cause(
    b_report: object,
    determinism: tuple[object, ...],
    cutoff: tuple[object, ...],
    degeneration: tuple[object, ...],
) -> tuple[
    tuple[RootCauseSubject, ...],
    RootCauseDisposition,
    tuple[str, ...],
    tuple[str, ...],
]:
    """Recompute subjects, disposition, gaps, and recommendations."""

    same = tuple(
        item
        for item in determinism
        if item.diagnostic_kind is DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT
    )
    decimal = tuple(
        item
        for item in determinism
        if item.diagnostic_kind
        is DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION
    )
    found: set[RootCauseSubject] = set()
    if _gate_conflated(b_report):
        found.add(RootCauseSubject.DETERMINISM_GATE_CONFLATION)
    if any(
        attribution.evidence_kind
        is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
        for variant in degeneration
        for attribution in variant.attributions
    ):
        found.add(RootCauseSubject.DEGENERATION_GLOBAL_PROPAGATION)
    if any(item.core_semantic_mismatch for item in decimal):
        found.add(RootCauseSubject.CORE_DECIMAL_CONTEXT_DEPENDENCE)
    if any(not item.metric_semantic_equal for item in cutoff):
        found.add(RootCauseSubject.METRIC_FIXED_CUTOFF_SEMANTICS)
    if any(not item.full_payload_equal for item in same):
        found.add(RootCauseSubject.SAME_CONTEXT_NONDETERMINISM)
    if any(
        not item.frame_bundles_equal
        or not item.active_box_events_equal
        or not item.frozen_boxes_equal
        for item in cutoff
    ):
        found.add(RootCauseSubject.FRAME_OR_LEDGER_FUTURE_REWRITE)
    if any(
        not item.source_prefix_valid
        or not item.processing_schedule_equal
        or not item.shared_asof_audit_passed
        or not item.prefix_audit_passed
        or item.final_layer is CutoffRewriteLayer.HARNESS_CONTRACT
        for item in cutoff
    ):
        found.add(RootCauseSubject.PREFIX_HARNESS_ERROR)
    subjects = tuple(item for item in RootCauseSubject if item in found)
    harness = bool(
        found
        & {
            RootCauseSubject.DETERMINISM_GATE_CONFLATION,
            RootCauseSubject.DEGENERATION_GLOBAL_PROPAGATION,
            RootCauseSubject.PREFIX_HARNESS_ERROR,
        }
    )
    protected = bool(
        found
        & {
            RootCauseSubject.CORE_DECIMAL_CONTEXT_DEPENDENCE,
            RootCauseSubject.METRIC_FIXED_CUTOFF_SEMANTICS,
            RootCauseSubject.SAME_CONTEXT_NONDETERMINISM,
            RootCauseSubject.FRAME_OR_LEDGER_FUTURE_REWRITE,
        }
    )
    unreliable = (
        len(same) != 40
        or len(decimal) != 40
        or len(cutoff) != 15
        or len(degeneration) != 25
    )
    disposition = (
        RootCauseDisposition.INSUFFICIENT_EVIDENCE
        if unreliable
        else RootCauseDisposition.MIXED_ROOT_CAUSE
        if harness and protected
        else RootCauseDisposition.HARNESS_CORRECTION_REQUIRED
        if harness
        else RootCauseDisposition.PROTECTED_CORE_REMEDIATION_REQUIRED
        if protected
        else RootCauseDisposition.NO_ROOT_CAUSE_FOUND
    )
    gaps = tuple(
        text
        for subject in subjects
        for text in _GAP_BY_SUBJECT.get(subject, ())
    )
    recommendations = tuple(
        text
        for subject in subjects
        for text in _RECOMMENDATION_BY_SUBJECT[subject]
    )
    if disposition is RootCauseDisposition.INSUFFICIENT_EVIDENCE:
        recommendations += (
            "Collect the missing bounded diagnostic evidence before assigning remediation",
        )
    recommendations += (_FROZEN_BOUNDARY_RECOMMENDATION,)
    return subjects, disposition, gaps, recommendations


def build_root_cause_report(manifest, b_report, determinism, cutoff):
    determinism = tuple(determinism)
    cutoff = tuple(cutoff)
    degeneration = attribute_degeneration(b_report)
    same = tuple(
        item
        for item in determinism
        if item.diagnostic_kind is DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT
    )
    decimal = tuple(
        item
        for item in determinism
        if item.diagnostic_kind
        is DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION
    )
    subjects, disposition, gaps, recommendations = derive_root_cause(
        b_report, determinism, cutoff, degeneration
    )
    all_attributions = tuple(
        attribution
        for variant in degeneration
        for attribution in variant.attributions
    )
    kwargs = {
        "rca_manifest_id": manifest.rca_manifest_id,
        "b_run_report_id": b_report.run_report_id,
        "original_stage_status": b_report.stage_status,
        "determinism_results": determinism,
        "cutoff_results": cutoff,
        "degeneration_attributions": degeneration,
        "same_context_mismatch_count": sum(
            not item.full_payload_equal for item in same
        ),
        "decimal_context_mismatch_count": sum(
            not item.full_payload_equal for item in decimal
        ),
        "core_semantic_mismatch_count": sum(
            item.core_semantic_mismatch for item in determinism
        ),
        "core_identity_only_mismatch_count": sum(
            item.core_identity_only_mismatch for item in determinism
        ),
        "audit_semantic_mismatch_count": sum(
            item.audit_semantic_mismatch for item in determinism
        ),
        "audit_identity_or_provenance_mismatch_count": sum(
            item.audit_identity_or_provenance_mismatch
            for item in determinism
        ),
        "metric_semantic_mismatch_count": sum(
            item.metric_semantic_mismatch for item in determinism
        ),
        "metric_identity_or_provenance_mismatch_count": sum(
            item.metric_identity_or_provenance_mismatch
            for item in determinism
        ),
        "case_derived_only_mismatch_count": sum(
            item.case_derived_only_mismatch for item in determinism
        ),
        "prefix_source_invalid_count": sum(
            not item.source_prefix_valid for item in cutoff
        ),
        "frame_bundle_rewrite_count": sum(
            not item.frame_bundles_equal for item in cutoff
        ),
        "active_box_ledger_rewrite_count": sum(
            not item.active_box_events_equal or not item.frozen_boxes_equal
            for item in cutoff
        ),
        "metric_semantic_rewrite_count": sum(
            not item.metric_semantic_equal for item in cutoff
        ),
        "identity_only_cutoff_difference_count": sum(
            item.identity_only_difference for item in cutoff
        ),
        "harness_contract_mismatch_count": sum(
            item.final_layer is CutoffRewriteLayer.HARNESS_CONTRACT
            for item in cutoff
        ),
        "variant_direct_evidence_count": sum(
            item.evidence_kind is DegenerationEvidenceKind.VARIANT_DIRECT
            for item in all_attributions
        ),
        "global_propagation_evidence_count": sum(
            item.evidence_kind
            is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
            for item in all_attributions
        ),
        "direct_degeneration_rule_count": sum(
            len(item.direct_triggered_rule_codes) for item in degeneration
        ),
        "global_baseline_propagation_count": sum(
            len(item.global_propagated_rule_codes) for item in degeneration
        ),
        "shared_static_evidence_count": sum(
            item.evidence_kind
            is DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE
            for item in all_attributions
        ),
        "insufficient_evidence_count": sum(
            item.evidence_kind
            is DegenerationEvidenceKind.INSUFFICIENT_EVIDENCE
            for item in all_attributions
        ),
        "root_cause_subjects": subjects,
        "disposition": disposition,
        "admitted_attribution_gaps": gaps,
        "recommendations": recommendations,
        "original_b_evidence_modified": False,
        "gate_results_modified": False,
        "stage_status_modified": False,
        "protected_source_modified": False,
        "oos_executed": False,
        "full_matrix_reexecuted": False,
        "all_cutoffs_reexecuted": False,
        "schema_version": 1,
    }
    payload = {
        key: value.value
        if hasattr(value, "value")
        else [item.to_dict() for item in value]
        if key
        in (
            "determinism_results",
            "cutoff_results",
            "degeneration_attributions",
        )
        else [item.value for item in value]
        if key == "root_cause_subjects"
        else list(value)
        if isinstance(value, tuple)
        else value
        for key, value in kwargs.items()
    }
    return C008CBRootCauseReport(
        root_cause_report_id=semantic_id(
            C008CBRootCauseReport._PREFIX, payload
        ),
        **kwargs,
    )


__all__ = ["build_root_cause_report", "derive_root_cause"]
