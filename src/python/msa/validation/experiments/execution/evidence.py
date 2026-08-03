"""Canonical evidence writer and full source-bound report verifier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..contracts import DatasetPartition
from ..identity import canonical_json_bytes, digest
from .contracts import C008CBExecutionManifest, C008CBRunReport
from .degeneration import evaluate_validation_degeneration
from .deltas import calculate_metric_deltas
from .errors import C008CBEvidenceError, C008CBReportError
from .gate_evaluator import evaluate_c008c_b_gates
from .manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
    validate_c008c_b_execution_manifest,
)
from .report import (
    _partition_summaries,
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


def _read_manifest(path: Path) -> C008CBExecutionManifest:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        manifest = C008CBExecutionManifest.from_dict(payload)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise C008CBEvidenceError(
            "committed B execution manifest cannot be parsed"
        ) from exc
    if raw != canonical_json_bytes(manifest.to_dict()):
        raise C008CBEvidenceError(
            "committed B execution manifest is not canonical evidence bytes"
        )
    return manifest


def _same_payloads(actual: tuple, expected: tuple) -> bool:
    return tuple(item.to_dict() for item in actual) == tuple(
        item.to_dict() for item in expected
    )


def _validate_existing_references(
    manifest: C008CBExecutionManifest,
    report: C008CBRunReport,
    root: Path,
) -> None:
    """Cross-check stored nested evidence without executing the Core."""

    for pair, result in zip(
        manifest.execution_pairs, report.case_results, strict=True
    ):
        expected = (
            pair.execution_pair_id,
            pair.dataset_case_id,
            pair.variant_id,
            pair.partition,
            pair.scenario,
            pair.seed,
            pair.source_input_payload_digest,
            pair.core_config_payload_digest,
            pair.metric_config_payload_digest,
        )
        actual = (
            result.execution_pair_id,
            result.dataset_case_id,
            result.variant_id,
            result.partition,
            result.scenario,
            result.seed,
            result.source_input_payload_digest,
            result.core_config_payload_digest,
            result.metric_config_payload_digest,
        )
        if actual != expected:
            raise C008CBEvidenceError(
                "CaseResult facts differ from its frozen execution pair"
            )

    for pair, result, comparison in zip(
        manifest.execution_pairs,
        report.case_results,
        report.determinism_comparisons,
        strict=True,
    ):
        if (
            comparison.execution_pair_id != pair.execution_pair_id
            or comparison.dataset_case_id != pair.dataset_case_id
            or comparison.variant_id != pair.variant_id
            or comparison.first_case_result_id != result.case_result_id
            or comparison.first_case_payload_digest
            != digest(result.to_dict())
            or not comparison.decimal_context_changed
        ):
            raise C008CBEvidenceError(
                "determinism comparison has inconsistent source references"
            )

    _, dataset, _, plan, _ = load_c008c_b_authority(root)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    baseline_variant_id = manifest.variant_ids[0]
    replay_schedule = [
        (sample_id, "BASELINE", case_id, baseline_variant_id)
        for sample_id, case_id in zip(
            manifest.baseline_replay_sample_ids,
            manifest.executable_case_ids,
            strict=True,
        )
    ]
    replay_schedule.extend(
        (sample_id, "VARIANT", case_id, variant_id)
        for sample_id, (variant_id, case_id) in zip(
            manifest.variant_replay_sample_ids,
            (
                (variant_id, case_id)
                for variant_id in manifest.variant_ids[1:]
                for case_id in plan.variant_replay_policy.dataset_case_ids
            ),
            strict=True,
        )
    )
    for comparison, expected in zip(
        report.replay_comparisons, replay_schedule, strict=True
    ):
        sample_id, scope, case_id, variant_id = expected
        case = cases[case_id]
        if (
            comparison.replay_sample_id != sample_id
            or comparison.scope != scope
            or comparison.dataset_case_id != case_id
            or comparison.variant_id != variant_id
            or comparison.partition is not case.partition
            or comparison.scenario is not case.scenario_kind
            or comparison.seed != case.seed
        ):
            raise C008CBEvidenceError(
                "replay comparison differs from the frozen replay schedule"
            )

    for comparison, case_id in zip(
        report.fixed_cutoff_comparisons,
        manifest.fixed_cutoff_case_ids,
        strict=True,
    ):
        case = cases[case_id]
        if (
            comparison.dataset_case_id != case_id
            or comparison.baseline_variant_id != baseline_variant_id
            or comparison.partition is not case.partition
            or comparison.scenario is not case.scenario_kind
            or comparison.seed != case.seed
        ):
            raise C008CBEvidenceError(
                "fixed-cutoff comparison differs from its frozen case"
            )

    if any(
        item.partition is DatasetPartition.OOS or item.seed == 3
        for item in (
            *report.case_results,
            *report.replay_comparisons,
            *report.fixed_cutoff_comparisons,
        )
    ):
        raise C008CBEvidenceError(
            "existing B evidence contains a forbidden OOS outcome"
        )

    expected_deltas = calculate_metric_deltas(report.case_results, root)
    if not _same_payloads(
        report.metric_delta_summaries, expected_deltas
    ):
        raise C008CBEvidenceError(
            "stored metric deltas differ from stored CaseResults"
        )
    expected_degeneration = evaluate_validation_degeneration(
        report.case_results,
        expected_deltas,
        report.replay_comparisons,
        report.fixed_cutoff_comparisons,
        root,
    )
    if not _same_payloads(
        report.degeneration_summaries, expected_degeneration
    ):
        raise C008CBEvidenceError(
            "stored degeneration results differ from stored evidence"
        )
    expected_gates = evaluate_c008c_b_gates(
        manifest,
        report.case_results,
        report.determinism_comparisons,
        report.replay_comparisons,
        report.fixed_cutoff_comparisons,
        expected_degeneration,
        root,
    )
    if not _same_payloads(report.gate_results, expected_gates):
        raise C008CBEvidenceError(
            "stored GateResults differ from stored evidence"
        )
    expected_partitions = _partition_summaries(
        report.case_results,
        expected_deltas,
        report.replay_comparisons,
        expected_degeneration,
        root,
    )
    if not _same_payloads(
        report.partition_summaries, expected_partitions
    ):
        raise C008CBEvidenceError(
            "stored partition summaries differ from stored evidence"
        )


def check_existing_c008c_b_evidence(
    root: Path | None = None,
) -> tuple[Path, Path]:
    """Validate existing evidence without re-executing B-stage outcomes.

    This mode performs the committed C-008C-A authority preflight, protected
    source validation, strict B contract and identity reconstruction, frozen
    schedule/OOS checks, and internal derived-evidence consistency checks. It
    does not call the Core, Replay, fixed-cutoff execution, or the formal full
    source-bound verifier.
    """

    base = _root(root)
    manifest_path = base / _MANIFEST_PATH
    report_path = base / _REPORT_PATH
    manifest = _read_manifest(manifest_path)
    report = _read_report(report_path)
    validate_c008c_b_execution_manifest(manifest, base)
    validate_c008c_b_report(report, manifest, base)
    _validate_existing_references(manifest, report, base)
    for path, payload in (
        (manifest_path, manifest.to_dict()),
        (report_path, report.to_dict()),
    ):
        try:
            actual = path.read_bytes()
        except OSError as exc:
            raise C008CBEvidenceError(
                f"B evidence cannot be read: {path.name}"
            ) from exc
        canonical = canonical_json_bytes(payload)
        if actual != canonical or hashlib.sha256(actual).digest() != (
            hashlib.sha256(canonical).digest()
        ):
            raise C008CBEvidenceError(
                f"B evidence SHA/canonical-byte mismatch: {path.name}"
            )
    return manifest_path, report_path


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
    "check_existing_c008c_b_evidence",
    "verify_c008c_b_report",
    "write_c008c_b_evidence",
]
