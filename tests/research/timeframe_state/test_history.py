from dataclasses import replace
from datetime import timedelta

import pytest

from msa.domain import Direction
from msa.research.timeframe_state import (
    TimeframeStateEngineError,
    TimeframeStateHistory,
)
from tests.research.timeframe_state.fixtures import (
    START,
    T1,
    base_pair,
    bar,
    direction_sequence_input,
    timeframe_engine,
    timeframe_input,
)


def test_history_snapshots_are_strictly_chronological_with_exact_event_prefixes() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    assert all(
        current.as_of_time > previous.as_of_time
        for previous, current in zip(history.snapshots, history.snapshots[1:])
    )
    for snapshot in history.snapshots:
        assert snapshot.events == history.events[: len(snapshot.events)]
    assert history.final_snapshot == history.snapshots[-1]
    assert history.final_snapshot.events == history.events


def test_no_new_event_preserves_all_state_facts_except_as_of() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    original = timeframe_engine().build_as_of(data, T1)
    observed = timeframe_engine().build_as_of(data, T1 + timedelta(minutes=30))
    old_payload = original.state.to_dict()
    new_payload = observed.state.to_dict()
    del old_payload["as_of_time"]
    del new_payload["as_of_time"]
    assert new_payload == old_payload
    assert observed.events == original.events


def test_history_rejects_non_chronological_snapshots() -> None:
    history = timeframe_engine().build_batch(timeframe_input(base_pair(), (bar(0),)))
    with pytest.raises(TimeframeStateEngineError, match="chronological"):
        TimeframeStateHistory(
            events=history.events,
            snapshots=tuple(reversed(history.snapshots)),
            final_snapshot=history.snapshots[0],
            config_snapshot=history.config_snapshot,
        )


def test_history_rejects_snapshot_config_change() -> None:
    history = timeframe_engine().build_batch(timeframe_input(base_pair(), (bar(0),)))
    with pytest.raises(TimeframeStateEngineError, match="contradicts config"):
        replace(
            history.snapshots[-1],
            config_snapshot=replace(history.config_snapshot, policy_id="changed"),
        )


def test_state_id_changes_have_a_corresponding_event() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    for previous, current in zip(history.snapshots, history.snapshots[1:]):
        if current.state.state_id != previous.state.state_id:
            assert len(current.events) == len(previous.events) + 1
            assert current.events[-1].current_state_id == current.state.state_id


def test_state_origin_and_confirm_equal_semantic_event_time() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    for snapshot in history.snapshots:
        event = snapshot.events[-1]
        if snapshot.state.state_id == event.current_state_id:
            assert snapshot.state.origin_time == event.event_confirm_time
            assert snapshot.state.confirm_time == event.event_confirm_time


def test_report_matches_state_explanation_and_event_ledger() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    for snapshot in history.snapshots:
        report = snapshot.report
        explanation = snapshot.explanation
        assert report.direction is snapshot.state.direction
        assert explanation.final_direction is snapshot.state.direction
        assert report.state_event_count == len(snapshot.events)
        assert report.relevant_subject_count == len(explanation.relevant_subject_ids)
        assert report.selected_confirmed_upper_id == explanation.selected_confirmed_upper_id
        assert report.selected_confirmed_lower_id == explanation.selected_confirmed_lower_id


def test_history_retains_old_immutable_snapshots() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    first_payload = history.snapshots[0].to_dict()
    assert history.snapshots[0].state.direction is Direction.UNKNOWN
    assert history.snapshots[0].to_dict() == first_payload
