from decimal import Decimal
from dataclasses import replace

import pytest

from msa.domain import BoundarySide
from msa.research.active_box import ActiveBoxContractError, ActiveBoxSideAction, build_side_decision, selection_key

from .fixtures import config, score_frame


@pytest.mark.parametrize(("field","better","worse"),[
    ("distance",Decimal("1"),Decimal("2")),
    ("selection_score",Decimal("2"),Decimal("1")),
    ("quality_score",Decimal("2"),Decimal("1")),
    ("distinct_context_count",2,1),
    ("distinct_source_type_count",2,1),
])
def test_selection_key_priority_components(field,better,worse) -> None:
    base=selection_key(score_frame().upper_zones[0])
    assert replace(base,**{field:better}).sort_key<replace(base,**{field:worse}).sort_key


def test_nearest_qualified_order_is_recomputed_not_side_rank() -> None:
    frame=score_frame(); decision=build_side_decision(frame,config(),BoundarySide.UPPER)
    expected=tuple(zone.zone_key_id for zone in sorted(frame.upper_zones,key=lambda item:selection_key(item).sort_key))
    assert decision.eligible_zone_key_ids_in_order==expected
    assert decision.action is ActiveBoxSideAction.SELECT
    assert decision.selected_zone_key_id==expected[0]


def test_input_zone_permutation_cannot_change_decision() -> None:
    frame=score_frame(); first=build_side_decision(frame,config(),BoundarySide.LOWER)
    assert first.to_dict()==build_side_decision(frame,config(),BoundarySide.LOWER).to_dict()


def test_no_current_and_no_candidate_is_none() -> None:
    decision=build_side_decision(score_frame(),config(minimum_quality_score=Decimal("999")),BoundarySide.UPPER)
    assert decision.action is ActiveBoxSideAction.NONE and decision.selected_zone_key_id is None


def test_missing_current_replaces_or_clears() -> None:
    frame=score_frame()
    assert build_side_decision(frame,config(),BoundarySide.UPPER,"missing").action is ActiveBoxSideAction.REPLACE
    assert build_side_decision(frame,config(minimum_quality_score=Decimal("999")),BoundarySide.UPPER,"missing").action is ActiveBoxSideAction.CLEAR


def test_current_first_or_only_is_retained() -> None:
    frame=score_frame(); near=sorted(frame.upper_zones,key=lambda item:item.distance)[0]
    decision=build_side_decision(frame,config(),BoundarySide.UPPER,near.zone_key_id)
    assert decision.action is ActiveBoxSideAction.RETAIN and decision.selected_zone_key_id==near.zone_key_id


def test_far_current_is_replaced_when_distance_gain_strictly_exceeds_margin() -> None:
    frame=score_frame(); far=max(frame.upper_zones,key=lambda item:item.distance)
    decision=build_side_decision(frame,config(absolute_replacement_distance_margin=Decimal("9"),minimum_replacement_selection_score_improvement=Decimal("999")),BoundarySide.UPPER,far.zone_key_id)
    assert decision.distance_gain==Decimal("10") and decision.action is ActiveBoxSideAction.REPLACE


def test_distance_equality_and_score_equality_do_not_replace() -> None:
    frame=score_frame(); near=min(frame.upper_zones,key=lambda item:item.distance); far=max(frame.upper_zones,key=lambda item:item.distance)
    gain=near.selection_score-far.selection_score
    decision=build_side_decision(frame,config(absolute_replacement_distance_margin=Decimal("10"),minimum_replacement_selection_score_improvement=gain),BoundarySide.UPPER,far.zone_key_id)
    assert decision.distance_gain==Decimal("10") and decision.selection_gain==gain
    assert decision.action is ActiveBoxSideAction.RETAIN


def test_nonnegative_distance_and_strict_score_gain_can_replace() -> None:
    frame=score_frame(); far=max(frame.upper_zones,key=lambda item:item.distance)
    decision=build_side_decision(frame,config(absolute_replacement_distance_margin=Decimal("999"),minimum_replacement_selection_score_improvement=Decimal("0.1")),BoundarySide.UPPER,far.zone_key_id)
    assert decision.action is ActiveBoxSideAction.REPLACE


@pytest.mark.parametrize("bad",["provenance",[],None])
def test_direct_decision_construction_rejects_invalid_provenance(bad) -> None:
    decision=build_side_decision(score_frame(),config(),BoundarySide.LOWER)
    with pytest.raises(ActiveBoxContractError):
        replace(decision,provenance=bad)
