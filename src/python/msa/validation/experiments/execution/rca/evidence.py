"""Canonical writer and non-reexecuting verifier for locked RCA evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...identity import canonical_json_bytes, semantic_id
from ..evidence import check_existing_c008c_b_evidence
from .contracts import (
    C008CBRCAEvidenceLock,
    C008CBRCAManifest,
    C008CBRootCauseReport,
    DiagnosticLayer,
)
from .cutoff import run_cutoff_diagnostics
from .determinism import run_determinism_diagnostics
from .errors import C008CBRCAEvidenceError
from .manifest import (
    build_c008c_b_rca_manifest,
    load_b_sources,
    validate_c008c_b_rca_manifest,
)
from .report import build_root_cause_report


MANIFEST_PATH = Path(
    "docs/validation/evidence/c008c_b_root_cause_manifest.json"
)
REPORT_PATH = Path(
    "docs/validation/evidence/c008c_b_root_cause_report.json"
)
LOCK_PATH = Path("docs/validation/evidence/c008c_b_root_cause_lock.json")
ANALYSIS_PATH = Path("docs/validation/c008c_b_root_cause_analysis.md")

# Frozen only after the single authorized formal rerun.  check-existing fails
# closed until this reviewed source constant is replaced by that formal Lock ID.
REVIEWED_RCA_EVIDENCE_LOCK_ID = (
    "c008c-b-rca-evidence-lock-v1-"
    "db11000639f8f950e03b7af5e61c48af3840df84e407275d121f963be6f69580"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _base(root: Path | None) -> Path:
    result = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    if not (result / "pyproject.toml").is_file():
        raise C008CBRCAEvidenceError("RCA root is not an MSA checkout")
    return result


def _read(path: Path, cls: type):
    try:
        raw = path.read_bytes()
        value = cls.from_dict(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise C008CBRCAEvidenceError(
            f"invalid RCA evidence: {path.name}"
        ) from exc
    if raw != canonical_json_bytes(value.to_dict()):
        raise C008CBRCAEvidenceError(
            f"non-canonical RCA evidence: {path.name}"
        )
    return value, raw


def _unique_paths(results, layer: DiagnosticLayer, semantic: bool) -> tuple[str, ...]:
    paths = []
    for result in results:
        summary = next(item for item in result.layer_summaries if item.layer is layer)
        path = (
            summary.first_semantic_difference_path
            if semantic
            else summary.first_identity_difference_path
        )
        if path is not None and path not in paths:
            paths.append(path)
    return tuple(paths)


def _component_path(result, component_name: str) -> str | None:
    return next(
        item.first_difference_path
        for item in result.components
        if item.component_name == component_name
    )


def analysis_bytes(manifest, report) -> bytes:
    decimal = report.determinism_results[1::2]
    layers: dict[str, int] = {}
    for result in report.cutoff_results:
        layers[result.final_layer.value] = layers.get(result.final_layer.value, 0) + 1
    metric_rewrites = tuple(
        (item.dataset_case_id, _component_path(item, "metric_semantic"))
        for item in report.cutoff_results
        if not item.metric_semantic_equal
    )
    identity_controls = tuple(
        (item.dataset_case_id, _component_path(item, "metric_full_payload"))
        for item in report.cutoff_results
        if item.identity_only_difference
    )
    descriptive: dict[str, int] = {}
    for item in report.degeneration_attributions:
        status = item.descriptive_status_without_global_propagation
        descriptive[status] = descriptive.get(status, 0) + 1
    text = f"""# C-008C-B Root Cause Analysis

This is bounded diagnostic evidence. It does not recalculate any frozen Gate,
does not modify the original B Evidence, and leaves `BLOCKED_BEFORE_OOS` intact.

## Frozen schedules

- RCA Manifest: `{manifest.rca_manifest_id}`
- B Report: `{manifest.b_run_report_id}`
- Determinism: 40 pairs, normal A + normal B + precision-7 `ROUND_FLOOR`
- Fixed cutoff: 15 cases, one selected checkpoint per case
- Replay/OOS/full 390 matrix/full AsOf matrix: not executed

## Source-derived findings

- Root Cause Subjects: `{[item.value for item in report.root_cause_subjects]}`
- Disposition: `{report.disposition.value}`
- Attribution gaps: `{list(report.admitted_attribution_gaps)}`
- Recommendations: `{list(report.recommendations)}`

## Determinism results

