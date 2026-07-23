from dataclasses import replace

import pytest

from msa.research.msa_core import (
    MSACoreIntegrationError,
    build_msa_core_run,
)

from .fixtures import (
    batch_run,
    resigned_source_fields,
    source_lineage_attack,
)


SOURCE_LINEAGE_ATTACKS = (
    "reference_bar_payload",
    "lifecycle_history",
    "timeframe_state_history",
    "default_causal_schedule",
    "future_input_facts",
)


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


@pytest.mark.parametrize("case", SOURCE_LINEAGE_ATTACKS)
def test_resigned_source_input_cannot_reuse_another_run_history(case) -> None:
    run, source_b = source_lineage_attack(case)
    canonical, run_id, provenance = resigned_source_fields(run, source_b)
    with pytest.raises(MSACoreIntegrationError):
        replace(
            run,
            source_input=canonical,
            run_id=run_id,
            provenance=provenance,
        )


@pytest.mark.parametrize("case", SOURCE_LINEAGE_ATTACKS)
def test_builder_cannot_bind_another_source_to_formal_histories(case) -> None:
    run, source_b = source_lineage_attack(case)
    with pytest.raises(MSACoreIntegrationError):
        build_msa_core_run(
            run.config_snapshot,
            source_b,
            run.resonance_history,
            run.score_history,
            run.active_box_history,
        )


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
