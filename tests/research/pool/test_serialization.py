from dataclasses import FrozenInstanceError
from decimal import Decimal
import json
from pathlib import Path

import pytest

from msa.domain import StructureCluster
from msa.research.pool import (
    ClusterExplanation,
    ClusterFormationEvent,
    DependencyGroup,
    LevelPoolClusterer,
    LevelPoolHistory,
    LevelPoolReport,
    LevelPoolSerializationError,
    LevelPoolSnapshot,
)
from tests.research.pool.fixtures import (
    T1,
    T2,
    assignment,
    candidate,
    clusterer,
    pool_input,
)


def objects():
    data = pool_input(
        (
            candidate("a", confirm_time=T1),
            candidate("b", low="100.5", confirm_time=T2),
        ),
        (assignment("a", "shared"), assignment("b", "shared")),
    )
    engine = clusterer()
    history = engine.build_batch(data)
    snapshot = history.final_snapshot
    explanation = snapshot.explanations[0]
    event = history.formation_events[-1]
    return {
        "clusterer": (engine, LevelPoolClusterer.from_dict),
        "cluster": (snapshot.clusters[0], StructureCluster.from_dict),
        "group": (explanation.dependency_groups[0], DependencyGroup.from_dict),
        "explanation": (explanation, ClusterExplanation.from_dict),
        "report": (snapshot.report, LevelPoolReport.from_dict),
        "snapshot": (snapshot, LevelPoolSnapshot.from_dict),
        "event": (event, ClusterFormationEvent.from_dict),
        "history": (history, LevelPoolHistory.from_dict),
    }


@pytest.mark.parametrize(
    "kind",
    [
        "clusterer",
        "cluster",
        "group",
        "explanation",
        "report",
        "snapshot",
        "event",
        "history",
    ],
)
def test_public_objects_round_trip_deterministically(kind: str) -> None:
    value, factory = objects()[kind]
    payload = value.to_dict()
    restored = factory(payload)
    assert restored == value
    assert json.dumps(restored.to_dict(), sort_keys=True) == json.dumps(
        payload, sort_keys=True
    )


@pytest.mark.parametrize(
    "kind",
    ["clusterer", "group", "explanation", "report", "snapshot", "event", "history"],
)
def test_unknown_field_and_schema_fail_closed(kind: str) -> None:
    value, factory = objects()[kind]
    payload = value.to_dict()
    payload["future"] = True
    with pytest.raises(LevelPoolSerializationError, match="unknown fields"):
        factory(payload)
    del payload["future"]
    payload["schema_version"] = 999
    with pytest.raises(LevelPoolSerializationError, match="schema_version"):
        factory(payload)


@pytest.mark.parametrize(
    ("kind", "field"),
    [
        ("group", "member_candidate_ids"),
        ("explanation", "dependency_groups"),
        ("report", "assumptions"),
        ("snapshot", "clusters"),
        ("event", "supersedes_cluster_ids"),
        ("history", "formation_events"),
    ],
)
def test_tuple_serialization_contract_requires_ordered_lists(kind: str, field: str) -> None:
    value, factory = objects()[kind]
    payload = value.to_dict()
    payload[field] = tuple(payload[field])
    with pytest.raises(LevelPoolSerializationError, match="ordered list"):
        factory(payload)


def test_nested_values_are_immutable_and_mapping_free() -> None:
    history = objects()["history"][0]
    with pytest.raises(FrozenInstanceError):
        history.final_snapshot = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        history.formation_events[0].supersedes_cluster_ids = ()  # type: ignore[misc]
    assert isinstance(history.formation_events, tuple)
    assert isinstance(history.final_snapshot.clusters, tuple)
    assert isinstance(history.final_snapshot.explanations[0].dependency_groups, tuple)


def test_public_payload_uses_decimal_strings_and_utc_times() -> None:
    snapshot = objects()["snapshot"][0]
    payload = snapshot.to_dict()
    explanation = payload["explanations"][0]
    assert isinstance(explanation["effective_tolerance"], str)
    assert payload["as_of_time"].endswith("+00:00")
    assert explanation["origin_time"].endswith("+00:00")


