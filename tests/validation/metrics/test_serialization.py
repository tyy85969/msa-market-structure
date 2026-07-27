import pytest

from msa.validation import (
    MetricEvaluationReport,
    MetricSerializationError,
)

from .fixtures import touch_report


def test_complete_report_strict_round_trip() -> None:
    report = touch_report()
    assert MetricEvaluationReport.from_dict(report.to_dict()) == report


@pytest.mark.parametrize(
    "path",
    ("report", "config", "formula", "event", "observation", "aggregate"),
)
def test_unknown_fields_fail_closed(path: str) -> None:
    payload = touch_report().to_dict()
    if path == "report":
        target = payload
    elif path == "config":
        target = payload["config_snapshot"]
    elif path == "formula":
        target = payload["formula_registry"][0]
    elif path == "event":
        target = payload["events"][0]
    elif path == "observation":
        target = payload["observations"][0]
    else:
        target = payload["aggregates"][0]
    target["unknown"] = True
    with pytest.raises(MetricSerializationError):
        MetricEvaluationReport.from_dict(payload)


def test_unknown_schema_fails_closed() -> None:
    payload = touch_report().to_dict()
    payload["schema_version"] = 99
    with pytest.raises(MetricSerializationError):
        MetricEvaluationReport.from_dict(payload)
