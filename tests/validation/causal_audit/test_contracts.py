from dataclasses import FrozenInstanceError, fields, is_dataclass, replace

import pytest

from msa.validation import (
    AuditSeverity,
    CausalAuditCode,
    CausalAuditConfig,
    CausalAuditReport,
    CausalAuditor,
    ValidationInputError,
)

from .fixtures import valid_run


def test_auditor_is_frozen_slotted_and_has_only_config() -> None:
    value = CausalAuditor()
    assert is_dataclass(value)
    assert tuple(item.name for item in fields(value)) == ("config",)
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.config = CausalAuditConfig()  # type: ignore[misc]


def test_config_controls_warning_and_information_severity_explicitly() -> None:
    value = CausalAuditConfig(
        warning_codes=(CausalAuditCode.REPORT_COUNT_MISMATCH,),
        informational_codes=(CausalAuditCode.UNSUPPORTED_TRADING_FIELD,),
    )
    assert (
        value.severity_for(CausalAuditCode.REPORT_COUNT_MISMATCH)
        is AuditSeverity.WARNING
    )
    assert (
        value.severity_for(CausalAuditCode.UNSUPPORTED_TRADING_FIELD)
        is AuditSeverity.INFORMATIONAL
    )
    assert (
        value.severity_for(CausalAuditCode.FUTURE_EVIDENCE)
        is AuditSeverity.ERROR
    )


def test_report_is_strict_round_trippable() -> None:
    report = CausalAuditor().audit_run(valid_run())
    assert CausalAuditReport.from_dict(report.to_dict()) == report


def test_report_identity_cannot_be_resigned_by_caller() -> None:
    report = CausalAuditor().audit_run(valid_run())
    with pytest.raises(ValidationInputError):
        replace(report, audit_report_id="causal-audit-report-v1-" + "0" * 64)


def test_contract_fields_do_not_expose_mutable_lists_or_dicts() -> None:
    report = CausalAuditor().audit_run(valid_run())
    values = tuple(getattr(report, item.name) for item in fields(report))
    assert not any(isinstance(item, (list, dict)) for item in values)
