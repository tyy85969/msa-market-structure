from msa.research.msa_core.identity import digest

from .fixtures import batch_run, extra_run


def test_repeated_runs_are_byte_deterministic() -> None:
    first = batch_run()
    second = batch_run()
    assert first.to_dict() == second.to_dict()
    assert first.run_id == second.run_id
    assert tuple(item.bundle_id for item in first.frame_bundles) == tuple(
        item.bundle_id for item in second.frame_bundles
    )


def test_extra_asof_changes_only_current_and_later_identity() -> None:
    baseline = batch_run()
    replayed = extra_run()
    assert replayed.frame_bundles[0].to_dict() == baseline.frame_bundles[
        0
    ].to_dict()
    assert replayed.run_id != baseline.run_id
    assert digest(replayed.to_dict()) != digest(baseline.to_dict())
