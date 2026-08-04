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
    DiagnosticLayer,
    DeterminismDiagnosticKind,
    DeterminismDiagnosticResult,
    LayerDifferenceSummary,
    MismatchLayer,
    RootCauseDisposition,
)
from .manifest import load_b_sources, validate_c008c_b_rca_manifest
from .payload_diff import payload_differences
from .projections import (
    ExplicitProjection,
    split_audit_projection,
    split_case_result_projection,
    split_core_run_projection,
    split_metric_projection,
)


def _payload(artifact: object, config: object) -> dict[str, object]:
    return {
        "config": config,
        "core_run": None if artifact.run is None else artifact.run.to_dict(),
        "audit": None if artifact.audit is None else artifact.audit.to_dict(),
        "metric": (
            None
            if artifact.metric_report is None
            else artifact.metric_report.to_dict()
        ),
        "case_result": artifact.result.to_dict(),
    }


def _summary(
    layer: DiagnosticLayer,
    left: ExplicitProjection,
    right: ExplicitProjection,
) -> LayerDifferenceSummary:
    semantic_count, semantic_differences = payload_differences(
        left.semantic, right.semantic, max_stored=1
    )
    identity_count, identity_differences = payload_differences(
        left.identity, right.identity, max_stored=1
    )
    semantic = semantic_differences[0] if semantic_differences else None
    identity = identity_differences[0] if identity_differences else None
    kwargs = {
        "layer": layer,
        "semantic_difference_count": semantic_count,
        "identity_difference_count": identity_count,
        "first_semantic_difference_path": (
            None if semantic is None else semantic.path
        ),
        "first_identity_difference_path": (
            None if identity is None else identity.path
        ),
        "first_semantic_left_subtree_digest": (
            None if semantic is None else semantic.left_subtree_digest
        ),
        "first_semantic_right_subtree_digest": (
            None if semantic is None else semantic.right_subtree_digest
        ),
        "first_identity_left_subtree_digest": (
            None if identity is None else identity.left_subtree_digest
        ),
        "first_identity_right_subtree_digest": (
            None if identity is None else identity.right_subtree_digest
        ),
        "schema_version": 1,
    }
    payload = {
        **kwargs,
        "layer": layer.value,
    }
    return LayerDifferenceSummary(
        layer_difference_summary_id=semantic_id(
            LayerDifferenceSummary._PREFIX, payload
        ),
        **kwargs,
    )


def _layer_projections(payload: dict[str, object]) -> tuple[ExplicitProjection, ...]:
    return (
        ExplicitProjection(semantic=payload["config"], identity={}),
        split_core_run_projection(payload["core_run"]),
        split_audit_projection(payload["audit"]),
        split_metric_projection(payload["metric"]),
        split_case_result_projection(payload["case_result"]),
    )


