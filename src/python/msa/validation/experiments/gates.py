"""Machine-readable frozen hard-gate registry for later C-008C execution."""

from __future__ import annotations

from decimal import Decimal

from .contracts import (
    EXECUTION_BASE_COMMIT,
    ExperimentGateDefinition,
    GateSeverity,
)
from .identity import semantic_id
from .policy_contracts import (
    ExperimentDegenerationRule,
    ExperimentGateParameter,
    ExperimentGatePolicy,
    ExperimentSampleCoverageRule,
    GateParameterKind,
)


_FUTURE_EVIDENCE_KINDS = (
    "authority_snapshot",
    "dataset_manifest",
    "experiment_plan",
    "protected_source_manifest",
    "experiment_case_result",
    "core_run",
    "causal_audit_report",
    "metric_evaluation_report",
    "replay_comparison",
    "fixed_cutoff_comparison",
    "deterministic_comparison",
    "metric_coverage_summary",
    "degeneration_summary",
    "experiment_report",
    "freeze_candidate",
)


def _integer(name: str, value: int) -> ExperimentGateParameter:
    return ExperimentGateParameter(name, GateParameterKind.INTEGER, value)


def _decimal(name: str, value: str) -> ExperimentGateParameter:
    return ExperimentGateParameter(
        name, GateParameterKind.DECIMAL, Decimal(value)
    )


def _boolean(name: str, value: bool) -> ExperimentGateParameter:
    return ExperimentGateParameter(name, GateParameterKind.BOOLEAN, value)


def _text(name: str, value: str) -> ExperimentGateParameter:
    return ExperimentGateParameter(name, GateParameterKind.TEXT, value)


def _texts(name: str, *values: str) -> ExperimentGateParameter:
    return ExperimentGateParameter(
        name, GateParameterKind.TEXT_SEQUENCE, tuple(values)
    )


def _coverage_rules() -> tuple[ExperimentSampleCoverageRule, ...]:
    interpretation = (
        "Synthetic engineering coverage only not significance or profitability"
    )
    excluded = ("CENSORED", "UNAVAILABLE")
    values = (
        ("CONFIRMATION_DELAY_BARS", "MATURED", 10),
        ("CONFIRMATION_DELAY_ATR", "MATURED", 10),
        ("FALSE_TURN_RATE", "RESOLVED_OR_MATURED", 5),
        ("CONTINUED_BREAK_RATE", "MATURED", 5),
        ("TREND_CAPTURE_RATIO", "MATURED", 5),
        ("MFE", "MATURED", 20),
        ("MAE", "MATURED", 20),
        ("FIRST_TOUCH_REACTION", "MATURED", 20),
        ("BOX_CHURN", "BOX_EPISODES", 5),
        ("RESONANCE_LIFT", "MATCHED_PAIRS", 3),
    )
    return tuple(
        ExperimentSampleCoverageRule(
            metric_code=metric,
            denominator_kind=denominator,
            minimum_count=minimum,
            excluded_statuses=excluded,
            duplication_allowed=False,
            scope="SYNTHETIC_OOS",
            interpretation=interpretation,
        )
        for metric, denominator, minimum in values
    )


def _degeneration_rules() -> tuple[ExperimentDegenerationRule, ...]:
    return (
        ExperimentDegenerationRule(
            "PIPELINE_EXECUTION_FAILURE",
            "Variant cannot execute through the formal pipeline",
            (_boolean("formal_pipeline_must_complete", True),),
        ),
        ExperimentDegenerationRule(
            "CAUSAL_AUDIT_FAILURE",
            "Variant Run cannot pass the formal CausalAuditor",
            (_boolean("causal_audit_must_pass", True),),
        ),
        ExperimentDegenerationRule(
            "METRIC_SOURCE_BIND_FAILURE",
            "Metric Report cannot pass source-bound Run validation",
            (_boolean("metric_report_must_source_bind", True),),
        ),
        ExperimentDegenerationRule(
            "BATCH_REPLAY_MISMATCH",
            "Batch and Replay complete payloads differ",
            (_texts("compared_payloads", "core_run", "metric_evaluation_report"),),
        ),
        ExperimentDegenerationRule(
            "FUTURE_PREFIX_REWRITE",
            "A future append rewrites a frozen prefix or fixed cutoff",
            (_boolean("future_append_must_preserve_prefix", True),),
        ),
        ExperimentDegenerationRule(
            "STRUCTURE_EVENT_COLLAPSE",
            "Baseline has at least ten events and Variant has zero in Validation",
            (
                _integer("baseline_minimum_structure_events", 10),
                _integer("variant_structure_events", 0),
                _text("partition", "VALIDATION"),
            ),
        ),
        ExperimentDegenerationRule(
            "BOX_EPISODE_COLLAPSE",
            "Baseline has at least five Box episodes and Variant has zero",
            (
                _integer("baseline_minimum_box_episodes", 5),
                _integer("variant_box_episodes", 0),
                _text("partition", "VALIDATION"),
            ),
        ),
        ExperimentDegenerationRule(
            "MULTI_METRIC_COVERAGE_COLLAPSE",
            "At least five metric coverages each decline by more than ninety percent",
            (
                _integer("minimum_metric_count", 5),
                _decimal("decline_fraction_exclusive", "0.90"),
            ),
        ),
        ExperimentDegenerationRule(
            "AGGREGATE_SET_INCOMPLETE",
            "The formal ten-aggregate set is incomplete",
            (_integer("required_aggregate_count", 10),),
        ),
        ExperimentDegenerationRule(
            "INVALID_OR_REPAIRED_CONFIG",
            "Variant Config is invalid or was automatically repaired",
            (
                _boolean("formal_config_required", True),
                _boolean("automatic_repair_allowed", False),
            ),
        ),
    )


