from __future__ import annotations

from copy import deepcopy

import pytest

from msa.validation import (
    CausalAuditReport,
    CausalAuditor,
    MSAValidationError,
)
from msa.validation.identity import semantic_id

from .fixtures import (
    valid_prefix_pair,
    valid_run,
    valid_shared_asof_pair,
)
from .mutations import mutation_report


def _resign_check(payload: dict[str, object]) -> None:
    identity = {
        key: value
        for key, value in payload.items()
        if key != "check_result_id"
    }
    payload["check_result_id"] = semantic_id(
        "causal-audit-check-v1-", identity
    )


def _resign_report(payload: dict[str, object]) -> None:
    identity = {
        key: value
        for key, value in payload.items()
        if key != "audit_report_id"
    }
    payload["audit_report_id"] = semantic_id(
        "causal-audit-report-v1-", identity
    )


def _reject_resigned(payload: dict[str, object]) -> None:
    _resign_report(payload)
    with pytest.raises(MSAValidationError):
        CausalAuditReport.from_dict(payload)


def _passing_payload() -> dict[str, object]:
    return deepcopy(CausalAuditor().audit_run(valid_run()).to_dict())


@pytest.mark.parametrize(
    "attack",
    ("delete", "only_pass", "repeat", "reorder"),
)
def test_resigned_required_check_set_attacks_are_rejected(
    attack: str,
) -> None:
    payload = _passing_payload()
    checks = payload["executed_checks"]
    assert isinstance(checks, list)
    if attack == "delete":
        del checks[3]
    elif attack == "only_pass":
        checks[:] = checks[:1]
    elif attack == "repeat":
        checks.insert(2, deepcopy(checks[1]))
    else:
        checks[0], checks[1] = checks[1], checks[0]
    _reject_resigned(payload)


def test_resigned_arbitrary_check_name_is_rejected() -> None:
    payload = _passing_payload()
    checks = payload["executed_checks"]
    assert isinstance(checks, list)
    check = checks[0]
    assert isinstance(check, dict)
    check["check_name"] = "CALLER_DEFINED_CHECK"
    _resign_check(check)
    _reject_resigned(payload)


def test_resigned_finding_moved_to_wrong_check_is_rejected() -> None:
    report = mutation_report("future_evidence", CausalAuditor())
    payload = deepcopy(report.to_dict())
    findings = payload["findings"]
    checks = payload["executed_checks"]
    assert isinstance(findings, list) and isinstance(checks, list)
    finding = next(
        item
        for item in findings
        if item["code"] == "FUTURE_EVIDENCE"
    )
    source = next(
        item
        for item in checks
        if item["check_name"] == "FUTURE_EVIDENCE"
    )
    target = next(
        item
        for item in checks
        if item["check_name"] == "REPORT_COUNT_MISMATCH"
    )
    source["finding_ids"].remove(finding["finding_id"])
    source["passed"] = not source["finding_ids"]
    target["finding_ids"].append(finding["finding_id"])
    target["passed"] = False
    _resign_check(source)
    _resign_check(target)
    _reject_resigned(payload)


@pytest.mark.parametrize("attack", ("duplicate", "unreferenced"))
def test_resigned_finding_reference_attacks_are_rejected(
    attack: str,
) -> None:
    report = mutation_report("future_evidence", CausalAuditor())
    payload = deepcopy(report.to_dict())
    findings = payload["findings"]
    checks = payload["executed_checks"]
    assert isinstance(findings, list) and isinstance(checks, list)
    finding_id = next(
        item["finding_id"]
        for item in findings
        if item["code"] == "FUTURE_EVIDENCE"
    )
    owner = next(
        item
        for item in checks
        if finding_id in item["finding_ids"]
    )
    if attack == "unreferenced":
        owner["finding_ids"].remove(finding_id)
        owner["passed"] = not owner["finding_ids"]
        _resign_check(owner)
    else:
        target = next(
            item
            for item in checks
            if item["check_name"] == "REPORT_COUNT_MISMATCH"
        )
        target["finding_ids"].append(finding_id)
        target["passed"] = False
        _resign_check(target)
    _reject_resigned(payload)


@pytest.mark.parametrize("attack", ("assumptions", "entrypoint", "binding"))
def test_resigned_authority_metadata_attacks_are_rejected(
    attack: str,
) -> None:
    payload = _passing_payload()
    assumptions = payload["assumptions"]
    provenance = payload["provenance"]
    assert isinstance(assumptions, list)
    assert isinstance(provenance, list)
    if attack == "assumptions":
        assumptions[0] = "Caller supplied assumption"
    elif attack == "entrypoint":
        provenance[0] = "caller.audit"
    else:
        provenance[1] = "subject_run_id=forged-run"
    _reject_resigned(payload)


def _reports_by_kind() -> tuple[CausalAuditReport, ...]:
    auditor = CausalAuditor()
    run = valid_run()
    prefix, extended_prefix = valid_prefix_pair()
    baseline, extended_shared, cutoff = valid_shared_asof_pair()
    return (
        auditor.audit_run(run),
        auditor.compare_batch_replay(run, valid_run()),
        auditor.compare_prefix(prefix, extended_prefix),
        auditor.compare_shared_asof(
            baseline, extended_shared, cutoff
        ),
    )


@pytest.mark.parametrize("report_index", range(4))
def test_resigned_subject_id_attack_is_rejected_for_every_report_kind(
    report_index: int,
) -> None:
    payload = deepcopy(_reports_by_kind()[report_index].to_dict())
    subject_ids = payload["subject_ids"]
    assert isinstance(subject_ids, list)
    subject_ids[0] = "forged-subject-id"
    _reject_resigned(payload)


def test_resigned_subject_order_attack_is_rejected() -> None:
    prefix, extended = valid_prefix_pair()
    payload = deepcopy(
        CausalAuditor().compare_prefix(prefix, extended).to_dict()
    )
    subject_ids = payload["subject_ids"]
    assert isinstance(subject_ids, list)
    assert len(subject_ids) == 2
    subject_ids.reverse()
    _reject_resigned(payload)
