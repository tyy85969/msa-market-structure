"""Independent public-payload auditor for C-007D MSA Core Runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from msa.research.active_box import (
    ActiveBoxEvent,
    ActiveBoxEventType,
    ActiveBoxSelectionFrame,
    ActiveBoxSelectionHistory,
    ActiveBoxSelector,
    ActiveBoxSnapshot,
)
from msa.research.msa_core import (
    MSACoreFrameBundle,
    MSACorePipeline,
    MSACoreRun,
    MSACoreRunReport,
    replay_msa_core_run,
)
from msa.research.resonance import (
    ResonanceFrame,
    ResonanceFrameAssembler,
    ResonanceFrameHistory,
    ResonanceFrameInput,
    ResonanceScoreFrame,
    ResonanceScoreHistory,
    ResonanceScorer,
    replay_history,
)

from .contracts import (
    AuditSeverity,
    CAUSAL_AUDIT_ASSUMPTIONS,
    CausalAuditCheckResult,
    CausalAuditCode,
    CausalAuditConfig,
    CausalAuditFact,
    CausalAuditFinding,
    CausalAuditKind,
    CausalAuditReport,
    audit_entrypoint,
    audit_provenance_keys,
    audit_subject_key_count,
    required_audit_codes,
)
from .errors import (
    CausalAuditError,
    ValidationConfigurationError,
    ValidationInputError,
)
from .identity import digest, semantic_id


_AUDITABLE_ERRORS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    AssertionError,
    RuntimeError,
)
_TRADING_FIELDS = {
    "buy",
    "sell",
    "entry",
    "exit",
    "stop",
    "stop_loss",
    "target",
    "take_profit",
    "profit",
    "profit_factor",
    "return",
    "returns",
    "win_rate",
    "pnl",
}


def _safe_text(value: object, field_name: str, max_length: int) -> str:
    try:
        if (
            isinstance(value, str)
            and value
            and len(value) <= max_length
        ):
            return value
    except _AUDITABLE_ERRORS:
        pass
    return f"invalid-{field_name}"


def _safe_identifier(value: object, position: str) -> str:
    return _safe_text(value, f"object-id-{position}", 512)


def _render_fact_value(value: object, key: str) -> str:
    try:
        if type(value) is datetime:
            rendered = value.isoformat()
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "null"
        elif isinstance(value, Enum):
            return _render_fact_value(value.value, key)
        elif type(value) in (int, Decimal):
            rendered = str(value)
        elif isinstance(value, str):
            rendered = value
        else:
            rendered = f"invalid-fact-value-{key}"
    except _AUDITABLE_ERRORS:
        rendered = f"invalid-fact-value-{key}"
    return _safe_text(rendered, f"fact-value-{key}", 512)


def _fact(key: object, value: object) -> CausalAuditFact:
    safe_key = _safe_text(key, "fact-key", 96)
    return CausalAuditFact(
        key=safe_key,
        value=_render_fact_value(value, safe_key),
    )


def _resolve_config(config: object | None) -> CausalAuditConfig:
    if config is None:
        return CausalAuditConfig()
    if not isinstance(config, CausalAuditConfig):
        raise ValidationConfigurationError(
            "config must be CausalAuditConfig or None"
        )
    try:
        restored = CausalAuditConfig.from_dict(config.to_dict())
    except _AUDITABLE_ERRORS as exc:
        raise ValidationConfigurationError(
            "config must be a strict round-trippable CausalAuditConfig"
        ) from exc
    if restored != config:
        raise ValidationConfigurationError(
            "config must be a strict round-trippable CausalAuditConfig"
        )
    return config


def _finding(
    config: CausalAuditConfig,
    code: CausalAuditCode,
    stage: object,
    *,
    as_of_time: datetime | None,
    object_ids: tuple[object, ...],
    facts: tuple[CausalAuditFact, ...],
) -> CausalAuditFinding:
    normalized_ids: list[str] = []
    for index, value in enumerate(object_ids):
        normalized = _safe_identifier(value, str(index))
        if normalized not in normalized_ids:
            normalized_ids.append(normalized)
    bounded_ids = tuple(normalized_ids[: config.max_object_ids])
    if not bounded_ids:
        bounded_ids = ("unknown-audit-object",)
    bounded_facts = facts[: config.max_facts]
    if not bounded_facts:
        bounded_facts = (_fact("violation", code.value),)
    payload = {
        "code": code.value,
        "severity": config.severity_for(code).value,
        "stage": _safe_text(stage, "finding-stage", 96),
        "as_of_time": (
            as_of_time.isoformat()
            if _is_utc(as_of_time)
            else None
        ),
        "object_ids": list(bounded_ids),
        "facts": [item.to_dict() for item in bounded_facts],
        "schema_version": 1,
    }
    return CausalAuditFinding(
        finding_id=semantic_id("causal-audit-finding-v1-", payload),
        code=code,
        severity=config.severity_for(code),
        stage=payload["stage"],
        as_of_time=(
            as_of_time
            if payload["as_of_time"] is not None
            else None
        ),
        object_ids=bounded_ids,
        facts=bounded_facts,
    )


def _check(
    code: CausalAuditCode, findings: tuple[CausalAuditFinding, ...]
) -> CausalAuditCheckResult:
    finding_ids = tuple(
        item.finding_id for item in findings if item.code is code
    )
    payload = {
        "check_name": code.value,
        "passed": not finding_ids,
        "finding_ids": list(finding_ids),
        "schema_version": 1,
    }
    return CausalAuditCheckResult(
        check_result_id=semantic_id("causal-audit-check-v1-", payload),
        check_name=code.value,
        passed=not finding_ids,
        finding_ids=finding_ids,
    )


def _report(
    *,
    kind: CausalAuditKind,
    subject_ids: tuple[str, ...],
    start: datetime,
    end: datetime,
    findings: tuple[CausalAuditFinding, ...],
    config: CausalAuditConfig,
    provenance_values: tuple[object, ...] = (),
) -> CausalAuditReport:
    normalized_roles = tuple(
        _safe_identifier(value, f"subject-{index}")
        for index, value in enumerate(subject_ids)
    )
    unique_subjects = tuple(dict.fromkeys(normalized_roles))
    unique_findings = tuple(
        {
            item.finding_id: item
            for item in findings
        }.values()
    )
    checks = tuple(
        _check(code, unique_findings)
        for code in required_audit_codes(kind)
    )
    errors = sum(
        item.severity is AuditSeverity.ERROR for item in unique_findings
    )
    warnings = sum(
        item.severity is AuditSeverity.WARNING for item in unique_findings
    )
    informational = sum(
        item.severity is AuditSeverity.INFORMATIONAL
        for item in unique_findings
    )
    provenance_keys = audit_provenance_keys(kind)
    subject_count = audit_subject_key_count(kind)
    if (
        len(normalized_roles) != subject_count
        or len(provenance_values)
        != len(provenance_keys) - subject_count
    ):
        raise CausalAuditError(
            "audit provenance values do not match audit kind"
        )
    rendered_values = (
        *normalized_roles,
        *(
            _render_fact_value(value, key)
            for key, value in zip(
                provenance_keys[subject_count:],
                provenance_values,
                strict=True,
            )
        ),
    )
    provenance = (
        audit_entrypoint(kind),
        *(
            f"{key}={value}"
            for key, value in zip(
                provenance_keys, rendered_values, strict=True
            )
        ),
    )
    identity_payload = {
        "audit_kind": kind.value,
        "subject_ids": list(unique_subjects),
        "started_as_of_time": start.isoformat(),
        "ended_as_of_time": end.isoformat(),
        "executed_checks": [item.to_dict() for item in checks],
        "findings": [item.to_dict() for item in unique_findings],
        "passed": errors == 0,
        "error_count": errors,
        "warning_count": warnings,
        "informational_count": informational,
        "config_snapshot": config.to_dict(),
        "assumptions": list(CAUSAL_AUDIT_ASSUMPTIONS),
        "provenance": list(provenance),
        "schema_version": 1,
    }
    return CausalAuditReport(
        audit_report_id=semantic_id(
            "causal-audit-report-v1-", identity_payload
        ),
        audit_kind=kind,
        subject_ids=unique_subjects,
        started_as_of_time=start,
        ended_as_of_time=end,
        executed_checks=checks,
        findings=unique_findings,
        passed=errors == 0,
        error_count=errors,
        warning_count=warnings,
        informational_count=informational,
        config_snapshot=config,
        assumptions=CAUSAL_AUDIT_ASSUMPTIONS,
        provenance=provenance,
    )


def _payload(value: object) -> object | None:
    method = getattr(value, "to_dict", None)
    if not callable(method):
        return None
    try:
        return method()
    except _AUDITABLE_ERRORS:
        return None


def _payload_equal(left: object, right: object) -> bool:
    left_payload = _payload(left)
    right_payload = _payload(right)
    return (
        left_payload is not None
        and right_payload is not None
        and left_payload == right_payload
    )


def _run_bounds(run: MSACoreRun) -> tuple[datetime, datetime]:
    candidates: list[datetime] = []
    processing_times = run.processing_times
    if isinstance(processing_times, tuple):
        candidates.extend(item for item in processing_times if _is_utc(item))
    bundles = run.frame_bundles
    if isinstance(bundles, tuple):
        candidates.extend(
            item.as_of_time
            for item in bundles
            if isinstance(item, MSACoreFrameBundle)
            and _is_utc(item.as_of_time)
        )
    if not candidates:
        raise CausalAuditError(
            "MSACoreRun has no safe deterministic AsOf bounds"
        )
    return min(candidates), max(candidates)


def _is_utc(value: object) -> bool:
    try:
        return (
            type(value) is datetime
            and value.tzinfo is not None
            and value.utcoffset() is not None
            and value.utcoffset().total_seconds() == 0
        )
    except _AUDITABLE_ERRORS:
        return False


def _trading_paths(value: object, path: str = "run") -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                child = f"{path}.{key}"
                if key.lower() in _TRADING_FIELDS:
                    found.append(child)
                found.extend(_trading_paths(item, child))
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            found.extend(_trading_paths(item, f"{path}[{index}]"))
    return tuple(found)


def _report_counts(run: MSACoreRun) -> dict[str, object] | None:
    if (
        not isinstance(run.resonance_history, ResonanceFrameHistory)
        or not isinstance(run.score_history, ResonanceScoreHistory)
        or not isinstance(
            run.active_box_history, ActiveBoxSelectionHistory
        )
    ):
        return None
    resonance_frames = run.resonance_history.frames
    score_frames = run.score_history.frames
    selection_frames = run.active_box_history.frames
    if (
        not isinstance(resonance_frames, tuple)
        or not isinstance(score_frames, tuple)
        or not isinstance(selection_frames, tuple)
        or any(not isinstance(item, ResonanceFrame) for item in resonance_frames)
        or any(
            not isinstance(item, ResonanceScoreFrame)
            for item in score_frames
        )
        or any(
            not isinstance(item, ActiveBoxSelectionFrame)
            for item in selection_frames
        )
        or not selection_frames
    ):
        return None
    events = tuple(
        event
        for frame in selection_frames
        for event in frame.emitted_events
        if isinstance(event, ActiveBoxEvent)
    )
    final_snapshot = selection_frames[-1].active_box_snapshot
    return {
        "start_time": resonance_frames[0].as_of_time,
        "end_time": resonance_frames[-1].as_of_time,
        "frame_count": len(resonance_frames),
        "score_frame_count": len(score_frames),
        "selection_frame_count": len(selection_frames),
        "evidence_count": sum(
            len(frame.evidence) for frame in resonance_frames
        ),
        "zone_count": sum(len(frame.zones) for frame in score_frames),
        "created_event_count": sum(
            event.event_type is ActiveBoxEventType.CREATED for event in events
        ),
        "frozen_event_count": sum(
            event.event_type is ActiveBoxEventType.FROZEN for event in events
        ),
        "frozen_box_count": len(run.active_box_history.frozen_boxes),
        "active_box_frame_count": sum(
            frame.active_box_snapshot is not None for frame in selection_frames
        ),
        "no_box_frame_count": sum(
            frame.active_box_snapshot is None for frame in selection_frames
        ),
        "final_has_active_box": final_snapshot is not None,
        "final_active_box_key_id": (
            None if final_snapshot is None else final_snapshot.box_key_id
        ),
        "frame_engine_id": run.config_snapshot.frame_config.engine_id,
        "scoring_engine_id": run.config_snapshot.scoring_config.engine_id,
        "active_box_engine_id": (
            run.config_snapshot.active_box_config.engine_id
        ),
        "integration_engine_id": run.config_snapshot.engine_id,
    }


def _append_formal_finding(
    run: MSACoreRun,
    config: CausalAuditConfig,
    findings: list[CausalAuditFinding],
) -> object | None:
    payload = _payload(run)
    formal = False
    if payload is not None:
        try:
            restored = MSACoreRun.from_dict(payload)
            formal = restored == run and restored.to_dict() == payload
        except _AUDITABLE_ERRORS:
            formal = False
    if not formal:
        findings.append(
            _finding(
                config,
                CausalAuditCode.FORMAL_CONTRACT_INVALID,
                "run.contract",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(_fact("strict_round_trip", False),),
            )
        )
    return payload


def _append_schedule_findings(
    run: MSACoreRun,
    config: CausalAuditConfig,
    findings: list[CausalAuditFinding],
) -> None:
    times = run.processing_times
    if (
        not isinstance(times, tuple)
        or not times
        or any(not _is_utc(item) for item in times)
        or any(
            current <= previous
            for previous, current in zip(times, times[1:])
            if isinstance(previous, datetime)
            and isinstance(current, datetime)
        )
    ):
        findings.append(
            _finding(
                config,
                CausalAuditCode.PROCESSING_TIME_INVALID,
                "run.schedule",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(
                    _fact(
                        "processing_time_count",
                        len(times) if isinstance(times, tuple) else "invalid",
                    ),
                ),
            )
        )
    if (
        isinstance(times, tuple)
        and all(isinstance(item, datetime) for item in times)
        and len(set(times)) != len(times)
    ):
        findings.append(
            _finding(
                config,
                CausalAuditCode.DUPLICATE_ASOF,
                "run.schedule",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(_fact("unique_asof", False),),
            )
        )
    bundles = run.frame_bundles
    if isinstance(bundles, tuple):
        bundle_times = tuple(
            item.as_of_time
            for item in bundles
            if isinstance(item, MSACoreFrameBundle)
        )
        if len(set(bundle_times)) != len(bundle_times):
            findings.append(
                _finding(
                    config,
                    CausalAuditCode.DUPLICATE_ASOF,
                    "run.bundles",
                    as_of_time=None,
                    object_ids=(run.run_id,),
                    facts=(_fact("unique_bundle_asof", False),),
                )
            )


def _append_bundle_findings(
    run: MSACoreRun,
    config: CausalAuditConfig,
    findings: list[CausalAuditFinding],
) -> None:
    histories = (
        run.resonance_history,
        run.score_history,
        run.active_box_history,
    )
    frames: tuple[tuple[object, ...], ...] = tuple(
        history.frames
        if isinstance(
            history,
            (
                ResonanceFrameHistory,
                ResonanceScoreHistory,
                ActiveBoxSelectionHistory,
            ),
        )
        and isinstance(history.frames, tuple)
        else ()
        for history in histories
    )
    bundles = (
        run.frame_bundles
        if isinstance(run.frame_bundles, tuple)
        else ()
    )
    counts = (
        len(run.processing_times)
        if isinstance(run.processing_times, tuple)
        else -1,
        len(bundles),
        *(len(item) for item in frames),
    )
    if len(set(counts)) != 1 or counts[0] <= 0:
        findings.append(
            _finding(
                config,
                CausalAuditCode.STAGE_FRAME_COUNT_MISMATCH,
                "run.stage_counts",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(
                    _fact(
                        "counts",
                        ",".join(str(item) for item in counts),
                    ),
                ),
            )
        )
    previous_snapshot: ActiveBoxSnapshot | None = None
    frozen_keys: list[str] = []
    for index, bundle in enumerate(bundles):
        if not isinstance(bundle, MSACoreFrameBundle):
            continue
        as_of = bundle.as_of_time
        object_ids = (run.run_id, bundle.bundle_id)
        resonance = bundle.resonance_frame
        score = bundle.score_frame
        selection = bundle.selection_frame
        if not (
            isinstance(resonance, ResonanceFrame)
            and isinstance(score, ResonanceScoreFrame)
            and isinstance(selection, ActiveBoxSelectionFrame)
        ):
            findings.append(
                _finding(
                    config,
                    CausalAuditCode.STAGE_FRAME_COUNT_MISMATCH,
                    "bundle.types",
                    as_of_time=as_of,
                    object_ids=object_ids,
                    facts=(_fact("formal_stage_types", False),),
                )
            )
            continue
        stage_times: tuple[object, ...] = (
            as_of,
            resonance.as_of_time,
            score.as_of_time,
            selection.as_of_time,
        )
        expected_time = (
            run.processing_times[index]
            if isinstance(run.processing_times, tuple)
            and index < len(run.processing_times)
            else None
        )
        history_frames = tuple(
            item[index] if index < len(item) else None for item in frames
        )
        if (
            not all(_is_utc(item) for item in stage_times)
            or len(set(stage_times)) != 1
            or expected_time != as_of
            or history_frames
            != (resonance, score, selection)
        ):
            findings.append(
                _finding(
                    config,
                    CausalAuditCode.STAGE_ASOF_MISMATCH,
                    "bundle.asof",
                    as_of_time=as_of,
                    object_ids=object_ids,
                    facts=(
                        _fact(
                            "stage_asof",
                            ",".join(str(item) for item in stage_times),
                        ),
                    ),
                )
            )
        if (
            score.source_frame_id != resonance.frame_id
            or not _payload_equal(score.source_frame, resonance)
        ):
            findings.append(
                _finding(
                    config,
                    CausalAuditCode.SCORE_SOURCE_MISMATCH,
                    "bundle.score",
                    as_of_time=as_of,
                    object_ids=(
                        bundle.bundle_id,
                        resonance.frame_id,
                        score.score_frame_id,
                    ),
                    facts=(
                        _fact("expected_source_frame_id", resonance.frame_id),
                        _fact("actual_source_frame_id", score.source_frame_id),
                    ),
                )
            )
        if (
            selection.source_score_frame_id != score.score_frame_id
            or not _payload_equal(selection.source_score_frame, score)
        ):
            findings.append(
                _finding(
                    config,
                    CausalAuditCode.SELECTION_SOURCE_MISMATCH,
                    "bundle.selection",
                    as_of_time=as_of,
                    object_ids=(
                        bundle.bundle_id,
                        score.score_frame_id,
                        selection.selection_frame_id,
                    ),
                    facts=(
                        _fact(
                            "expected_source_score_frame_id",
                            score.score_frame_id,
                        ),
                        _fact(
                            "actual_source_score_frame_id",
                            selection.source_score_frame_id,
                        ),
                    ),
                )
            )
        for evidence in resonance.evidence:
            if (
                _is_utc(evidence.state_confirm_time)
                and _is_utc(as_of)
                and evidence.state_confirm_time > as_of
            ):
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.FUTURE_EVIDENCE,
                        "bundle.resonance.evidence",
                        as_of_time=as_of,
                        object_ids=(bundle.bundle_id, evidence.evidence_id),
                        facts=(
                            _fact(
                                "state_confirm_time",
                                evidence.state_confirm_time,
                            ),
                            _fact("bundle_asof", as_of),
                        ),
                    )
                )
                if (
                    _is_utc(evidence.boundary.origin_time)
                    and evidence.boundary.origin_time <= as_of
                ):
                    findings.append(
                        _finding(
                            config,
                            CausalAuditCode.ORIGIN_USED_AS_VISIBILITY,
                            "bundle.resonance.evidence",
                            as_of_time=as_of,
                            object_ids=(
                                bundle.bundle_id,
                                evidence.evidence_id,
                            ),
                            facts=(
                                _fact(
                                    "origin_time",
                                    evidence.boundary.origin_time,
                                ),
                                _fact(
                                    "confirm_time",
                                    evidence.state_confirm_time,
                                ),
                            ),
                        )
                    )
        for context in resonance.context_states:
            if (
                _is_utc(context.state.confirm_time)
                and _is_utc(as_of)
                and context.state.confirm_time > as_of
            ):
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.FUTURE_CONTEXT_STATE,
                        "bundle.resonance.context",
                        as_of_time=as_of,
                        object_ids=(
                            bundle.bundle_id,
                            context.context_state_id,
                        ),
                        facts=(
                            _fact(
                                "state_confirm_time",
                                context.state.confirm_time,
                            ),
                            _fact("bundle_asof", as_of),
                        ),
                    )
                )
                if (
                    _is_utc(context.state.origin_time)
                    and context.state.origin_time <= as_of
                ):
                    findings.append(
                        _finding(
                            config,
                            CausalAuditCode.ORIGIN_USED_AS_VISIBILITY,
                            "bundle.resonance.context",
                            as_of_time=as_of,
                            object_ids=(
                                bundle.bundle_id,
                                context.context_state_id,
                            ),
                            facts=(
                                _fact(
                                    "origin_time",
                                    context.state.origin_time,
                                ),
                                _fact(
                                    "confirm_time",
                                    context.state.confirm_time,
                                ),
                            ),
                        )
                    )
        reference = resonance.reference_price.canonical_bar
        if (
            _is_utc(reference.available_time)
            and _is_utc(as_of)
            and reference.available_time > as_of
        ):
            findings.append(
                _finding(
                    config,
                    CausalAuditCode.FUTURE_REFERENCE_BAR,
                    "bundle.resonance.reference",
                    as_of_time=as_of,
                    object_ids=(
                        bundle.bundle_id,
                        resonance.reference_price.reference_id,
                    ),
                    facts=(
                        _fact("available_time", reference.available_time),
                        _fact("bundle_asof", as_of),
                    ),
                )
            )
        for event in selection.emitted_events:
            if not isinstance(event, ActiveBoxEvent):
                continue
            if event.event_confirm_time != as_of:
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.EVENT_TIME_MISMATCH,
                        "bundle.active_box.event",
                        as_of_time=as_of,
                        object_ids=(bundle.bundle_id, event.event_id),
                        facts=(
                            _fact(
                                "event_confirm_time",
                                event.event_confirm_time,
                            ),
                            _fact("bundle_asof", as_of),
                        ),
                    )
                )
            if event.event_type is ActiveBoxEventType.FROZEN:
                if event.resulting_box_snapshot.active_box.status.value != "FROZEN":
                    findings.append(
                        _finding(
                            config,
                            CausalAuditCode.FROZEN_LEDGER_MISMATCH,
                            "bundle.active_box.event",
                            as_of_time=as_of,
                            object_ids=(
                                event.event_id,
                                event.resulting_box_snapshot_id,
                            ),
                            facts=(_fact("result_status", event.resulting_box_snapshot.active_box.status.value),),
                        )
                    )
                normalized_frozen_key = _safe_identifier(
                    event.box_key_id,
                    f"frozen-{index}-{len(frozen_keys)}",
                )
                if normalized_frozen_key not in frozen_keys:
                    frozen_keys.append(normalized_frozen_key)
        snapshots: list[ActiveBoxSnapshot] = []
        if isinstance(selection.active_box_snapshot, ActiveBoxSnapshot):
            snapshots.append(selection.active_box_snapshot)
        snapshots.extend(
            event.resulting_box_snapshot
            for event in selection.emitted_events
            if isinstance(event, ActiveBoxEvent)
            and isinstance(event.resulting_box_snapshot, ActiveBoxSnapshot)
        )
        seen_snapshots: list[ActiveBoxSnapshot] = []
        for snapshot in snapshots:
            if any(snapshot is item for item in seen_snapshots):
                continue
            seen_snapshots.append(snapshot)
            if snapshot.active_box.as_of_time != as_of:
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.ACTIVE_BOX_ASOF_MISMATCH,
                        "bundle.active_box.snapshot",
                        as_of_time=as_of,
                        object_ids=(
                            bundle.bundle_id,
                            snapshot.box_snapshot_id,
                        ),
                        facts=(
                            _fact(
                                "active_box_asof",
                                snapshot.active_box.as_of_time,
                            ),
                            _fact("bundle_asof", as_of),
                        ),
                    )
                )
            if (
                (
                    _is_utc(
                        snapshot.lower_projection.selection_confirm_time
                    )
                    and _is_utc(as_of)
                    and snapshot.lower_projection.selection_confirm_time
                    > as_of
                )
                or (
                    _is_utc(
                        snapshot.upper_projection.selection_confirm_time
                    )
                    and _is_utc(as_of)
                    and snapshot.upper_projection.selection_confirm_time
                    > as_of
                )
            ):
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.PROJECTION_TIME_MISMATCH,
                        "bundle.active_box.projection",
                        as_of_time=as_of,
                        object_ids=(
                            bundle.bundle_id,
                            snapshot.box_snapshot_id,
                        ),
                        facts=(
                            _fact(
                                "lower_selection_time",
                                snapshot.lower_projection.selection_confirm_time,
                            ),
                            _fact(
                                "upper_selection_time",
                                snapshot.upper_projection.selection_confirm_time,
                            ),
                        ),
                    )
                )
            if (
                _is_utc(snapshot.created_time)
                and _is_utc(as_of)
                and snapshot.created_time > as_of
            ):
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.EPISODE_CREATED_TIME_MISMATCH,
                        "bundle.active_box.episode",
                        as_of_time=as_of,
                        object_ids=(
                            bundle.bundle_id,
                            snapshot.box_snapshot_id,
                        ),
                        facts=(
                            _fact("created_time", snapshot.created_time),
                            _fact("bundle_asof", as_of),
                        ),
                    )
                )
        current = selection.active_box_snapshot
        if isinstance(current, ActiveBoxSnapshot):
            if _safe_identifier(
                current.box_key_id, f"current-{index}"
            ) in frozen_keys:
                findings.append(
                    _finding(
                        config,
                        CausalAuditCode.FROZEN_EPISODE_REACTIVATED,
                        "bundle.active_box.episode",
                        as_of_time=as_of,
                        object_ids=(
                            bundle.bundle_id,
                            current.box_key_id,
                        ),
                        facts=(_fact("reactivated", True),),
                    )
                )
            if previous_snapshot is not None:
                if current.box_key_id == previous_snapshot.box_key_id:
                    if current.created_time != previous_snapshot.created_time:
                        findings.append(
                            _finding(
                                config,
                                CausalAuditCode.EPISODE_CREATED_TIME_MISMATCH,
                                "bundle.active_box.retain",
                                as_of_time=as_of,
                                object_ids=(
                                    current.box_key_id,
                                    current.box_snapshot_id,
                                ),
                                facts=(
                                    _fact(
                                        "previous_created_time",
                                        previous_snapshot.created_time,
                                    ),
                                    _fact(
                                        "current_created_time",
                                        current.created_time,
                                    ),
                                ),
                            )
                        )
                    if (
                        current.lower_projection
                        != previous_snapshot.lower_projection
                        or current.upper_projection
                        != previous_snapshot.upper_projection
                    ):
                        findings.append(
                            _finding(
                                config,
                                CausalAuditCode.RETAIN_PROJECTION_CHANGED,
                                "bundle.active_box.retain",
                                as_of_time=as_of,
                                object_ids=(
                                    current.box_key_id,
                                    current.box_snapshot_id,
                                ),
                                facts=(_fact("projection_stable", False),),
                            )
                        )
                elif (
                    current.created_time == previous_snapshot.created_time
                    and current.lower_projection
                    == previous_snapshot.lower_projection
                    and current.upper_projection
                    == previous_snapshot.upper_projection
                    and not any(
                        isinstance(event, ActiveBoxEvent)
                        and event.event_type is ActiveBoxEventType.CREATED
                        and event.box_key_id == current.box_key_id
                        for event in selection.emitted_events
                    )
                ):
                    findings.append(
                        _finding(
                            config,
                            CausalAuditCode.EPISODE_KEY_CHANGED,
                            "bundle.active_box.episode",
                            as_of_time=as_of,
                            object_ids=(
                                previous_snapshot.box_key_id,
                                current.box_key_id,
                            ),
                            facts=(_fact("created_event_present", False),),
                        )
                    )
            previous_snapshot = current
        else:
            previous_snapshot = None


def _append_ledger_findings(
    run: MSACoreRun,
    config: CausalAuditConfig,
    findings: list[CausalAuditFinding],
) -> None:
    history = run.active_box_history
    if not isinstance(history, ActiveBoxSelectionHistory):
        return
    flattened = tuple(
        event
        for frame in history.frames
        if isinstance(frame, ActiveBoxSelectionFrame)
        for event in frame.emitted_events
        if isinstance(event, ActiveBoxEvent)
    )
    if tuple(_payload(item) for item in flattened) != tuple(
        _payload(item) for item in history.events
    ):
        findings.append(
            _finding(
                config,
                CausalAuditCode.EVENT_LEDGER_MISMATCH,
                "active_box_history.events",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(
                    _fact("flattened_count", len(flattened)),
                    _fact("ledger_count", len(history.events)),
                ),
            )
        )
    expected_frozen = tuple(
        event.resulting_box_snapshot
        for event in flattened
        if event.event_type is ActiveBoxEventType.FROZEN
    )
    if tuple(_payload(item) for item in expected_frozen) != tuple(
        _payload(item) for item in history.frozen_boxes
    ):
        findings.append(
            _finding(
                config,
                CausalAuditCode.FROZEN_LEDGER_MISMATCH,
                "active_box_history.frozen_boxes",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(
                    _fact("expected_frozen_count", len(expected_frozen)),
                    _fact(
                        "actual_frozen_count", len(history.frozen_boxes)
                    ),
                ),
            )
        )


def _append_final_and_report_findings(
    run: MSACoreRun,
    config: CausalAuditConfig,
    findings: list[CausalAuditFinding],
) -> None:
    bundles = run.frame_bundles
    if (
        not isinstance(bundles, tuple)
        or not bundles
        or not _payload_equal(run.final_bundle, bundles[-1])
    ):
        findings.append(
            _finding(
                config,
                CausalAuditCode.FINAL_BUNDLE_MISMATCH,
                "run.final_bundle",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(_fact("equals_last_bundle", False),),
            )
        )
    expected = _report_counts(run)
    actual = run.report
    mismatch_fields: list[str] = []
    if expected is None or not isinstance(actual, MSACoreRunReport):
        mismatch_fields.append("report_type_or_inputs")
    else:
        mismatch_fields.extend(
            field_name
            for field_name, value in expected.items()
            if getattr(actual, field_name, object()) != value
        )
    if mismatch_fields:
        findings.append(
            _finding(
                config,
                CausalAuditCode.REPORT_COUNT_MISMATCH,
                "run.report",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(
                    _fact("mismatch_fields", ",".join(mismatch_fields)),
                ),
            )
        )


def _append_rebuild_findings(
    run: MSACoreRun,
    config: CausalAuditConfig,
    findings: list[CausalAuditFinding],
) -> None:
    try:
        expected_resonance = replay_history(
            ResonanceFrameAssembler(run.config_snapshot.frame_config),
            run.source_input,
            run.processing_times,
        )
        source_matches = _payload_equal(
            expected_resonance, run.resonance_history
        )
    except _AUDITABLE_ERRORS:
        source_matches = False
    if not source_matches:
        findings.append(
            _finding(
                config,
                CausalAuditCode.SOURCE_REPLAY_MISMATCH,
                "rebuild.resonance",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(_fact("public_replay_equal", False),),
            )
        )
    try:
        expected_score = ResonanceScorer(
            run.config_snapshot.scoring_config
        ).build_batch(run.resonance_history)
        score_matches = _payload_equal(expected_score, run.score_history)
    except _AUDITABLE_ERRORS:
        score_matches = False
    if not score_matches:
        findings.append(
            _finding(
                config,
                CausalAuditCode.SCORE_REBUILD_MISMATCH,
                "rebuild.score",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(_fact("public_scorer_equal", False),),
            )
        )
    try:
        expected_active = ActiveBoxSelector(
            run.config_snapshot.active_box_config
        ).build_batch(run.score_history)
        active_matches = _payload_equal(
            expected_active, run.active_box_history
        )
    except _AUDITABLE_ERRORS:
        active_matches = False
    if not active_matches:
        findings.append(
            _finding(
                config,
                CausalAuditCode.ACTIVE_BOX_REBUILD_MISMATCH,
                "rebuild.active_box",
                as_of_time=None,
                object_ids=(run.run_id,),
                facts=(_fact("public_selector_equal", False),),
            )
        )


@dataclass(frozen=True, slots=True)
class CausalAuditor:
    """Frozen, stateless C-008A audit facade."""

    config: CausalAuditConfig = CausalAuditConfig()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "config", _resolve_config(self.config)
        )

    def audit_run(self, run: MSACoreRun) -> CausalAuditReport:
        if not isinstance(run, MSACoreRun):
            raise ValidationInputError("run must be an MSACoreRun")
        start, end = _run_bounds(run)
        findings: list[CausalAuditFinding] = []
        payload = _append_formal_finding(run, self.config, findings)
        try:
            _append_schedule_findings(run, self.config, findings)
            _append_bundle_findings(run, self.config, findings)
            _append_ledger_findings(run, self.config, findings)
            _append_final_and_report_findings(run, self.config, findings)
            _append_rebuild_findings(run, self.config, findings)
            trading_paths = (
                () if payload is None else _trading_paths(payload)
            )
        except _AUDITABLE_ERRORS:
            findings.append(
                _finding(
                    self.config,
                    CausalAuditCode.FORMAL_CONTRACT_INVALID,
                    "run.unsafe_inspection",
                    as_of_time=None,
                    object_ids=(run.run_id,),
                    facts=(_fact("safe_audit_completed", False),),
                )
            )
            trading_paths = ()
        for path in trading_paths:
            findings.append(
                _finding(
                    self.config,
                    CausalAuditCode.UNSUPPORTED_TRADING_FIELD,
                    "run.payload",
                    as_of_time=None,
                    object_ids=(run.run_id,),
                    facts=(_fact("field_path", path),),
                )
            )
        return _report(
            kind=CausalAuditKind.SINGLE_RUN,
            subject_ids=(run.run_id,),
            start=start,
            end=end,
            findings=tuple(findings),
            config=self.config,
            provenance_values=(
                digest(payload) if payload is not None else "unavailable",
            ),
        )

    def compare_batch_replay(
        self, batch_run: MSACoreRun, replay_run: MSACoreRun
    ) -> CausalAuditReport:
        from .comparison import compare_batch_replay

        return compare_batch_replay(self, batch_run, replay_run)

    def compare_prefix(
        self, prefix_run: MSACoreRun, extended_run: MSACoreRun
    ) -> CausalAuditReport:
        from .comparison import compare_prefix

        return compare_prefix(self, prefix_run, extended_run)

    def compare_shared_asof(
        self,
        baseline_run: MSACoreRun,
        extended_run: MSACoreRun,
        cutoff_time: datetime,
    ) -> CausalAuditReport:
        from .comparison import compare_shared_asof

        return compare_shared_asof(
            self, baseline_run, extended_run, cutoff_time
        )

    def audit_pipeline(
        self,
        pipeline: MSACorePipeline,
        source_input: ResonanceFrameInput,
    ) -> CausalAuditReport:
        if not isinstance(pipeline, MSACorePipeline):
            raise ValidationInputError(
                "pipeline must be an MSACorePipeline"
            )
        if not isinstance(source_input, ResonanceFrameInput):
            raise ValidationInputError(
                "source_input must be a ResonanceFrameInput"
            )
        try:
            batch = pipeline.run(source_input)
            replayed = replay_msa_core_run(pipeline, source_input)
        except _AUDITABLE_ERRORS as exc:
            raise CausalAuditError(
                "public Batch or Replay could not audit pipeline causality"
            ) from exc
        from .comparison import compare_batch_replay

        comparison = compare_batch_replay(self, batch, replayed)
        return _report(
            kind=CausalAuditKind.PIPELINE_CAUSALITY,
            subject_ids=(batch.run_id, replayed.run_id),
            start=comparison.started_as_of_time,
            end=comparison.ended_as_of_time,
            findings=comparison.findings,
            config=self.config,
        )


def audit_msa_core_run(
    run: MSACoreRun,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(_resolve_config(config)).audit_run(run)


def audit_pipeline_causality(
    pipeline: MSACorePipeline,
    source_input: ResonanceFrameInput,
    config: CausalAuditConfig | None = None,
) -> CausalAuditReport:
    return CausalAuditor(_resolve_config(config)).audit_pipeline(
        pipeline, source_input
    )
