"""Complete-payload causal comparisons for formal MSA Core Runs."""

from __future__ import annotations

from datetime import datetime

from msa.research.msa_core import MSACoreRun

from .causal_audit import (
    _RUN_CODES,
    CausalAuditor,
    _fact,
    _finding,
    _payload,
    _report,
    _run_bounds,
)
from .contracts import (
    CausalAuditCode,
    CausalAuditConfig,
    CausalAuditKind,
    CausalAuditReport,
)
from .errors import (
    ValidationComparisonError,
    ValidationInputError,
)
from .identity import digest


def _runs(
    left: object, right: object
) -> tuple[MSACoreRun, MSACoreRun]:
    if not isinstance(left, MSACoreRun) or not isinstance(right, MSACoreRun):
        raise ValidationInputError(
            "comparison inputs must both be MSACoreRun"
        )
    return left, right


def _codes(extra: CausalAuditCode) -> tuple[CausalAuditCode, ...]:
    return tuple(dict.fromkeys((*_RUN_CODES, extra)))


def _bounds(
    left: MSACoreRun, right: MSACoreRun
) -> tuple[datetime, datetime]:
    left_start, left_end = _run_bounds(left)
    right_start, right_end = _run_bounds(right)
    return min(left_start, right_start), max(left_end, right_end)


def _child_findings(
    auditor: CausalAuditor, left: MSACoreRun, right: MSACoreRun
) -> list:
    return [
        *auditor.audit_run(left).findings,
        *auditor.audit_run(right).findings,
    ]


def compare_batch_replay(
    auditor: CausalAuditor,
    batch_run: MSACoreRun,
    replay_run: MSACoreRun,
) -> CausalAuditReport:
    batch, replayed = _runs(batch_run, replay_run)
    findings = _child_findings(auditor, batch, replayed)
    batch_payload = _payload(batch)
    replay_payload = _payload(replayed)
    if (
        batch_payload is None
        or replay_payload is None
        or batch_payload != replay_payload
    ):
        findings.append(
            _finding(
                auditor.config,
                CausalAuditCode.BATCH_REPLAY_MISMATCH,
                "comparison.batch_replay",
                as_of_time=None,
                object_ids=(batch.run_id, replayed.run_id),
                facts=(
                    _fact(
                        "batch_digest",
                        (
                            "unavailable"
                            if batch_payload is None
                            else digest(batch_payload)
                        ),
                    ),
                    _fact(
                        "replay_digest",
                        (
                            "unavailable"
                            if replay_payload is None
                            else digest(replay_payload)
                        ),
                    ),
                ),
            )
        )
    start, end = _bounds(batch, replayed)
    return _report(
        kind=CausalAuditKind.BATCH_REPLAY,
        subject_ids=(batch.run_id, replayed.run_id),
        start=start,
        end=end,
        findings=tuple(findings),
        codes=_codes(CausalAuditCode.BATCH_REPLAY_MISMATCH),
        config=auditor.config,
        provenance=(
            "msa.validation.comparison.compare_batch_replay",
            f"batch_run_id={batch.run_id}",
            f"replay_run_id={replayed.run_id}",
        ),
    )


def compare_prefix(
    auditor: CausalAuditor,
    prefix_run: MSACoreRun,
    extended_run: MSACoreRun,
) -> CausalAuditReport:
    prefix, extended = _runs(prefix_run, extended_run)
    prefix_times = prefix.processing_times
    extended_times = extended.processing_times
    if (
        not isinstance(prefix_times, tuple)
        or not isinstance(extended_times, tuple)
        or not prefix_times
        or len(prefix_times) >= len(extended_times)
        or extended_times[: len(prefix_times)] != prefix_times
    ):
        raise ValidationComparisonError(
            "prefix processing_times must be a strict starting prefix"
        )
    findings = _child_findings(auditor, prefix, extended)
    rewritten: list[str] = []
    extended_by_asof = {
        bundle.as_of_time: bundle for bundle in extended.frame_bundles
    }
    for bundle in prefix.frame_bundles:
        counterpart = extended_by_asof.get(bundle.as_of_time)
        if (
            counterpart is None
            or _payload(bundle) != _payload(counterpart)
        ):
            rewritten.append(bundle.as_of_time.isoformat())
    prefix_events = tuple(
        _payload(item) for item in prefix.active_box_history.events
    )
    extended_old_events = tuple(
        _payload(item)
        for item in extended.active_box_history.events
        if isinstance(item.event_confirm_time, datetime)
        and item.event_confirm_time <= prefix_times[-1]
    )
    prefix_frozen = tuple(
        _payload(item) for item in prefix.active_box_history.frozen_boxes
    )
    extended_old_frozen = tuple(
        _payload(item)
        for item in extended.active_box_history.frozen_boxes
        if isinstance(item.active_box.confirm_time, datetime)
        and item.active_box.confirm_time <= prefix_times[-1]
    )
    if (
        prefix_events != extended_old_events
        or prefix_frozen != extended_old_frozen
    ):
        rewritten.append("ledger")
    if rewritten:
        findings.append(
            _finding(
                auditor.config,
                CausalAuditCode.PREFIX_REWRITE,
                "comparison.prefix",
                as_of_time=prefix_times[-1],
                object_ids=(prefix.run_id, extended.run_id),
                facts=(
                    _fact("rewritten", ",".join(rewritten)),
                    _fact("prefix_count", len(prefix_times)),
                ),
            )
        )
    start, end = _bounds(prefix, extended)
    return _report(
        kind=CausalAuditKind.PREFIX_STABILITY,
        subject_ids=(prefix.run_id, extended.run_id),
        start=start,
        end=end,
        findings=tuple(findings),
        codes=_codes(CausalAuditCode.PREFIX_REWRITE),
        config=auditor.config,
        provenance=(
            "msa.validation.comparison.compare_prefix",
            f"prefix_run_id={prefix.run_id}",
            f"extended_run_id={extended.run_id}",
        ),
    )


