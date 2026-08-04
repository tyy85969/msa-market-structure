from msa.validation.experiments.execution import ExperimentCaseResult


def test_failed_case_result_round_trips_without_fake_payload(
    compact_components,
) -> None:
    result = compact_components["case_results"][0]
    restored = ExperimentCaseResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.run_id is None
    assert restored.audit_report_id is None
    assert restored.metric_report_id is None
    assert restored.aggregates == ()
