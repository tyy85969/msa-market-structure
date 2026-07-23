from datetime import timedelta

from msa.research.msa_core import iter_msa_core_frame_bundles

from .fixtures import batch_run, config, pipeline, source_input


def test_batch_uses_every_formal_stage_history() -> None:
    run = batch_run()
    assert run.score_history.source_history == run.resonance_history
    assert (
        run.active_box_history.source_score_history == run.score_history
    )
    assert len(run.frame_bundles) == len(run.processing_times) == 4
    assert run.final_bundle == run.frame_bundles[-1]


def test_public_bundle_iterator_matches_run() -> None:
    run = batch_run()
    assert tuple(
        iter_msa_core_frame_bundles(
            config(),
            run.resonance_history,
            run.score_history,
            run.active_box_history,
        )
    ) == run.frame_bundles


def test_pipeline_has_no_cross_run_mutable_state() -> None:
    value = pipeline()
    first = value.run(source_input())
    second = value.run(source_input())
    assert first.to_dict() == second.to_dict()


def test_more_than_one_hundred_processing_times_smoke() -> None:
    value = pipeline()
    source = source_input()
    baseline = value.run(source)
    start = baseline.processing_times[0]
    schedule = tuple(
        sorted(
            {
                *(start + timedelta(minutes=index) for index in range(99)),
                *baseline.processing_times,
            }
        )
    )
    from msa.research.msa_core import replay_msa_core_run

    run = replay_msa_core_run(value, source, schedule)
    assert len(run.frame_bundles) >= 100
    assert len(run.frame_bundles) == len(run.processing_times)
    assert tuple(item.as_of_time for item in run.frame_bundles) == schedule
