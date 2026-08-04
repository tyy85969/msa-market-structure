"""Outcome-independent construction of the bounded RCA schedule."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...contracts import DatasetPartition
from ...identity import canonical_json_bytes, digest, semantic_id
from ..contracts import C008CBExecutionManifest, C008CBRunReport, FixedCutoffStatus
from ..manifest import load_c008c_b_authority, validate_c008c_b_execution_manifest
from ..report import validate_c008c_b_report
from .contracts import C008CBRCADiagnosticPair, C008CBRCAManifest
from .errors import C008CBRCAManifestError


_B_MANIFEST = Path("docs/validation/evidence/c008c_b_execution_manifest.json")
_B_REPORT = Path("docs/validation/evidence/c008c_b_dev_validation_report.json")

_ASSUMPTIONS = (
    "RCA schedule is frozen before any diagnostic Core Run",
    "Baseline covers all 15 DEVELOPMENT and VALIDATION cases",
    "Each non-Baseline Variant uses the first VALIDATION case in frozen Dataset order",
    "Selection reads no Metric outcome and excludes every seed 3 OOS case",
    "Stable controls use the median formal checkpoint and rewrite cases use the earliest unstable checkpoint",
    "Each pair permits two same-context Runs and one precision 7 ROUND_FLOOR Run",
)


def _read(base: Path, relative: Path, cls: type) -> tuple[object, bytes]:
    try:
        raw = (base / relative).read_bytes()
        result = cls.from_dict(json.loads(raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise C008CBRCAManifestError(f"cannot read {relative.as_posix()}") from exc
    if raw != canonical_json_bytes(result.to_dict()):
        raise C008CBRCAManifestError(f"non-canonical {relative.as_posix()}")
    return result, raw


def load_b_sources(root: Path) -> tuple[C008CBExecutionManifest, C008CBRunReport, bytes, bytes]:
    manifest, manifest_raw = _read(root, _B_MANIFEST, C008CBExecutionManifest)
    report, report_raw = _read(root, _B_REPORT, C008CBRunReport)
    validate_c008c_b_execution_manifest(manifest, root)
    validate_c008c_b_report(report, manifest, root)
    return manifest, report, manifest_raw, report_raw


def _diagnostic_pair(pair: object, selection_kind: str) -> C008CBRCADiagnosticPair:
    kwargs = {
        "execution_pair_id": pair.execution_pair_id,
        "dataset_case_id": pair.dataset_case_id,
        "variant_id": pair.variant_id,
        "partition": pair.partition.value,
        "scenario": pair.scenario.value,
        "seed": pair.seed,
        "schedule_index": pair.schedule_index,
        "selection_kind": selection_kind,
        "schema_version": 1,
    }
    return C008CBRCADiagnosticPair(
        diagnostic_pair_id=semantic_id(C008CBRCADiagnosticPair._PREFIX, kwargs),
        **kwargs,
    )


def build_c008c_b_rca_manifest(root: Path | None = None) -> C008CBRCAManifest:
    base = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    b_manifest, b_report, b_manifest_raw, b_report_raw = load_b_sources(base)
    baseline, dataset, _, plan, protected = load_c008c_b_authority(base)
    pair_index = {
        (item.dataset_case_id, item.variant_id): item
        for item in b_manifest.execution_pairs
    }
    baseline_id = plan.variants[0].variant_id
    b_cases = tuple(
        item for item in dataset.cases if item.partition is not DatasetPartition.OOS
    )
    validation_case = next(
        item for item in dataset.cases if item.partition is DatasetPartition.VALIDATION
    )
    pairs = tuple(
        _diagnostic_pair(pair_index[(case.dataset_case_id, baseline_id)], "BASELINE_ALL_B")
        for case in b_cases
    ) + tuple(
        _diagnostic_pair(
            pair_index[(validation_case.dataset_case_id, variant.variant_id)],
            "VARIANT_FIRST_VALIDATION",
        )
        for variant in plan.variants[1:]
    )
    cutoff_indices = []
    cutoff_kinds = []
    cutoff_times = []
    for comparison in b_report.fixed_cutoff_comparisons:
        if comparison.status is FixedCutoffStatus.STABLE:
            index = len(comparison.checkpoints) // 2
            kind = "STABLE_MEDIAN_CONTROL"
        else:
            index = next(
                i for i, checkpoint in enumerate(comparison.checkpoints)
                if not checkpoint.stable
            )
            kind = "EARLIEST_UNSTABLE"
        cutoff_indices.append(index)
        cutoff_kinds.append(kind)
        cutoff_times.append(comparison.checkpoints[index].cutoff_as_of_time.isoformat())
    cutoff_case_ids = tuple(
        item.dataset_case_id for item in b_report.fixed_cutoff_comparisons
    )
    diagnostic_digest = digest([item.to_dict() for item in pairs])
    cutoff_digest = digest([
        {
            "dataset_case_id": case_id,
            "cutoff_as_of_time": time,
            "checkpoint_index": index,
            "selection_kind": kind,
        }
        for case_id, time, index, kind in zip(
            cutoff_case_ids, cutoff_times, cutoff_indices, cutoff_kinds, strict=True
        )
    ])
    kwargs = {
        "baseline_id": baseline.baseline_id,
        "dataset_manifest_id": dataset.dataset_manifest_id,
        "experiment_plan_id": plan.experiment_plan_id,
        "protected_source_manifest_id": protected.protected_source_manifest_id,
        "b_execution_manifest_id": b_manifest.execution_manifest_id,
        "b_run_report_id": b_report.run_report_id,
        "b_manifest_sha256": hashlib.sha256(b_manifest_raw).hexdigest(),
        "b_report_sha256": hashlib.sha256(b_report_raw).hexdigest(),
        "diagnostic_pairs": pairs,
        "cutoff_case_ids": cutoff_case_ids,
        "cutoff_as_of_times": tuple(cutoff_times),
        "cutoff_checkpoint_indices": tuple(cutoff_indices),
        "cutoff_selection_kinds": tuple(cutoff_kinds),
        "diagnostic_schedule_digest": diagnostic_digest,
        "cutoff_schedule_digest": cutoff_digest,
        "same_context_runs_per_pair": 2,
        "altered_decimal_runs_per_pair": 1,
        "decimal_precision": 7,
        "decimal_rounding": "ROUND_FLOOR",
        "assumptions": _ASSUMPTIONS,
        "schema_version": 1,
    }
    payload = {
        key: [item.to_dict() for item in value]
        if key == "diagnostic_pairs"
        else list(value) if isinstance(value, tuple) else value
        for key, value in kwargs.items()
    }
    return C008CBRCAManifest(
        rca_manifest_id=semantic_id(C008CBRCAManifest._PREFIX, payload), **kwargs
    )


def validate_c008c_b_rca_manifest(
    manifest: C008CBRCAManifest, root: Path | None = None
) -> C008CBRCAManifest:
    if not isinstance(manifest, C008CBRCAManifest):
        raise C008CBRCAManifestError("manifest must be C008CBRCAManifest")
    expected = build_c008c_b_rca_manifest(root)
    if manifest.to_dict() != expected.to_dict():
        raise C008CBRCAManifestError("RCA manifest differs from frozen sources")
    if C008CBRCAManifest.from_dict(manifest.to_dict()) != manifest:
        raise C008CBRCAManifestError("RCA manifest round-trip mismatch")
    return manifest


__all__ = ["build_c008c_b_rca_manifest", "load_b_sources", "validate_c008c_b_rca_manifest"]
