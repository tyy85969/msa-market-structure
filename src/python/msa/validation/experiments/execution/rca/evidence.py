"""Canonical writer and non-reexecuting verifier for RCA evidence."""

from __future__ import annotations

import json
from pathlib import Path

from ...identity import canonical_json_bytes
from ..evidence import check_existing_c008c_b_evidence
from .contracts import C008CBRCAManifest, C008CBRootCauseReport
from .cutoff import run_cutoff_diagnostics
from .determinism import run_determinism_diagnostics
from .errors import C008CBRCAEvidenceError
from .manifest import build_c008c_b_rca_manifest, load_b_sources, validate_c008c_b_rca_manifest
from .report import build_root_cause_report


MANIFEST_PATH = Path("docs/validation/evidence/c008c_b_root_cause_manifest.json")
REPORT_PATH = Path("docs/validation/evidence/c008c_b_root_cause_report.json")
ANALYSIS_PATH = Path("docs/validation/c008c_b_root_cause_analysis.md")


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
        raise C008CBRCAEvidenceError(f"invalid RCA evidence: {path.name}") from exc
    if raw != canonical_json_bytes(value.to_dict()):
        raise C008CBRCAEvidenceError(f"non-canonical RCA evidence: {path.name}")
    return value


def _analysis(manifest, report) -> bytes:
    same = report.same_context_mismatch_count
    decimal = report.decimal_context_mismatch_count
    layers = {}
    for result in report.cutoff_results:
        layers[result.final_layer.value] = layers.get(result.final_layer.value, 0) + 1
    text = f"""# C-008C-B Root Cause Analysis

This is bounded diagnostic evidence. It does not recalculate any frozen Gate,
does not modify the original B Evidence, and leaves `BLOCKED_BEFORE_OOS` intact.

## Frozen schedules

- RCA Manifest: `{manifest.rca_manifest_id}`
- B Report: `{manifest.b_run_report_id}`
- Determinism: 40 pairs, normal A + normal B + precision-7 `ROUND_FLOOR`
- Fixed cutoff: 15 cases, one selected checkpoint per case
- Replay/OOS/full 390 matrix/full AsOf matrix: not executed

## Attribution gaps in the original B harness

1. The original determinism comparison is normal versus altered Decimal context,
   not normal run 1 versus normal run 2. The two failed Gates therefore are not
   independent experimental evidence.
2. `FUTURE_PREFIX_REWRITE` is one global Baseline fixed-cutoff aggregate applied
   to every non-Baseline Variant. It is not 25 direct Variant rewrite findings.

## Results

- Same-context mismatches: {same}/40
- Decimal-context mismatches: {decimal}/40
- Core semantic mismatches: {report.core_semantic_mismatch_count}
- Cutoff final-layer counts: {layers}
- Direct degeneration triggers: {report.direct_degeneration_rule_count}
- Global Baseline propagations: {report.global_baseline_propagation_count}
- Disposition: `{report.disposition.value}`

`compare_shared_asof` uses the strict boundary `item.as_of_time < cutoff_time`.
Supplying formal AsOf plus one microsecond therefore includes the exact formal
AsOf and is not, by itself, classified as a harness defect.

## Boundary

The original B Manifest/Report, Gate results, Stage status, protected source,
Dataset, Plan, parameters, thresholds, Metrics, Causal Audit, Reference, and
Core are unchanged. Any correction or remediation requires separate approval.
"""
    return text.replace("\r\n", "\n").encode("utf-8")


def write_c008c_b_rca_evidence(root: Path | None = None):
    base = _base(root)
    manifest = build_c008c_b_rca_manifest(base)
    manifest_path = base / MANIFEST_PATH
    report_path = base / REPORT_PATH
    analysis_path = base / ANALYSIS_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    # Freeze the outcome-independent schedule before any diagnostic Core Run.
    manifest_path.write_bytes(canonical_json_bytes(manifest.to_dict()))
    determinism = run_determinism_diagnostics(manifest, base)
    cutoff = run_cutoff_diagnostics(manifest, base)
    _, b_report, _, _ = load_b_sources(base)
    report = build_root_cause_report(manifest, b_report, determinism, cutoff)
    report_path.write_bytes(canonical_json_bytes(report.to_dict()))
    analysis_path.write_bytes(_analysis(manifest, report))
    return manifest_path, report_path, analysis_path


def check_existing_c008c_b_rca_evidence(root: Path | None = None):
    base = _base(root)
    # Includes committed A authority, protected bytes, B contracts and bytes.
    check_existing_c008c_b_evidence(base)
    _, b_report, _, _ = load_b_sources(base)
    manifest = _read(base / MANIFEST_PATH, C008CBRCAManifest)
    report = _read(base / REPORT_PATH, C008CBRootCauseReport)
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
    expected_cutoff_schedule = tuple(zip(
        manifest.cutoff_case_ids,
        manifest.cutoff_as_of_times,
        manifest.cutoff_checkpoint_indices,
        manifest.cutoff_selection_kinds,
        strict=True,
    ))
    if cutoff_schedule != expected_cutoff_schedule:
        raise C008CBRCAEvidenceError("RCA cutoff schedule mismatch")
    if tuple(
        item.variant_id for item in report.degeneration_attributions
    ) != tuple(item.variant_id for item in b_report.degeneration_summaries):
        raise C008CBRCAEvidenceError("RCA degeneration schedule mismatch")
    same = report.determinism_results[::2]
    decimal = report.determinism_results[1::2]
    expected_counts = (
        sum(not x.full_payload_equal for x in same),
        sum(not x.full_payload_equal for x in decimal),
        sum(x.core_semantic_mismatch for x in report.determinism_results),
        sum(x.core_identity_only_mismatch for x in report.determinism_results),
        sum(x.audit_semantic_mismatch for x in report.determinism_results),
        sum(x.audit_identity_or_provenance_mismatch for x in report.determinism_results),
        sum(x.metric_semantic_mismatch for x in report.determinism_results),
        sum(x.metric_identity_or_provenance_mismatch for x in report.determinism_results),
        sum(x.case_derived_only_mismatch for x in report.determinism_results),
        sum(not x.source_prefix_valid for x in report.cutoff_results),
        sum(not x.frame_bundles_equal for x in report.cutoff_results),
        sum(not x.active_box_events_equal or not x.frozen_boxes_equal for x in report.cutoff_results),
        sum(not x.metric_semantic_equal for x in report.cutoff_results),
        sum(x.identity_only_difference for x in report.cutoff_results),
    )
    actual_counts = (
        report.same_context_mismatch_count,
        report.decimal_context_mismatch_count,
        report.core_semantic_mismatch_count,
        report.core_identity_only_mismatch_count,
        report.audit_semantic_mismatch_count,
        report.audit_identity_or_provenance_mismatch_count,
        report.metric_semantic_mismatch_count,
        report.metric_identity_or_provenance_mismatch_count,
        report.case_derived_only_mismatch_count,
        report.prefix_source_invalid_count,
        report.frame_bundle_rewrite_count,
        report.active_box_ledger_rewrite_count,
        report.metric_semantic_rewrite_count,
        report.identity_only_cutoff_difference_count,
    )
    if actual_counts != expected_counts:
        raise C008CBRCAEvidenceError("RCA report derived counts are inconsistent")
    analysis = base / ANALYSIS_PATH
    if analysis.read_bytes() != _analysis(manifest, report):
        raise C008CBRCAEvidenceError("RCA analysis document is not source-bound")
    return base / MANIFEST_PATH, base / REPORT_PATH, analysis


__all__ = ["check_existing_c008c_b_rca_evidence", "write_c008c_b_rca_evidence"]
