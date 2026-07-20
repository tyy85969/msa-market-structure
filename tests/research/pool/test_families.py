import pytest

from msa.data import Timeframe
from msa.domain import BoundarySide, StructureSourceType
from msa.research.pool import LevelPoolInputError
from tests.research.pool.fixtures import (
    T1,
    assignment,
    candidate,
    clusterer,
    pool_input,
)


def test_explicit_family_groups_cross_timeframe_members() -> None:
    values = (
        candidate("m15", timeframe=Timeframe.M15, low="100"),
        candidate("h4", timeframe=Timeframe.H4, low="100.5"),
    )
    data = pool_input(
        values,
        (assignment("m15", "extreme-x"), assignment("h4", "extreme-x")),
    )
    explanation = clusterer().build_as_of(data, T1).explanations[0]
    assert explanation.raw_member_count == 2
    assert explanation.dependency_family_count == 1
    assert explanation.dependency_groups[0].timeframes == (
        Timeframe.H4,
        Timeframe.M15,
    )
    assert explanation.dependency_groups[0].explicit_assignment is True


def test_unassigned_candidates_receive_unique_implicit_families() -> None:
    data = pool_input((candidate("a"), candidate("b", low="100.5")))
    groups = clusterer().build_as_of(data, T1).explanations[0].dependency_groups
    assert {item.dependency_family_id for item in groups} == {
        "candidate:a",
        "candidate:b",
    }
    assert all(item.explicit_assignment is False for item in groups)


@pytest.mark.parametrize("shared_fact", ["structure_family", "price", "source"])
def test_shared_candidate_facts_do_not_auto_assign_dependency(shared_fact: str) -> None:
    kwargs = {}
    if shared_fact == "source":
        kwargs["source_type"] = StructureSourceType.PERIODIC_EXTREME
    first = candidate("a", **kwargs)
    second = candidate("b", low="100", **kwargs)
    explanation = clusterer().build_as_of(pool_input((first, second)), T1).explanations[0]
    assert explanation.raw_member_count == 2
    assert explanation.dependency_family_count == 2


def test_same_family_across_side_is_rejected() -> None:
    values = (
        candidate("upper"),
        candidate("lower", side=BoundarySide.LOWER, low="90"),
    )
    with pytest.raises(LevelPoolInputError, match="cannot span"):
        pool_input(
            values,
            (assignment("upper", "same"), assignment("lower", "same")),
        )


def test_assignment_unknown_candidate_and_duplicate_assignment_are_rejected() -> None:
    with pytest.raises(LevelPoolInputError, match="unknown"):
        pool_input((candidate("a"),), (assignment("missing"),))
    with pytest.raises(LevelPoolInputError, match="at most one"):
        pool_input(
            (candidate("a"),),
            (assignment("a", "x"), assignment("a", "y")),
        )


def test_explicit_family_collision_with_implicit_id_is_rejected() -> None:
    with pytest.raises(LevelPoolInputError, match="collides"):
        pool_input(
            (candidate("a"), candidate("b")),
            (assignment("a", "candidate:b"),),
        )


def test_split_family_is_reported_without_forced_price_merge() -> None:
    values = (candidate("a", low="100"), candidate("b", low="110"))
    data = pool_input(
        values,
        (assignment("a", "shared"), assignment("b", "shared")),
    )
    snapshot = clusterer().build_as_of(data, T1)
    assert len(snapshot.clusters) == 2
    assert snapshot.report.split_dependency_family_count == 1
    assert all(item.dependency_family_count == 1 for item in snapshot.explanations)


def test_dependency_groups_never_remove_raw_members_or_create_scores() -> None:
    values = (candidate("a"), candidate("b", low="100.5"))
    data = pool_input(
        values,
        (assignment("a", "shared"), assignment("b", "shared")),
    )
    snapshot = clusterer().build_as_of(data, T1)
    cluster = snapshot.clusters[0]
    explanation = snapshot.explanations[0]
    assert {item.object_id for item in cluster.member_refs} == {"a", "b"}
    assert explanation.raw_member_count == 2
    assert not any(
        "score" in field or "penalty" in field
        for field in explanation.__dataclass_fields__
    )
