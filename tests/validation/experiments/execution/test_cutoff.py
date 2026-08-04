from msa.validation.experiments.execution import FixedCutoffStatus


def test_cutoff_evidence_never_contains_oos_case(
    compact_components,
) -> None:
    comparisons = compact_components["cutoff"]
    assert len(comparisons) == 15
    assert all(item.seed != 3 for item in comparisons)
    assert all(
        item.status is FixedCutoffStatus.EXECUTION_FAILED
        for item in comparisons
    )
