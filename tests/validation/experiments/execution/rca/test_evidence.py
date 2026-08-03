import inspect

from msa.validation.experiments.execution.rca import evidence


def test_check_existing_never_reexecutes_diagnostics():
    source = inspect.getsource(evidence.check_existing_c008c_b_rca_evidence)
    assert "run_determinism_diagnostics" not in source
    assert "run_cutoff_diagnostics" not in source


def test_writer_freezes_manifest_before_diagnostics():
    source = inspect.getsource(evidence.write_c008c_b_rca_evidence)
    assert source.index("manifest_path.write_bytes") < source.index("run_determinism_diagnostics")
