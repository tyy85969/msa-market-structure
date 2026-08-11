"""Append-only canonical Evidence for formal C-008C-B-v2 outcomes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..identity import canonical_json_bytes
from .contracts_v2 import (
    C008CBV2ExecutionContract,
    C008CBV2RunReport,
    build_c008c_b_v2_execution_contract,
)
from .errors import C008CBEvidenceError
from .manifest import build_c008c_b_execution_manifest
from .report_v2 import (
    run_c008c_b_v2_dev_validation,
    validate_c008c_b_v2_execution_contract,
    validate_c008c_b_v2_report,
)


B_V2_EXECUTION_CONTRACT_PATH = Path(
    "docs/validation/evidence/c008c_b_v2_execution_contract.json"
)
B_V2_REPORT_PATH = Path(
    "docs/validation/evidence/c008c_b_v2_dev_validation_report.json"
)

_HISTORICAL_PATHS = (
    Path("docs/validation/evidence/c008c_b_execution_manifest.json"),
    Path("docs/validation/evidence/c008c_b_dev_validation_report.json"),
    Path("docs/validation/evidence/c008c_protected_source_manifest.json"),
    Path("docs/validation/evidence/c008c_h2_decimal_remediation.json"),
    Path(
        "docs/validation/evidence/"
        "c008c_h3_metric_fixed_cutoff_transition.json"
    ),
)


def _root(root: Path | None) -> Path:
    base = Path.cwd() if root is None else Path(root)
    try:
        resolved = base.resolve(strict=True)
    except OSError as exc:
        raise C008CBEvidenceError("repository root cannot be resolved") from exc
    if not (resolved / "pyproject.toml").is_file():
        raise C008CBEvidenceError("repository root is not an MSA checkout")
    return resolved


def _evidence_paths(base: Path) -> tuple[Path, Path]:
    evidence_dir = (base / "docs/validation/evidence").resolve()
    contract_path = (base / B_V2_EXECUTION_CONTRACT_PATH).resolve()
    report_path = (base / B_V2_REPORT_PATH).resolve()
    historical = {(base / item).resolve() for item in _HISTORICAL_PATHS}
    if (
        contract_path.parent != evidence_dir
        or report_path.parent != evidence_dir
        or contract_path == report_path
        or contract_path in historical
        or report_path in historical
        or contract_path.name != "c008c_b_v2_execution_contract.json"
        or report_path.name != "c008c_b_v2_dev_validation_report.json"
    ):
        raise C008CBEvidenceError(
            "B-v2 Evidence paths must be append-only and distinct from v1"
        )
    return contract_path, report_path


def _frozen_bytes(base: Path) -> dict[Path, bytes]:
    try:
        return {item: (base / item).read_bytes() for item in _HISTORICAL_PATHS}
    except OSError as exc:
        raise C008CBEvidenceError(
            "historical authority cannot be snapshotted"
        ) from exc


def _assert_frozen_bytes(base: Path, expected: dict[Path, bytes]) -> None:
    try:
        changed = tuple(
            item
            for item, raw in expected.items()
            if (base / item).read_bytes() != raw
        )
    except OSError as exc:
        raise C008CBEvidenceError(
            "historical authority cannot be rechecked"
        ) from exc
    if changed:
        raise C008CBEvidenceError(
            "B-v2 operation changed historical authority: "
            + ", ".join(item.as_posix() for item in changed)
        )


def _read_payload(path: Path, label: str) -> tuple[bytes, dict[str, object]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C008CBEvidenceError(f"missing or invalid {label}") from exc
    if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
        raise C008CBEvidenceError(f"non-canonical {label}")
    return raw, payload


def check_existing_c008c_b_v2_evidence(
    root: Path | None = None,
) -> tuple[Path, Path]:
    """Verify committed v2 Evidence without Core/Replay/cutoff execution."""

    base = _root(root)
    contract_path, report_path = _evidence_paths(base)
    contract_raw, contract_payload = _read_payload(
        contract_path, "B-v2 execution contract Evidence"
    )
    report_raw, report_payload = _read_payload(
        report_path, "B-v2 report Evidence"
    )
    try:
        contract = C008CBV2ExecutionContract.from_dict(contract_payload)
        report = C008CBV2RunReport.from_dict(report_payload)
        manifest = build_c008c_b_execution_manifest(base)
        validate_c008c_b_v2_execution_contract(contract, manifest)
        validate_c008c_b_v2_report(report, contract, manifest, base)
    except (TypeError, ValueError) as exc:
        raise C008CBEvidenceError(
            "B-v2 Evidence differs from reviewed source authority"
        ) from exc
    if (
        contract_raw != canonical_json_bytes(contract.to_dict())
        or report_raw != canonical_json_bytes(report.to_dict())
    ):
        raise C008CBEvidenceError("B-v2 Evidence canonical-byte mismatch")
    return contract_path, report_path


def _write_or_refuse_different(path: Path, expected: bytes) -> None:
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise C008CBEvidenceError(
                f"existing B-v2 Evidence cannot be read: {path.name}"
            ) from exc
        if existing != expected:
            raise C008CBEvidenceError(
                f"refusing to overwrite different B-v2 Evidence: {path.name}"
            )
    try:
        path.write_bytes(expected)
    except OSError as exc:
        raise C008CBEvidenceError(
            f"unable to write B-v2 Evidence: {path.name}"
        ) from exc


def write_c008c_b_v2_evidence(
    root: Path | None = None,
    *,
    check: bool = False,
) -> tuple[Path, Path]:
    """Execute/write v2 only, or fully re-execute and byte-check it."""

    base = _root(root)
    frozen = _frozen_bytes(base)
    contract_path, report_path = _evidence_paths(base)
    try:
        manifest = build_c008c_b_execution_manifest(base)
        contract = build_c008c_b_v2_execution_contract(manifest)
        validate_c008c_b_v2_execution_contract(contract, manifest)
        if check:
            _, contract_payload = _read_payload(
                contract_path, "B-v2 execution contract Evidence"
            )
            _, report_payload = _read_payload(
                report_path, "B-v2 report Evidence"
            )
            committed_contract = C008CBV2ExecutionContract.from_dict(
                contract_payload
            )
            committed_report = C008CBV2RunReport.from_dict(report_payload)
            validate_c008c_b_v2_execution_contract(
                committed_contract, manifest
            )
            validate_c008c_b_v2_report(
                committed_report, committed_contract, manifest, base
            )
        report = run_c008c_b_v2_dev_validation(base)
        validate_c008c_b_v2_report(report, contract, manifest, base)
        expected_contract = canonical_json_bytes(contract.to_dict())
        expected_report = canonical_json_bytes(report.to_dict())
        if check:
            try:
                actual_contract = contract_path.read_bytes()
                actual_report = report_path.read_bytes()
            except OSError as exc:
                raise C008CBEvidenceError(
                    "committed B-v2 Evidence cannot be read"
                ) from exc
            if (
                actual_contract != expected_contract
                or actual_report != expected_report
            ):
                raise C008CBEvidenceError(
                    "B-v2 Evidence differs from full source-bound execution"
                )
        else:
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                for path, expected in (
                    (contract_path, expected_contract),
                    (report_path, expected_report),
                ):
                    if path.exists() and path.read_bytes() != expected:
                        raise C008CBEvidenceError(
                            "refusing to overwrite different B-v2 Evidence: "
                            + path.name
                        )
            except OSError as exc:
                raise C008CBEvidenceError(
                    "existing B-v2 Evidence cannot be preflighted"
                ) from exc
            _write_or_refuse_different(contract_path, expected_contract)
            _write_or_refuse_different(report_path, expected_report)
    finally:
        _assert_frozen_bytes(base, frozen)
    return contract_path, report_path


def b_v2_evidence_sha256(path: Path) -> str:
    """Return a printable Evidence digest without changing validation."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "B_V2_EXECUTION_CONTRACT_PATH",
    "B_V2_REPORT_PATH",
    "b_v2_evidence_sha256",
    "check_existing_c008c_b_v2_evidence",
    "write_c008c_b_v2_evidence",
]