_GATE_SPECS = (
    (
        "BASE_COMMIT_MATCH",
        "authority",
        "Execution base equals the frozen C-008C-A commit",
        "Execution base exactly equals the frozen commit before any Run",
        "Execution base is missing or differs from the frozen commit",
        ("authority_snapshot", "experiment_plan"),
        (_text("expected_execution_base_commit", EXECUTION_BASE_COMMIT),),
    ),
    (
        "CORE_PROFILE_AUTHORIZED",
        "authority",
        "Core Profile equals the formal authority",
        "Authority snapshot completely equals the validated Core Profile",
        "Profile identity config payload or reference commit differs",
        ("authority_snapshot",),
        (_text("comparison_scope", "COMPLETE_AUTHORITY_PAYLOAD"),),
    ),
    (
        "PROTECTED_SOURCE_UNCHANGED",
        "source",
        "Every protected source byte remains unchanged",
        "Every declared path size category and SHA-256 equals the manifest",
        "Any protected file is added removed unreadable or byte-different",
        ("protected_source_manifest",),
        (_text("comparison_scope", "PATH_SIZE_CATEGORY_SHA256"),),
    ),
    (
        "DATASET_MANIFEST_VALID",
        "dataset",
        "Dataset manifest equals the frozen source-bound authority",
        "All twenty cases and manifest metadata equal the formal Builder",
        "Any case input metadata rule assumption order or identity differs",
        ("dataset_manifest",),
        (_integer("required_case_count", 20),),
    ),
    (
        "DATASET_PARTITIONS_DISJOINT",
        "dataset",
        "Source inputs are disjoint across partitions",
        "All case IDs and source digests are unique across partitions",
        "Any case or source input is reused across partitions",
        ("dataset_manifest",),
        (_boolean("cross_partition_reuse_allowed", False),),
    ),
    (
        "ALL_SCENARIOS_PRESENT",
        "dataset",
        "Every frozen scenario is present in every partition",
        "Five scenarios cover Development Validation and OOS as declared",
        "Any declared scenario or required partition coverage is absent",
        ("dataset_manifest",),
        (
            _integer("scenario_count", 5),
            _integer("partition_count", 3),
        ),
    ),
    (
        "PLAN_PREDECLARED",
        "plan",
        "Plan identity exists before any outcome",
        "Complete source-bound Plan equals authority before execution",
        "Plan is absent changed or constructed after outcome access",
        ("authority_snapshot", "experiment_plan"),
        (_boolean("must_exist_before_outcomes", True),),
    ),
    (
        "PLAN_OUTCOME_INDEPENDENT",
        "plan",
        "Plan payload contains no outcome input",
        "Plan construction reads only frozen authority and policy inputs",
        "Any Run metric OOS result or outcome affects Plan identity",
        ("experiment_plan",),
        (_boolean("outcome_inputs_allowed", False),),
    ),
    (
        "MODEL_VARIANTS_OAT",
        "variant",
        "Every model sensitivity changes exactly one axis",
        "Each of eight model LOW or HIGH variants changes one public axis",
        "A model sensitivity changes zero multiple or private fields",
        ("experiment_plan",),
        (_integer("changed_axis_count_per_variant", 1),),
    ),
    (
        "METRIC_VARIANTS_OAT",
        "variant",
        "Every metric sensitivity changes exactly one axis",
        "Each metric LOW or HIGH variant changes one public metric axis",
        "A metric sensitivity changes zero multiple or private fields",
        ("experiment_plan",),
        (_integer("changed_axis_count_per_variant", 1),),
    ),
    (
        "ABLATION_PUBLIC_CONFIG_ONLY",
        "ablation",
        "Supported ablations use only public Config",
        "Four supported ablations are exactly expressible by public Config",
        "A supported ablation patches source or a private field",
        ("experiment_plan",),
        (_integer("supported_ablation_count", 4),),
    ),
    (
        "INCREMENT_ENDS_AT_BASELINE",
        "increment",
        "Final increment equals the complete baseline",
        "Five fixed increments restore one contribution class and end at Baseline",
        "Order changes a step restores multiple classes or endpoint differs",
        ("experiment_plan",),
        (_integer("increment_step_count", 5),),
    ),
    (
        "ALL_CASES_MUST_EXECUTE",
        "execution",
        "Every declared case and variant pair is executed",
        "All twenty cases execute all twenty-six variants for 520 unique pairs",
        "Any one of the 520 predeclared execution pairs is missing or duplicated",
        ("experiment_plan", "experiment_case_result"),
        (
            _integer("dataset_case_count", 20),
            _integer("variant_count", 26),
            _integer("required_execution_pair_count", 520),
        ),
    ),
    (
        "ALL_CORE_RUNS_MUST_AUDIT",
        "execution",
        "Every Core Run passes the formal causal audit",
        "Each execution result binds a Run with a passing complete causal audit",
        "Any Run lacks its audit source binding or has a failed audit check",
        ("experiment_case_result", "core_run", "causal_audit_report"),
        (_integer("required_audit_per_run", 1),),
    ),
    (
        "ALL_METRIC_REPORTS_MUST_SOURCE_BIND",
        "metrics",
        "Every metric report is source-bound to its Run",
        "Every execution report completely source-binds to its formal Core Run",
        "A report is absent forged partial or inconsistent with its Run",
        ("experiment_case_result", "core_run", "metric_evaluation_report"),
        (_boolean("complete_source_binding_required", True),),
    ),
    (
        "BASELINE_BATCH_REPLAY_PARITY",
        "replay",
        "Baseline Batch and Replay payloads are equal",
        "Baseline Run and Metric Report payloads match for all twenty cases",
        "Any Baseline case has a Batch and Replay payload difference",
        ("replay_comparison", "core_run", "metric_evaluation_report"),
        (
            _integer("baseline_variant_count", 1),
            _integer("dataset_case_count", 20),
            _integer("required_replay_sample_count", 20),
            _texts(
                "complete_payloads",
                "core_run",
                "metric_evaluation_report",
            ),
        ),
    ),
    (
        "VARIANT_REPLAY_SAMPLE_PARITY",
        "replay",
        "Frozen non-Baseline replay samples preserve parity",
        "All twenty-five variants match on the five seed-two Validation cases",
        "Any one of the 125 frozen variant replay samples differs",
        ("replay_comparison", "core_run", "metric_evaluation_report"),
        (
            _integer("non_baseline_variant_count", 25),
            _integer("validation_case_count", 5),
            _integer("required_replay_sample_count", 125),
            _integer("validation_seed", 2),
        ),
    ),
    (
        "FIXED_CUTOFF_STABILITY",
        "lookahead",
        "Earlier causal cutoffs remain byte-stable",
        "Baseline complete payloads match at every formal AsOf for all cases",
        "A future append changes any payload frozen at an earlier causal AsOf",
        (
            "fixed_cutoff_comparison",
            "core_run",
            "causal_audit_report",
            "metric_evaluation_report",
        ),
        (
            _integer("baseline_variant_count", 1),
            _integer("dataset_case_count", 20),
            _text("cutoff_scope", "EVERY_FORMAL_CAUSAL_ASOF"),
            _text("comparison_scope", "COMPLETE_FORMAL_PAYLOAD"),
        ),
    ),
    (
        "DETERMINISTIC_REPEAT",
        "determinism",
        "Repeated execution produces identical payloads",
        "Repeated Runs reports and comparisons are byte-identical",
        "Any repeated formal execution produces a different payload",
        (
            "deterministic_comparison",
            "core_run",
            "metric_evaluation_report",
        ),
        (_integer("minimum_repeat_count", 2),),
    ),
    (
        "DECIMAL_CONTEXT_INDEPENDENCE",
        "determinism",
        "Global Decimal context cannot alter payloads",
        "Authority Plan Run and report payloads survive context changes",
        "Precision or rounding context changes any formal payload",
        ("authority_snapshot", "experiment_plan", "deterministic_comparison"),
        (_boolean("global_decimal_context_is_input", False),),
    ),
    (
        "TEN_AGGREGATES_ALWAYS_PRESENT",
        "metrics",
        "All ten formal aggregates are present",
        "Every metric report contains all ten formal aggregate definitions",
        "A metric report omits duplicates or invents an aggregate",
        ("metric_evaluation_report", "metric_coverage_summary"),
        (_integer("required_aggregate_count", 10),),
    ),
    (
        "OOS_SAMPLE_COVERAGE",
        "dataset",
        "Synthetic OOS metric coverage meets frozen minima",
        "Every metric meets its denominator-specific minimum without copying",
        "Any metric misses its minimum counts censored or unavailable as matured",
        ("metric_coverage_summary", "metric_evaluation_report"),
        (
            _boolean("censored_counts_as_matured", False),
            _boolean("unavailable_counts_as_zero", False),
            _boolean("sample_duplication_allowed", False),
            _text("interpretation", "SYNTHETIC_ENGINEERING_COVERAGE_ONLY"),
        ),
    ),
    (
        "NO_NEIGHBORHOOD_DEGENERATION",
        "sensitivity",
        "Variants avoid the ten frozen structural degeneration conditions",
        "Every variant avoids all ten rules or is reported as SENSITIVE only",
        "Any variant triggers one or more frozen degeneration conditions",
        (
            "degeneration_summary",
            "experiment_case_result",
            "causal_audit_report",
            "metric_evaluation_report",
        ),
        (
            _text("non_degenerate_large_change_label", "SENSITIVE"),
            _boolean("sensitive_implies_better", False),
            _boolean("parameter_selection_allowed", False),
        ),
    ),
    (
        "NO_PARAMETER_OPTIMIZATION",
        "governance",
        "No outcome selects or changes parameters",
        "Experiment report preserves all predeclared values and order",
        "An outcome changes a value order winner leaderboard or recommendation",
        ("experiment_plan", "experiment_report"),
        (_boolean("outcome_driven_selection_allowed", False),),
    ),
    (
        "NO_TRADING_FIELDS",
        "governance",
        "No trading or execution field is introduced",
        "Authority Plan and report contain structural validation fields only",
        "Any signal order position profit or trading field appears",
        ("authority_snapshot", "experiment_plan", "experiment_report"),
        (_texts("forbidden_interpretations", "TRADING", "PROFITABILITY"),),
    ),
    (
        "EVIDENCE_REPRODUCIBLE",
        "evidence",
        "Authority evidence regenerates byte-for-byte",
        "All four canonical authority files equal regenerated bytes",
        "Any authority file is missing reordered host-bound or byte-different",
        (
            "authority_snapshot",
            "dataset_manifest",
            "experiment_plan",
            "protected_source_manifest",
        ),
        (_integer("canonical_authority_file_count", 4),),
    ),
    (
        "FREEZE_SOURCE_BOUND",
        "freeze",
        "Any later freeze candidate binds protected source",
        "Candidate report and protected-source manifest completely source-bind",
        "Candidate is absent premature or differs from protected source evidence",
        ("experiment_report", "protected_source_manifest", "freeze_candidate"),
        (_boolean("candidate_allowed_in_c008c_a", False),),
    ),
)


