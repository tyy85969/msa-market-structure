from decimal import Decimal

from msa.validation import ValidationMetricName

from .fixtures import base_report


def test_initial_box_is_zero_and_pair_change_adds_one_churn() -> None:
    report = base_report()
    values = tuple(
        item.value
        for item in report.observations
        if item.metric_name is ValidationMetricName.BOX_CHURN
    )
    assert values == (Decimal("0"), Decimal("1"))
    aggregate = next(
        item
        for item in report.aggregates
        if item.metric_name is ValidationMetricName.BOX_CHURN
    )
    assert aggregate.value == Decimal("1")
    assert aggregate.denominator is None
