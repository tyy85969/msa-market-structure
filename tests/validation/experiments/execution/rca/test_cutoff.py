import inspect

from msa.validation.experiments.execution.rca import cutoff


def test_cutoff_schedule_has_one_checkpoint_per_case(rca_manifest):
    assert len(set(rca_manifest.cutoff_case_ids)) == 15
    assert rca_manifest.cutoff_selection_kinds.count("STABLE_MEDIAN_CONTROL") == 6
    assert rca_manifest.cutoff_selection_kinds.count("EARLIEST_UNSTABLE") == 9


def test_comparator_adapter_keeps_exact_cutoff():
    source = inspect.getsource(cutoff._execute)
    assert "timedelta(microseconds=1)" in source
    assert '"comparator_boundary_operator": "<"' in source
    assert '"exact_cutoff_included": True' in source
