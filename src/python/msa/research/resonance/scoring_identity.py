"""Private canonical identities for C-007B resonance scoring."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping, Sequence


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _component_id(
    *,
    engine_id: str,
    engine_version: str,
    policy_id: str,
    member_evidence_ids: Sequence[str],
    shared_family_ids: Sequence[str],
    schema_version: int,
) -> str:
    identity = {
        "engine_id": engine_id,
        "engine_version": engine_version,
        "policy_id": policy_id,
        "member_evidence_ids": list(member_evidence_ids),
        "shared_family_ids": list(shared_family_ids),
        "schema_version": schema_version,
    }
    return f"resonance-dependency-component-v1-{_digest(identity)}"


def _contribution_id(
    *,
    config: Mapping[str, object],
    evidence_id: str,
    subject_id: str,
    lifecycle_state_id: str,
    context: Mapping[str, object],
    side: str,
    tier: str,
    lifecycle_state: str,
    direction: str,
    direction_relation: str,
    context_weight: str,
    tier_weight: str,
    lifecycle_weight: str,
    age_seconds: str,
    freshness_factor: str,
    touch_count: int,
    extra_touches: int,
    touch_factor: str,
    direction_factor: str,
    raw_contribution: str,
    dependency_component_id: str,
    schema_version: int,
) -> str:
    identity = {
        "config": dict(config),
        "evidence_id": evidence_id,
        "subject_id": subject_id,
        "lifecycle_state_id": lifecycle_state_id,
        "context": dict(context),
        "side": side,
        "tier": tier,
        "lifecycle_state": lifecycle_state,
        "direction": direction,
        "direction_relation": direction_relation,
        "context_weight": context_weight,
        "tier_weight": tier_weight,
        "lifecycle_weight": lifecycle_weight,
        "age_seconds": age_seconds,
        "freshness_factor": freshness_factor,
        "touch_count": touch_count,
        "extra_touches": extra_touches,
        "touch_factor": touch_factor,
        "direction_factor": direction_factor,
        "raw_contribution": raw_contribution,
        "dependency_component_id": dependency_component_id,
        "schema_version": schema_version,
    }
    return f"resonance-contribution-v1-{_digest(identity)}"


def _zone_key_id(
    *,
    engine_id: str,
    engine_version: str,
    policy_id: str,
    side: str,
    price_range: Mapping[str, object],
    member_subject_ids: Sequence[str],
    member_boundary_ranges: Sequence[Mapping[str, object]],
    schema_version: int,
) -> str:
    identity = {
        "engine_id": engine_id,
        "engine_version": engine_version,
        "policy_id": policy_id,
        "side": side,
        "price_range": dict(price_range),
        "member_subject_ids": list(member_subject_ids),
        "member_boundary_ranges": [dict(item) for item in member_boundary_ranges],
        "schema_version": schema_version,
    }
    return f"resonance-zone-key-v1-{_digest(identity)}"


def _zone_snapshot_id(
    *,
    source_frame_id: str,
    config: Mapping[str, object],
    zone_key_id: str,
    member_evidence_ids: Sequence[str],
    contribution_ids: Sequence[str],
    dependency_component_ids: Sequence[str],
    scores: Mapping[str, object],
    price_relation: str,
    distance: str,
    resonance_class: str,
    schema_version: int,
) -> str:
    identity = {
        "source_frame_id": source_frame_id,
        "config": dict(config),
        "zone_key_id": zone_key_id,
        "member_evidence_ids": list(member_evidence_ids),
        "contribution_ids": list(contribution_ids),
        "dependency_component_ids": list(dependency_component_ids),
        "scores": dict(scores),
        "price_relation": price_relation,
        "distance": distance,
        "resonance_class": resonance_class,
        "schema_version": schema_version,
    }
    return f"resonance-zone-snapshot-v1-{_digest(identity)}"


def _score_frame_id(
    *,
    source_frame_id: str,
    as_of_time: str,
    config: Mapping[str, object],
    zone_snapshot_ids: Sequence[str],
    report: Mapping[str, object],
    schema_version: int,
) -> str:
    identity = {
        "source_frame_id": source_frame_id,
        "as_of_time": as_of_time,
        "config": dict(config),
        "zone_snapshot_ids": list(zone_snapshot_ids),
        "report": dict(report),
        "schema_version": schema_version,
    }
    return f"resonance-score-frame-v1-{_digest(identity)}"
