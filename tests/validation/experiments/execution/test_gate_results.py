from msa.validation.experiments.execution import GateEvaluationStatus


def test_all_27_gates_preserve_fail_partial_and_deferred_status(
    compact_components,
) -> None:
    results = {
        item.gate_code: item for item in compact_components["gates"]
    }
    assert len(results) == 27
    assert (
        results["ALL_CASES_MUST_EXECUTE"].status
        is GateEvaluationStatus.DEFERRED_TO_C008C_C
    )
    assert (
        results["OOS_SAMPLE_COVERAGE"].status
        is GateEvaluationStatus.DEFERRED_TO_C008C_C
    )
    assert (
        results["FREEZE_SOURCE_BOUND"].status
        is GateEvaluationStatus.DEFERRED_TO_C008C_C
    )
    assert (
        results["ALL_CORE_RUNS_MUST_AUDIT"].status
        is GateEvaluationStatus.FAIL
    )
    assert (
        results["NO_NEIGHBORHOOD_DEGENERATION"].status
        is GateEvaluationStatus.FAIL
    )
