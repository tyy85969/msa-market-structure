from msa.validation.experiments.execution import MetricDeltaStatus


def test_all_3750_unavailable_deltas_remain_none(
    compact_components,
) -> None:
    summaries = compact_components["deltas"]
    deltas = tuple(
        item for summary in summaries for item in summary.metric_deltas
    )
    assert len(summaries) == 50
    assert len(deltas) == 3750
    assert all(
        item.delta_status is MetricDeltaStatus.BOTH_UNAVAILABLE
        for item in deltas
    )
    assert all(item.absolute_delta is None for item in deltas)
