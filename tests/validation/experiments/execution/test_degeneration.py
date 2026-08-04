from msa.validation.experiments.execution import DegenerationStatus


def test_all_ten_frozen_rules_are_evaluated_per_variant(
    compact_components,
) -> None:
    summaries = compact_components["degeneration"]
    assert len(summaries) == 25
    assert all(len(item.findings) == 10 for item in summaries)
    assert all(
        item.status is DegenerationStatus.DEGENERATED
        for item in summaries
    )
    assert all(
        "PIPELINE_EXECUTION_FAILURE" in item.triggered_rule_codes
        for item in summaries
    )
