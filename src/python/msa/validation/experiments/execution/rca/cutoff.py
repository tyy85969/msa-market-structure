"""One-checkpoint fixed-cutoff component attribution."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from msa.research.msa_core import MSACorePipeline
from msa.validation.causal_audit import CausalAuditor
from msa.validation.metrics import StructuralMetricEvaluator, validate_metric_evaluation_report

from ...identity import semantic_id
from ..cutoff import _truncate_source
from ..manifest import load_c008c_b_authority
from .contracts import (
    C008CBRCAManifest,
    CutoffRewriteLayer,
    FixedCutoffComponentResult,
    FixedCutoffDiagnosticResult,
)
from .manifest import validate_c008c_b_rca_manifest
from .payload_diff import payload_differences
from .projections import project_metric_semantics


def _payloads(values: tuple) -> list[object]:
    return [item.to_dict() for item in values]


def _component(name: str, left: object, right: object) -> FixedCutoffComponentResult:
    total, differences = payload_differences(left, right)
    first = differences[0] if differences else None
    kwargs = {
        "component_name": name,
        "equal": total == 0,
        "total_difference_count": total,
        "differences": differences,
        "first_difference_path": None if first is None else first.path,
        "first_left_subtree_digest": (
            None if first is None else first.left_subtree_digest
        ),
        "first_right_subtree_digest": (
            None if first is None else first.right_subtree_digest
        ),
        "schema_version": 1,
    }
    payload = {**kwargs, "differences": [item.to_dict() for item in differences]}
    return FixedCutoffComponentResult(
        component_result_id=semantic_id(FixedCutoffComponentResult._PREFIX, payload),
        **kwargs,
    )


def _execute(item: tuple[object, object, str, int, str]):
    case, baseline, cutoff_text, index, selection_kind = item
    cutoff = datetime.fromisoformat(cutoff_text)
    pipeline = MSACorePipeline(baseline.core_config_snapshot)
    extended = pipeline.run(case.source_input)
    prefix_source = _truncate_source(case.source_input, cutoff)
    prefix = pipeline.run(prefix_source)
    prefix_times = prefix.processing_times
    expected_times = extended.processing_times[: len(prefix_times)]
    schedule_equal = prefix_times == expected_times and prefix_times[-1] == cutoff
    source_valid = (
        all(x.as_of_time <= cutoff for x in prefix_source.lifecycle_history.snapshots)
        and all(
            x.as_of_time <= cutoff
            for history in prefix_source.timeframe_state_histories
            for x in history.snapshots
        )
        and all(x.available_time <= cutoff for x in prefix_source.reference_price_data.bars)
        and all(x.is_complete for x in prefix_source.reference_price_data.bars)
        and schedule_equal
        and prefix_source.lifecycle_history.events
        == prefix_source.lifecycle_history.final_snapshot.events
        and all(
            history.events == history.final_snapshot.events
            for history in prefix_source.timeframe_state_histories
        )
    )
    extended_bundles = {
        x.as_of_time: x for x in extended.frame_bundles if x.as_of_time <= cutoff
    }
    frame_left = _payloads(prefix.frame_bundles)
    frame_right = [extended_bundles[x.as_of_time].to_dict() for x in prefix.frame_bundles]
    events_left = _payloads(prefix.active_box_history.events)
    events_right = _payloads(tuple(
        x for x in extended.active_box_history.events if x.event_confirm_time <= cutoff
    ))
    frozen_left = _payloads(prefix.active_box_history.frozen_boxes)
    frozen_right = _payloads(tuple(
        x for x in extended.active_box_history.frozen_boxes
        if x.active_box.confirm_time <= cutoff
    ))
    auditor = CausalAuditor()
    supplied = cutoff + timedelta(microseconds=1)
    shared_audit = auditor.compare_shared_asof(prefix, extended, supplied)
    prefix_audit = auditor.compare_prefix(prefix, extended)
    evaluator = StructuralMetricEvaluator(baseline.metric_config_snapshot)
    prefix_metric = evaluator.evaluate(prefix)
    extended_metric = evaluator.evaluate(extended, cutoff)
    validate_metric_evaluation_report(prefix, prefix_metric)
    validate_metric_evaluation_report(extended, extended_metric)
    components = (
        _component("processing_schedule", [x.isoformat() for x in prefix_times], [x.isoformat() for x in expected_times]),
        _component("frame_bundles", frame_left, frame_right),
        _component("active_box_events", events_left, events_right),
        _component("frozen_boxes", frozen_left, frozen_right),
        _component(
            "metric_semantic",
            project_metric_semantics(prefix_metric.to_dict()),
            project_metric_semantics(extended_metric.to_dict()),
        ),
        _component("metric_full_payload", prefix_metric.to_dict(), extended_metric.to_dict()),
    )
    frame_equal, events_equal, frozen_equal = (components[i].equal for i in (1, 2, 3))
    metric_semantic_equal = components[4].equal
    metric_full_equal = components[5].equal
    identity_only = metric_semantic_equal and not metric_full_equal
    if not source_valid:
        layer = CutoffRewriteLayer.PREFIX_SOURCE
    elif not schedule_equal:
        layer = CutoffRewriteLayer.PROCESSING_SCHEDULE
    elif not frame_equal:
        layer = CutoffRewriteLayer.FRAME_BUNDLE
    elif not events_equal or not frozen_equal:
        layer = CutoffRewriteLayer.ACTIVE_BOX_LEDGER
    elif not metric_semantic_equal:
        layer = CutoffRewriteLayer.METRIC_OUTCOME
    elif identity_only:
        layer = CutoffRewriteLayer.IDENTITY_OR_SOURCE_BINDING
    elif not shared_audit.passed or not prefix_audit.passed:
        layer = CutoffRewriteLayer.COMPARISON_AUDIT
    else:
        layer = CutoffRewriteLayer.NONE
    kwargs = {
        "dataset_case_id": case.dataset_case_id,
        "cutoff_as_of_time": cutoff_text,
        "checkpoint_index": index,
        "selection_kind": selection_kind,
        "source_prefix_valid": source_valid,
        "processing_schedule_equal": schedule_equal,
        "shared_asof_audit_passed": shared_audit.passed,
        "prefix_audit_passed": prefix_audit.passed,
        "frame_bundles_equal": frame_equal,
        "active_box_events_equal": events_equal,
        "frozen_boxes_equal": frozen_equal,
        "metric_semantic_equal": metric_semantic_equal,
        "metric_full_payload_equal": metric_full_equal,
        "identity_only_difference": identity_only,
        "comparator_boundary_operator": "<",
        "supplied_comparator_cutoff": supplied.isoformat(),
        "exact_cutoff_included": True,
        "components": components,
        "final_layer": layer,
        "schema_version": 1,
    }
    payload = {
        **kwargs,
        "components": [x.to_dict() for x in components],
        "final_layer": layer.value,
    }
    return FixedCutoffDiagnosticResult(
        cutoff_diagnostic_id=semantic_id(FixedCutoffDiagnosticResult._PREFIX, payload),
        **kwargs,
    )


def run_cutoff_diagnostics(manifest: C008CBRCAManifest, root: Path | None = None):
    base = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    validate_c008c_b_rca_manifest(manifest, base)
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    cases = {x.dataset_case_id: x for x in dataset.cases}
    baseline = plan.variants[0]
    schedule = tuple(
        (cases[case_id], baseline, time, index, kind)
        for case_id, time, index, kind in zip(
            manifest.cutoff_case_ids,
            manifest.cutoff_as_of_times,
            manifest.cutoff_checkpoint_indices,
            manifest.cutoff_selection_kinds,
            strict=True,
        )
    )
    results = []
    with ProcessPoolExecutor(max_workers=12) as executor:
        for index, result in enumerate(executor.map(_execute, schedule), 1):
            results.append(result)
            print(f"C-008C-B RCA cutoff progress {index}/15", flush=True)
    return tuple(results)


__all__ = ["run_cutoff_diagnostics"]
