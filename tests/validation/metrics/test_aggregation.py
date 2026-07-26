from decimal import Decimal

from msa.validation import MetricAggregateStatus, ValidationMetricName

from .fixtures import touch_report


def test_report_always_contains_registry_ordered_ten_aggregates() -> None:
    report = touch_report()
    assert len(report.aggregates) == 10
    assert tuple(item.metric_name for item in report.aggregates) == tuple(
        item.metric_name for item in report.formula_registry
    )


def test_aggregate_counts_and_values_recompute_from_observations() -> None:
    report = touch_report()
    mfe = next(
        item
        for item in report.aggregates
        if item.metric_name is ValidationMetricName.MFE
    )
    assert mfe.status is MetricAggregateStatus.AVAILABLE
    assert mfe.eligible_count == mfe.matured_count == 2
    assert mfe.censored_count == mfe.unavailable_count == 0
    assert mfe.numerator == Decimal("49")
    assert mfe.denominator == Decimal("2")
    assert mfe.value == Decimal("24.5")
