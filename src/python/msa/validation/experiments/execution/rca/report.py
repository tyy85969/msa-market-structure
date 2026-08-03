"""Aggregate bounded diagnostics into the immutable RCA report."""

from __future__ import annotations

from ...identity import semantic_id
from .contracts import (
    C008CBRCAManifest,
    C008CBRootCauseReport,
    CutoffRewriteLayer,
    DegenerationEvidenceKind,
    DeterminismDiagnosticKind,
    RootCauseDisposition,
)
from .degeneration import attribute_degeneration


_GAPS = (
    "Existing ExperimentDeterminismComparison compares normal context with altered Decimal context and has no independent normal-versus-normal repeat",
    "Existing Gate evaluator uses that one comparison set for both DETERMINISTIC_REPEAT and DECIMAL_CONTEXT_INDEPENDENCE",
    "Existing FUTURE_PREFIX_REWRITE degeneration evidence is one global Baseline fixed-cutoff aggregate propagated to all 25 Variants",
)

_RECOMMENDATIONS = (
    "Use a separately authorized change to split formal same-context and Decimal-context Gate evidence",
    "Use a separately authorized change to make degeneration evidence subject-bound instead of globally propagated",
    "Do not recalculate formal Gates or change BLOCKED_BEFORE_OOS until the project owner reviews this RCA",
)


def build_root_cause_report(manifest, b_report, determinism, cutoff):
    degeneration = attribute_degeneration(b_report)
    same = tuple(x for x in determinism if x.diagnostic_kind is DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT)
    decimal = tuple(x for x in determinism if x.diagnostic_kind is DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION)
    core_problem = (
        any(not x.full_payload_equal for x in same)
        or any(x.core_semantic_mismatch for x in decimal)
        or any(x.final_layer in (CutoffRewriteLayer.FRAME_BUNDLE, CutoffRewriteLayer.ACTIVE_BOX_LEDGER) for x in cutoff)
    )
    harness_problem = True
    disposition = RootCauseDisposition.MIXED_ROOT_CAUSE if core_problem and harness_problem else RootCauseDisposition.PROTECTED_CORE_REMEDIATION_REQUIRED if core_problem else RootCauseDisposition.HARNESS_CORRECTION_REQUIRED
    kwargs = {
        "rca_manifest_id": manifest.rca_manifest_id,
        "b_run_report_id": b_report.run_report_id,
        "original_stage_status": b_report.stage_status,
        "determinism_results": tuple(determinism),
        "cutoff_results": tuple(cutoff),
        "degeneration_attributions": degeneration,
        "same_context_mismatch_count": sum(not x.full_payload_equal for x in same),
        "decimal_context_mismatch_count": sum(not x.full_payload_equal for x in decimal),
        "core_semantic_mismatch_count": sum(x.core_semantic_mismatch for x in determinism),
        "core_identity_only_mismatch_count": sum(x.core_identity_only_mismatch for x in determinism),
        "audit_semantic_mismatch_count": sum(x.audit_semantic_mismatch for x in determinism),
        "audit_identity_or_provenance_mismatch_count": sum(x.audit_identity_or_provenance_mismatch for x in determinism),
        "metric_semantic_mismatch_count": sum(x.metric_semantic_mismatch for x in determinism),
        "metric_identity_or_provenance_mismatch_count": sum(x.metric_identity_or_provenance_mismatch for x in determinism),
        "case_derived_only_mismatch_count": sum(x.case_derived_only_mismatch for x in determinism),
        "prefix_source_invalid_count": sum(not x.source_prefix_valid for x in cutoff),
        "frame_bundle_rewrite_count": sum(not x.frame_bundles_equal for x in cutoff),
        "active_box_ledger_rewrite_count": sum(not x.active_box_events_equal or not x.frozen_boxes_equal for x in cutoff),
        "metric_semantic_rewrite_count": sum(not x.metric_semantic_equal for x in cutoff),
        "identity_only_cutoff_difference_count": sum(x.identity_only_difference for x in cutoff),
        "harness_contract_mismatch_count": sum(x.final_layer is CutoffRewriteLayer.HARNESS_CONTRACT for x in cutoff),
        "direct_degeneration_rule_count": sum(len(x.direct_triggered_rule_codes) for x in degeneration),
        "global_baseline_propagation_count": sum(len(x.global_propagated_rule_codes) for x in degeneration),
        "disposition": disposition,
        "admitted_attribution_gaps": _GAPS,
        "recommendations": _RECOMMENDATIONS,
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
        key: value.value if hasattr(value, "value") else [x.to_dict() for x in value]
        if key in ("determinism_results", "cutoff_results", "degeneration_attributions")
        else list(value) if isinstance(value, tuple) else value
        for key, value in kwargs.items()
    }
    return C008CBRootCauseReport(
        root_cause_report_id=semantic_id(C008CBRootCauseReport._PREFIX, payload), **kwargs
    )


__all__ = ["build_root_cause_report"]
