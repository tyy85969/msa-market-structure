from copy import deepcopy
from decimal import Decimal

import pytest

from msa.data import Timeframe
from msa.domain import BoundarySide, LifecycleState, MarketRole, StructureCluster, StructureObjectKind, StructureSourceType
from msa.research.active_box import ActiveBoxProjectionError, ActiveBoxZoneProjection, project_zone
from msa.research.active_box.identity import cluster_identity_payload, semantic_id
from msa.research.active_box.projection import validate_zone_projection
from msa.research.resonance import ResonanceScorer
from tests.research.resonance.fixtures import H4_PRIMARY, H12_MACRO, MACRO, START, bar, custom_bundle, subject
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import config, initial_frame, score_frame


@pytest.mark.parametrize(("side","role"),[(BoundarySide.UPPER,MarketRole.RESISTANCE),(BoundarySide.LOWER,MarketRole.SUPPORT)])
def test_projection_is_formal_cluster_boundary_with_explicit_context(side,role) -> None:
    frame=score_frame(); zone=(frame.upper_zones if side is BoundarySide.UPPER else frame.lower_zones)[0]
    result=project_zone(frame,zone,config(),frame.as_of_time)
    assert result.boundary==result.cluster.to_boundary_ref()
    assert result.boundary.object_kind is StructureObjectKind.STRUCTURE_CLUSTER
    assert result.cluster.lifecycle_state is LifecycleState.CONFIRMED
    assert result.boundary.market_role is role
    assert result.boundary.price_range==zone.price_range
    assert result.boundary.timeframe is config().output_timeframe
    assert result.boundary.scale==config().output_scale
    assert result.boundary.confirm_time==frame.as_of_time


def test_projection_exactly_covers_zone_members_and_earliest_origin() -> None:
    projection=initial_frame().active_box_snapshot.upper_projection
    evidence={item.evidence_id:item for item in initial_frame().source_score_frame.source_frame.evidence}
    expected=tuple(sorted(evidence[item].boundary.object_id for item in projection.member_evidence_ids))
    assert projection.member_boundary_ids==expected
    assert projection.cluster.origin_time==min(item.origin_time for item in projection.cluster.member_refs)
    assert projection.cluster.cluster_family=="active-box-zone-v1:"+projection.source_zone_key_id


def test_cross_timeframe_zone_members_project_without_context_inference() -> None:
    subjects=(
        subject("h4",BoundarySide.UPPER,"110","111",source_types=(StructureSourceType.SWING,),families=("a",)),
        subject("h12",BoundarySide.UPPER,"110.5","111.5",timeframe=Timeframe.H12,scale=MACRO,source_types=(StructureSourceType.PERIODIC_EXTREME,),families=("b",)),
    )
    engine,data=custom_bundle(subjects,(bar(-1),),(H4_PRIMARY,H12_MACRO))
    frame=ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,H12_MACRO))).score_frame(engine.build_as_of(data,START))
    zone=frame.upper_zones[0]; result=project_zone(frame,zone,config(),frame.as_of_time)
    assert len(result.cluster.timeframes)==2
    assert result.cluster.timeframe is config().output_timeframe


def test_future_selection_time_and_non_source_zone_fail_closed() -> None:
    frame=score_frame(); zone=frame.upper_zones[0]
    with pytest.raises(ActiveBoxProjectionError,match="must equal"): project_zone(frame,zone,config(),frame.as_of_time.replace(hour=frame.as_of_time.hour+1))
    other=score_frame(at=frame.as_of_time.replace(hour=frame.as_of_time.hour+1)).upper_zones[0]
    with pytest.raises(ActiveBoxProjectionError,match="not the exact"): project_zone(frame,other,config(),frame.as_of_time)


def test_projection_round_trip_and_arbitrary_identity_rejected() -> None:
    value=initial_frame().active_box_snapshot.lower_projection
    assert ActiveBoxZoneProjection.from_dict(value.to_dict())==value
    payload=value.to_dict(); payload["projection_id"]="active-box-projection-v1-"+"0"*64; payload["provenance"]["source_object_id"]=payload["projection_id"]
    with pytest.raises(Exception,match="projection_id"): ActiveBoxZoneProjection.from_dict(payload)


