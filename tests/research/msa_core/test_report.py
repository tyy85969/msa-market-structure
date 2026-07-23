from dataclasses import replace

import pytest

from msa.research.msa_core import MSACoreIntegrationError

from .fixtures import batch_run


def test_report_recomputes_authoritative_counts() -> None:
    run = batch_run()
    report = run.report
    assert report.frame_count == len(run.resonance_history.frames)
    assert report.evidence_count == sum(
        len(item.evidence) for item in run.resonance_history.frames
    )
    assert report.zone_count == sum(
        len(item.zones) for item in run.score_history.frames
    )
    assert report.created_event_count == 2
    assert report.frozen_event_count == report.frozen_box_count == 1
    assert report.warnings == report.errors == ()


def test_report_contains_no_trading_metrics() -> None:
    keys = set(batch_run().report.to_dict())
    assert not keys.intersection(
        {
            "profit",
            "win_rate",
            "return",
            "buy",
            "sell",
            "entry",
            "exit",
            "stop",
            "target",
        }
    )


def test_run_rejects_internally_resigned_report() -> None:
    run = batch_run()
    forged = replace(
        run.report,
        evidence_count=run.report.evidence_count + 1,
    )
    with pytest.raises(MSACoreIntegrationError):
        replace(run, report=forged)
