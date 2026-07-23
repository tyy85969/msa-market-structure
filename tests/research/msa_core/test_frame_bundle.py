from dataclasses import replace

import pytest

from msa.research.msa_core import MSACoreIntegrationError

from .fixtures import batch_run


def test_bundle_maps_three_authoritative_frames_exactly() -> None:
    run = batch_run()
    for index, bundle in enumerate(run.frame_bundles):
        assert bundle.as_of_time == run.processing_times[index]
        assert bundle.resonance_frame == run.resonance_history.frames[index]
        assert bundle.score_frame == run.score_history.frames[index]
        assert bundle.selection_frame == run.active_box_history.frames[index]
        assert bundle.score_frame.source_frame == bundle.resonance_frame
        assert bundle.selection_frame.source_score_frame == bundle.score_frame


def test_bundle_rejects_another_asof_score_frame() -> None:
    run = batch_run()
    with pytest.raises(MSACoreIntegrationError):
        replace(run.frame_bundles[0], score_frame=run.score_history.frames[1])


def test_bundle_rejects_another_selection_frame() -> None:
    run = batch_run()
    with pytest.raises(MSACoreIntegrationError):
        replace(
            run.frame_bundles[0],
            selection_frame=run.active_box_history.frames[1],
        )


def test_bundle_rejects_resigned_id_and_provenance() -> None:
    bundle = batch_run().frame_bundles[0]
    with pytest.raises(MSACoreIntegrationError):
        replace(bundle, bundle_id="msa-core-bundle-v1-" + "0" * 64)
    with pytest.raises(MSACoreIntegrationError):
        replace(
            bundle,
            provenance=replace(bundle.provenance, policy_id="forged"),
        )


def test_bundle_full_round_trip() -> None:
    bundle = batch_run().frame_bundles[0]
    assert type(bundle).from_dict(bundle.to_dict()) == bundle
