"""Canonical evidence writer and full source-bound report verifier."""

from __future__ import annotations

import json
from pathlib import Path

from ..identity import canonical_json_bytes
from .contracts import C008CBRunReport
from .errors import C008CBEvidenceError, C008CBReportError
from .manifest import build_c008c_b_execution_manifest
from .report import (
    run_c008c_b_dev_validation,
    validate_c008c_b_report,
)


_MANIFEST_PATH = Path(
    "docs/validation/evidence/c008c_b_execution_manifest.json"
)
_REPORT_PATH = Path(
    "docs/validation/evidence/c008c_b_dev_validation_report.json"
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


def verify_c008c_b_report(
    report: C008CBRunReport,
    root: Path | None = None,
) -> C008CBRunReport:
    """Re-execute the exact B authority and compare the complete report."""

    validated = validate_c008c_b_report(report, root=root)
    expected = run_c008c_b_dev_validation(root)
    if expected.to_dict() != validated.to_dict():
        raise C008CBReportError(
            "report differs from complete source-bound B re-execution"
        )
    return validated


def _read_report(path: Path) -> C008CBRunReport:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        report = C008CBRunReport.from_dict(payload)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise C008CBEvidenceError(
            "committed B report evidence cannot be parsed"
        ) from exc
    if raw != canonical_json_bytes(report.to_dict()):
        raise C008CBEvidenceError(
            "committed B report is not canonical evidence bytes"
        )
    return report


def write_c008c_b_evidence(
    root: Path | None = None,
    *,
    check: bool = False,
) -> tuple[Path, Path]:
    """Generate or source-bound byte-check the two compact B evidence files."""

    base = _root(root)
    manifest = build_c008c_b_execution_manifest(base)
    manifest_path = base / _MANIFEST_PATH
    report_path = base / _REPORT_PATH
    if check:
        committed_report = _read_report(report_path)
        report = verify_c008c_b_report(committed_report, base)
    else:
        report = run_c008c_b_dev_validation(base)
    payloads = (
        (manifest_path, canonical_json_bytes(manifest.to_dict())),
        (report_path, canonical_json_bytes(report.to_dict())),
    )
    if check:
        for path, expected in payloads:
            try:
                actual = path.read_bytes()
            except OSError as exc:
                raise C008CBEvidenceError(
                    f"B evidence cannot be read: {path.name}"
                ) from exc
            if actual != expected:
                raise C008CBEvidenceError(
                    f"B evidence differs from source-bound execution: {path.name}"
                )
    else:
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            for path, expected in payloads:
                path.write_bytes(expected)
        except OSError as exc:
            raise C008CBEvidenceError(
                "unable to write canonical B evidence"
            ) from exc
    return manifest_path, report_path


__all__ = [
    "verify_c008c_b_report",
    "write_c008c_b_evidence",
]
