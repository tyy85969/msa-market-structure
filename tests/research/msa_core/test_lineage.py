from dataclasses import replace

import pytest

from msa.research.msa_core import MSACoreIntegrationError

from .fixtures import batch_run


def test_bundle_provenance_has_exact_stage_parents() -> None:
    for bundle in batch_run().frame_bundles:
        assert bundle.provenance.parent_object_ids == tuple(
            sorted(
                (
                    bundle.resonance_frame.frame_id,
                    bundle.score_frame.score_frame_id,
                    bundle.selection_frame.selection_frame_id,
                )
            )
        )
        assert bundle.provenance.notes == ("engine_id=c007d-msa-core",)


def test_run_provenance_is_bounded() -> None:
    run = batch_run()
    assert len(run.provenance.parent_object_ids) == 6
    assert run.provenance.source_object_id == run.run_id
    assert run.provenance.notes == ("engine_id=c007d-msa-core",)


def test_run_rejects_forged_provenance_parent() -> None:
    run = batch_run()
    forged = replace(
        run.provenance,
        parent_object_ids=(*run.provenance.parent_object_ids[:-1], "forged"),
    )
    with pytest.raises(MSACoreIntegrationError):
        replace(run, provenance=forged)


def test_every_frame_is_causal_at_bundle_asof() -> None:
    for bundle in batch_run().frame_bundles:
        assert all(
            item.state_confirm_time <= bundle.as_of_time
            for item in bundle.resonance_frame.evidence
        )
        assert all(
            item.state.confirm_time <= bundle.as_of_time
            for item in bundle.resonance_frame.context_states
        )
        assert (
            bundle.resonance_frame.reference_price.canonical_bar.available_time
            <= bundle.as_of_time
        )
        assert all(
            item.event_confirm_time == bundle.as_of_time
            for item in bundle.selection_frame.emitted_events
        )
