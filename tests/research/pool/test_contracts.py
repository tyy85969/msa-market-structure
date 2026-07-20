from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import json

import pytest

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    PriceRange,
    ScaleDescriptor,
    StructureObjectKind,
    StructureSourceType,
)
from msa.research.pool import (
    LevelPoolClusteringError,
    DependencyFamilyAssignment,
    LevelPoolConfig,
    LevelPoolConfigurationError,
    LevelPoolInput,
    LevelPoolInputError,
    LevelPoolSerializationError,
    LinkageMode,
    ToleranceMode,
)
from tests.research.pool.fixtures import (
    SCALE,
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


@pytest.mark.parametrize("kind", ["absolute", "normalized"])
def test_valid_config_round_trip_is_exact(kind: str) -> None:
    config = absolute_config() if kind == "absolute" else normalized_config()
    payload = config.to_dict()
    assert LevelPoolConfig.from_dict(payload) == config
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        config.to_dict(), sort_keys=True
    )


def test_absolute_zero_tolerance_is_valid() -> None:
    assert absolute_config(absolute_tolerance=Decimal("0")).effective_tolerance == 0


def test_normalized_zero_multiplier_is_valid() -> None:
    config = normalized_config(normalized_tolerance=Decimal("0"))
    assert config.effective_tolerance == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalization_unit", Decimal("0")),
        ("normalization_unit", Decimal("NaN")),
        ("normalized_tolerance", Decimal("-0.1")),
    ],
)
def test_invalid_normalized_decimal_is_rejected(field: str, value: object) -> None:
    with pytest.raises(LevelPoolConfigurationError, match=field):
        normalized_config(**{field: value})


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (absolute_config, "absolute_tolerance"),
        (normalized_config, "normalization_unit"),
        (normalized_config, "normalized_tolerance"),
    ],
)
def test_float_decimal_configuration_is_rejected(factory, field: str) -> None:
    with pytest.raises(LevelPoolConfigurationError, match="Decimal"):
        factory(**{field: 1.0})


def test_strict_false_is_rejected() -> None:
    with pytest.raises(LevelPoolConfigurationError, match="strict must be True"):
        absolute_config(strict=False)


def test_unknown_linkage_is_rejected_during_deserialization() -> None:
    payload = absolute_config().to_dict()
    payload["linkage_mode"] = "COMPLETE_LINK"
    with pytest.raises(LevelPoolSerializationError, match="invalid serialized"):
        LevelPoolConfig.from_dict(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"normalization_unit": Decimal("1")},
        {"normalized_tolerance": Decimal("1")},
        {
            "tolerance_mode": ToleranceMode.NORMALIZED,
            "absolute_tolerance": Decimal("1"),
            "normalization_unit": Decimal("1"),
            "normalized_tolerance": Decimal("1"),
        },
    ],
)
def test_illegal_tolerance_field_combinations_fail(overrides: dict) -> None:
    with pytest.raises(LevelPoolConfigurationError):
        absolute_config(**overrides)


@pytest.mark.parametrize("field", ["pool_id", "pool_version", "policy_id"])
def test_empty_config_identifiers_fail(field: str) -> None:
    with pytest.raises(LevelPoolConfigurationError, match=field):
        absolute_config(**{field: ""})


def test_config_requires_explicit_cluster_context() -> None:
    with pytest.raises(LevelPoolConfigurationError, match="cluster_timeframe"):
        absolute_config(cluster_timeframe="H4")
    with pytest.raises(LevelPoolConfigurationError, match="cluster_scale"):
        absolute_config(cluster_scale=None)


def test_config_and_enums_are_frozen_versioned_public_values() -> None:
    config = absolute_config()
    with pytest.raises(FrozenInstanceError):
        config.strict = False  # type: ignore[misc]
    assert ToleranceMode.from_dict(ToleranceMode.ABSOLUTE.to_dict()) is ToleranceMode.ABSOLUTE
    assert LinkageMode.from_dict(LinkageMode.SINGLE_LINK.to_dict()) is LinkageMode.SINGLE_LINK


