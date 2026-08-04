import pytest

from msa.validation.experiments.execution.errors import C008CBCaseError
from msa.validation.experiments.execution.runner import _execute_pair


def test_seed_three_is_rejected_before_pipeline_entry(
    compact_components,
    monkeypatch,
) -> None:
    manifest = compact_components["manifest"]
    pair = manifest.deferred_oos_pairs[0]
    dataset = compact_components["dataset"]
    plan = compact_components["plan"]
    case = next(
        item
        for item in dataset.cases
        if item.dataset_case_id == pair.dataset_case_id
    )
    variant = next(
        item
        for item in plan.variants
        if item.variant_id == pair.variant_id
    )
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("seed=3 reached Core")

    monkeypatch.setattr(
        "msa.research.msa_core.MSACorePipeline.run", forbidden
    )
    with pytest.raises(C008CBCaseError):
        _execute_pair(pair, case, variant)
    assert not called


def test_pair_level_failures_preserve_all_390_results(
    compact_components,
) -> None:
    results = compact_components["case_results"]
    assert len(results) == 390
    assert len({item.execution_pair_id for item in results}) == 390
    assert all(item.run_id is None for item in results)
    assert all(item.metric_report_id is None for item in results)
