from copy import deepcopy

from msa.validation import CausalAuditCode

from .fixtures import auditor, valid_run


def test_batch_replay_requires_complete_payload_equality() -> None:
    run = valid_run()
    report = auditor().compare_batch_replay(run, deepcopy(run))
    assert report.passed


def test_one_nested_report_field_fails_complete_comparison() -> None:
    batch = valid_run()
    replayed = deepcopy(batch)
    object.__setattr__(
        replayed.report,
        "zone_count",
        replayed.report.zone_count + 1,
    )
    report = auditor().compare_batch_replay(batch, replayed)
    assert not report.passed
    assert CausalAuditCode.BATCH_REPLAY_MISMATCH in {
        item.code for item in report.findings
    }
