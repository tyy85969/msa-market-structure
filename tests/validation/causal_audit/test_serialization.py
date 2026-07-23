from copy import deepcopy

import pytest

from msa.validation import (
    AuditSeverity,
    CausalAuditConfig,
    CausalAuditReport,
    MetricDefinition,
    SyntheticScenarioDescriptor,
    ValidationSerializationError,
    default_metric_registry,
)

from .fixtures import auditor, valid_run
from .scenarios import all_descriptors


@pytest.mark.parametrize(
    "value",
    [
        CausalAuditConfig(),
        *default_metric_registry(),
        *all_descriptors(),
    ],
)
def test_public_contracts_strictly_round_trip(value) -> None:
    assert type(value).from_dict(value.to_dict()) == value


@pytest.mark.parametrize(
    "value",
    [
        CausalAuditConfig(),
        default_metric_registry()[0],
        all_descriptors()[0],
        auditor().audit_run(valid_run()),
    ],
)
def test_unknown_fields_and_unknown_schema_are_rejected(value) -> None:
    payload = value.to_dict()
    unknown = deepcopy(payload)
    unknown["unknown"] = True
    with pytest.raises(ValidationSerializationError):
        type(value).from_dict(unknown)
    wrong_schema = deepcopy(payload)
    wrong_schema["schema_version"] = 2
    with pytest.raises(ValidationSerializationError):
        type(value).from_dict(wrong_schema)


def test_enums_have_strict_versioned_serialization() -> None:
    assert AuditSeverity.from_dict(AuditSeverity.ERROR.to_dict()) is (
        AuditSeverity.ERROR
    )
    with pytest.raises(ValidationSerializationError):
        AuditSeverity.from_dict({"schema_version": 1, "value": "UNKNOWN"})


def test_report_full_payload_round_trip() -> None:
    report = auditor().audit_run(valid_run())
    assert CausalAuditReport.from_dict(report.to_dict()).to_dict() == (
        report.to_dict()
    )
