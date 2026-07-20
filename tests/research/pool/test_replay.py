from datetime import datetime, timedelta

import pytest

from msa.research.pool import LevelPoolInputError, replay_history
from tests.research.pool.fixtures import (
    T0,
    T1,
    T2,
    T3,
    candidate,
    clusterer,
    pool_input,
)


def test_as_of_visibility_uses_confirm_time_with_equality() -> None:
    data = pool_input((candidate("a", origin_time=T0, confirm_time=T1),))
    before = clusterer().build_as_of(data, T1 - timedelta(microseconds=1))
    at_time = clusterer().build_as_of(data, T1)
    assert before.clusters == ()
    assert before.visible_candidate_ids == ()
    assert len(at_time.clusters) == 1
    assert at_time.visible_candidate_ids == ("a",)


def test_origin_time_never_grants_visibility() -> None:
    value = candidate("a", origin_time=T0 - timedelta(days=20), confirm_time=T2)
    assert clusterer().build_as_of(pool_input((value,)), T1).clusters == ()


def test_naive_processing_time_is_rejected() -> None:
    with pytest.raises(LevelPoolInputError, match="timezone-aware"):
        clusterer().build_as_of(
            pool_input((candidate(),)), datetime(2026, 7, 1, 1)
        )


def test_future_candidate_does_not_expand_earlier_snapshot() -> None:
    base = pool_input((candidate("a", low="100", confirm_time=T1),))
    appended = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("future", low="101", origin_time=T0, confirm_time=T2),
        )
    )
    assert clusterer().build_as_of(base, T1).to_dict() == clusterer().build_as_of(appended, T1).to_dict()


def test_future_bridge_does_not_merge_components_early() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("b", low="102", confirm_time=T1),
            candidate("bridge", low="101", origin_time=T0, confirm_time=T2),
        )
    )
    before = clusterer().build_as_of(data, T2 - timedelta(microseconds=1))
    at_bridge = clusterer().build_as_of(data, T2)
    assert len(before.clusters) == 2
    assert len(at_bridge.clusters) == 1
    assert at_bridge.clusters[0].confirm_time == T2


def test_initial_and_extension_events_preserve_immutable_history() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("b", low="100.5", confirm_time=T2),
        )
    )
    history = clusterer().build_batch(data)
    assert len(history.formation_events) == 2
    first, second = history.formation_events
    assert [item.object_id for item in first.cluster.member_refs] == ["a"]
    assert {item.object_id for item in second.cluster.member_refs} == {"a", "b"}
    assert second.supersedes_cluster_ids == (first.cluster.cluster_id,)
    assert first.cluster.cluster_id != second.cluster.cluster_id
    assert first.first_seen_time == first.cluster.confirm_time == T1
    assert second.first_seen_time == second.cluster.confirm_time == T2


def test_bridge_supersedes_two_prior_clusters() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("b", low="102", confirm_time=T1),
            candidate("bridge", low="101", confirm_time=T2),
        )
    )
    history = clusterer().build_batch(data)
    initial = history.formation_events[:2]
    merged = history.formation_events[-1]
    assert len(initial) == 2
    assert set(merged.supersedes_cluster_ids) == {
        item.cluster.cluster_id for item in initial
    }
    assert {item.object_id for item in merged.cluster.member_refs} == {
        "a",
        "b",
        "bridge",
    }


def test_same_confirm_time_is_atomic_without_intermediate_cluster() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("b", low="100.5", confirm_time=T1),
        )
    )
    history = clusterer().build_batch(data)
    assert len(history.formation_events) == 1
    assert {item.object_id for item in history.formation_events[0].cluster.member_refs} == {"a", "b"}


def test_batch_and_default_replay_are_fully_equal() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("b", low="102", confirm_time=T1),
            candidate("bridge", low="101", confirm_time=T2),
            candidate("future", low="110", confirm_time=T3),
        )
    )
    batch = clusterer().build_batch(data)
    replay = replay_history(clusterer(), data)
    assert replay.to_dict() == batch.to_dict()
    assert replay.final_snapshot.to_dict() == batch.final_snapshot.to_dict()


def test_explicit_complete_schedule_matches_batch() -> None:
    data = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("b", low="100.5", confirm_time=T2),
        )
    )
    assert replay_history(clusterer(), data, (T1, T2)).to_dict() == clusterer().build_batch(data).to_dict()


def test_sparse_schedule_cannot_claim_late_first_appearance() -> None:
    data = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("b", low="100.5", confirm_time=T2),
        )
    )
    with pytest.raises(LevelPoolInputError, match="every cluster first_seen_time"):
        replay_history(clusterer(), data, (T2,))


@pytest.mark.parametrize(
    "schedule",
    [
        (datetime(2026, 7, 1, 1),),
        (T1, T1),
        (T2, T1),
    ],
)
def test_invalid_replay_schedule_is_rejected(schedule) -> None:
    with pytest.raises(LevelPoolInputError):
        replay_history(clusterer(), pool_input((candidate(),)), schedule)


def test_future_append_does_not_change_old_formation_events() -> None:
    old_data = pool_input((candidate("a", confirm_time=T1),))
    new_data = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("future", low="100.5", confirm_time=T2),
        )
    )
    old_event = clusterer().build_batch(old_data).formation_events[0]
    appended_event = clusterer().build_batch(new_data).formation_events[0]
    assert old_event.to_dict() == appended_event.to_dict()


def test_future_price_change_cannot_change_past_snapshot_or_event() -> None:
    first = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("future", low="100.5", confirm_time=T2),
        )
    )
    changed = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("future", low="500", confirm_time=T2),
        )
    )
    assert clusterer().build_as_of(first, T1).to_dict() == clusterer().build_as_of(changed, T1).to_dict()
    assert clusterer().build_batch(first).formation_events[0].to_dict() == clusterer().build_batch(changed).formation_events[0].to_dict()
