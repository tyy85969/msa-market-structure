from decimal import Decimal

import pytest

from msa.domain import BoundarySide
from msa.research.active_box import (
    ActiveBoxSelectionFrame,
    ActiveBoxSideAction,
    build_selection_frame,
    build_side_decision,
)

from .fixtures import config, initial_frame, score_frame


def test_frame_binds_two_exact_decisions_box_event_report_and_provenance() -> None:
    frame=initial_frame()
    assert frame.lower_decision.side is BoundarySide.LOWER
    assert frame.upper_decision.side is BoundarySide.UPPER
    assert frame.active_box_snapshot.observed_lower_zone_key_id==frame.lower_decision.selected_zone_key_id
    assert frame.active_box_snapshot.observed_upper_zone_key_id==frame.upper_decision.selected_zone_key_id
    assert frame.report.created_event_count==1 and frame.report.frozen_event_count==0
    assert frame.report.warnings==frame.report.errors==()
    assert ActiveBoxSelectionFrame.from_dict(frame.to_dict())==frame


def test_no_pair_means_no_active_box() -> None:
    source=score_frame(); cfg=config(minimum_quality_score=Decimal("999"))
    lower=build_side_decision(source,cfg,BoundarySide.LOWER)
    upper=build_side_decision(source,cfg,BoundarySide.UPPER)
    frame=build_selection_frame(source_score_frame=source,lower_decision=lower,upper_decision=upper,active_box_snapshot=None,emitted_events=(),config=cfg)
    assert lower.action is upper.action is ActiveBoxSideAction.NONE
    assert frame.active_box_snapshot is None and not frame.report.has_active_box


def test_arbitrary_frame_id_and_report_attack_fail_closed() -> None:
    payload=initial_frame().to_dict(); payload["selection_frame_id"]="active-box-selection-frame-v1-"+"1"*64; payload["provenance"]["source_object_id"]=payload["selection_frame_id"]
    with pytest.raises(Exception,match="selection_frame_id"): ActiveBoxSelectionFrame.from_dict(payload)
    payload=initial_frame().to_dict(); payload["report"]["upper_zone_count"]+=1
    with pytest.raises(Exception,match="report"): ActiveBoxSelectionFrame.from_dict(payload)


def test_active_geometry_uses_current_reference_price() -> None:
    frame=initial_frame(); price=frame.source_score_frame.source_frame.reference_price.price
    assert frame.active_box_snapshot.active_box.lower_boundary.price_range.high<=price<=frame.active_box_snapshot.active_box.upper_boundary.price_range.low


def test_initial_pair_without_created_event_fails_closed() -> None:
    frame=initial_frame()
    with pytest.raises(Exception,match="event pattern"):
        build_selection_frame(source_score_frame=frame.source_score_frame,lower_decision=frame.lower_decision,upper_decision=frame.upper_decision,
            active_box_snapshot=frame.active_box_snapshot,emitted_events=(),config=frame.config_snapshot)
