from msa.validation.experiments.execution import (
    C008CBExecutionManifest,
    build_c008c_b_execution_manifest,
)


def test_manifest_freezes_complete_b_and_oos_schedules() -> None:
    manifest = build_c008c_b_execution_manifest()
    assert len(manifest.execution_pairs) == 390
    assert len(manifest.deferred_oos_pairs) == 130
    assert len(manifest.variant_replay_sample_ids) == 125
    assert len(manifest.baseline_replay_sample_ids) == 15
    assert len(manifest.deferred_baseline_replay_sample_ids) == 5
    assert len(manifest.fixed_cutoff_case_ids) == 15
    assert len(manifest.deferred_fixed_cutoff_case_ids) == 5
    assert all(item.seed != 3 for item in manifest.execution_pairs)
    assert all(item.seed == 3 for item in manifest.deferred_oos_pairs)


def test_manifest_round_trips_exactly() -> None:
    manifest = build_c008c_b_execution_manifest()
    restored = C008CBExecutionManifest.from_dict(manifest.to_dict())
    assert restored == manifest
    assert restored.to_dict() == manifest.to_dict()


def test_manifest_does_not_call_core_pipeline(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("outcome entrypoint called during manifest build")

    monkeypatch.setattr(
        "msa.research.msa_core.MSACorePipeline.run", forbidden
    )
    manifest = build_c008c_b_execution_manifest()
    assert len(manifest.execution_pairs) == 390
