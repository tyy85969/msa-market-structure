import hashlib
import subprocess
from pathlib import Path

from msa.validation.experiments import write_c008c_authority_evidence


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "docs/reference/core_alpha_v1_config.json"


def test_reference_json_and_repository_attributes_are_portable() -> None:
    data = REFERENCE.read_bytes()
    assert b"\r\n" not in data
    assert hashlib.sha256(data).hexdigest() == (
        "f7cae328c78e5f1e7bdb69cdb4eb3f8bada9d7facae656cbd8652751a24db396"
    )
    result = subprocess.run(
        [
            "git",
            "check-attr",
            "text",
            "eol",
            "--",
            "docs/reference/core_alpha_v1_config.json",
            "docs/validation/evidence/c008c_experiment_plan.json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "docs/reference/core_alpha_v1_config.json: text: set" in result.stdout
    assert "docs/reference/core_alpha_v1_config.json: eol: lf" in result.stdout
    assert (
        "docs/validation/evidence/c008c_experiment_plan.json: eol: lf"
        in result.stdout
    )


def test_committed_evidence_is_exactly_reproducible() -> None:
    paths = write_c008c_authority_evidence(check=True)
    first = tuple(path.read_bytes() for path in paths)
    assert all(item.endswith(b"\n") and b"\r\n" not in item for item in first)
    assert tuple(path.read_bytes() for path in paths) == first
