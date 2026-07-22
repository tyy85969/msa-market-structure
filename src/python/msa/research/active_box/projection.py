"""Formal ResonanceZone -> StructureCluster -> BoundaryRef projection."""

from __future__ import annotations

from datetime import datetime

from msa.domain import (
    BoundarySide,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    StructureCluster,
)
from msa.research.resonance import ResonanceScoreFrame, ResonanceZone

from .contracts import (
    SCHEMA_VERSION,
    ActiveBoxSelectionConfig,
    ActiveBoxZoneProjection,
)
from .errors import ActiveBoxProjectionError
from .identity import semantic_id


_MODULE = "msa.research.active_box.projection"


def project_zone(
    source_score_frame: ResonanceScoreFrame,
    zone: ResonanceZone,
    config: ActiveBoxSelectionConfig,
    selection_confirm_time: datetime,
) -> ActiveBoxZoneProjection:
    if not isinstance(source_score_frame, ResonanceScoreFrame):
        raise ActiveBoxProjectionError("source_score_frame must be a ResonanceScoreFrame")
    if not isinstance(zone, ResonanceZone) or not isinstance(config, ActiveBoxSelectionConfig):
        raise ActiveBoxProjectionError("zone/config type is invalid")
    if selection_confirm_time != source_score_frame.as_of_time:
        raise ActiveBoxProjectionError("selection_confirm_time must equal source ScoreFrame AsOf")
    if config.symbol != source_score_frame.source_frame.config_snapshot.symbol:
        raise ActiveBoxProjectionError("config symbol conflicts with source ScoreFrame")
    source_zone = next(
        (item for item in source_score_frame.zones if item.zone_key_id == zone.zone_key_id),
        None,
    )
    if source_zone is None or source_zone != zone or zone.source_frame_id != source_score_frame.source_frame_id:
        raise ActiveBoxProjectionError("Zone is not the exact current source ScoreFrame Zone")
    evidence_by_id = {
        item.evidence_id: item for item in source_score_frame.source_frame.evidence
    }
    if len(evidence_by_id) != len(source_score_frame.source_frame.evidence):
        raise ActiveBoxProjectionError("source Frame Evidence IDs must be unique")
    try:
        selected_evidence = tuple(evidence_by_id[item] for item in zone.member_evidence_ids)
    except KeyError as exc:
        raise ActiveBoxProjectionError("Zone member Evidence is missing from source Frame") from exc
    if tuple(sorted(item.evidence_id for item in selected_evidence)) != tuple(sorted(zone.member_evidence_ids)):
        raise ActiveBoxProjectionError("projection Evidence coverage is not exact")
    if not selected_evidence:
        raise ActiveBoxProjectionError("projection members must not be empty")
    if any(item.boundary.boundary_side is not zone.side for item in selected_evidence):
        raise ActiveBoxProjectionError("projection member side conflicts with Zone")
    members = tuple(sorted((item.boundary for item in selected_evidence), key=lambda item: item.object_id))
    if len({item.object_id for item in members}) != len(members):
        raise ActiveBoxProjectionError("projection Boundary IDs must be unique")
    if any(item.confirm_time > selection_confirm_time for item in members):
        raise ActiveBoxProjectionError("projection cannot use a future member")
    envelope = PriceRange(
        low=min(item.price_range.low for item in members),
        high=max(item.price_range.high for item in members),
    )
    if envelope != zone.price_range:
        raise ActiveBoxProjectionError("projection range must equal the complete Zone envelope")
    evidence_ids = tuple(sorted(item.evidence_id for item in selected_evidence))
    boundary_ids = tuple(item.object_id for item in members)
    family = f"active-box-zone-v1:{zone.zone_key_id}"
    cluster_payload = {
        "config": config.to_dict(), "source_score_frame_id": source_score_frame.score_frame_id,
        "source_zone_key_id": zone.zone_key_id, "source_zone_snapshot_id": zone.zone_snapshot_id,
        "selection_confirm_time": selection_confirm_time.isoformat(),
        "symbol": config.symbol, "timeframe": config.output_timeframe.value,
        "scale": config.output_scale.to_dict(), "price_range": zone.price_range.to_dict(),
        "boundary_side": zone.side.value,
        "market_role": (MarketRole.RESISTANCE if zone.side is BoundarySide.UPPER else MarketRole.SUPPORT).value,
        "lifecycle_state": LifecycleState.CONFIRMED.value,
        "origin_time": min(item.origin_time for item in members).isoformat(),
        "member_refs": [item.to_dict() for item in members], "cluster_family": family,
        "schema_version": SCHEMA_VERSION,
    }
    cluster_id = semantic_id("active-box-zone-cluster-v1-", cluster_payload)
    parents = (
        source_score_frame.score_frame_id, zone.zone_snapshot_id,
        *evidence_ids, *boundary_ids,
    )
    cluster_provenance = ProvenanceRef(
        source_module=_MODULE, source_version=config.engine_version,
        source_object_id=cluster_id, policy_id=config.policy_id,
        parent_object_ids=parents, notes=(f"engine_id={config.engine_id}",),
    )
    try:
        cluster = StructureCluster(
            cluster_id=cluster_id, symbol=config.symbol,
            timeframe=config.output_timeframe, scale=config.output_scale,
            price_range=zone.price_range, boundary_side=zone.side,
            market_role=MarketRole.RESISTANCE if zone.side is BoundarySide.UPPER else MarketRole.SUPPORT,
            lifecycle_state=LifecycleState.CONFIRMED,
            origin_time=min(item.origin_time for item in members),
            confirm_time=selection_confirm_time, member_refs=members,
            cluster_family=family, provenance=cluster_provenance,
        )
        boundary = cluster.to_boundary_ref()
    except (TypeError, ValueError) as exc:
        raise ActiveBoxProjectionError(f"invalid formal StructureCluster projection: {exc}") from exc
    projection_payload = {
        "config": config.to_dict(), "source_score_frame_id": source_score_frame.score_frame_id,
        "source_zone_key_id": zone.zone_key_id, "source_zone_snapshot_id": zone.zone_snapshot_id,
        "selection_confirm_time": selection_confirm_time.isoformat(), "cluster": cluster.to_dict(),
        "boundary": boundary.to_dict(), "member_evidence_ids": list(evidence_ids),
        "member_boundary_ids": list(boundary_ids), "schema_version": SCHEMA_VERSION,
    }
    projection_id = semantic_id("active-box-projection-v1-", projection_payload)
    projection_provenance = ProvenanceRef(
        source_module=_MODULE, source_version=config.engine_version,
        source_object_id=projection_id, policy_id=config.policy_id,
        parent_object_ids=parents, notes=(f"engine_id={config.engine_id}",),
    )
    try:
        return ActiveBoxZoneProjection(
            projection_id=projection_id,
            source_score_frame_id=source_score_frame.score_frame_id,
            source_zone_key_id=zone.zone_key_id,
            source_zone_snapshot_id=zone.zone_snapshot_id,
            selection_confirm_time=selection_confirm_time,
            cluster=cluster, boundary=boundary, provenance=projection_provenance,
            config_snapshot=config, member_evidence_ids=evidence_ids,
            member_boundary_ids=boundary_ids,
        )
    except (TypeError, ValueError) as exc:
        raise ActiveBoxProjectionError(f"invalid ActiveBoxZoneProjection: {exc}") from exc
