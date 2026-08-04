import json
from pathlib import Path

from msa.validation.experiments.execution import (
    C008CBExecutionManifest,
    build_c008c_b_execution_manifest,
    check_existing_c008c_b_evidence,
)
from msa.validation.experiments.identity import canonical_json_bytes


def test_committed_manifest_evidence_is_canonical_and_current() -> None:
    path = Path(
        "docs/validation/evidence/c008c_b_execution_manifest.json"
    )
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    committed = C008CBExecutionManifest.from_dict(payload)
    expected = build_c008c_b_execution_manifest()
    assert committed.to_dict() == expected.to_dict()
    assert raw == canonical_json_bytes(expected.to_dict())


def test_existing_evidence_check_never_executes_core(monkeypatch) -> None:
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("existing-evidence check executed the Core")

    monkeypatch.setattr(
        "msa.research.msa_core.MSACorePipeline.run", forbidden
    )
    paths = check_existing_c008c_b_evidence()
    assert tuple(path.name for path in paths) == (
        "c008c_b_execution_manifest.json",
        "c008c_b_dev_validation_report.json",
    )
    assert not called
