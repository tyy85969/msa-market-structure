from copy import deepcopy

from msa.validation import CausalAuditCode

from .fixtures import auditor, valid_run


def test_public_event_and_frozen_ledgers_pass() -> None:
    assert auditor().audit_run(valid_run()).passed


def test_rewritten_event_ledger_fails() -> None:
    run = deepcopy(valid_run())
    object.__setattr__(
        run.active_box_history,
        "events",
        run.active_box_history.events[1:],
    )
    report = auditor().audit_run(run)
    assert CausalAuditCode.EVENT_LEDGER_MISMATCH in {
        item.code for item in report.findings
    }


def test_rewritten_frozen_ledger_fails() -> None:
    run = deepcopy(valid_run())
    object.__setattr__(run.active_box_history, "frozen_boxes", ())
    report = auditor().audit_run(run)
    assert CausalAuditCode.FROZEN_LEDGER_MISMATCH in {
        item.code for item in report.findings
    }