@pytest.mark.parametrize(
    "source_type",
    [
        StructureSourceType.SWING,
        StructureSourceType.PERIODIC_EXTREME,
        StructureSourceType.HISTORICAL_REACTION,
    ],
)
def test_all_supported_candidate_sources_are_valid(source_type) -> None:
    assert pool_input((candidate(source_type=source_type),)).candidates[0].source_type is source_type


def test_mixed_timeframe_and_scale_are_valid() -> None:
    values = (
        candidate("a", timeframe=Timeframe.M15),
        candidate("b", timeframe=Timeframe.H4, scale=ScaleDescriptor("other", 9)),
    )
    assert len(pool_input(values).candidates) == 2


def test_mixed_symbol_and_duplicate_id_are_rejected() -> None:
    with pytest.raises(LevelPoolInputError, match="same symbol"):
        pool_input((candidate("a"), candidate("b", symbol="EURUSD")))
    with pytest.raises(LevelPoolInputError, match="unique"):
        pool_input((candidate("same"), candidate("same", low="101")))


def test_empty_candidate_pool_is_rejected() -> None:
    with pytest.raises(LevelPoolInputError, match="must not be empty"):
        LevelPoolInput(())


def test_forming_candidate_is_rejected() -> None:
    forming = candidate(
        confirmation_status=ConfirmationStatus.FORMING,
        lifecycle_state=LifecycleState.CANDIDATE,
        confirm_time=None,
    )
    with pytest.raises(LevelPoolInputError, match="CONFIRMED"):
        pool_input((forming,))


@pytest.mark.parametrize(
    "state",
    [
        LifecycleState.FRESH,
        LifecycleState.TESTED,
        LifecycleState.WEAKENED,
        LifecycleState.BROKEN,
        LifecycleState.FLIPPED,
        LifecycleState.RETIRED,
    ],
)
def test_post_c005_lifecycle_states_are_rejected(state: LifecycleState) -> None:
    with pytest.raises(LevelPoolInputError, match="exactly CONFIRMED"):
        pool_input((candidate(lifecycle_state=state),))


@pytest.mark.parametrize(
    ("side", "wrong_role"),
    [
        (BoundarySide.UPPER, MarketRole.SUPPORT),
        (BoundarySide.LOWER, MarketRole.RESISTANCE),
    ],
)
def test_side_role_mismatch_is_rejected(side, wrong_role) -> None:
    with pytest.raises(LevelPoolInputError, match="side/role"):
        pool_input((candidate(side=side, role=wrong_role),))


def test_unsupported_source_type_is_rejected_fail_closed() -> None:
    value = candidate()
    object.__setattr__(value, "source_type", "OTHER")
    with pytest.raises(LevelPoolInputError, match="unsupported"):
        pool_input((value,))


def test_input_tuple_and_candidates_are_not_modified() -> None:
    values = (candidate("b", low="101"), candidate("a", low="100"))
    before = tuple(item.to_dict() for item in values)
    data = pool_input(values)
    assert data.candidates is values
    assert tuple(item.to_dict() for item in values) == before


def test_assignment_and_input_round_trip() -> None:
    data = pool_input((candidate("a"),), (assignment("a"),))
    assert LevelPoolInput.from_dict(data.to_dict()) == data
    assert DependencyFamilyAssignment.from_dict(
        data.family_assignments[0].to_dict()
    ) == data.family_assignments[0]


@pytest.mark.parametrize("kind", ["config", "input", "assignment"])
def test_unknown_field_and_schema_are_rejected(kind: str) -> None:
    if kind == "config":
        payload = absolute_config().to_dict()
        factory = LevelPoolConfig.from_dict
    elif kind == "input":
        payload = pool_input((candidate(),)).to_dict()
        factory = LevelPoolInput.from_dict
    else:
        payload = assignment("candidate-a").to_dict()
        factory = DependencyFamilyAssignment.from_dict
    payload["future"] = True
    with pytest.raises(LevelPoolSerializationError, match="unknown fields"):
        factory(payload)
    del payload["future"]
    payload["schema_version"] = 2
    with pytest.raises(LevelPoolSerializationError, match="schema_version"):
        factory(payload)


