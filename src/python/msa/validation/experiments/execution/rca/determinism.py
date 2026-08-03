"""Independent same-context and Decimal-context diagnostics."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from decimal import ROUND_FLOOR, localcontext
from pathlib import Path

from ...identity import semantic_id
from ..manifest import load_c008c_b_authority
from ..runner import _execute_pair
from .contracts import (
    C008CBRCAManifest,
    DeterminismDiagnosticKind,
    DeterminismDiagnosticResult,
    MismatchLayer,
    RootCauseDisposition,
)
from .manifest import load_b_sources, validate_c008c_b_rca_manifest
from .payload_diff import payload_differences


_IDENTITY_TOKENS = ("_id", "digest", "provenance", "source_run_id")


def _semantic(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _semantic(item)
            for key, item in value.items()
            if not any(token in key for token in _IDENTITY_TOKENS)
        }
    if isinstance(value, list):
        return [_semantic(item) for item in value]
    return value


def _payload(artifact: object, config: object) -> dict[str, object]:
    return {
        "config": config,
        "core_run": None if artifact.run is None else artifact.run.to_dict(),
        "audit": None if artifact.audit is None else artifact.audit.to_dict(),
        "metric": (
            None if artifact.metric_report is None else artifact.metric_report.to_dict()
        ),
        "case_result": artifact.result.to_dict(),
    }


def _classify(left: dict[str, object], right: dict[str, object]) -> tuple:
    equality = {key: left[key] == right[key] for key in left}
    core_semantic = _semantic(left["core_run"]) != _semantic(right["core_run"])
    audit_semantic = _semantic(left["audit"]) != _semantic(right["audit"])
    metric_semantic = _semantic(left["metric"]) != _semantic(right["metric"])
    core_identity = not equality["core_run"] and not core_semantic
    audit_identity = not equality["audit"] and not audit_semantic
    metric_identity = not equality["metric"] and not metric_semantic
    case_only = (
        not equality["case_result"]
        and all(equality[key] for key in ("config", "core_run", "audit", "metric"))
    )
    layer = MismatchLayer.NONE
    if not equality["config"]:
        layer = MismatchLayer.CONFIG_SNAPSHOT
    elif core_semantic:
        layer = MismatchLayer.CORE_RUN_SEMANTIC
    elif core_identity:
        layer = MismatchLayer.CORE_RUN_IDENTITY
    elif audit_semantic:
        layer = MismatchLayer.AUDIT_SEMANTIC
    elif audit_identity:
        layer = MismatchLayer.AUDIT_IDENTITY_OR_PROVENANCE
    elif metric_semantic:
        layer = MismatchLayer.METRIC_SEMANTIC
    elif metric_identity:
        layer = MismatchLayer.METRIC_IDENTITY_OR_PROVENANCE
    elif case_only:
        layer = MismatchLayer.CASE_RESULT_DERIVED
    elif not all(equality.values()):
        layer = MismatchLayer.UNKNOWN
    return (
        equality,
        layer,
        core_semantic,
        core_identity,
        audit_semantic,
        audit_identity,
        metric_semantic,
        metric_identity,
        case_only,
    )


def _result(pair_id: str, kind: DeterminismDiagnosticKind, left: dict, right: dict):
    total, differences = payload_differences(left, right)
    classified = _classify(left, right)
    equality, layer, *flags = classified
    semantic_path = next(
        (
            item.path
            for item in differences
            if not any(token in item.path.lower() for token in _IDENTITY_TOKENS)
        ),
        None,
    )
    disposition = (
        RootCauseDisposition.NO_ROOT_CAUSE_FOUND
        if total == 0
        else RootCauseDisposition.PROTECTED_CORE_REMEDIATION_REQUIRED
        if flags[0]
        else RootCauseDisposition.HARNESS_CORRECTION_REQUIRED
    )
    kwargs = {
        "diagnostic_pair_id": pair_id,
        "diagnostic_kind": kind,
        "config_payload_equal": equality["config"],
        "core_run_payload_equal": equality["core_run"],
        "audit_payload_equal": equality["audit"],
        "metric_payload_equal": equality["metric"],
        "case_result_payload_equal": equality["case_result"],
        "full_payload_equal": total == 0,
        "total_difference_count": total,
        "differences": differences,
        "mismatch_layer": layer,
        "first_semantic_difference_path": semantic_path,
        "core_semantic_mismatch": flags[0],
        "core_identity_only_mismatch": flags[1],
        "audit_semantic_mismatch": flags[2],
        "audit_identity_or_provenance_mismatch": flags[3],
        "metric_semantic_mismatch": flags[4],
        "metric_identity_or_provenance_mismatch": flags[5],
        "case_derived_only_mismatch": flags[6],
        "disposition": disposition,
        "schema_version": 1,
    }
    payload = {
        key: value.value if hasattr(value, "value") else [x.to_dict() for x in value]
        if key == "differences" else value
        for key, value in kwargs.items()
    }
    return DeterminismDiagnosticResult(
        diagnostic_result_id=semantic_id(
            DeterminismDiagnosticResult._PREFIX, payload
        ),
        **kwargs,
    )


def _run_item(item: tuple[object, object, object, str]):
    pair, case, variant, diagnostic_pair_id = item
    config = {
        "core_config_snapshot": variant.core_config_snapshot.to_dict(),
        "metric_config_snapshot": variant.metric_config_snapshot.to_dict(),
    }
    normal_a = _execute_pair(pair, case, variant)
    normal_b = _execute_pair(pair, case, variant)
    with localcontext() as altered_context:
        altered_context.prec = 7
        altered_context.rounding = ROUND_FLOOR
        altered = _execute_pair(pair, case, variant)
    first = _payload(normal_a, config)
    return (
        _result(
            diagnostic_pair_id,
            DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT,
            first,
            _payload(normal_b, config),
        ),
        _result(
            diagnostic_pair_id,
            DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION,
            first,
            _payload(altered, config),
        ),
    )


def run_determinism_diagnostics(
    manifest: C008CBRCAManifest, root: Path | None = None
) -> tuple[DeterminismDiagnosticResult, ...]:
    base = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    validate_c008c_b_rca_manifest(manifest, base)
    b_manifest, _, _, _ = load_b_sources(base)
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    pairs = {item.execution_pair_id: item for item in b_manifest.execution_pairs}
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    scheduled = tuple(
        (
            pairs[item.execution_pair_id],
            cases[item.dataset_case_id],
            variants[item.variant_id],
            item.diagnostic_pair_id,
        )
        for item in manifest.diagnostic_pairs
    )
    results = []
    with ProcessPoolExecutor(max_workers=12) as executor:
        for index, pair_results in enumerate(executor.map(_run_item, scheduled), 1):
            results.extend(pair_results)
            if index % 10 == 0:
                print(f"C-008C-B RCA determinism progress {index}/40", flush=True)
    return tuple(results)


__all__ = ["run_determinism_diagnostics"]