- Same-context mismatches: {report.same_context_mismatch_count}/40
- Decimal-context mismatches: {report.decimal_context_mismatch_count}/40
- Core semantic mismatches: {report.core_semantic_mismatch_count}
- Audit semantic mismatches: {report.audit_semantic_mismatch_count}
- Audit identity/provenance mismatches: {report.audit_identity_or_provenance_mismatch_count}
- Metric semantic mismatches: {report.metric_semantic_mismatch_count}
- Decimal Core first semantic paths: `{list(_unique_paths(decimal, DiagnosticLayer.CORE, True))}`
- Decimal Audit first identity/provenance paths: `{list(_unique_paths(decimal, DiagnosticLayer.AUDIT, False))}`
- Decimal Metric first semantic paths: `{list(_unique_paths(decimal, DiagnosticLayer.METRIC, True))}`

## Fixed-cutoff results

- Final-layer counts: `{layers}`
- Metric semantic rewrites and first paths: `{list(metric_rewrites)}`
- Identity/source controls and first paths: `{list(identity_controls)}`
- Prefix Source invalid: {report.prefix_source_invalid_count}
- Frame rewrites: {report.frame_bundle_rewrite_count}
- Active Box Ledger rewrites: {report.active_box_ledger_rewrite_count}

`compare_shared_asof` uses the strict boundary `item.as_of_time < cutoff_time`.
Supplying formal AsOf plus one microsecond includes the exact formal AsOf; the
RCA independently validates the truncated Prefix Source before classification.

## Degeneration attribution

- Variant-direct evidence: {report.variant_direct_evidence_count}
- Global Baseline propagation evidence: {report.global_propagation_evidence_count}
- Shared static evidence: {report.shared_static_evidence_count}
- Insufficient evidence: {report.insufficient_evidence_count}
- Direct triggered rules: {report.direct_degeneration_rule_count}
- Global propagated triggered rules: {report.global_baseline_propagation_count}
- Status without global propagation: `{descriptive}`

## Boundary

