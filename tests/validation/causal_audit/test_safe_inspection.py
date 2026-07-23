from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from msa.validation import CausalAuditCode, CausalAuditor

from .fixtures import valid_run


@pytest.mark.parametrize(
    ("target", "value"),
    (
        ("run_id", None),
        ("run_id", []),
        ("run_id", {}),
        ("bundle_id", None),
        ("event_id", []),
        ("event_id", "x" * 10_000),
        ("box_key_id", []),
    ),
)
def test_illegal_object_ids_return_bounded_failed_reports(
    target: str,
    value: object,
) -> None:
    run = deepcopy(valid_run())
    if target == "run_id":
        subject = run
    elif target == "bundle_id":
        subject = run.frame_bundles[0]
    elif target == "event_id":
        subject = run.frame_bundles[0].selection_frame.emitted_events[0]
    else:
        subject = (
            run.frame_bundles[2]
            .selection_frame.active_box_snapshot
        )
    object.__setattr__(subject, target, value)
    if target == "bundle_id":
        object.__setattr__(
            run.frame_bundles[0].score_frame,
            "source_frame_id",
            "forged-source",
        )
    elif target == "event_id":
        object.__setattr__(
            subject,
            "event_confirm_time",
            run.processing_times[0] + timedelta(microseconds=1),
        )

    report = CausalAuditor().audit_run(run)

    assert not report.passed
    assert any(
        object_id.startswith("invalid-object-id-")
        for finding in report.findings
        for object_id in finding.object_ids
    ) or any(
        subject_id.startswith("invalid-object-id-")
        for subject_id in report.subject_ids
    )
    assert all(
        0 < len(object_id) <= 512
        for finding in report.findings
        for object_id in finding.object_ids
    )
    assert all(
        0 < len(fact.value) <= 512
        for finding in report.findings
        for fact in finding.facts
    )


def test_overlong_illegal_id_and_fact_are_normalized_without_repr() -> None:
    run = deepcopy(valid_run())
    overlong = "x" * 10_000
    score = run.frame_bundles[0].score_frame
    object.__setattr__(score, "source_frame_id", overlong)

    report = CausalAuditor().audit_run(run)

    assert not report.passed
    assert CausalAuditCode.SCORE_SOURCE_MISMATCH in {
        item.code for item in report.findings
    }
    assert overlong not in str(report.to_dict())
    assert all(
        len(fact.value) <= 512
        for finding in report.findings
        for fact in finding.facts
    )


@pytest.mark.parametrize(
    ("bundle_index", "event_name", "direction"),
    (
        (0, "CREATED", 1),
        (0, "CREATED", -1),
        (1, "FROZEN", 1),
        (1, "FROZEN", -1),
    ),
)
def test_every_event_result_snapshot_active_box_asof_is_audited(
    bundle_index: int,
    event_name: str,
    direction: int,
) -> None:
    run = deepcopy(valid_run())
    bundle = run.frame_bundles[bundle_index]
    event = next(
        item
        for item in bundle.selection_frame.emitted_events
        if item.event_type.value == event_name
    )
    detached = deepcopy(event.resulting_box_snapshot)
    object.__setattr__(
        detached.active_box,
        "as_of_time",
        bundle.as_of_time
        + direction * timedelta(microseconds=1),
    )
    object.__setattr__(
        event, "resulting_box_snapshot", detached
    )

    report = CausalAuditor().audit_run(run)

    assert not report.passed
    assert CausalAuditCode.ACTIVE_BOX_ASOF_MISMATCH in {
        item.code for item in report.findings
    }


def test_current_and_event_result_snapshots_are_independently_audited() -> None:
    run = deepcopy(valid_run())
    bundle = run.frame_bundles[0]
    current = bundle.selection_frame.active_box_snapshot
    event = bundle.selection_frame.emitted_events[0]
    detached = deepcopy(event.resulting_box_snapshot)
    object.__setattr__(
        current.active_box,
        "as_of_time",
        bundle.as_of_time - timedelta(microseconds=1),
    )
    object.__setattr__(
        detached.active_box,
        "as_of_time",
        bundle.as_of_time + timedelta(microseconds=1),
    )
    object.__setattr__(
        event, "resulting_box_snapshot", detached
    )

    report = CausalAuditor().audit_run(run)
    findings = tuple(
        item
        for item in report.findings
        if item.code is CausalAuditCode.ACTIVE_BOX_ASOF_MISMATCH
    )

    assert len(findings) >= 2
