from pathlib import Path

import pytest

from msa.validation.experiments import baseline, dataset, gates, plan
from msa.validation.experiments import protected_source
from msa.validation.experiments import (
    ExperimentEvidenceError,
    write_c008c_authority_evidence,
)
from msa.validation.remediation import (
    REVIEWED_REMEDIATION_ID,
    check_existing_decimal_remediation_evidence,
)


ROOT = Path(__file__).resolve().parents[3]


def test_versioned_remediation_evidence_is_canonical_and_source_bound() -> None:
    path = check_existing_decimal_remediation_evidence(ROOT)
    assert path.name == "c008c_h2_decimal_remediation.json"
    assert REVIEWED_REMEDIATION_ID.startswith(
        "c008c-h2-decimal-remediation-v1-"
    )


def test_historical_v1_evidence_cannot_be_regenerated() -> None:
    with pytest.raises(
        ExperimentEvidenceError,
        match="cannot be regenerated after the reviewed H2 remediation",
    ):
        write_c008c_authority_evidence(ROOT, check=False)


def test_missing_remediation_evidence_cannot_restore_v1_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remediation_path = (
        ROOT / "docs/validation/evidence/c008c_h2_decimal_remediation.json"
    ).resolve()
    original_is_file = Path.is_file

    def simulated_is_file(path: Path) -> bool:
        if path.resolve() == remediation_path:
            return False
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", simulated_is_file)

    with pytest.raises(
        ExperimentEvidenceError,
        match="cannot be regenerated after the reviewed H2 remediation",
    ):
        write_c008c_authority_evidence(ROOT, check=False)


def test_regeneration_refusal_precedes_authority_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_authority_execution(*args: object, **kwargs: object) -> None:
        raise AssertionError("authority execution must not occur")

    for module, name in (
        (baseline, "core_experiment_baseline"),
        (dataset, "build_c008c_synthetic_dataset"),
        (gates, "default_c008c_gate_registry"),
        (plan, "default_c008c_experiment_plan"),
        (protected_source, "build_protected_source_manifest"),
    ):
        monkeypatch.setattr(module, name, forbidden_authority_execution)

    with pytest.raises(
        ExperimentEvidenceError,
        match="cannot be regenerated after the reviewed H2 remediation",
    ):
        write_c008c_authority_evidence(ROOT, check=False)


def test_historical_v1_evidence_byte_verification_remains_supported() -> None:
    paths = write_c008c_authority_evidence(ROOT, check=True)
    assert tuple(path.name for path in paths) == (
        "c008c_baseline_snapshot.json",
        "c008c_dataset_manifest.json",
        "c008c_experiment_plan.json",
        "c008c_protected_source_manifest.json",
    )
