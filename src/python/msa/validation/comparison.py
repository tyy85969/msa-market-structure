"""Complete-payload causal comparisons for formal MSA Core Runs."""

from __future__ import annotations

from datetime import datetime

from msa.research.active_box import (
    ActiveBoxEvent,
    ActiveBoxSelectionHistory,
    ActiveBoxSnapshot,
)
from msa.research.msa_core import MSACoreFrameBundle, MSACoreRun

from .causal_audit import (
    CausalAuditor,
    _fact,
    _finding,
    _payload,
    _report,
    _resolve_config,
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


def _is_utc(value: object) -> bool:
    try:
        return (
            type(value) is datetime
            and value.tzinfo is not None
            and value.utcoffset() is not None
            and value.utcoffset().total_seconds() == 0
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _runs(
    left: object, right: object
) -> tuple[MSACoreRun, MSACoreRun]:
    if not isinstance(left, MSACoreRun) or not isinstance(right, MSACoreRun):
        raise ValidationInputError(
            "comparison inputs must both be MSACoreRun"
        )
    return left, right


def _inspect_comparison_parts(
    run: MSACoreRun,
    role: str,
) -> tuple[
    tuple[datetime, ...],
    tuple[MSACoreFrameBundle, ...],
    tuple[ActiveBoxEvent, ...],
    tuple[ActiveBoxSnapshot, ...],
]:
    times = run.processing_times
    if (
        not isinstance(times, tuple)
        or not times
        or any(not _is_utc(item) for item in times)
    ):
        raise ValidationComparisonError(
            f"{role} processing_times are not safely comparable"
        )
    try:
        if any(
            current <= previous
            for previous, current in zip(times, times[1:])
        ):
            raise ValidationComparisonError(
                f"{role} processing_times must be strictly increasing"
            )
    except TypeError as exc:
        raise ValidationComparisonError(
            f"{role} processing_times are not safely comparable"
        ) from exc

    bundles = run.frame_bundles
    if (
        not isinstance(bundles, tuple)
        or any(
            not isinstance(item, MSACoreFrameBundle)
            or not _is_utc(item.as_of_time)
            for item in bundles
        )
    ):
        raise ValidationComparisonError(
            f"{role} frame_bundles are not safely comparable"
        )
    bundle_times = tuple(item.as_of_time for item in bundles)
    if len(set(bundle_times)) != len(bundle_times):
        raise ValidationComparisonError(
            f"{role} frame_bundles contain duplicate AsOf values"
        )

    history = run.active_box_history
    if (
        not isinstance(history, ActiveBoxSelectionHistory)
        or not isinstance(history.events, tuple)
        or not isinstance(history.frozen_boxes, tuple)
        or any(
            not isinstance(item, ActiveBoxEvent)
            or not _is_utc(item.event_confirm_time)
            for item in history.events
        )
        or any(
            not isinstance(item, ActiveBoxSnapshot)
            or not _is_utc(item.active_box.confirm_time)
            for item in history.frozen_boxes
        )
    ):
        raise ValidationComparisonError(
            f"{role} Active Box ledger is not safely comparable"
        )
    return times, bundles, history.events, history.frozen_boxes


def _comparison_parts(
    run: MSACoreRun,
    role: str,
) -> tuple[
    tuple[datetime, ...],
    tuple[MSACoreFrameBundle, ...],
    tuple[ActiveBoxEvent, ...],
    tuple[ActiveBoxSnapshot, ...],
]:
    try:
        return _inspect_comparison_parts(run, role)
    except ValidationComparisonError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValidationComparisonError(
            f"{role} run is not safely comparable"
        ) from exc


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
        config=auditor.config,
    )


def compare_prefix(
    auditor: CausalAuditor,
    prefix_run: MSACoreRun,
    extended_run: MSACoreRun,
) -> CausalAuditReport:
    prefix, extended = _runs(prefix_run, extended_run)
    (
        prefix_times,
        prefix_bundles,
        prefix_events_ledger,
        prefix_frozen_ledger,
    ) = _comparison_parts(prefix, "prefix")
    (
        extended_times,
        extended_bundles,
        extended_events_ledger,
        extended_frozen_ledger,
    ) = _comparison_parts(extended, "extended")
    if (
        len(prefix_times) >= len(extended_times)
        or extended_times[: len(prefix_times)] != prefix_times
    ):
        raise ValidationComparisonError(
            "prefix processing_times must be a strict starting prefix"
        )
    findings = _child_findings(auditor, prefix, extended)
    rewritten: list[str] = []
    extended_by_asof = {
        bundle.as_of_time: bundle for bundle in extended_bundles
    }
    for bundle in prefix_bundles:
        counterpart = extended_by_asof.get(bundle.as_of_time)
        if (
            counterpart is None
            or _payload(bundle) != _payload(counterpart)
        ):
            rewritten.append(bundle.as_of_time.isoformat())
    prefix_events = tuple(
        _payload(item) for item in prefix_events_ledger
    )
    extended_old_events = tuple(
        _payload(item)
        for item in extended_events_ledger
        if item.event_confirm_time <= prefix_times[-1]
    )
    prefix_frozen = tuple(
        _payload(item) for item in prefix_frozen_ledger
    )
    extended_old_frozen = tuple(
        _payload(item)
        for item in extended_frozen_ledger
        if item.active_box.confirm_time <= prefix_times[-1]
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
        config=auditor.config,
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
    (
        baseline_times,
        baseline_bundles,
        baseline_events_ledger,
        baseline_frozen_ledger,
    ) = _comparison_parts(baseline, "baseline")
    (
        _,
        extended_bundles,
        extended_events_ledger,
        extended_frozen_ledger,
    ) = _comparison_parts(extended, "extended")
    findings = _child_findings(auditor, baseline, extended)
    baseline_by_asof = {
        item.as_of_time: item
        for item in baseline_bundles
        if item.as_of_time < cutoff_time
    }
    extended_by_asof = {
        item.as_of_time: item
        for item in extended_bundles
        if item.as_of_time < cutoff_time
    }
    shared = tuple(
        item
        for item in baseline_times
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
        for item in baseline_events_ledger
        if item.event_confirm_time < cutoff_time
    )
    extended_events = tuple(
        _payload(item)
        for item in extended_events_ledger
        if item.event_confirm_time < cutoff_time
    )
    baseline_frozen = tuple(
        _payload(item)
        for item in baseline_frozen_ledger
        if item.active_box.confirm_time < cutoff_time
    )
    extended_frozen = tuple(
        _payload(item)
        for item in extended_frozen_ledger
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
        config=auditor.config,
        provenance_values=(
            cutoff_time,
        ),
    )


def audit_batch_replay_equivalence(
    batch_run: MSACoreRun,
    replay_run: MSACoreRun,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(
        _resolve_config(config)
    ).compare_batch_replay(
        batch_run, replay_run
    )


def audit_prefix_stability(
    prefix_run: MSACoreRun,
    extended_run: MSACoreRun,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(
        _resolve_config(config)
    ).compare_prefix(
        prefix_run, extended_run
    )


def audit_shared_asof_stability(
    baseline_run: MSACoreRun,
    extended_run: MSACoreRun,
    cutoff_time: datetime,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(
        _resolve_config(config)
    ).compare_shared_asof(
        baseline_run, extended_run, cutoff_time
    )
