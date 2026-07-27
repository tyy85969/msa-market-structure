from msa.reference import core_alpha_v1_config
from msa.research.msa_core import MSACorePipeline, replay_msa_core_run
from msa.validation import evaluate_structural_metrics
from tests.research.msa_core.fixtures import (
    extra_schedule,
    pipeline,
    source_input,
)


def test_batch_pipeline_complete_payload_is_unchanged() -> None:
    source = source_input()
    old = pipeline().run(source)
    new = MSACorePipeline(core_alpha_v1_config()).run(source)
    assert new.to_dict() == old.to_dict()
    assert new.run_id == old.run_id
    assert tuple(item.bundle_id for item in new.frame_bundles) == tuple(
        item.bundle_id for item in old.frame_bundles
    )


def test_default_replay_complete_payload_is_unchanged() -> None:
    source = source_input()
    old = replay_msa_core_run(pipeline(), source)
    new = replay_msa_core_run(
        MSACorePipeline(core_alpha_v1_config()), source
    )
    assert new.to_dict() == old.to_dict()


def test_extra_asof_replay_complete_payload_is_unchanged() -> None:
    source = source_input()
    schedule = extra_schedule()
    old = replay_msa_core_run(pipeline(), source, schedule)
    new = replay_msa_core_run(
        MSACorePipeline(core_alpha_v1_config()), source, schedule
    )
    assert new.to_dict() == old.to_dict()


def test_metric_report_complete_payload_is_unchanged() -> None:
    source = source_input()
    old_run = pipeline().run(source)
    new_run = MSACorePipeline(core_alpha_v1_config()).run(source)
    old_report = evaluate_structural_metrics(old_run)
    new_report = evaluate_structural_metrics(new_run)
    assert new_report.to_dict() == old_report.to_dict()
