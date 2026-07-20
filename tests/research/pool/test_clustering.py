from datetime import timedelta
from decimal import Decimal
from itertools import permutations

import pytest

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    LifecycleState,
    MarketRole,
    ScaleDescriptor,
    StructureSourceType,
)
from msa.research.pool import LevelPoolClusterer
from tests.research.pool.fixtures import (
    T0,
    T1,
    T2,
    absolute_config,
    assignment,
    candidate,
    clusterer,
    normalized_config,
    pool_input,
)


@pytest.mark.parametrize(
    ("second_price", "expected_clusters"),
    [("100", 1), ("100.5", 1), ("101", 1), ("101.0001", 2)],
)
def test_single_link_threshold_is_inclusive(
    second_price: str, expected_clusters: int
) -> None:
    data = pool_input((candidate("a", low="100"), candidate("b", low=second_price)))
    snapshot = clusterer().build_as_of(data, T1)
    assert len(snapshot.clusters) == expected_clusters


def test_upper_and_lower_never_merge() -> None:
    data = pool_input(
        (
            candidate("upper", low="100"),
            candidate("lower", low="100", side=BoundarySide.LOWER),
        )
    )
    snapshot = clusterer().build_as_of(data, T1)
    assert len(snapshot.clusters) == 2
    assert {item.boundary_side for item in snapshot.clusters} == {
        BoundarySide.UPPER,
        BoundarySide.LOWER,
    }


def test_singleton_component_outputs_structure_cluster() -> None:
    value = clusterer().build_as_of(pool_input((candidate("only"),)), T1).clusters[0]
    assert [item.object_id for item in value.member_refs] == ["only"]
    assert value.lifecycle_state is LifecycleState.CONFIRMED


def test_single_link_chain_bridges_nonadjacent_endpoints() -> None:
    values = (
        candidate("a", low="100"),
        candidate("b", low="101"),
        candidate("c", low="102"),
    )
    snapshot = clusterer().build_as_of(pool_input(values), T1)
    assert len(snapshot.clusters) == 1
    assert {item.object_id for item in snapshot.clusters[0].member_refs} == {
        "a",
        "b",
        "c",
    }
    assert snapshot.report.graph_edge_count == 2
    assert "chain bridging" in snapshot.report.warnings[0]


def test_zone_envelope_origin_confirm_and_explicit_context_mapping() -> None:
    member_scale = ScaleDescriptor("member-other", 2)
    values = (
        candidate(
            "a",
            low="99",
            high="100",
            origin_time=T0,
            confirm_time=T1,
            timeframe=Timeframe.M15,
        ),
        candidate(
            "b",
            low="100.5",
            high="102",
            origin_time=T0 + timedelta(minutes=30),
            confirm_time=T2,
            timeframe=Timeframe.H1,
            scale=member_scale,
        ),
    )
    config = absolute_config(
        cluster_timeframe=Timeframe.W,
        cluster_scale=ScaleDescriptor("explicit-output", 8),
    )
    cluster = LevelPoolClusterer(config).build_as_of(pool_input(values), T2).clusters[0]
    assert cluster.price_range.low == Decimal("99")
    assert cluster.price_range.high == Decimal("102")
    assert cluster.origin_time == T0
    assert cluster.confirm_time == T2
    assert cluster.timeframe is Timeframe.W
    assert cluster.scale == ScaleDescriptor("explicit-output", 8)
    assert {item.timeframe for item in cluster.member_refs} == {
        Timeframe.M15,
        Timeframe.H1,
    }
    assert {item.scale for item in cluster.member_refs} == {
        values[0].scale,
        member_scale,
    }


def test_source_types_timeframes_families_and_all_refs_are_preserved() -> None:
    values = (
        candidate("s", source_type=StructureSourceType.SWING),
        candidate(
            "p",
            low="100.2",
            source_type=StructureSourceType.PERIODIC_EXTREME,
            timeframe=Timeframe.H4,
            structure_family="periodic-extreme-h4-v1",
        ),
        candidate(
            "r",
            low="100.4",
            source_type=StructureSourceType.HISTORICAL_REACTION,
            timeframe=Timeframe.D,
            structure_family="historical-reaction-baseline-v1",
        ),
    )
    snapshot = clusterer().build_as_of(pool_input(values), T1)
    cluster = snapshot.clusters[0]
    explanation = snapshot.explanations[0]
    assert len(cluster.member_refs) == 3
    assert explanation.source_types == (
        StructureSourceType.HISTORICAL_REACTION,
        StructureSourceType.PERIODIC_EXTREME,
        StructureSourceType.SWING,
    )
    assert set(explanation.timeframes) == {Timeframe.H1, Timeframe.H4, Timeframe.D}
    assert set(explanation.structure_families) == {
        "confirmed-pivot-strict-v1",
        "periodic-extreme-h4-v1",
        "historical-reaction-baseline-v1",
    }


