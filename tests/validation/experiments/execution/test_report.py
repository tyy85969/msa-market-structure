from msa.validation.experiments.execution import C008CBStageStatus


def test_hard_failure_blocks_before_oos(compact_components) -> None:
    report = compact_components["report"]
    assert report.stage_status is C008CBStageStatus.BLOCKED_BEFORE_OOS
    assert report.executed_pair_count == 390
    assert report.deferred_oos_pair_count == 130
    assert report.failed_case_count == 390
    payload = report.to_dict()
    for forbidden in (
        "winner",
        "leaderboard",
        "recommended_parameter",
        "trading",
    ):
        assert forbidden not in payload
