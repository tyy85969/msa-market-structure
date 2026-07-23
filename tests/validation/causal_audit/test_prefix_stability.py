from copy import deepcopy

from msa.validation import CausalAuditCode

from .fixtures import auditor, valid_prefix_pair


def test_future_append_preserves_complete_old_prefix() -> None:
    prefix, extended = valid_prefix_pair()
    report = auditor().compare_prefix(prefix, extended)
    assert report.passed


def test_historical_bundle_rewrite_fails_prefix_audit() -> None:
    prefix, extended = valid_prefix_pair()
    mutated = deepcopy(extended)
    evidence = mutated.frame_bundles[0].resonance_frame.evidence[0]
    object.__setattr__(evidence, "touch_count", evidence.touch_count + 1)
    report = auditor().compare_prefix(prefix, mutated)
    assert not report.passed
    assert CausalAuditCode.PREFIX_REWRITE in {
        item.code for item in report.findings
    }
