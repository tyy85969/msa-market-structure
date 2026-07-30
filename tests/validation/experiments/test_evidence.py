import hashlib
import subprocess
from pathlib import Path

import pytest

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


def test_evidence_check_validates_every_source_authority_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msa.validation.experiments import authority, protected_source

    counts = {
        "baseline": 0,
        "dataset": 0,
        "gates": 0,
        "plan": 0,
        "protected": 0,
    }

    def wrap(name: str, function: object) -> object:
        def checked(*args: object, **kwargs: object) -> object:
            counts[name] += 1
            return function(*args, **kwargs)  # type: ignore[operator]

        return checked

    monkeypatch.setattr(
        authority,
        "validate_core_experiment_baseline",
        wrap("baseline", authority.validate_core_experiment_baseline),
    )
    monkeypatch.setattr(
        authority,
        "validate_c008c_synthetic_dataset",
        wrap("dataset", authority.validate_c008c_synthetic_dataset),
    )
    monkeypatch.setattr(
        authority,
        "validate_c008c_gate_registry",
        wrap("gates", authority.validate_c008c_gate_registry),
    )
    monkeypatch.setattr(
        authority,
        "validate_c008c_experiment_plan",
        wrap("plan", authority.validate_c008c_experiment_plan),
    )
    monkeypatch.setattr(
        protected_source,
        "validate_protected_source_manifest",
        wrap(
            "protected",
            protected_source.validate_protected_source_manifest,
        ),
    )
    protected_source.write_c008c_authority_evidence(check=True)
    assert counts == {
        "baseline": 1,
        "dataset": 1,
        "gates": 1,
        "plan": 1,
        "protected": 1,
    }
