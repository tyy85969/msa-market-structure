"""Test-only future-leak and lineage mutations for C-008A."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from msa.validation import CausalAuditCode, CausalAuditor
from tests.research.msa_core.fixtures import (
    extra_run,
    source_input,
)

from .fixtures import valid_prefix_pair, valid_run


MUTATIONS: tuple[tuple[str, CausalAuditCode], ...] = (
    ("future_evidence", CausalAuditCode.FUTURE_EVIDENCE),
    ("future_context", CausalAuditCode.FUTURE_CONTEXT_STATE),
    ("future_reference", CausalAuditCode.FUTURE_REFERENCE_BAR),
    ("score_source", CausalAuditCode.SCORE_SOURCE_MISMATCH),
    ("selection_source", CausalAuditCode.SELECTION_SOURCE_MISMATCH),
    ("active_box_asof", CausalAuditCode.ACTIVE_BOX_ASOF_MISMATCH),
    ("event_confirm_time", CausalAuditCode.EVENT_TIME_MISMATCH),
    ("projection_time", CausalAuditCode.PROJECTION_TIME_MISMATCH),
    ("historical_bundle", CausalAuditCode.PREFIX_REWRITE),
    ("event_ledger", CausalAuditCode.EVENT_LEDGER_MISMATCH),
    ("frozen_ledger", CausalAuditCode.FROZEN_LEDGER_MISMATCH),
    (
        "frozen_reactivated",
        CausalAuditCode.FROZEN_EPISODE_REACTIVATED,
    ),
    ("retain_projection", CausalAuditCode.RETAIN_PROJECTION_CHANGED),
    ("episode_key", CausalAuditCode.EPISODE_KEY_CHANGED),
    ("final_bundle", CausalAuditCode.FINAL_BUNDLE_MISMATCH),
    ("report_count", CausalAuditCode.REPORT_COUNT_MISMATCH),
    ("source_history", CausalAuditCode.SOURCE_REPLAY_MISMATCH),
    ("score_history", CausalAuditCode.SCORE_REBUILD_MISMATCH),
    ("active_box_history", CausalAuditCode.ACTIVE_BOX_REBUILD_MISMATCH),
    ("batch_nested", CausalAuditCode.BATCH_REPLAY_MISMATCH),
)


def _run_copy():
    return deepcopy(valid_run())


def mutation_report(name: str, auditor: CausalAuditor):
    if name == "historical_bundle":
        prefix, extended = valid_prefix_pair()
        mutated = deepcopy(extended)
        evidence = mutated.frame_bundles[0].resonance_frame.evidence[0]
        object.__setattr__(evidence, "touch_count", evidence.touch_count + 1)
        return auditor.compare_prefix(prefix, mutated)
    if name == "batch_nested":
        batch = valid_run()
        replayed = deepcopy(batch)
        object.__setattr__(
            replayed.report,
            "evidence_count",
            replayed.report.evidence_count + 1,
        )
        return auditor.compare_batch_replay(batch, replayed)

    run = _run_copy()
    first = run.frame_bundles[0]
    if name == "future_evidence":
        evidence = first.resonance_frame.evidence[0]
        object.__setattr__(
            evidence,
            "state_confirm_time",
            first.as_of_time + timedelta(microseconds=1),
        )
    elif name == "future_context":
        state = first.resonance_frame.context_states[0].state
        object.__setattr__(
            state,
            "confirm_time",
            first.as_of_time + timedelta(microseconds=1),
        )
    elif name == "future_reference":
        bar = first.resonance_frame.reference_price.canonical_bar
        object.__setattr__(
            bar,
            "available_time",
            first.as_of_time + timedelta(microseconds=1),
        )
    elif name == "score_source":
        object.__setattr__(
            first.score_frame,
            "source_frame_id",
            run.frame_bundles[1].resonance_frame.frame_id,
        )
    elif name == "selection_source":
        object.__setattr__(
            first.selection_frame,
            "source_score_frame_id",
            run.frame_bundles[1].score_frame.score_frame_id,
        )
    elif name == "active_box_asof":
        snapshot = first.selection_frame.active_box_snapshot
        object.__setattr__(
            snapshot.active_box,
            "as_of_time",
            first.as_of_time + timedelta(microseconds=1),
        )
    elif name == "event_confirm_time":
        event = first.selection_frame.emitted_events[0]
        object.__setattr__(
            event,
            "event_confirm_time",
            first.as_of_time + timedelta(microseconds=1),
        )
    elif name == "projection_time":
        snapshot = first.selection_frame.active_box_snapshot
        object.__setattr__(
            snapshot.lower_projection,
            "selection_confirm_time",
            first.as_of_time + timedelta(microseconds=1),
        )
    elif name == "event_ledger":
        object.__setattr__(
            run.active_box_history,
            "events",
            run.active_box_history.events[1:],
        )
    elif name == "frozen_ledger":
        object.__setattr__(
            run.active_box_history,
            "frozen_boxes",
            (),
        )
    elif name == "frozen_reactivated":
        snapshot = run.frame_bundles[2].selection_frame.active_box_snapshot
        object.__setattr__(
            snapshot,
            "box_key_id",
            run.active_box_history.frozen_boxes[0].box_key_id,
        )
    elif name == "retain_projection":
        snapshot = run.frame_bundles[2].selection_frame.active_box_snapshot
        earlier = run.frame_bundles[0].selection_frame.active_box_snapshot
        object.__setattr__(
            snapshot, "lower_projection", earlier.lower_projection
        )
    elif name == "episode_key":
        snapshot = run.frame_bundles[2].selection_frame.active_box_snapshot
        object.__setattr__(
            snapshot,
            "box_key_id",
            "active-box-key-v1-" + ("0" * 64),
        )
    elif name == "final_bundle":
        object.__setattr__(run, "final_bundle", run.frame_bundles[0])
    elif name == "report_count":
        object.__setattr__(
            run.report,
            "evidence_count",
            run.report.evidence_count + 1,
        )
    elif name == "source_history":
        object.__setattr__(
            run, "source_input", source_input(include_extra=True)
        )
    elif name == "score_history":
        object.__setattr__(
            run.score_history,
            "source_history",
            extra_run().resonance_history,
        )
    elif name == "active_box_history":
        object.__setattr__(
            run.active_box_history,
            "source_score_history",
            extra_run().score_history,
        )
    else:
        raise AssertionError(f"unknown mutation: {name}")
    return auditor.audit_run(run)
