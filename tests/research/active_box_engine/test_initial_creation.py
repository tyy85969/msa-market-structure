from decimal import Decimal

from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
)
from msa.domain import BoundarySide
from msa.research.resonance import ResonanceScorer
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    START,
    bar,
    custom_bundle,
    subject,
)
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import score_history, selector


def test_complete_initial_pair_creates_one_active_episode() -> None:
    frame = score_history().frames[0]
    result = selector().select_frame(frame)
    assert result.active_box_snapshot is not None
    assert len(result.emitted_events) == 1
    assert result.emitted_events[0].event_type is ActiveBoxEventType.CREATED
    assert (
        result.emitted_events[0].event_reason
        is ActiveBoxEventReason.INITIAL_PAIR
    )
    assert (
        result.active_box_snapshot.active_box.selection_price
        == frame.source_frame.reference_price.price
    )
    assert (
        result.active_box_snapshot.lower_projection.source_score_frame_id
        == frame.score_frame_id
    )
    assert (
        result.active_box_snapshot.upper_projection.source_score_frame_id
        == frame.score_frame_id
    )


def test_no_or_partial_initial_pair_creates_no_box_or_event() -> None:
    frame = score_history().frames[0]
    none = selector(minimum_quality_score=Decimal("999")).select_frame(frame)
    lower_only = selector(
        minimum_selection_score=Decimal("0.37")
    ).select_frame(frame)
    for result in (none, lower_only):
        assert result.active_box_snapshot is None
        assert result.emitted_events == ()


def test_upper_only_initial_selection_creates_no_half_box() -> None:
    engine, data = custom_bundle(
        (subject("upper", BoundarySide.UPPER, "110", "111"),),
        (bar(-1),),
        (H4_PRIMARY,),
    )
    frame = ResonanceScorer(
        scoring_config(contexts=(H4_PRIMARY,))
    ).score_frame(engine.build_as_of(data, START))
    result = selector().select_frame(frame)
    assert result.lower_decision.selected_zone_key_id is None
    assert result.upper_decision.selected_zone_key_id is not None
    assert result.active_box_snapshot is None
    assert result.emitted_events == ()
