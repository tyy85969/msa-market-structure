from datetime import timedelta

from msa.research.pool import replay_history
from tests.research.pool.fixtures import (
    T0,
    T1,
    T2,
    T3,
    candidate,
    clusterer,
    pool_input,
)


def test_candidate_origin_never_backdates_cluster_formation_or_lineage() -> None:
    data = pool_input(
        (
            candidate("a", low="100", origin_time=T0, confirm_time=T1),
            candidate(
                "b",
                low="100.5",
                origin_time=T0 - timedelta(days=10),
                confirm_time=T2,
            ),
        )
    )
    before_t1 = clusterer().build_as_of(data, T1 - timedelta(microseconds=1))
    at_t1 = clusterer().build_as_of(data, T1)
    before_t2 = clusterer().build_as_of(data, T2 - timedelta(microseconds=1))
    at_t2 = clusterer().build_as_of(data, T2)
    history = clusterer().build_batch(data)

    assert before_t1.clusters == ()
    assert len(at_t1.clusters) == 1
    assert [item.object_id for item in at_t1.clusters[0].member_refs] == ["a"]
    assert before_t2.to_dict() == at_t1.to_dict() | {
        "as_of_time": before_t2.as_of_time.isoformat(),
        "snapshot_id": before_t2.snapshot_id,
    }
    assert {item.object_id for item in at_t2.clusters[0].member_refs} == {"a", "b"}
    assert at_t2.clusters[0].confirm_time == T2
    assert history.formation_events[1].supersedes_cluster_ids == (
        history.formation_events[0].cluster.cluster_id,
    )


def test_bridge_at_t3_cannot_merge_two_old_clusters_before_t3() -> None:
    data = pool_input(
        (
            candidate("left", low="100", confirm_time=T1),
            candidate("right", low="102", confirm_time=T1),
            candidate("bridge", low="101", origin_time=T0, confirm_time=T3),
        )
    )
    before = clusterer().build_as_of(data, T3 - timedelta(microseconds=1))
    after = clusterer().build_as_of(data, T3)
    history = clusterer().build_batch(data)
    merged_event = history.formation_events[-1]
    assert len(before.clusters) == 2
    assert len(after.clusters) == 1
    assert merged_event.first_seen_time == T3
    assert len(merged_event.supersedes_cluster_ids) == 2


def test_same_confirm_time_candidates_enter_as_one_atomic_snapshot() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T2),
            candidate("b", low="100.5", confirm_time=T2),
            candidate("c", low="101", confirm_time=T2),
        )
    )
    history = clusterer().build_batch(data)
    assert len(history.formation_events) == 1
    assert {item.object_id for item in history.formation_events[0].cluster.member_refs} == {
        "a",
        "b",
        "c",
    }


def test_future_append_and_future_price_do_not_rewrite_old_snapshot_or_events() -> None:
    base = pool_input((candidate("a", confirm_time=T1),))
    append_near = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("future", low="100.5", confirm_time=T2),
        )
    )
    append_far = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("future", low="900", confirm_time=T2),
        )
    )
    base_snapshot = clusterer().build_as_of(base, T1)
    near_snapshot = clusterer().build_as_of(append_near, T1)
    far_snapshot = clusterer().build_as_of(append_far, T1)
    assert base_snapshot.to_dict() == near_snapshot.to_dict() == far_snapshot.to_dict()
    base_event = clusterer().build_batch(base).formation_events[0].to_dict()
    assert clusterer().build_batch(append_near).formation_events[0].to_dict() == base_event
    assert clusterer().build_batch(append_far).formation_events[0].to_dict() == base_event


def test_batch_history_and_replay_match_first_seen_and_supersedes_exactly() -> None:
    data = pool_input(
        (
            candidate("a", low="100", confirm_time=T1),
            candidate("b", low="102", confirm_time=T1),
            candidate("bridge", low="101", confirm_time=T3),
        )
    )
    batch = clusterer().build_batch(data)
    replay = replay_history(clusterer(), data)
    assert [item.to_dict() for item in replay.formation_events] == [
        item.to_dict() for item in batch.formation_events
    ]
    assert replay.final_snapshot.to_dict() == batch.final_snapshot.to_dict()
    assert all(
        item.first_seen_time == item.cluster.confirm_time
        for item in replay.formation_events
    )