def test_serialized_tuples_require_ordered_lists() -> None:
    payload = pool_input((candidate(),)).to_dict()
    payload["candidates"] = tuple(payload["candidates"])
    with pytest.raises(LevelPoolSerializationError, match="ordered list"):
        LevelPoolInput.from_dict(payload)


def test_fixture_scale_is_not_inferred_from_timeframe() -> None:
    assert candidate(timeframe=Timeframe.W).scale == SCALE


def coherent_snapshot():
    return clusterer().build_as_of(
        pool_input(
            (
                candidate("a", low="100", confirm_time=T1),
                candidate("b", low="100.5", confirm_time=T1),
            )
        ),
        T1,
    )


@pytest.mark.parametrize(
    "visible_ids",
    [
        ("a", "b", "ghost"),
        ("a",),
        ("ghost",),
    ],
)
def test_snapshot_rejects_visible_and_cluster_member_partition_mismatch(
    visible_ids: tuple[str, ...],
) -> None:
    with pytest.raises(LevelPoolClusteringError, match="exactly partition"):
        replace(coherent_snapshot(), visible_candidate_ids=visible_ids)


def test_snapshot_rejects_candidate_membership_in_two_clusters() -> None:
    snapshot = clusterer().build_as_of(pool_input((candidate("a"),)), T1)
    duplicate_cluster = replace(
        snapshot.clusters[0], cluster_id="duplicate-membership-cluster"
    )
    duplicate_explanation = replace(
        snapshot.explanations[0], cluster_id="duplicate-membership-cluster"
    )
    with pytest.raises(LevelPoolClusteringError, match="exactly one cluster"):
        replace(
            snapshot,
            clusters=(snapshot.clusters[0], duplicate_cluster),
            explanations=(snapshot.explanations[0], duplicate_explanation),
        )


def test_snapshot_rejects_non_candidate_member_reference() -> None:
    snapshot = clusterer().build_as_of(pool_input((candidate("a"),)), T1)
    cluster = snapshot.clusters[0]
    nested_ref = replace(
        cluster.member_refs[0],
        object_kind=StructureObjectKind.STRUCTURE_CLUSTER,
    )
    nested_cluster = replace(cluster, member_refs=(nested_ref,))
    with pytest.raises(LevelPoolClusteringError, match="LEVEL_CANDIDATE"):
        replace(snapshot, clusters=(nested_cluster,))


def test_valid_clusters_exactly_partition_visible_candidates() -> None:
    snapshot = coherent_snapshot()
    member_ids = tuple(
        sorted(
            member.object_id
            for cluster in snapshot.clusters
            for member in cluster.member_refs
        )
    )
    assert member_ids == snapshot.visible_candidate_ids
    assert len(member_ids) == len(set(member_ids))


@pytest.mark.parametrize(
    "field_name",
    [
        "member_candidate_ids",
        "raw_member_count",
        "boundary_side",
        "price_range",
        "origin_time",
        "confirm_time",
        "source_types",
        "timeframes",
        "member_scales",
        "structure_families",
        "effective_tolerance",
        "tolerance_mode",
        "linkage_mode",
    ],
)
def test_snapshot_rejects_explanation_fact_mismatch(field_name: str) -> None:
    snapshot = clusterer().build_as_of(pool_input((candidate("a"),)), T1)
    explanation = replace(snapshot.explanations[0])
    mismatches = {
        "member_candidate_ids": ("ghost",),
        "raw_member_count": 2,
        "boundary_side": BoundarySide.LOWER,
        "price_range": PriceRange(Decimal("90"), Decimal("90")),
        "origin_time": T0.replace(minute=1),
        "confirm_time": T2,
        "source_types": (StructureSourceType.PERIODIC_EXTREME,),
        "timeframes": (Timeframe.H4,),
        "member_scales": (ScaleDescriptor("other-scale", 9),),
        "structure_families": ("other-family",),
        "effective_tolerance": Decimal("2"),
        "tolerance_mode": ToleranceMode.NORMALIZED,
        "linkage_mode": "COMPLETE_LINK",
    }
    object.__setattr__(explanation, field_name, mismatches[field_name])
    with pytest.raises(LevelPoolClusteringError, match="explanation"):
        replace(snapshot, explanations=(explanation,))
