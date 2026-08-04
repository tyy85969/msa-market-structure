from msa.validation.experiments.execution import ReplayComparisonStatus


def test_replay_evidence_preserves_exact_frozen_sample_sets(
    compact_components,
) -> None:
    comparisons = compact_components["replay"]
    baseline = tuple(item for item in comparisons if item.scope == "BASELINE")
    variants = tuple(item for item in comparisons if item.scope == "VARIANT")
    assert len(baseline) == 15
    assert len(variants) == 125
    assert len({item.replay_sample_id for item in comparisons}) == 140
    assert all(
        item.status is ReplayComparisonStatus.EXECUTION_FAILED
        for item in comparisons
    )
