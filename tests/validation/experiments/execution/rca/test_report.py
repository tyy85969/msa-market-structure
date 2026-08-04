from msa.validation.experiments.execution.contracts import C008CBStageStatus
from msa.validation.experiments.execution.rca.contracts import RootCauseDisposition


def test_report_enums_keep_blocked_stage_and_bounded_dispositions():
    assert C008CBStageStatus.BLOCKED_BEFORE_OOS.value == "BLOCKED_BEFORE_OOS"
    assert {x.value for x in RootCauseDisposition} == {
        "HARNESS_CORRECTION_REQUIRED",
        "PROTECTED_CORE_REMEDIATION_REQUIRED",
        "MIXED_ROOT_CAUSE",
        "NO_ROOT_CAUSE_FOUND",
        "INSUFFICIENT_EVIDENCE",
    }
