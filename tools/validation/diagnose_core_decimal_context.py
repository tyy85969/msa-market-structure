"""Bounded, read-only diagnosis of C-008C Core Decimal-context dependence."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.research.msa_core import MSACorePipeline
from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.experiments.baseline import core_experiment_baseline
from msa.validation.experiments.synthetic_suite import (
    build_synthetic_source_input,
)
from msa.validation.metrics import StructuralMetricEvaluator
from msa.validation.metrics.errors import StructuralMetricError


DIAGNOSIS_VERSION = "c008c-h2-core-decimal-context-diagnosis-v1"
VALIDATION_SEED = 2
MAXIMUM_CASES = 3
SELECTED_SCENARIOS = (
    SyntheticScenarioKind.SINGLE_TREND,
    SyntheticScenarioKind.V_REVERSAL,
    SyntheticScenarioKind.FALSE_BREAK,
)
_DEFAULT_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)
_ALTERED_CONTEXT = Context(prec=7, rounding=ROUND_FLOOR)
_CONTRIBUTION_FIELDS = (
    "freshness_factor",
    "touch_factor",
    "raw_contribution",
)
_ZONE_SCORE_FIELDS = (
    "dependency_adjusted_base_score",
    "source_diversity_bonus",
    "context_diversity_bonus",
    "quality_score",
    "distance_factor",
    "placement_factor",
    "selection_score",
)
_IDENTITY_OR_PROVENANCE_FIELDS = {
    "metric_report_id",
    "source_run_id",
    "provenance",
}


class DecimalDiagnosisError(ValueError):
    """Raised when a request exceeds the frozen diagnostic boundary."""


@dataclass(frozen=True, slots=True)
class _CaseArtifacts:
    run: object
    metric_report: object | None
    metric_error_type: str | None


def _context_payload(context: Context) -> dict[str, object]:
    return {"precision": context.prec, "rounding": context.rounding}


def _run_once(source_input: object, context: Context) -> _CaseArtifacts:
    baseline = core_experiment_baseline()
    with localcontext(context):
        run = MSACorePipeline(baseline.core_config_snapshot).run(source_input)
        try:
            metric_report = StructuralMetricEvaluator(
                baseline.metric_config_snapshot
            ).evaluate(run)
        except StructuralMetricError as exc:
            return _CaseArtifacts(
                run=run,
                metric_report=None,
                metric_error_type=type(exc).__name__,
            )
    return _CaseArtifacts(
        run=run,
        metric_report=metric_report,
        metric_error_type=None,
    )


def _zones_by_key(frame: object) -> Mapping[str, object]:
    return {zone.zone_key_id: zone for zone in frame.zones}


def _contributions_by_evidence(zone: object) -> Mapping[str, object]:
    return {item.evidence_id: item for item in zone.contributions}


def _first_numeric_divergence(default_run: object, altered_run: object):
    for frame_index, (default_frame, altered_frame) in enumerate(
        zip(default_run.score_history.frames, altered_run.score_history.frames)
    ):
        altered_zones = _zones_by_key(altered_frame)
        for zone_index, default_zone in enumerate(default_frame.zones):
            altered_zone = altered_zones[default_zone.zone_key_id]
            altered_contributions = _contributions_by_evidence(altered_zone)
            for contribution_index, default_contribution in enumerate(
                default_zone.contributions
            ):
                altered_contribution = altered_contributions[
                    default_contribution.evidence_id
                ]
                for field_name in _CONTRIBUTION_FIELDS:
                    default_value = getattr(default_contribution, field_name)
                    altered_value = getattr(altered_contribution, field_name)
                    if default_value != altered_value:
                        return (
                            frame_index,
                            zone_index,
                            contribution_index,
                            default_zone,
                            altered_zone,
                            default_contribution,
                            altered_contribution,
                            field_name,
                            default_value,
                            altered_value,
                        )
            for field_name in _ZONE_SCORE_FIELDS:
                default_value = getattr(default_zone, field_name)
                altered_value = getattr(altered_zone, field_name)
                if default_value != altered_value:
                    raise DecimalDiagnosisError(
                        "zone score diverged before any stored contribution"
                    )
    raise DecimalDiagnosisError("no non-identity Core numeric divergence found")


def _component_for(zone: object, component_id: str) -> object:
    return next(
        item
        for item in zone.dependency_components
        if item.component_id == component_id
    )


def _first_zone_score_difference(default_zone: object, altered_zone: object):
    for field_name in _ZONE_SCORE_FIELDS:
        default_value = getattr(default_zone, field_name)
        altered_value = getattr(altered_zone, field_name)
        if default_value != altered_value:
            return field_name, default_value, altered_value
    raise DecimalDiagnosisError("numeric divergence did not reach a zone score")


def _divergent_zone_scores(
    default_zone: object, altered_zone: object
) -> dict[str, dict[str, str]]:
    return {
        field_name: {
            "default": str(getattr(default_zone, field_name)),
            "altered": str(getattr(altered_zone, field_name)),
        }
        for field_name in _ZONE_SCORE_FIELDS
        if getattr(default_zone, field_name)
        != getattr(altered_zone, field_name)
    }


def _first_metric_semantic_difference(
    default_value: object,
    altered_value: object,
    path: str = "",
):
    if isinstance(default_value, dict) and isinstance(altered_value, dict):
        for key in default_value:
            if key in _IDENTITY_OR_PROVENANCE_FIELDS or key.endswith("_id"):
                continue
            found = _first_metric_semantic_difference(
                default_value[key], altered_value[key], f"{path}/{key}"
            )
            if found is not None:
                return found
        return None
    if isinstance(default_value, list) and isinstance(altered_value, list):
        for index, (left, right) in enumerate(
            zip(default_value, altered_value)
        ):
            found = _first_metric_semantic_difference(
                left, right, f"{path}/{index}"
            )
            if found is not None:
                return found
        if len(default_value) != len(altered_value):
            return path or "/", len(default_value), len(altered_value)
        return None
    if default_value != altered_value:
        return path or "/", default_value, altered_value
    return None


def reproduce_freshness_expression(
    age_seconds: Decimal,
    freshness_horizon_seconds: Decimal,
) -> dict[str, object]:
    """Evaluate the isolated divergent expression without mutating Context."""

    def evaluate(context: Context) -> tuple[Decimal, Decimal]:
        with localcontext(context):
            quotient = age_seconds / freshness_horizon_seconds
            return quotient, Decimal("1") - quotient

    default_quotient, default_output = evaluate(_DEFAULT_CONTEXT)
    repeated_quotient, repeated_output = evaluate(_DEFAULT_CONTEXT)
    altered_quotient, altered_output = evaluate(_ALTERED_CONTEXT)
    return {
        "operands": {
            "age_seconds": str(age_seconds),
            "freshness_horizon_seconds": str(
                freshness_horizon_seconds
            ),
        },
        "default_division_output": str(default_quotient),
        "altered_division_output": str(altered_quotient),
        "default_output": str(default_output),
        "altered_output": str(altered_output),
        "default_repeat_output": str(repeated_output),
        "default_repeat_equal": (
            default_quotient == repeated_quotient
            and default_output == repeated_output
        ),
        "default_altered_different": default_output != altered_output,
    }


def diagnose_source_input(
    scenario: SyntheticScenarioKind,
    seed: int,
    source_input: object,
) -> dict[str, object]:
    if seed != VALIDATION_SEED:
        raise DecimalDiagnosisError(
            "diagnosis accepts only non-OOS VALIDATION seed 2"
        )
    if scenario not in SELECTED_SCENARIOS:
        raise DecimalDiagnosisError("scenario is outside the bounded selection")
    before = source_input.to_dict()
    default = _run_once(source_input, _DEFAULT_CONTEXT)
    altered = _run_once(source_input, _ALTERED_CONTEXT)
    if source_input.to_dict() != before:
        raise DecimalDiagnosisError("Core execution modified source input")
    (
        frame_index,
        zone_index,
        contribution_index,
        default_zone,
        altered_zone,
        default_contribution,
        altered_contribution,
        field_name,
        default_value,
        altered_value,
    ) = _first_numeric_divergence(default.run, altered.run)
    default_component = _component_for(
        default_zone, default_contribution.dependency_component_id
    )
    altered_component = _component_for(
        altered_zone, altered_contribution.dependency_component_id
    )
    zone_field, default_zone_value, altered_zone_value = (
        _first_zone_score_difference(default_zone, altered_zone)
    )
    reproduction = reproduce_freshness_expression(
        default_contribution.age_seconds,
        default.run.config_snapshot.scoring_config.freshness_horizon_seconds,
    )
    if default.metric_report is None:
        raise DecimalDiagnosisError(
            "default-context Core Run did not produce a Metric Report"
        )
    if altered.metric_report is None:
        metric_propagation = {
            "default_status": "PRODUCED",
            "default_metric_report_id": (
                default.metric_report.metric_report_id
            ),
            "default_source_run_id": default.metric_report.source_run_id,
            "altered_status": "REJECTED_BEFORE_REPORT",
            "altered_metric_report_id": None,
            "altered_source_run_id": altered.run.run_id,
            "altered_error_type": altered.metric_error_type,
            "rejection_boundary": (
                "StructuralMetricEvaluator independent CausalAuditor"
            ),
        }
    else:
        metric_difference = _first_metric_semantic_difference(
            default.metric_report.to_dict(), altered.metric_report.to_dict()
        )
        if metric_difference is None:
            raise DecimalDiagnosisError(
                "Core numeric divergence did not reach Metric Report semantics"
            )
        metric_path, default_metric_value, altered_metric_value = (
            metric_difference
        )
        metric_propagation = {
            "default_status": "PRODUCED",
            "default_metric_report_id": (
                default.metric_report.metric_report_id
            ),
            "default_source_run_id": default.metric_report.source_run_id,
            "altered_status": "PRODUCED",
            "altered_metric_report_id": (
                altered.metric_report.metric_report_id
            ),
            "altered_source_run_id": altered.metric_report.source_run_id,
            "first_non_identity_difference_path": metric_path,
            "default": str(default_metric_value),
            "altered": str(altered_metric_value),
        }
    return {
        "scenario": scenario.value,
        "seed": seed,
        "input_unchanged": True,
        "first_non_identity_numeric_difference": {
            "frame_index": frame_index,
            "zone_index": zone_index,
            "contribution_index": contribution_index,
            "function": "ResonanceScorer._draft",
            "field": field_name,
            "expression": (
                'max(freshness_floor, Decimal("1") - '
                "age / freshness_horizon_seconds)"
            ),
            **reproduction,
            "stored_default_output": str(default_value),
            "stored_altered_output": str(altered_value),
            "classification": {
                "root_operation": "division",
                "decimal_construction": False,
                "division": True,
                "multiplication": "propagation_only",
                "normalization": False,
                "quantize": False,
                "comparison_threshold": False,
                "semantic_id_preceded_by_numeric_expression": True,
            },
        },
        "propagation": {
            "dependency_contribution": {
                "field": "raw_contribution",
                "default": str(default_contribution.raw_contribution),
                "altered": str(altered_contribution.raw_contribution),
                "contribution_id_default": default_contribution.contribution_id,
                "contribution_id_altered": altered_contribution.contribution_id,
            },
            "dependency_component": {
                "field": "adjusted_component_score",
                "default": str(default_component.adjusted_component_score),
                "altered": str(altered_component.adjusted_component_score),
            },
            "zone_score": {
                "field": zone_field,
                "default": str(default_zone_value),
                "altered": str(altered_zone_value),
                "divergent_fields": _divergent_zone_scores(
                    default_zone, altered_zone
                ),
                "zone_snapshot_id_default": default_zone.zone_snapshot_id,
                "zone_snapshot_id_altered": altered_zone.zone_snapshot_id,
            },
            "score_frame_id": {
                "default": default.run.score_history.frames[
                    frame_index
                ].score_frame_id,
                "altered": altered.run.score_history.frames[
                    frame_index
                ].score_frame_id,
            },
            "run_id": {
                "default": default.run.run_id,
                "altered": altered.run.run_id,
            },
            "metric_report": metric_propagation,
        },
    }


def diagnose_cases(
    requests: Iterable[tuple[SyntheticScenarioKind, int]],
) -> dict[str, object]:
    selected = tuple(requests)
    if not selected or len(selected) > MAXIMUM_CASES:
        raise DecimalDiagnosisError("diagnosis requires one to three cases")
    if len({scenario for scenario, _ in selected}) != len(selected):
        raise DecimalDiagnosisError("diagnostic scenarios must be unique")
    if any(seed != VALIDATION_SEED for _, seed in selected):
        raise DecimalDiagnosisError(
            "diagnosis accepts only non-OOS VALIDATION seed 2"
        )
    if any(scenario not in SELECTED_SCENARIOS for scenario, _ in selected):
        raise DecimalDiagnosisError("scenario is outside the bounded selection")
    cases = tuple(
        diagnose_source_input(
            scenario,
            seed,
            build_synthetic_source_input(scenario, seed),
        )
        for scenario, seed in selected
    )
    return {
        "diagnosis_version": DIAGNOSIS_VERSION,
        "execution_policy": {
            "baseline": "formal Core experiment baseline",
            "partition": "VALIDATION",
            "seed": VALIDATION_SEED,
            "case_count": len(cases),
            "maximum_case_count": MAXIMUM_CASES,
            "runs_per_case": {
                "default_context": 1,
                "altered_context": 1,
            },
            "default_context": _context_payload(_DEFAULT_CONTEXT),
            "altered_context": _context_payload(_ALTERED_CONTEXT),
            "oos_executed": False,
            "b_executed": False,
            "variants_executed": False,
            "replay_executed": False,
            "fixed_cutoff_executed": False,
            "formal_evidence_written": False,
        },
        "cases": list(cases),
        "static_investigation": {
            "core_execution_path_has_local_decimal_context": False,
            "metric_layer_has_local_decimal_context": True,
            "surveyed_path_has_direct_getcontext_dependency": False,
            "decimal_constant_constructed_from_float_literal": False,
            "unfixed_intermediate_division": True,
            "unquantized_decimal_before_semantic_id": True,
            "first_division_site": (
                "src/python/msa/research/resonance/scoring.py:277"
            ),
            "semantic_id_sites": [
                "src/python/msa/research/resonance/scoring.py:315",
                "src/python/msa/research/resonance/scoring.py:418",
                "src/python/msa/research/resonance/scoring.py:172",
            ],
            "notes": [
                "Core scoring performs freshness and distance division in the ambient Decimal Context.",
                "Core contribution and zone identities serialize unquantized Decimal results with str().",
                "Metric evaluation has local Decimal contexts, but it consumes the already context-dependent Core Run.",
            ],
        },
    }


def build_diagnosis() -> dict[str, object]:
    return diagnose_cases(
        (scenario, VALIDATION_SEED) for scenario in SELECTED_SCENARIOS
    )


def render_diagnosis(diagnosis: Mapping[str, object]) -> str:
    return json.dumps(
        diagnosis,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def main() -> int:
    print(render_diagnosis(build_diagnosis()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
