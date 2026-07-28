"""Predeclared C-008C sensitivity, ablation, and increment plan."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from msa.reference import core_alpha_v1_config
from msa.research.msa_core import MSACoreConfig
from msa.validation.metrics.contracts import StructuralMetricConfig

from .baseline import core_experiment_baseline
from .contracts import (
    AblationSupportStatus,
    ExperimentAblation,
    ExperimentIncrementStep,
    ExperimentKind,
    ExperimentParameterAxis,
    ExperimentParameterValue,
    ExperimentPlan,
    ExperimentVariant,
    ParameterAxisKind,
    RealMarketOOSStatus,
    VariantLevel,
)
from .dataset import build_c008c_synthetic_dataset
from .gates import default_c008c_gate_registry
from .identity import semantic_id


_AXIS_ASSUMPTIONS = (
    "Values define an engineering robustness neighborhood",
    "Values are not an optimization range or search space",
    "Values are not recommended or profitable parameters",
)
_VARIANT_ASSUMPTIONS = (
    "Variant identity is frozen before outcomes",
    "No outcome selects or modifies this variant",
)


def _parameter(
    level: VariantLevel, value: Decimal | int
) -> ExperimentParameterValue:
    return ExperimentParameterValue(level=level, value=value)


def _axis(
    code: str,
    kind: ParameterAxisKind,
    field_path: str,
    low: Decimal | int,
    baseline: Decimal | int,
    high: Decimal | int,
) -> ExperimentParameterAxis:
    values = (
        _parameter(VariantLevel.LOW, low),
        _parameter(VariantLevel.BASELINE, baseline),
        _parameter(VariantLevel.HIGH, high),
    )
    payload = {
        "code": code,
        "kind": kind.value,
        "field_path": field_path,
        "values": [item.to_dict() for item in values],
        "purpose": "One-axis-at-a-time engineering sensitivity",
        "assumptions": list(_AXIS_ASSUMPTIONS),
        "schema_version": 1,
    }
    return ExperimentParameterAxis(
        axis_id=semantic_id("c008c-parameter-axis-v1-", payload),
        code=code,
        kind=kind,
        field_path=field_path,
        values=values,
        purpose="One-axis-at-a-time engineering sensitivity",
        assumptions=_AXIS_ASSUMPTIONS,
    )


def _axes() -> tuple[ExperimentParameterAxis, ...]:
    return (
        _axis(
            "DEPENDENCY_REPEAT_CREDIT",
            ParameterAxisKind.MODEL,
            "scoring_config.dependency_repeat_credit",
            Decimal("0"),
            Decimal("0.25"),
            Decimal("0.5"),
        ),
        _axis(
            "SOURCE_DIVERSITY_BONUS_PER_EXTRA",
            ParameterAxisKind.MODEL,
            "scoring_config.source_diversity_bonus_per_extra",
            Decimal("0"),
            Decimal("0.2"),
            Decimal("0.4"),
        ),
        _axis(
            "CONTEXT_DIVERSITY_BONUS_PER_EXTRA",
            ParameterAxisKind.MODEL,
            "scoring_config.context_diversity_bonus_per_extra",
            Decimal("0"),
            Decimal("0.3"),
            Decimal("0.6"),
        ),
        _axis(
            "MINIMUM_REPLACEMENT_SCORE_IMPROVEMENT",
            ParameterAxisKind.MODEL,
            (
                "active_box_config."
                "minimum_replacement_selection_score_improvement"
            ),
            Decimal("0"),
            Decimal("0.1"),
            Decimal("0.2"),
        ),
        _axis(
            "ATR_PERIOD",
            ParameterAxisKind.METRIC,
            "metric_config.atr_period",
            10,
            14,
            20,
        ),
        _axis(
            "TURN_RESOLUTION_BARS",
            ParameterAxisKind.METRIC,
            "metric_config.turn_resolution_bars",
            4,
            8,
            12,
        ),
        _axis(
            "BREAK_OBSERVATION_BARS",
            ParameterAxisKind.METRIC,
            "metric_config.break_observation_bars",
            4,
            8,
            12,
        ),
        _axis(
            "REACTION_OBSERVATION_BARS",
            ParameterAxisKind.METRIC,
            "metric_config.reaction_observation_bars",
            4,
            8,
            12,
        ),
    )


def _core_variant(
    baseline: MSACoreConfig,
    field_path: str,
    value: Decimal | int,
) -> MSACoreConfig:
    if field_path.startswith("scoring_config."):
        field = field_path.split(".", 1)[1]
        return replace(
            baseline,
            scoring_config=replace(
                baseline.scoring_config, **{field: value}
            ),
        )
    if field_path.startswith("active_box_config."):
        field = field_path.split(".", 1)[1]
        return replace(
            baseline,
            active_box_config=replace(
                baseline.active_box_config, **{field: value}
            ),
        )
    raise ValueError(f"unsupported model axis: {field_path}")


def _metric_variant(
    baseline: StructuralMetricConfig,
    field_path: str,
    value: Decimal | int,
) -> StructuralMetricConfig:
    field = field_path.split(".", 1)[1]
    return replace(baseline, **{field: value})


def _variant(
    *,
    code: str,
    kind: ExperimentKind,
    level: VariantLevel,
    axis_id: str | None,
    changed_paths: tuple[str, ...],
    core: MSACoreConfig,
    metric: StructuralMetricConfig,
) -> ExperimentVariant:
    payload = {
        "code": code,
        "experiment_kind": kind.value,
        "level": level.value,
        "axis_id": axis_id,
        "changed_field_paths": list(changed_paths),
        "core_config_snapshot": core.to_dict(),
        "metric_config_snapshot": metric.to_dict(),
        "assumptions": list(_VARIANT_ASSUMPTIONS),
        "schema_version": 1,
    }
    return ExperimentVariant(
        variant_id=semantic_id("c008c-experiment-variant-v1-", payload),
        code=code,
        experiment_kind=kind,
        level=level,
        axis_id=axis_id,
        changed_field_paths=changed_paths,
        core_config_snapshot=core,
        metric_config_snapshot=metric,
        assumptions=_VARIANT_ASSUMPTIONS,
    )


def _sensitivity_variants(
    axes: tuple[ExperimentParameterAxis, ...],
    core: MSACoreConfig,
    metric: StructuralMetricConfig,
) -> tuple[ExperimentVariant, ...]:
    baseline_variant = _variant(
        code="BASELINE",
        kind=ExperimentKind.BASELINE,
        level=VariantLevel.BASELINE,
        axis_id=None,
        changed_paths=(),
        core=core,
        metric=metric,
    )
    result = [baseline_variant]
    for axis in axes:
        for item in (axis.values[0], axis.values[2]):
            if axis.kind is ParameterAxisKind.MODEL:
                variant_core = _core_variant(core, axis.field_path, item.value)
                variant_metric = metric
                kind = ExperimentKind.MODEL_SENSITIVITY
            else:
                variant_core = core
                variant_metric = _metric_variant(
                    metric, axis.field_path, item.value
                )
                kind = ExperimentKind.METRIC_SENSITIVITY
            result.append(
                _variant(
                    code=f"{axis.code}_{item.level.value}",
                    kind=kind,
                    level=item.level,
                    axis_id=axis.axis_id,
                    changed_paths=(axis.field_path,),
                    core=variant_core,
                    metric=variant_metric,
                )
            )
    return tuple(result)


def _ablation(
    *,
    code: str,
    target: str,
    hypothesis: str,
    paths: tuple[str, ...],
    baseline_values: tuple[Decimal | int, ...],
    neutralized_values: tuple[Decimal | int, ...],
    status: AblationSupportStatus,
    reason: str,
    snapshot: MSACoreConfig | None,
) -> ExperimentAblation:
    baseline_parameters = tuple(
        _parameter(VariantLevel.BASELINE, item)
        for item in baseline_values
    )
    neutralized_parameters = tuple(
        _parameter(VariantLevel.NEUTRALIZED, item)
        for item in neutralized_values
    )
    payload = {
        "code": code,
        "target": target,
        "hypothesis": hypothesis,
        "field_paths": list(paths),
        "baseline_values": [
            item.to_dict() for item in baseline_parameters
        ],
        "neutralized_values": [
            item.to_dict() for item in neutralized_parameters
        ],
        "support_status": status.value,
        "reason": reason,
        "core_config_snapshot": (
            None if snapshot is None else snapshot.to_dict()
        ),
        "schema_version": 1,
    }
    return ExperimentAblation(
        ablation_id=semantic_id(
            "c008c-experiment-ablation-v1-", payload
        ),
        code=code,
        target=target,
        hypothesis=hypothesis,
        field_paths=paths,
        baseline_values=baseline_parameters,
        neutralized_values=neutralized_parameters,
        support_status=status,
        reason=reason,
        core_config_snapshot=snapshot,
    )


def _supported_ablations(
    core: MSACoreConfig,
) -> tuple[ExperimentAblation, ...]:
    dependency = replace(
        core,
        scoring_config=replace(
            core.scoring_config, dependency_repeat_credit=Decimal("0")
        ),
    )
    source = replace(
        core,
        scoring_config=replace(
            core.scoring_config,
            source_diversity_bonus_per_extra=Decimal("0"),
            source_diversity_bonus_cap=Decimal("0"),
        ),
    )
    context = replace(
        core,
        scoring_config=replace(
            core.scoring_config,
            context_diversity_bonus_per_extra=Decimal("0"),
            context_diversity_bonus_cap=Decimal("0"),
        ),
    )
    hysteresis = replace(
        core,
        active_box_config=replace(
            core.active_box_config,
            minimum_replacement_selection_score_improvement=Decimal("0"),
            absolute_replacement_distance_margin=Decimal("0"),
        ),
    )
    supported = AblationSupportStatus.SUPPORTED_BY_PUBLIC_CONFIG
    return (
        _ablation(
            code="DEPENDENCY_REPEAT_NEUTRALIZED",
            target="Dependency repeat contribution",
            hypothesis="Repeat credit affects structural score concentration",
            paths=("scoring_config.dependency_repeat_credit",),
            baseline_values=(Decimal("0.25"),),
            neutralized_values=(Decimal("0"),),
            status=supported,
            reason="Exactly expressible by public ResonanceScoringConfig",
            snapshot=dependency,
        ),
        _ablation(
            code="SOURCE_DIVERSITY_NEUTRALIZED",
            target="Source diversity contribution",
            hypothesis="Source diversity affects structural score stability",
            paths=(
                "scoring_config.source_diversity_bonus_per_extra",
                "scoring_config.source_diversity_bonus_cap",
            ),
            baseline_values=(Decimal("0.2"), Decimal("1")),
            neutralized_values=(Decimal("0"), Decimal("0")),
            status=supported,
            reason="Exactly expressible by public ResonanceScoringConfig",
            snapshot=source,
        ),
        _ablation(
            code="CONTEXT_DIVERSITY_NEUTRALIZED",
            target="Context diversity contribution",
            hypothesis="Context diversity affects structural score stability",
            paths=(
                "scoring_config.context_diversity_bonus_per_extra",
                "scoring_config.context_diversity_bonus_cap",
            ),
            baseline_values=(Decimal("0.3"), Decimal("1")),
            neutralized_values=(Decimal("0"), Decimal("0")),
            status=supported,
            reason="Exactly expressible by public ResonanceScoringConfig",
            snapshot=context,
        ),
        _ablation(
            code="ACTIVE_BOX_HYSTERESIS_NEUTRALIZED",
            target="Active Box hysteresis contribution",
            hypothesis="Hysteresis affects Active Box churn stability",
            paths=(
                (
                    "active_box_config."
                    "minimum_replacement_selection_score_improvement"
                ),
                "active_box_config.absolute_replacement_distance_margin",
            ),
            baseline_values=(Decimal("0.1"), Decimal("1")),
            neutralized_values=(Decimal("0"), Decimal("0")),
            status=supported,
            reason="Exactly expressible by public ActiveBoxSelectionConfig",
            snapshot=hysteresis,
        ),
    )


def _unsupported_ablations() -> tuple[ExperimentAblation, ...]:
    unsupported = AblationSupportStatus.UNSUPPORTED_BY_PUBLIC_CONFIG
    values = (
        (
            "RESONANCE_CLUSTERING_ALGORITHM_REMOVAL",
            "Resonance clustering algorithm",
            "internal.resonance_clustering_algorithm",
        ),
        (
            "LIFECYCLE_REMOVAL",
            "Lifecycle engine",
            "internal.lifecycle_engine",
        ),
        (
            "DIRECTION_ENGINE_REMOVAL",
            "Direction engine",
            "internal.direction_engine",
        ),
        (
            "ACTIVE_BOX_SELECTOR_REMOVAL",
            "Active Box selector",
            "internal.active_box_selector",
        ),
    )
    return tuple(
        _ablation(
            code=code,
            target=target,
            hypothesis=f"Removal of {target} requires a separate contract",
            paths=(path,),
            baseline_values=(1,),
            neutralized_values=(0,),
            status=unsupported,
            reason="Removal cannot be expressed through the public Config",
            snapshot=None,
        )
        for code, target, path in values
    )


def _increment(
    index: int,
    code: str,
    restored: str,
    paths: tuple[str, ...],
    snapshot: MSACoreConfig,
) -> ExperimentIncrementStep:
    payload = {
        "step_index": index,
        "code": code,
        "restored_contribution": restored,
        "changed_field_paths": list(paths),
        "core_config_snapshot": snapshot.to_dict(),
        "schema_version": 1,
    }
    return ExperimentIncrementStep(
        increment_step_id=semantic_id(
            "c008c-increment-step-v1-", payload
        ),
        step_index=index,
        code=code,
        restored_contribution=restored,
        changed_field_paths=paths,
        core_config_snapshot=snapshot,
    )


def _increment_steps(
    core: MSACoreConfig,
) -> tuple[ExperimentIncrementStep, ...]:
    all_paths = (
        "scoring_config.dependency_repeat_credit",
        "scoring_config.source_diversity_bonus_per_extra",
        "scoring_config.source_diversity_bonus_cap",
        "scoring_config.context_diversity_bonus_per_extra",
        "scoring_config.context_diversity_bonus_cap",
        (
            "active_box_config."
            "minimum_replacement_selection_score_improvement"
        ),
        "active_box_config.absolute_replacement_distance_margin",
    )
    step0 = replace(
        core,
        scoring_config=replace(
            core.scoring_config,
            dependency_repeat_credit=Decimal("0"),
            source_diversity_bonus_per_extra=Decimal("0"),
            source_diversity_bonus_cap=Decimal("0"),
            context_diversity_bonus_per_extra=Decimal("0"),
            context_diversity_bonus_cap=Decimal("0"),
        ),
        active_box_config=replace(
            core.active_box_config,
            minimum_replacement_selection_score_improvement=Decimal("0"),
            absolute_replacement_distance_margin=Decimal("0"),
        ),
    )
    step1 = replace(
        step0,
        scoring_config=replace(
            step0.scoring_config, dependency_repeat_credit=Decimal("0.25")
        ),
    )
    step2 = replace(
        step1,
        scoring_config=replace(
            step1.scoring_config,
            source_diversity_bonus_per_extra=Decimal("0.2"),
            source_diversity_bonus_cap=Decimal("1"),
        ),
    )
    step3 = replace(
        step2,
        scoring_config=replace(
            step2.scoring_config,
            context_diversity_bonus_per_extra=Decimal("0.3"),
            context_diversity_bonus_cap=Decimal("1"),
        ),
    )
    step4 = replace(
        step3,
        active_box_config=replace(
            step3.active_box_config,
            minimum_replacement_selection_score_improvement=Decimal("0.1"),
            absolute_replacement_distance_margin=Decimal("1"),
        ),
    )
    return (
        _increment(0, "INCREMENT_STEP_0", "NONE_ALL_NEUTRALIZED", all_paths, step0),
        _increment(
            1,
            "INCREMENT_STEP_1",
            "DEPENDENCY_REPEAT",
            (all_paths[0],),
            step1,
        ),
        _increment(
            2,
            "INCREMENT_STEP_2",
            "SOURCE_DIVERSITY",
            (all_paths[1], all_paths[2]),
            step2,
        ),
        _increment(
            3,
            "INCREMENT_STEP_3",
            "CONTEXT_DIVERSITY",
            (all_paths[3], all_paths[4]),
            step3,
        ),
        _increment(
            4,
            "INCREMENT_STEP_4",
            "ACTIVE_BOX_HYSTERESIS",
            (all_paths[5], all_paths[6]),
            step4,
        ),
    )


def default_c008c_experiment_plan() -> ExperimentPlan:
    baseline = core_experiment_baseline()
    dataset = build_c008c_synthetic_dataset()
    axes = _axes()
    sensitivity = _sensitivity_variants(
        axes,
        baseline.core_config_snapshot,
        baseline.metric_config_snapshot,
    )
    supported = _supported_ablations(baseline.core_config_snapshot)
    ablations = (*supported, *_unsupported_ablations())
    increments = _increment_steps(baseline.core_config_snapshot)
    ablation_variants = tuple(
        _variant(
            code=item.code,
            kind=ExperimentKind.ABLATION,
            level=VariantLevel.NEUTRALIZED,
            axis_id=None,
            changed_paths=item.field_paths,
            core=item.core_config_snapshot,  # type: ignore[arg-type]
            metric=baseline.metric_config_snapshot,
        )
        for item in supported
    )
    increment_variants = tuple(
        _variant(
            code=item.code,
            kind=ExperimentKind.INCREMENT,
            level=VariantLevel.INCREMENT,
            axis_id=None,
            changed_paths=item.changed_field_paths,
            core=item.core_config_snapshot,
            metric=baseline.metric_config_snapshot,
        )
        for item in increments
    )
    variants = (*sensitivity, *ablation_variants, *increment_variants)
    gates = default_c008c_gate_registry()
    partition_rules = (
        "DEVELOPMENT uses seeds 0 and 1",
        "VALIDATION uses seed 2",
        "OOS uses seed 3 and remains locked before outcomes",
    )
    scenario_seed_rules = (
        "Every scenario uses seeds 0 1 2 3 exactly once",
        "Case order is scenario enum order then ascending seed",
    )
    execution_order = (
        "BASELINE",
        "DETERMINISM",
        "REPLAY_PARITY",
        "MODEL_SENSITIVITY",
        "METRIC_SENSITIVITY",
        "ABLATION",
        "INCREMENT",
        "OOS_BASELINE",
        "OOS_VARIANT",
    )
    assumptions = (
        "Plan identity is frozen before any experiment outcome",
        "No metric report aggregate or OOS outcome builds this plan",
        "No winner leaderboard or best parameter exists",
        "Synthetic OOS is not real-market OOS",
        "Active Box is not a trading signal",
    )
    payload = {
        "baseline_id": baseline.baseline_id,
        "dataset_manifest_id": dataset.dataset_manifest_id,
        "axes": [item.to_dict() for item in axes],
        "variants": [item.to_dict() for item in variants],
        "ablations": [item.to_dict() for item in ablations],
        "increment_steps": [item.to_dict() for item in increments],
        "gate_definitions": [item.to_dict() for item in gates],
        "partition_rules": list(partition_rules),
        "scenario_seed_rules": list(scenario_seed_rules),
        "metric_definition_ids": list(baseline.metric_definition_ids),
        "metric_formula_ids": list(baseline.metric_formula_ids),
        "execution_order": list(execution_order),
        "real_market_oos_status": (
            RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET.value
        ),
        "assumptions": list(assumptions),
        "schema_version": 1,
    }
    return ExperimentPlan(
        experiment_plan_id=semantic_id(
            "c008c-experiment-plan-v1-", payload
        ),
        baseline_id=baseline.baseline_id,
        dataset_manifest_id=dataset.dataset_manifest_id,
        axes=axes,
        variants=variants,
        ablations=ablations,
        increment_steps=increments,
        gate_definitions=gates,
        partition_rules=partition_rules,
        scenario_seed_rules=scenario_seed_rules,
        metric_definition_ids=baseline.metric_definition_ids,
        metric_formula_ids=baseline.metric_formula_ids,
        execution_order=execution_order,
        real_market_oos_status=(
            RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET
        ),
        assumptions=assumptions,
    )
