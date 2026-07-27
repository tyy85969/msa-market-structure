from __future__ import annotations

from msa.validation import MetricEventKind, ValidationMetricName

from .fixtures import direction_report, touch_report


def touch_observations():
    report = touch_report()
    return {
        name: tuple(
            item
            for item in report.observations
            if item.metric_name is name
        )
        for name in (
            ValidationMetricName.MFE,
            ValidationMetricName.MAE,
            ValidationMetricName.FIRST_TOUCH_REACTION,
        )
    }


def direction_observations():
    report = direction_report()
    return {
        name: tuple(
            item
            for item in report.observations
            if item.metric_name is name
        )
        for name in (
            ValidationMetricName.FALSE_TURN_RATE,
            ValidationMetricName.CONTINUED_BREAK_RATE,
            ValidationMetricName.TREND_CAPTURE_RATIO,
        )
    }


def event_ids(report, kind: MetricEventKind) -> tuple[str, ...]:
    return tuple(
        item.metric_event_id
        for item in report.events
        if item.kind is kind
    )
