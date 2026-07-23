from msa.validation import CausalAuditCode

from .fixtures import auditor, valid_run


def test_valid_single_run_passes_all_independent_checks() -> None:
    report = auditor().audit_run(valid_run())
    assert report.passed
    assert report.error_count == 0
    assert report.findings == ()
    assert {item.check_name for item in report.executed_checks} == {
        item.value
        for item in CausalAuditCode
        if item
        not in {
            CausalAuditCode.BATCH_REPLAY_MISMATCH,
            CausalAuditCode.PREFIX_REWRITE,
            CausalAuditCode.SHARED_ASOF_REWRITE,
        }
    }


def test_single_run_audit_does_not_mutate_subject() -> None:
    run = valid_run()
    before = run.to_dict()
    auditor().audit_run(run)
    assert run.to_dict() == before


def test_single_run_report_bounds_equal_subject_schedule() -> None:
    run = valid_run()
    report = auditor().audit_run(run)
    assert report.started_as_of_time == run.processing_times[0]
    assert report.ended_as_of_time == run.processing_times[-1]
