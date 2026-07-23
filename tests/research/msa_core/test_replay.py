from datetime import timedelta

import pytest

from msa.research.msa_core import MSACoreReplayError, replay_msa_core_run

from .fixtures import extra_run, extra_schedule, pipeline, source_input


def test_default_replay_equals_complete_batch_payload() -> None:
    value = pipeline()
    source = source_input()
    assert replay_msa_core_run(value, source).to_dict() == value.run(
        source
    ).to_dict()


def test_explicit_replay_inserts_one_exact_bundle() -> None:
    run = extra_run()
    assert run.processing_times == extra_schedule()
    assert len(run.frame_bundles) == 5


@pytest.mark.parametrize(
    "schedule_factory",
    [
        lambda default: (),
        lambda default: tuple(reversed(default)),
        lambda default: (default[0], default[0], *default[1:]),
        lambda default: default[1:],
        lambda default: (
            default[0] - timedelta(microseconds=1),
            *default,
        ),
        lambda default: (
            default[0].replace(tzinfo=None),
            *default[1:],
        ),
        lambda default: (object(), *default[1:]),
    ],
)
def test_explicit_replay_schedule_fails_closed(schedule_factory) -> None:
    default = pipeline().run(source_input()).processing_times
    with pytest.raises(MSACoreReplayError):
        replay_msa_core_run(
            pipeline(), source_input(), schedule_factory(default)
        )


def test_extra_asof_preserves_complete_prefix_before_insertion() -> None:
    baseline = pipeline().run(source_input())
    replayed = extra_run()
    assert replayed.frame_bundles[0].to_dict() == baseline.frame_bundles[
        0
    ].to_dict()
    assert replayed.frame_bundles[1].as_of_time == extra_schedule()[1]


def test_stage_replay_mismatch_is_rejected(monkeypatch) -> None:
    value = pipeline()
    source = source_input()
    baseline_score = value.run(source).score_history
    monkeypatch.setattr(
        "msa.research.msa_core.replay.replay_score_history",
        lambda *args, **kwargs: baseline_score,
    )
    with pytest.raises(MSACoreReplayError):
        replay_msa_core_run(value, source, extra_schedule())


def test_active_box_stage_replay_history_mismatch_is_rejected(
    monkeypatch,
) -> None:
    value = pipeline()
    source = source_input()
    formally_valid_but_different = value.run(source).active_box_history
    monkeypatch.setattr(
        "msa.research.msa_core.replay.replay_active_box_history",
        lambda *args, **kwargs: formally_valid_but_different,
    )
    with pytest.raises(MSACoreReplayError):
        replay_msa_core_run(value, source, extra_schedule())