The original B Manifest/Report, Gate results, Stage status, protected source,
Dataset, Plan, parameters, thresholds, Metrics, Causal Audit, Reference, and
Core are unchanged. No remediation is performed by this RCA hardening task.
"""
    return text.replace("\r\n", "\n").encode("utf-8")


def build_evidence_lock(
    manifest,
    manifest_raw: bytes,
    report,
    report_raw: bytes,
    analysis_raw: bytes,
    b_manifest,
    b_manifest_raw: bytes,
    b_report,
    b_report_raw: bytes,
) -> C008CBRCAEvidenceLock:
    kwargs = {
        "rca_manifest_id": manifest.rca_manifest_id,
        "rca_manifest_sha256": _sha(manifest_raw),
        "root_cause_report_id": report.root_cause_report_id,
        "root_cause_report_sha256": _sha(report_raw),
        "analysis_sha256": _sha(analysis_raw),
        "b_execution_manifest_id": b_manifest.execution_manifest_id,
        "b_manifest_sha256": _sha(b_manifest_raw),
        "b_run_report_id": b_report.run_report_id,
        "b_report_sha256": _sha(b_report_raw),
        "schema_version": 1,
    }
    return C008CBRCAEvidenceLock(
        evidence_lock_id=semantic_id(C008CBRCAEvidenceLock._PREFIX, kwargs),
        **kwargs,
    )


def write_c008c_b_rca_evidence(root: Path | None = None):
    base = _base(root)
    manifest = build_c008c_b_rca_manifest(base)
    manifest_path = base / MANIFEST_PATH
    report_path = base / REPORT_PATH
    analysis_path = base / ANALYSIS_PATH
    lock_path = base / LOCK_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_raw = canonical_json_bytes(manifest.to_dict())
    # Freeze the outcome-independent schedule before any diagnostic Core Run.
    manifest_path.write_bytes(manifest_raw)
    determinism = run_determinism_diagnostics(manifest, base)
    cutoff = run_cutoff_diagnostics(manifest, base)
    b_manifest, b_report, b_manifest_raw, b_report_raw = load_b_sources(base)
    report = build_root_cause_report(
        manifest, b_report, determinism, cutoff
    )
    report_raw = canonical_json_bytes(report.to_dict())
    analysis_raw = analysis_bytes(manifest, report)
    report_path.write_bytes(report_raw)
    analysis_path.write_bytes(analysis_raw)
    lock = build_evidence_lock(
        manifest,
        manifest_raw,
        report,
        report_raw,
        analysis_raw,
        b_manifest,
        b_manifest_raw,
        b_report,
        b_report_raw,
    )
    lock_path.write_bytes(canonical_json_bytes(lock.to_dict()))
    return manifest_path, report_path, analysis_path, lock_path


def check_existing_c008c_b_rca_evidence(root: Path | None = None):
    base = _base(root)
    # This verifies committed A authority, protected bytes, B contracts/bytes,
    # and does not call either RCA diagnostic executor.
    check_existing_c008c_b_evidence(base)
    b_manifest, b_report, b_manifest_raw, b_report_raw = load_b_sources(base)
    manifest, manifest_raw = _read(base / MANIFEST_PATH, C008CBRCAManifest)
    report, report_raw = _read(base / REPORT_PATH, C008CBRootCauseReport)
    lock, lock_raw = _read(base / LOCK_PATH, C008CBRCAEvidenceLock)
    validate_c008c_b_rca_manifest(manifest, base)
    if report.rca_manifest_id != manifest.rca_manifest_id:
        raise C008CBRCAEvidenceError("RCA report does not bind RCA manifest")
    if report.b_run_report_id != b_report.run_report_id:
        raise C008CBRCAEvidenceError("RCA report does not bind existing B report")
    if report.original_stage_status is not b_report.stage_status:
        raise C008CBRCAEvidenceError("RCA changed the original Stage status")
    for pair, same, decimal in zip(
        manifest.diagnostic_pairs,
        report.determinism_results[::2],
        report.determinism_results[1::2],
        strict=True,
    ):
        if (
            same.diagnostic_pair_id != pair.diagnostic_pair_id
            or decimal.diagnostic_pair_id != pair.diagnostic_pair_id
            or same.diagnostic_kind.value != "SAME_CONTEXT_REPEAT"
            or decimal.diagnostic_kind.value
            != "DECIMAL_CONTEXT_PERTURBATION"
            or same.diagnostic_result_id == decimal.diagnostic_result_id
        ):
            raise C008CBRCAEvidenceError("RCA diagnostic schedule mismatch")
    cutoff_schedule = tuple(
        (
            item.dataset_case_id,
            item.cutoff_as_of_time,
            item.checkpoint_index,
            item.selection_kind,
        )
        for item in report.cutoff_results
    )
    expected_cutoff_schedule = tuple(
        zip(
            manifest.cutoff_case_ids,
            manifest.cutoff_as_of_times,
            manifest.cutoff_checkpoint_indices,
            manifest.cutoff_selection_kinds,
            strict=True,
        )
    )
    if cutoff_schedule != expected_cutoff_schedule:
        raise C008CBRCAEvidenceError("RCA cutoff schedule mismatch")
    expected_report = build_root_cause_report(
        manifest,
        b_report,
        report.determinism_results,
        report.cutoff_results,
    )
    if report.to_dict() != expected_report.to_dict():
        raise C008CBRCAEvidenceError(
            "RCA report derived fields or disposition are inconsistent"
        )
    analysis_raw = (base / ANALYSIS_PATH).read_bytes()
    if analysis_raw != analysis_bytes(manifest, report):
        raise C008CBRCAEvidenceError(
            "RCA analysis document is not source-bound"
        )
    expected_lock = build_evidence_lock(
        manifest,
        manifest_raw,
        report,
        report_raw,
        analysis_raw,
        b_manifest,
        b_manifest_raw,
        b_report,
        b_report_raw,
    )
    if lock.to_dict() != expected_lock.to_dict():
        raise C008CBRCAEvidenceError("RCA Evidence Lock bindings mismatch")
    if lock.evidence_lock_id != REVIEWED_RCA_EVIDENCE_LOCK_ID:
        raise C008CBRCAEvidenceError(
            "RCA Evidence Lock differs from reviewed verifier authority"
        )
    if lock_raw != canonical_json_bytes(lock.to_dict()):
        raise C008CBRCAEvidenceError("RCA Evidence Lock is non-canonical")
    return (
        base / MANIFEST_PATH,
        base / REPORT_PATH,
        base / ANALYSIS_PATH,
        base / LOCK_PATH,
    )


__all__ = [
    "REVIEWED_RCA_EVIDENCE_LOCK_ID",
    "analysis_bytes",
    "build_evidence_lock",
    "check_existing_c008c_b_rca_evidence",
    "write_c008c_b_rca_evidence",
]
