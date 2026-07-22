from dataclasses import replace
from decimal import Decimal

import pytest

from msa.data import Timeframe
from msa.domain import BoundarySide, LifecycleState, MarketRole, StructureObjectKind, StructureSourceType
from msa.research.active_box import ActiveBoxProjectionError, ActiveBoxZoneProjection, project_zone
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