def _resign_projection(payload, *, recompute_cluster: bool = True):
    payload=deepcopy(payload)
    parents=sorted(set((payload["source_score_frame_id"],payload["source_zone_snapshot_id"],
        *payload["member_evidence_ids"],*payload["member_boundary_ids"])))
    payload["cluster"]["provenance"]["parent_object_ids"]=parents
    payload["provenance"]["parent_object_ids"]=parents
    cluster=StructureCluster.from_dict(payload["cluster"])
    if recompute_cluster:
        cluster_id=semantic_id("active-box-zone-cluster-v1-",cluster_identity_payload(
            config=config(),source_score_frame_id=payload["source_score_frame_id"],source_zone_key_id=payload["source_zone_key_id"],
            source_zone_snapshot_id=payload["source_zone_snapshot_id"],selection_confirm_time=cluster.confirm_time,symbol=cluster.symbol,
            timeframe=cluster.timeframe,scale=cluster.scale,price_range=cluster.price_range,boundary_side=cluster.boundary_side,
            market_role=cluster.market_role,lifecycle_state=cluster.lifecycle_state,origin_time=cluster.origin_time,member_refs=cluster.member_refs,
            cluster_family=cluster.cluster_family,schema_version=1))
        payload["cluster"]["cluster_id"]=cluster_id
    payload["cluster"]["provenance"]["source_object_id"]=payload["cluster"]["cluster_id"]
    cluster=StructureCluster.from_dict(payload["cluster"])
    payload["boundary"]=cluster.to_boundary_ref().to_dict()
    identity={"config":payload["config_snapshot"],"source_score_frame_id":payload["source_score_frame_id"],"source_zone_key_id":payload["source_zone_key_id"],
        "source_zone_snapshot_id":payload["source_zone_snapshot_id"],"selection_confirm_time":payload["selection_confirm_time"],"cluster":payload["cluster"],
        "boundary":payload["boundary"],"member_evidence_ids":payload["member_evidence_ids"],"member_boundary_ids":payload["member_boundary_ids"],"schema_version":1}
    payload["projection_id"]=semantic_id("active-box-projection-v1-",identity)
    payload["provenance"]["source_object_id"]=payload["projection_id"]
    return payload


def test_fully_resigned_arbitrary_cluster_id_is_rejected() -> None:
    payload=initial_frame().active_box_snapshot.upper_projection.to_dict()
    payload["cluster"]["cluster_id"]="active-box-zone-cluster-v1-"+"a"*64
    payload=_resign_projection(payload,recompute_cluster=False)
    with pytest.raises(Exception,match="cluster_id"): ActiveBoxZoneProjection.from_dict(payload)


@pytest.mark.parametrize(("field","value","message"),[
    ("cluster_family","active-box-zone-v1:wrong","family"),
    ("market_role","SUPPORT","role"),
])
def test_fully_resigned_cluster_semantic_attacks_are_rejected(field,value,message) -> None:
    payload=initial_frame().active_box_snapshot.upper_projection.to_dict(); payload["cluster"][field]=value
    payload=_resign_projection(payload)
    with pytest.raises(Exception,match=message): ActiveBoxZoneProjection.from_dict(payload)


def test_fully_resigned_wrong_envelope_is_rejected() -> None:
    payload=initial_frame().active_box_snapshot.upper_projection.to_dict(); payload["cluster"]["price_range"]["high"]="999"
    payload=_resign_projection(payload)
    with pytest.raises(Exception,match="envelope"): ActiveBoxZoneProjection.from_dict(payload)


def test_same_zone_key_wrong_snapshot_and_other_frame_projection_are_rejected() -> None:
    current=score_frame(); projection=initial_frame().active_box_snapshot.upper_projection
    payload=projection.to_dict(); payload["source_zone_snapshot_id"]="wrong"; payload=_resign_projection(payload)
    forged=ActiveBoxZoneProjection.from_dict(payload)
    with pytest.raises(ActiveBoxProjectionError): validate_zone_projection(current,config(),forged)
    other=ResonanceScorer(scoring_config(candidate_tier_weight=Decimal("0.6"))).score_frame(current.source_frame)
    assert other.as_of_time==current.as_of_time and other.score_frame_id!=current.score_frame_id
    with pytest.raises(ActiveBoxProjectionError): validate_zone_projection(other,config(),projection)


def test_fully_resigned_member_identity_attack_is_not_authoritative() -> None:
    current=score_frame(); payload=initial_frame().active_box_snapshot.upper_projection.to_dict()
    payload["cluster"]["member_refs"][0]["object_id"]="forged-member"
    payload["member_boundary_ids"][0]="forged-member"
    payload["member_boundary_ids"]=sorted(payload["member_boundary_ids"])
    payload["cluster"]["member_refs"]=sorted(payload["cluster"]["member_refs"],key=lambda item:item["object_id"])
    forged=ActiveBoxZoneProjection.from_dict(_resign_projection(payload))
    with pytest.raises(ActiveBoxProjectionError): validate_zone_projection(current,config(),forged)
