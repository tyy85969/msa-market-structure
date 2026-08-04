from types import SimpleNamespace

from msa.validation.experiments.execution.rca.contracts import (
    DegenerationEvidenceKind,
)
from msa.validation.experiments.execution.rca.degeneration import (
    attribute_degeneration,
)


def test_frozen_report_maps_global_static_and_direct_evidence(b_report):
    results = attribute_degeneration(b_report)
    assert len(results) == 25
    kinds = {
        item.evidence_kind
        for result in results
        for item in result.attributions
    }
    assert DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION in kinds
    assert DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE in kinds
    assert DegenerationEvidenceKind.VARIANT_DIRECT in kinds
    for result in results:
        future = next(
            item
            for item in result.attributions
            if item.rule_code == "FUTURE_PREFIX_REWRITE"
        )
        assert future.shared_baseline_evidence
        assert not future.variant_specific
        config = next(
            item
            for item in result.attributions
            if item.rule_code == "INVALID_OR_REPAIRED_CONFIG"
        )
        assert config.evidence_kind is DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE
        assert not config.variant_specific and not config.shared_baseline_evidence


def test_insufficient_status_overrides_rule_family_behaviorally():
    status = lambda value: SimpleNamespace(value=value)
    findings = (
        SimpleNamespace(
            degeneration_finding_id="finding-direct",
            rule_code="PIPELINE_EXECUTION_FAILURE",
            triggered=False,
            status=status("NOT_DEGENERATED"),
        ),
        SimpleNamespace(
            degeneration_finding_id="finding-global",
            rule_code="FUTURE_PREFIX_REWRITE",
            triggered=True,
            status=status("DEGENERATED"),
        ),
        SimpleNamespace(
            degeneration_finding_id="finding-static",
            rule_code="INVALID_OR_REPAIRED_CONFIG",
            triggered=False,
            status=status("NOT_DEGENERATED"),
        ),
        SimpleNamespace(
            degeneration_finding_id="finding-insufficient",
            rule_code="BOX_EPISODE_COLLAPSE",
            triggered=False,
            status=status("INSUFFICIENT_EVIDENCE"),
        ),
    )
    report = SimpleNamespace(
        execution_manifest_id="manifest-a",
        fixed_cutoff_comparisons=(
            SimpleNamespace(fixed_cutoff_comparison_id="cutoff-a"),
        ),
        degeneration_summaries=(
            SimpleNamespace(
                variant_id="variant-a",
                status=status("DEGENERATED"),
                findings=findings,
                non_zero_validation_delta_count=0,
            ),
        ),
    )
    result = attribute_degeneration(report)[0]
    by_rule = {item.rule_code: item for item in result.attributions}
    assert by_rule["PIPELINE_EXECUTION_FAILURE"].evidence_kind is DegenerationEvidenceKind.VARIANT_DIRECT
    assert by_rule["FUTURE_PREFIX_REWRITE"].evidence_kind is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
    assert by_rule["INVALID_OR_REPAIRED_CONFIG"].evidence_kind is DegenerationEvidenceKind.SHARED_STATIC_EVIDENCE
    insufficient = by_rule["BOX_EPISODE_COLLAPSE"]
    assert insufficient.evidence_kind is DegenerationEvidenceKind.INSUFFICIENT_EVIDENCE
    assert insufficient.evidence_direct_subject == "INSUFFICIENT_VARIANT_EVIDENCE"