def build_determinism_result(
    pair_id: str,
    kind: DeterminismDiagnosticKind,
    left: dict[str, object],
    right: dict[str, object],
) -> DeterminismDiagnosticResult:
    """Build a source-derived diagnostic with independent per-layer summaries."""

    left_layers = _layer_projections(left)
    right_layers = _layer_projections(right)
    summaries = tuple(
        _summary(layer, left_item, right_item)
        for layer, left_item, right_item in zip(
            DiagnosticLayer, left_layers, right_layers, strict=True
        )
    )
    by_layer = {item.layer: item for item in summaries}
    _, differences = payload_differences(left, right)
    total = sum(
        item.semantic_difference_count + item.identity_difference_count
        for item in summaries
    )
    equality = {
        layer: summary.semantic_difference_count == 0
        and summary.identity_difference_count == 0
        for layer, summary in by_layer.items()
    }
    core = by_layer[DiagnosticLayer.CORE]
    audit = by_layer[DiagnosticLayer.AUDIT]
    metric = by_layer[DiagnosticLayer.METRIC]
    case = by_layer[DiagnosticLayer.CASE_RESULT]
    layer = MismatchLayer.NONE
    if by_layer[DiagnosticLayer.CONFIG].semantic_difference_count:
        layer = MismatchLayer.CONFIG_SNAPSHOT
    elif core.semantic_difference_count:
        layer = MismatchLayer.CORE_RUN_SEMANTIC
    elif core.identity_difference_count:
        layer = MismatchLayer.CORE_RUN_IDENTITY
    elif audit.semantic_difference_count:
        layer = MismatchLayer.AUDIT_SEMANTIC
    elif audit.identity_difference_count:
        layer = MismatchLayer.AUDIT_IDENTITY_OR_PROVENANCE
    elif metric.semantic_difference_count:
        layer = MismatchLayer.METRIC_SEMANTIC
    elif metric.identity_difference_count:
        layer = MismatchLayer.METRIC_IDENTITY_OR_PROVENANCE
    elif case.semantic_difference_count or case.identity_difference_count:
        layer = MismatchLayer.CASE_RESULT_DERIVED
    protected_semantic = any(
        by_layer[item].semantic_difference_count
        for item in (
            DiagnosticLayer.CORE,
            DiagnosticLayer.AUDIT,
            DiagnosticLayer.METRIC,
        )
    )
    disposition = (
        RootCauseDisposition.NO_ROOT_CAUSE_FOUND
        if total == 0
        else RootCauseDisposition.PROTECTED_CORE_REMEDIATION_REQUIRED
        if protected_semantic
        else RootCauseDisposition.HARNESS_CORRECTION_REQUIRED
    )
    first_semantic = next(
        (
            item.first_semantic_difference_path
            for item in summaries
            if item.semantic_difference_count
        ),
        None,
    )
    kwargs = {
        "diagnostic_pair_id": pair_id,
        "diagnostic_kind": kind,
        "config_payload_equal": equality[DiagnosticLayer.CONFIG],
        "core_run_payload_equal": equality[DiagnosticLayer.CORE],
        "audit_payload_equal": equality[DiagnosticLayer.AUDIT],
        "metric_payload_equal": equality[DiagnosticLayer.METRIC],
        "case_result_payload_equal": equality[DiagnosticLayer.CASE_RESULT],
        "full_payload_equal": total == 0,
        "total_difference_count": total,
        "differences": differences,
        "layer_summaries": summaries,
        "mismatch_layer": layer,
        "first_semantic_difference_path": first_semantic,
        "core_semantic_mismatch": core.semantic_difference_count > 0,
        "core_identity_only_mismatch": (
            core.semantic_difference_count == 0
            and core.identity_difference_count > 0
        ),
        "audit_semantic_mismatch": audit.semantic_difference_count > 0,
        "audit_identity_or_provenance_mismatch": (
            audit.semantic_difference_count == 0
            and audit.identity_difference_count > 0
        ),
        "metric_semantic_mismatch": metric.semantic_difference_count > 0,
        "metric_identity_or_provenance_mismatch": (
            metric.semantic_difference_count == 0
            and metric.identity_difference_count > 0
        ),
        "case_derived_only_mismatch": (
            case.semantic_difference_count + case.identity_difference_count > 0
            and all(
                equality[item]
                for item in tuple(DiagnosticLayer)[:-1]
            )
        ),
        "disposition": disposition,
        "schema_version": 1,
    }
    payload = {
        key: value.value
        if hasattr(value, "value")
        else [item.to_dict() for item in value]
        if key in ("differences", "layer_summaries")
        else value
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
        build_determinism_result(
            diagnostic_pair_id,
            DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT,
            first,
            _payload(normal_b, config),
        ),
        build_determinism_result(
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
                print(
                    f"C-008C-B RCA determinism progress {index}/40",
                    flush=True,
                )
    return tuple(results)


__all__ = ["build_determinism_result", "run_determinism_diagnostics"]
