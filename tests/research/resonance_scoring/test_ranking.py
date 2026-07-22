from dataclasses import replace
from decimal import Decimal

import pytest

from msa.research.resonance import ResonanceScoreFrame, ResonanceScoringEngineError
from msa.research.resonance.scoring_contracts import _rank_sort_key

from .fixtures import score_frame


def test_upper_and_lower_ranks_are_independent_contiguous_and_deterministic() -> None:
    frame = score_frame()
    assert tuple(item.side_rank for item in frame.upper_zones) == tuple(range(1, len(frame.upper_zones) + 1))
    assert tuple(item.side_rank for item in frame.lower_zones) == tuple(range(1, len(frame.lower_zones) + 1))
    assert frame.upper_zones == tuple(sorted(frame.upper_zones, key=_rank_sort_key))
    assert frame.lower_zones == tuple(sorted(frame.lower_zones, key=_rank_sort_key))


def test_rank_key_records_all_contract_tie_break_fields() -> None:
    zone = score_frame().upper_zones[0]
    key = zone.explanation.side_rank_key
    assert key.selection_score == zone.selection_score
    assert key.quality_score == zone.quality_score
    assert key.distinct_context_count == zone.distinct_context_count
    assert key.distinct_source_type_count == zone.distinct_source_type_count
    assert key.distance == zone.distance
    assert key.latest_evidence_confirm_time == zone.latest_evidence_confirm_time
    assert key.zone_key_id == zone.zone_key_id
    assert key.zone_snapshot_id == zone.zone_snapshot_id


def test_quality_breaks_zero_selection_tie_before_distance() -> None:
    frame = score_frame(
        absolute_distance_horizon=Decimal("1"),
        source_diversity_bonus_per_extra=Decimal("2"),
    )
    far_upper = tuple(item for item in frame.upper_zones if item.selection_score == 0)
    assert far_upper == tuple(sorted(far_upper, key=_rank_sort_key))


def test_rank_tampering_is_rejected_by_score_frame_contract() -> None:
    frame = score_frame()
    changed = replace(frame.upper_zones[0], side_rank=2)
    zones = (changed,) + frame.zones[1:]
    with pytest.raises(ResonanceScoringEngineError, match="side_rank"):
        replace(frame, zones=zones)


def test_repeated_scoring_produces_identical_full_payload() -> None:
    first = score_frame()
    second = score_frame()
    assert second.to_dict() == first.to_dict()
    assert ResonanceScoreFrame.from_dict(first.to_dict()) == first
