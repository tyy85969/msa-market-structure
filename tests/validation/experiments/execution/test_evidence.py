import json
from pathlib import Path

from msa.validation.experiments.execution import (
    C008CBExecutionManifest,
    build_c008c_b_execution_manifest,
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
