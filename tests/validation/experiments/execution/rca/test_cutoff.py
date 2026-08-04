import inspect
from copy import deepcopy

from msa.validation.experiments.execution.rca import cutoff
from msa.validation.experiments.execution.rca.projections import (
    project_metric_semantics,
)


def test_cutoff_schedule_has_one_checkpoint_per_case(rca_manifest):
    assert len(set(rca_manifest.cutoff_case_ids)) == 15
    assert rca_manifest.cutoff_selection_kinds.count("STABLE_MEDIAN_CONTROL") == 6
    assert rca_manifest.cutoff_selection_kinds.count("EARLIEST_UNSTABLE") == 9


def test_comparator_adapter_keeps_exact_cutoff():
    source = inspect.getsource(cutoff._execute)
    assert "timedelta(microseconds=1)" in source
    assert '"comparator_boundary_operator": "<"' in source
    assert '"exact_cutoff_included": True' in source


def _metric_payload():
    return {
        "metric_report_id": "report-a",
        "source_run_id": "run-a",
        "evaluation_as_of_time": "2026-01-01T00:00:00+00:00",
        "formula_registry": [{"metric_formula_id": "formula-a"}],
        "observations": [{"status": "MATURED", "value": "1"}],
        "aggregates": [
            {
                "formula_id": "formula-a",
                "metric_name": "TURN_RESOLUTION_RATE",
                "status": "AVAILABLE",
                "value": "1",
                "eligible_count": 2,
                "matured_count": 1,
                "censored_count": 1,
                "unavailable_count": 0,
            }
        ],
        "provenance": ["source_run_id=run-a"],
    }


def test_independent_metric_projection_preserves_cutoff_semantics():
    left = _metric_payload()
    for path, value in (
        (("formula_registry", 0, "metric_formula_id"), "formula-b"),
        (("observations", 0, "value"), "0"),
        (("aggregates", 0, "matured_count"), 0),
        (("aggregates", 0, "censored_count"), 2),
    ):
        right = deepcopy(left)
        right[path[0]][path[1]][path[2]] = value
        assert project_metric_semantics(left) != project_metric_semantics(right)


def test_independent_metric_projection_excludes_only_report_source_wrappers():
    left = _metric_payload()
    for key, value in (
        ("metric_report_id", "report-b"),
        ("source_run_id", "run-b"),
        ("provenance", ["source_run_id=run-b"]),
    ):
        right = deepcopy(left)
        right[key] = value
        assert project_metric_semantics(left) == project_metric_semantics(right)


def test_rca_cutoff_does_not_import_original_metric_projection():
    source = inspect.getsource(cutoff)
    assert "_metric_cutoff_projection" not in source
