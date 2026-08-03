from msa.validation.experiments.execution.rca.contracts import DegenerationEvidenceKind
from msa.validation.experiments.execution.rca.degeneration import attribute_degeneration


def test_global_rewrite_does_not_masquerade_as_variant_direct(b_report):
    results = attribute_degeneration(b_report)
    assert len(results) == 25
    for result in results:
        future = next(x for x in result.attributions if x.rule_code == "FUTURE_PREFIX_REWRITE")
        assert future.evidence_kind is DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
        assert future.shared_baseline_evidence and not future.variant_specific


def test_descriptive_projection_does_not_change_formal_status(b_report):
    results = attribute_degeneration(b_report)
    assert all(x.formal_status == "DEGENERATED" for x in results)
    assert all("FUTURE_PREFIX_REWRITE" in x.global_propagated_rule_codes for x in results)
