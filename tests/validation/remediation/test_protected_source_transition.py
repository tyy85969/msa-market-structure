from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from msa.validation.experiments import (
    ExperimentEvidenceError,
    ExperimentProtectedSourceError,
    ProtectedSourceManifest,
    build_protected_source_manifest,
    validate_protected_source_manifest,
    write_c008c_authority_evidence,
)
from msa.validation.remediation import (
    H3_REVIEWED_TRANSITION_ID,
    H3_TRANSITION_EVIDENCE_PATH,
    ProtectedSourceTransitionError,
    check_existing_decimal_remediation_evidence,
    check_existing_metric_fixed_cutoff_transition_evidence,
    validate_historical_protected_source_transition,
    validate_post_h2_protected_source_authority,
)


ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_MANIFEST_PATH = (
    ROOT / "docs/validation/evidence/c008c_protected_source_manifest.json"
)
HISTORICAL_MANIFEST_ID = (
    "c008c-protected-source-manifest-v1-"
    "f93cda3d0966ee1340addebe36e8c008591d94d19d966828471721a18fdf2356"
)
HISTORICAL_MANIFEST_SHA256 = (
    "a4651a946ddc3731d35953e01d2018874672504a48eba74e87819ffb47d649a7"
)
H2_EVIDENCE_SHA256 = (
    "97bb6868eb343572851aef07d32da805a71433549bf2d471d7dae9b11b467431"
)


def _historical_manifest(root: Path = ROOT) -> ProtectedSourceManifest:
    return ProtectedSourceManifest.from_dict(
        json.loads(
            (
                root
                / "docs/validation/evidence/"
                "c008c_protected_source_manifest.json"
            ).read_text(encoding="utf-8")
        )
    )


def _copy_transition_root(target: Path) -> None:
    (target / "docs/validation/evidence").mkdir(parents=True)
    shutil.copyfile(ROOT / "pyproject.toml", target / "pyproject.toml")
    evidence_names = (
        "c008c_b_dev_validation_report.json",
        "c008c_b_execution_manifest.json",
        "c008c_b_root_cause_lock.json",
        "c008c_b_root_cause_manifest.json",
        "c008c_b_root_cause_report.json",
        "c008c_baseline_snapshot.json",
        "c008c_dataset_manifest.json",
        "c008c_experiment_plan.json",
        "c008c_protected_source_manifest.json",
        "c008c_h2_decimal_remediation.json",
        H3_TRANSITION_EVIDENCE_PATH.name,
    )
    for name in evidence_names:
        shutil.copyfile(
            ROOT / "docs/validation/evidence" / name,
            target / "docs/validation/evidence" / name,
        )
    for entry in build_protected_source_manifest(ROOT).files:
        source = ROOT / entry.relative_path
        destination = target / entry.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_historical_and_h2_authorities_remain_byte_identical() -> None:
    historical_raw = HISTORICAL_MANIFEST_PATH.read_bytes()
    assert hashlib.sha256(historical_raw).hexdigest() == (
        HISTORICAL_MANIFEST_SHA256
    )
    historical = _historical_manifest()
    assert len(historical.files) == 77
    assert historical.protected_source_manifest_id == HISTORICAL_MANIFEST_ID
    h2_path = check_existing_decimal_remediation_evidence(ROOT)
    assert hashlib.sha256(h2_path.read_bytes()).hexdigest() == (
        H2_EVIDENCE_SHA256
    )


def test_post_h2_and_post_h3_authorities_are_distinct_and_valid() -> None:
    historical = _historical_manifest()
    post_h2 = validate_post_h2_protected_source_authority(
        historical, ROOT
    )
    current = build_protected_source_manifest(ROOT)
    assert len(post_h2.files) == 78
    assert len(current.files) == 78
    assert post_h2.protected_source_manifest_id != (
        current.protected_source_manifest_id
    )
    validate_historical_protected_source_transition(historical, ROOT)
    assert validate_protected_source_manifest(historical, ROOT) == historical
    assert validate_protected_source_manifest(current, ROOT) == current


def test_h3_transition_evidence_is_canonical_and_source_bound() -> None:
    path = check_existing_metric_fixed_cutoff_transition_evidence(ROOT)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path == ROOT / H3_TRANSITION_EVIDENCE_PATH
    assert payload["transition_id"] == H3_REVIEWED_TRANSITION_ID
    assert payload["reviewed_change"]["relative_path"] == (
        "src/python/msa/validation/metrics/events.py"
    )
    assert payload["post_h2_authority"]["protected_path_count"] == 78
    assert payload["post_h3_authority"]["protected_path_count"] == 78


def test_unreviewed_protected_source_change_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "unauthorized-protected-source"
    _copy_transition_root(root)
    target = root / "src/python/msa/validation/metrics/bars.py"
    target.write_bytes(
        target.read_bytes() + b"\n# unauthorized H3 test mutation\n"
    )
    historical = _historical_manifest(root)
    with pytest.raises(
        ProtectedSourceTransitionError,
        match="unreviewed protected source difference",
    ):
        validate_historical_protected_source_transition(historical, root)
    with pytest.raises(
        ExperimentProtectedSourceError,
        match="protected source differs from the frozen manifest",
    ):
        validate_protected_source_manifest(historical, root)


def test_missing_h3_evidence_cannot_restore_historical_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_path = (ROOT / H3_TRANSITION_EVIDENCE_PATH).resolve()
    original_is_file = Path.is_file

    def simulated_is_file(path: Path) -> bool:
        if path.resolve() == evidence_path:
            return False
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", simulated_is_file)
    with pytest.raises(
        ExperimentEvidenceError,
        match="cannot be regenerated after the reviewed H2 remediation",
    ):
        write_c008c_authority_evidence(ROOT, check=False)


def test_missing_h3_evidence_fails_transition_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_path = (ROOT / H3_TRANSITION_EVIDENCE_PATH).resolve()
    original_read_bytes = Path.read_bytes

    def simulated_read_bytes(path: Path) -> bytes:
        if path.resolve() == evidence_path:
            raise FileNotFoundError(evidence_path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", simulated_read_bytes)
    with pytest.raises(
        ProtectedSourceTransitionError,
        match="invalid H3 Protected Source transition Evidence",
    ):
        validate_historical_protected_source_transition(
            _historical_manifest(), ROOT
        )
