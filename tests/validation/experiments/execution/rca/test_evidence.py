from pathlib import Path

from msa.validation.experiments.execution.rca import evidence


ROOT = Path(__file__).resolve().parents[5]


def test_check_existing_passes_without_reexecuting_core(monkeypatch, b_sources):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("check-existing must not execute RCA diagnostics")

    monkeypatch.setattr(evidence, "run_determinism_diagnostics", forbidden)
    monkeypatch.setattr(evidence, "run_cutoff_diagnostics", forbidden)
    monkeypatch.setattr(
        evidence, "check_existing_c008c_b_evidence", lambda _root: None
    )
    monkeypatch.setattr(evidence, "load_b_sources", lambda _root: b_sources)
    monkeypatch.setattr(
        evidence,
        "validate_c008c_b_rca_manifest",
        lambda manifest, _root: manifest,
    )
    paths = evidence.check_existing_c008c_b_rca_evidence(ROOT)
    assert len(paths) == 4
    assert paths[-1].name == "c008c_b_root_cause_lock.json"