def compare_shared_asof(
    auditor: CausalAuditor,
    baseline_run: MSACoreRun,
    extended_run: MSACoreRun,
    cutoff_time: datetime,
) -> CausalAuditReport:
    baseline, extended = _runs(baseline_run, extended_run)
    if (
        not isinstance(cutoff_time, datetime)
        or cutoff_time.tzinfo is None
        or cutoff_time.utcoffset() is None
        or cutoff_time.utcoffset().total_seconds() != 0
    ):
        raise ValidationComparisonError(
            "cutoff_time must be an aware UTC datetime"
        )
    findings = _child_findings(auditor, baseline, extended)
    baseline_by_asof = {
        item.as_of_time: item
        for item in baseline.frame_bundles
        if item.as_of_time < cutoff_time
    }
    extended_by_asof = {
        item.as_of_time: item
        for item in extended.frame_bundles
        if item.as_of_time < cutoff_time
    }
    shared = tuple(
        item
        for item in baseline.processing_times
        if item < cutoff_time and item in extended_by_asof
    )
    rewritten = [
        item.isoformat()
        for item in shared
        if _payload(baseline_by_asof[item])
        != _payload(extended_by_asof[item])
    ]
    baseline_events = tuple(
        _payload(item)
        for item in baseline.active_box_history.events
        if item.event_confirm_time < cutoff_time
    )
    extended_events = tuple(
        _payload(item)
        for item in extended.active_box_history.events
        if item.event_confirm_time < cutoff_time
    )
    baseline_frozen = tuple(
        _payload(item)
        for item in baseline.active_box_history.frozen_boxes
        if item.active_box.confirm_time < cutoff_time
    )
    extended_frozen = tuple(
        _payload(item)
        for item in extended.active_box_history.frozen_boxes
        if item.active_box.confirm_time < cutoff_time
    )
    if baseline_events != extended_events or baseline_frozen != extended_frozen:
        rewritten.append("ledger")
    if rewritten:
        findings.append(
            _finding(
                auditor.config,
                CausalAuditCode.SHARED_ASOF_REWRITE,
                "comparison.shared_asof",
                as_of_time=cutoff_time,
                object_ids=(baseline.run_id, extended.run_id),
                facts=(
                    _fact("rewritten", ",".join(rewritten)),
                    _fact("shared_asof_count", len(shared)),
                ),
            )
        )
    start, end = _bounds(baseline, extended)
    return _report(
        kind=CausalAuditKind.SHARED_ASOF_STABILITY,
        subject_ids=(baseline.run_id, extended.run_id),
        start=start,
        end=end,
        findings=tuple(findings),
        codes=_codes(CausalAuditCode.SHARED_ASOF_REWRITE),
        config=auditor.config,
        provenance=(
            "msa.validation.comparison.compare_shared_asof",
            f"baseline_run_id={baseline.run_id}",
            f"extended_run_id={extended.run_id}",
            f"cutoff_time={cutoff_time.isoformat()}",
        ),
    )


def audit_batch_replay_equivalence(
    batch_run: MSACoreRun,
    replay_run: MSACoreRun,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(config or CausalAuditConfig()).compare_batch_replay(
        batch_run, replay_run
    )


def audit_prefix_stability(
    prefix_run: MSACoreRun,
    extended_run: MSACoreRun,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(config or CausalAuditConfig()).compare_prefix(
        prefix_run, extended_run
    )


def audit_shared_asof_stability(
    baseline_run: MSACoreRun,
    extended_run: MSACoreRun,
    cutoff_time: datetime,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(config or CausalAuditConfig()).compare_shared_asof(
        baseline_run, extended_run, cutoff_time
    )
