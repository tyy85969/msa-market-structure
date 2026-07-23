from datetime import timedelta

from msa.research.active_box import replay_active_box_history
from msa.research.resonance import ResonanceScoreHistory
from tests.research.resonance.fixtures import T1, assembler, frame_input
from tests.research.resonance_scoring.fixtures import scorer
from tests.research.active_box_engine.fixtures import score_history, selector


def test_future_append_does_not_change_past_complete_selection_payloads() -> None:
    source = score_history()
    value = selector()
    baseline = value.build_batch(source)
    for index, frame in enumerate(source.frames):
        prefix = ResonanceScoreHistory(
            frames=source.frames[: index + 1],
            final_frame=frame,
            source_history=__import__(
                "msa.research.resonance", fromlist=["ResonanceFrameHistory"]
            ).ResonanceFrameHistory(
                frames=source.source_history.frames[: index + 1],
                final_frame=source.source_history.frames[index],
                config_snapshot=source.source_history.config_snapshot,
            ),
            config_snapshot=source.config_snapshot,
        )
        assert (
            value.build_batch(prefix).frames[-1].to_dict()
            == baseline.frames[index].to_dict()
        )


def test_retain_uses_creation_projections_but_current_zone_observations() -> None:
    history = selector().build_batch(score_history())
    first = history.frames[0].active_box_snapshot
    for frame in history.frames[1:]:
        current = frame.active_box_snapshot
        assert current.lower_projection == first.lower_projection
        assert current.upper_projection == first.upper_projection
        assert (
            current.observed_lower_zone_snapshot_id
            == frame.lower_decision.selected_zone_snapshot_id
        )
        assert (
            current.observed_upper_zone_snapshot_id
            == frame.upper_decision.selected_zone_snapshot_id
        )


def test_legal_extra_asof_frame_only_changes_itself_and_later_state() -> None:
    source = score_history()
    score_engine = scorer()
    extra_source = assembler().build_as_of(
        frame_input(), T1 + timedelta(minutes=30)
    )
    extra = score_engine.score_frame(extra_source)
    replay_frames = (
        source.frames[0],
        source.frames[1],
        extra,
        *source.frames[2:],
    )
    replay = ResonanceScoreHistory(
        frames=replay_frames,
        final_frame=replay_frames[-1],
        source_history=source.source_history,
        config_snapshot=source.config_snapshot,
    )
    value = selector()
    baseline = value.build_batch(source)
    result = replay_active_box_history(value, source, replay)
    assert result.frames[0].to_dict() == baseline.frames[0].to_dict()
    assert result.frames[1].to_dict() == baseline.frames[1].to_dict()


def test_default_replay_and_batch_are_complete_payload_equivalent() -> None:
    value = selector()
    source = score_history()
    assert (
        replay_active_box_history(value, source).to_dict()
        == value.build_batch(source).to_dict()
    )