def test_cluster_role_and_provenance_are_complete_and_bounded() -> None:
    values = (candidate("b", low="100.5"), candidate("a", low="100"))
    cluster = clusterer().build_as_of(pool_input(values), T1).clusters[0]
    assert cluster.market_role is MarketRole.RESISTANCE
    assert cluster.provenance.source_module == "msa.research.pool.clustering"
    assert cluster.provenance.policy_id == "range-gap-single-link-v1"
    assert cluster.provenance.parent_object_ids == ("a", "b")
    notes = "\n".join(cluster.provenance.notes)
    assert "effective_tolerance=1" in notes
    assert "dependency_groups=" in notes
    assert not hasattr(cluster.provenance, "__dict__")


def test_report_counts_singletons_merges_sources_and_timeframes() -> None:
    values = (
        candidate("a", low="100"),
        candidate("b", low="100.5"),
        candidate("c", low="110", timeframe=Timeframe.H4),
    )
    report = clusterer().build_as_of(pool_input(values), T1).report
    assert report.visible_candidate_count == 3
    assert report.cluster_count == 2
    assert report.singleton_cluster_count == 1
    assert report.merged_cluster_count == 1
    assert report.graph_edge_count == 1
    assert dict(report.source_type_counts) == {"SWING": 3}
    assert dict(report.timeframe_counts) == {"H1": 2, "H4": 1}


def test_reversed_and_fixed_permutations_are_identical() -> None:
    values = (
        candidate("a", low="100"),
        candidate("b", low="101"),
        candidate("c", low="110"),
        candidate("d", low="90", side=BoundarySide.LOWER),
    )
    baseline = clusterer().build_as_of(pool_input(values), T1).to_dict()
    for order in list(permutations(values))[:12] + [tuple(reversed(values))]:
        assert clusterer().build_as_of(pool_input(tuple(order)), T1).to_dict() == baseline


def test_cluster_id_is_deterministic_and_not_input_position_based() -> None:
    values = (candidate("a", low="100"), candidate("b", low="100.5"))
    first = clusterer().build_as_of(pool_input(values), T1).clusters[0]
    second = clusterer().build_as_of(pool_input(tuple(reversed(values))), T1).clusters[0]
    assert first.cluster_id == second.cluster_id
    assert first.to_dict() == second.to_dict()


def test_cluster_id_changes_for_member_fact_and_membership() -> None:
    base = (candidate("a", low="100"), candidate("b", low="100.5"))
    original = clusterer().build_as_of(pool_input(base), T1).clusters[0].cluster_id
    changed_fact = (
        candidate("a", low="100.1"),
        candidate("b", low="100.5"),
    )
    changed_member = base + (candidate("c", low="100.8"),)
    assert clusterer().build_as_of(pool_input(changed_fact), T1).clusters[0].cluster_id != original
    assert clusterer().build_as_of(pool_input(changed_member), T1).clusters[0].cluster_id != original


def test_cluster_id_changes_for_tolerance_family_and_context() -> None:
    values = (candidate("a", low="100"), candidate("b", low="100.5"))
    base_data = pool_input(values)
    original = clusterer().build_as_of(base_data, T1).clusters[0].cluster_id
    tolerance_changed = clusterer(absolute_tolerance=Decimal("2")).build_as_of(base_data, T1).clusters[0].cluster_id
    normalized_same_effective = LevelPoolClusterer(normalized_config()).build_as_of(base_data, T1).clusters[0].cluster_id
    family_changed = clusterer().build_as_of(
        pool_input(values, (assignment("a", "shared"), assignment("b", "shared"))),
        T1,
    ).clusters[0].cluster_id
    context_changed = clusterer(cluster_timeframe=Timeframe.D).build_as_of(base_data, T1).clusters[0].cluster_id
    assert len({original, tolerance_changed, normalized_same_effective, family_changed, context_changed}) == 5


def test_cluster_identity_has_sha256_shape_and_no_clock_or_random_fields() -> None:
    cluster_id = clusterer().build_as_of(pool_input((candidate(),)), T1).clusters[0].cluster_id
    assert cluster_id.startswith("structure-cluster-v1-")
    assert len(cluster_id.removeprefix("structure-cluster-v1-")) == 64
