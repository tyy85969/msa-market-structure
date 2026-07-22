from dataclasses import replace
from datetime import timedelta

import pytest

from msa.research.resonance import (
    ResonanceFrameHistory,
    ResonanceScoreHistory,
    ResonanceScoringEngineError,
    ResonanceScoringInputError,
    replay_score_history,
)
from tests.research.resonance.fixtures import T2, assembler, frame_input

from .fixtures import scorer, source_history


def test_batch_scores_exactly_one_frame_per_source_frame() -> None:
    source = source_history()
    history = scorer().build_batch(source)
    assert len(history.frames) == len(source.frames)
    assert tuple(item.as_of_time for item in history.frames) == tuple(item.as_of_time for item in source.frames)
    assert tuple(item.source_frame_id for item in history.frames) == tuple(item.frame_id for item in source.frames)
    assert history.final_frame == history.frames[-1]


def test_default_replay_is_full_payload_equivalent_to_batch() -> None:
    source = source_history()
    assert replay_score_history(scorer(), source).to_dict() == scorer().build_batch(source).to_dict()


def test_explicit_replay_accepts_legal_extra_as_of_frame() -> None:
    source = source_history()
    extra = assembler().build_as_of(frame_input(), T2 + timedelta(seconds=30))
    frames = tuple(sorted(source.frames + (extra,), key=lambda item: item.as_of_time))
    replay = replay_score_history(scorer(), source, frames)
    assert len(replay.frames) == len(source.frames) + 1
    assert extra.frame_id in {item.source_frame_id for item in replay.frames}


def test_explicit_replay_rejects_missing_source_duplicate_and_time_regression() -> None:
    source = source_history()
    with pytest.raises(ResonanceScoringInputError, match="omit"):
        replay_score_history(scorer(), source, source.frames[:-1])
    with pytest.raises(ResonanceScoringInputError, match="strictly"):
        replay_score_history(scorer(), source, tuple(reversed(source.frames)))
    with pytest.raises(ResonanceScoringInputError, match="strictly"):
        replay_score_history(scorer(), source, source.frames + (source.frames[-1],))


def test_future_source_append_does_not_change_old_score_frame_payloads() -> None:
    full_source = source_history()
    prefix_source = ResonanceFrameHistory(
        frames=full_source.frames[:-1],
        final_frame=full_source.frames[-2],
        config_snapshot=full_source.config_snapshot,
    )
    prefix = scorer().build_batch(prefix_source)
    full = scorer().build_batch(full_source)
    assert tuple(item.to_dict() for item in full.frames[:-1]) == tuple(item.to_dict() for item in prefix.frames)


def test_price_only_and_lifecycle_only_identity_behavior() -> None:
    history = scorer().build_batch(source_history())
    at_t2 = next(item for item in history.frames if item.as_of_time == T2)
    at_t3 = history.frames[-1]
    by_subject_t2 = {zone.member_subject_ids: zone for zone in at_t2.zones}
    by_subject_t3 = {zone.member_subject_ids: zone for zone in at_t3.zones}
    assert set(by_subject_t2) == set(by_subject_t3)
    for key in by_subject_t2:
        assert by_subject_t2[key].zone_key_id == by_subject_t3[key].zone_key_id
        assert by_subject_t2[key].zone_snapshot_id != by_subject_t3[key].zone_snapshot_id
    at_t1 = history.frames[1]
    common = set(zone.member_subject_ids for zone in at_t1.zones) & set(by_subject_t2)
    for key in common:
        first = next(zone for zone in at_t1.zones if zone.member_subject_ids == key)
        second = by_subject_t2[key]
        assert first.zone_key_id == second.zone_key_id


def test_score_history_contract_rejects_final_frame_conflict() -> None:
    history = scorer().build_batch(source_history())
    with pytest.raises(ResonanceScoringEngineError, match="final_frame"):
        replace(history, final_frame=history.frames[0])
    assert ResonanceScoreHistory.from_dict(history.to_dict()) == history