def test_source_has_no_pickle_clock_uuid_or_builtin_hash_identity() -> None:
    source_dir = Path("src/python/msa/research/pool")
    text = "\n".join(path.read_text(encoding="utf-8") for path in source_dir.glob("*.py"))
    assert "pickle" not in text.lower()
    assert "datetime.now" not in text
    assert "uuid4" not in text
    assert "hash(" not in text


@pytest.mark.parametrize(
    "kind",
    [
        "snapshot-membership",
        "snapshot-member-kind",
        "snapshot-explanation",
        "history-missing-supersedes",
        "history-future-supersedes",
        "history-final-event",
    ],
)
def test_contradictory_nested_payloads_fail_as_serialization_errors(
    kind: str,
) -> None:
    if kind.startswith("snapshot"):
        value, factory = objects()["snapshot"]
        payload = value.to_dict()
        if kind == "snapshot-membership":
            payload["visible_candidate_ids"].append("ghost")
        elif kind == "snapshot-member-kind":
            payload["clusters"][0]["member_refs"][0]["object_kind"] = (
                "STRUCTURE_CLUSTER"
            )
        else:
            payload["explanations"][0]["boundary_side"] = "LOWER"
    else:
        value, factory = objects()["history"]
        payload = value.to_dict()
        if kind == "history-missing-supersedes":
            payload["formation_events"][-1]["supersedes_cluster_ids"] = [
                "missing-cluster"
            ]
        elif kind == "history-future-supersedes":
            future_id = payload["formation_events"][-1]["cluster"]["cluster_id"]
            payload["formation_events"][0]["supersedes_cluster_ids"] = [future_id]
        else:
            payload["formation_events"] = payload["formation_events"][:-1]
    with pytest.raises(LevelPoolSerializationError):
        factory(payload)


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
def test_serialized_explanation_mismatch_is_wrapped(
    field_name: str,
) -> None:
    snapshot = objects()["snapshot"][0]
    payload = snapshot.to_dict()
    explanation = payload["explanations"][0]
    mismatches = {
        "member_candidate_ids": ["ghost"],
        "raw_member_count": 99,
        "boundary_side": "LOWER",
        "price_range": {
            "schema_version": 1,
            "low": "90",
            "high": "90",
        },
        "origin_time": T1.isoformat(),
        "confirm_time": T1.isoformat(),
        "source_types": ["PERIODIC_EXTREME"],
        "timeframes": ["H4"],
        "member_scales": [
            {"schema_version": 1, "scale_id": "other", "rank": 8}
        ],
        "structure_families": ["other-family"],
        "effective_tolerance": str(Decimal("2")),
        "tolerance_mode": "NORMALIZED",
        "linkage_mode": "COMPLETE_LINK",
    }
    explanation[field_name] = mismatches[field_name]
    with pytest.raises(LevelPoolSerializationError):
        LevelPoolSnapshot.from_dict(payload)


def test_serialized_duplicate_cluster_membership_is_wrapped() -> None:
    snapshot = clusterer().build_as_of(pool_input((candidate("a"),)), T1)
    payload = snapshot.to_dict()
    duplicate_cluster = dict(payload["clusters"][0])
    duplicate_cluster["cluster_id"] = "duplicate-cluster"
    duplicate_explanation = dict(payload["explanations"][0])
    duplicate_explanation["cluster_id"] = "duplicate-cluster"
    payload["clusters"].append(duplicate_cluster)
    payload["explanations"].append(duplicate_explanation)
    with pytest.raises(LevelPoolSerializationError):
        LevelPoolSnapshot.from_dict(payload)


def test_serialized_supersedes_without_shared_member_is_wrapped() -> None:
    history = clusterer().build_batch(
        pool_input(
            (
                candidate("a", low="100", confirm_time=T1),
                candidate("b", low="110", confirm_time=T2),
            )
        )
    )
    payload = history.to_dict()
    old_id = payload["formation_events"][0]["cluster"]["cluster_id"]
    payload["formation_events"][1]["supersedes_cluster_ids"] = [old_id]
    with pytest.raises(LevelPoolSerializationError):
        LevelPoolHistory.from_dict(payload)
