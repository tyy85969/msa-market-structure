from copy import deepcopy

from msa.validation import CausalAuditCode

from .fixtures import auditor, valid_shared_asof_pair


def test_extra_asof_preserves_shared_bundles_before_cutoff() -> None:
    baseline, extended, cutoff = valid_shared_asof_pair()
    report = auditor().compare_shared_asof(baseline, extended, cutoff)
    assert report.passed


def test_extra_asof_cannot_rewrite_earlier_shared_bundle() -> None:
    baseline, extended, cutoff = valid_shared_asof_pair()
    mutated = deepcopy(extended)
    evidence = mutated.frame_bundles[0].resonance_frame.evidence[0]
    object.__setattr__(evidence, "touch_count", evidence.touch_count + 1)
    report = auditor().compare_shared_asof(baseline, mutated, cutoff)
    assert not report.passed
    assert CausalAuditCode.SHARED_ASOF_REWRITE in {
        item.code for item in report.findings
    }
