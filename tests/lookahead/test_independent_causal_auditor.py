from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

from msa.research.msa_core import replay_msa_core_run
from msa.research.resonance import ResonanceFrameInput
from msa.validation import (
    CausalAuditCode,
    CausalAuditor,
    audit_pipeline_causality,
)
from tests.lookahead.test_msa_core_pipeline_no_lookahead import (
    _single_context_pipeline,
)
from tests.research.msa_core.fixtures import (
    batch_run,
    pipeline,
    source_input,
)
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    T2,
    bar,
    base_subjects,
    lifecycle_history,
    load_result,
    subject,
    timeframe_history,
)
from tests.validation.causal_audit.fixtures import (
    valid_prefix_pair,
    valid_shared_asof_pair,
)
from tests.validation.causal_audit.mutations import mutation_report


def _codes(report):
    return {item.code for item in report.findings}


def test_normal_batch_run_passes_independent_auditor() -> None:
    assert CausalAuditor().audit_run(batch_run()).passed


def test_normal_default_replay_passes_independent_auditor() -> None:
    value = pipeline()
    source = source_input()
    replayed = replay_msa_core_run(value, source)
    assert CausalAuditor().audit_run(replayed).passed


def test_batch_and_replay_complete_payloads_pass() -> None:
    assert audit_pipeline_causality(pipeline(), source_input()).passed


def test_future_lifecycle_append_preserves_old_prefix() -> None:
    prefix, extended = valid_prefix_pair()
    assert (
        len(prefix.source_input.lifecycle_history.snapshots)
        < len(extended.source_input.lifecycle_history.snapshots)
    )
    assert CausalAuditor().compare_prefix(prefix, extended).passed


def test_future_timeframe_state_append_preserves_old_prefix() -> None:
    prefix, extended = valid_prefix_pair()
    assert all(
        len(left.snapshots) < len(right.snapshots)
        for left, right in zip(
            prefix.source_input.timeframe_state_histories,
            extended.source_input.timeframe_state_histories,
        )
    )
    assert CausalAuditor().compare_prefix(prefix, extended).passed


def test_future_reference_bar_append_preserves_old_prefix() -> None:
    prefix, extended = valid_prefix_pair()
    assert (
        len(prefix.source_input.reference_price_data.bars)
        < len(extended.source_input.reference_price_data.bars)
    )
    assert CausalAuditor().compare_prefix(prefix, extended).passed


def test_extra_asof_preserves_shared_prefix_before_cutoff() -> None:
    baseline, extended, cutoff = valid_shared_asof_pair()
    assert CausalAuditor().compare_shared_asof(
        baseline, extended, cutoff
    ).passed


def test_future_evidence_mutation_fails() -> None:
    report = mutation_report("future_evidence", CausalAuditor())
    assert CausalAuditCode.FUTURE_EVIDENCE in _codes(report)


def test_future_context_mutation_fails() -> None:
    report = mutation_report("future_context", CausalAuditor())
    assert CausalAuditCode.FUTURE_CONTEXT_STATE in _codes(report)


def test_future_reference_bar_mutation_fails() -> None:
    report = mutation_report("future_reference", CausalAuditor())
    assert CausalAuditCode.FUTURE_REFERENCE_BAR in _codes(report)


def test_event_backfill_mutation_fails() -> None:
    report = mutation_report("event_confirm_time", CausalAuditor())
    assert CausalAuditCode.EVENT_TIME_MISMATCH in _codes(report)


def test_frozen_ledger_rewrite_fails() -> None:
    report = mutation_report("frozen_ledger", CausalAuditor())
    assert CausalAuditCode.FROZEN_LEDGER_MISMATCH in _codes(report)


def test_retain_projection_rewrite_fails() -> None:
    report = mutation_report("retain_projection", CausalAuditor())
    assert CausalAuditCode.RETAIN_PROJECTION_CHANGED in _codes(report)


def test_origin_time_does_not_grant_visibility_before_confirm_time() -> None:
    base = base_subjects()[:3]
    future = subject(
        "future-origin-upper",
        side=base[0].boundary_side,
        low="140",
        high="141",
        confirm_time=T2,
    )
    bars = (bar(-1), bar(0), bar(1))
    history = lifecycle_history(base + (future,), bars)
    source = ResonanceFrameInput(
        history,
        (timeframe_history(history, H4_PRIMARY),),
        load_result(bars),
    )
    run = _single_context_pipeline().run(source)
    before = next(item for item in run.frame_bundles if item.as_of_time < T2)
    at_confirm = next(
        item for item in run.frame_bundles if item.as_of_time == T2
    )
    assert "future-origin-upper" not in {
        item.subject_id for item in before.resonance_frame.evidence
    }
    assert "future-origin-upper" in {
        item.subject_id for item in at_confirm.resonance_frame.evidence
    }
    assert CausalAuditor().audit_run(run).passed


def test_unavailable_reference_bar_is_not_consumed() -> None:
    source = source_input()
    bars = list(source.reference_price_data.bars)
    delayed_time = bars[-1].available_time + timedelta(hours=1)
    bars[-1] = replace(bars[-1], available_time=delayed_time)
    delayed = replace(
        source,
        reference_price_data=load_result(
            tuple(bars), config=source.reference_price_data.source_config
        ),
    )
    default = pipeline().run(delayed).processing_times
    schedule = tuple(sorted({*default, bars[-1].end_time}))
    run = replay_msa_core_run(pipeline(), delayed, schedule)
    at_end = next(
        item
        for item in run.frame_bundles
        if item.as_of_time == bars[-1].end_time
    )
    assert at_end.resonance_frame.reference_price.canonical_bar != bars[-1]
    assert CausalAuditor().audit_run(run).passed


def test_any_batch_replay_nested_payload_difference_fails() -> None:
    report = mutation_report("batch_nested", CausalAuditor())
    assert CausalAuditCode.BATCH_REPLAY_MISMATCH in _codes(report)


def test_auditor_does_not_sort_an_illegal_schedule_to_pass() -> None:
    run = deepcopy(batch_run())
    object.__setattr__(
        run, "processing_times", tuple(reversed(run.processing_times))
    )
    report = CausalAuditor().audit_run(run)
    assert not report.passed
    assert CausalAuditCode.PROCESSING_TIME_INVALID in _codes(report)


def test_auditor_does_not_delete_an_illegal_frame_to_pass() -> None:
    run = deepcopy(batch_run())
    object.__setattr__(run, "frame_bundles", run.frame_bundles[1:])
    report = CausalAuditor().audit_run(run)
    assert not report.passed
    assert CausalAuditCode.STAGE_FRAME_COUNT_MISMATCH in _codes(report)


def test_context_permutation_canonical_run_passes() -> None:
    value = pipeline()
    normal = value.run(source_input())
    permuted = value.run(source_input(reverse_histories=True))
    assert permuted.to_dict() == normal.to_dict()
    assert CausalAuditor().audit_run(permuted).passed


def test_all_audit_reports_repeat_complete_payloads() -> None:
    value = CausalAuditor()
    run = batch_run()
    assert value.audit_run(run).to_dict() == value.audit_run(run).to_dict()
    prefix, extended = valid_prefix_pair()
    assert value.compare_prefix(prefix, extended).to_dict() == (
        value.compare_prefix(prefix, extended).to_dict()
    )
    baseline, extra, cutoff = valid_shared_asof_pair()
    assert value.compare_shared_asof(
        baseline, extra, cutoff
    ).to_dict() == value.compare_shared_asof(
        baseline, extra, cutoff
    ).to_dict()