def _definition(
    code: str,
    subject: str,
    description: str,
    pass_condition: str,
    failure_condition: str,
    evidence: tuple[str, ...],
    parameters: tuple[ExperimentGateParameter, ...],
) -> ExperimentGateDefinition:
    if any(item not in _FUTURE_EVIDENCE_KINDS for item in evidence):
        raise ValueError(f"unknown future evidence kind for {code}")
    policy = ExperimentGatePolicy(
        policy_code=f"{code}_POLICY_V1",
        parameters=parameters,
        sample_coverage_rules=(
            _coverage_rules() if code == "OOS_SAMPLE_COVERAGE" else ()
        ),
        degeneration_rules=(
            _degeneration_rules()
            if code == "NO_NEIGHBORHOOD_DEGENERATION"
            else ()
        ),
        pass_condition=pass_condition,
        failure_condition=failure_condition,
    )
    payload = {
        "code": code,
        "severity": GateSeverity.HARD.value,
        "subject_kind": subject,
        "description": description,
        "policy": policy.to_dict(),
        "pass_rule": pass_condition,
        "failure_rule": failure_condition,
        "required_evidence_kinds": list(evidence),
        "schema_version": 1,
    }
    return ExperimentGateDefinition(
        gate_definition_id=semantic_id(
            "c008c-gate-definition-v1-", payload
        ),
        code=code,
        severity=GateSeverity.HARD,
        subject_kind=subject,
        description=description,
        policy=policy,
        pass_rule=pass_condition,
        failure_rule=failure_condition,
        required_evidence_kinds=evidence,
    )


def default_c008c_gate_registry() -> tuple[
    ExperimentGateDefinition, ...
]:
    return tuple(_definition(*item) for item in _GATE_SPECS)
