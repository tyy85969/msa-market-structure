from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from msa.validation.experiments import (
    DatasetPartition,
    ExperimentGatePolicy,
    build_c008c_synthetic_dataset,
    default_c008c_experiment_plan,
    default_c008c_gate_registry,
)


def _by_code() -> dict[str, object]:
    return {item.code: item for item in default_c008c_gate_registry()}


def test_all_gate_policies_are_typed_explicit_and_non_placeholder() -> None:
    gates = default_c008c_gate_registry()
    assert len(gates) == 27
    assert len({item.required_evidence_kinds for item in gates}) > 10
    for gate in gates:
        assert isinstance(gate.policy, ExperimentGatePolicy)
        assert gate.pass_rule == gate.policy.pass_condition
        assert gate.failure_rule == gate.policy.failure_condition
        assert gate.policy.parameters
        assert "required evidence satisfies its frozen exact rule" not in (
            gate.pass_rule
        )
        assert "required evidence is absent or differs" not in (
            gate.failure_rule
        )
        assert ExperimentGatePolicy.from_dict(
            gate.policy.to_dict()
        ) == gate.policy


def test_gate_evidence_kinds_match_the_frozen_subjects() -> None:
    gates = _by_code()
    assert gates["CORE_PROFILE_AUTHORIZED"].required_evidence_kinds == (
        "authority_snapshot",
    )
    assert gates["PROTECTED_SOURCE_UNCHANGED"].required_evidence_kinds == (
        "protected_source_manifest",
    )
    assert gates["ALL_CORE_RUNS_MUST_AUDIT"].required_evidence_kinds == (
        "experiment_case_result",
        "core_run",
        "causal_audit_report",
    )
    assert gates[
        "ALL_METRIC_REPORTS_MUST_SOURCE_BIND"
    ].required_evidence_kinds == (
        "experiment_case_result",
        "core_run",
        "metric_evaluation_report",
    )
    assert gates[
        "BASELINE_BATCH_REPLAY_PARITY"
    ].required_evidence_kinds == (
        "replay_comparison",
        "core_run",
        "metric_evaluation_report",
    )
    assert gates["OOS_SAMPLE_COVERAGE"].required_evidence_kinds == (
        "metric_coverage_summary",
        "metric_evaluation_report",
    )
    assert gates[
        "NO_NEIGHBORHOOD_DEGENERATION"
    ].required_evidence_kinds == (
        "degeneration_summary",
        "experiment_case_result",
        "causal_audit_report",
        "metric_evaluation_report",
    )
    assert gates["FREEZE_SOURCE_BOUND"].required_evidence_kinds == (
        "experiment_report",
        "protected_source_manifest",
        "freeze_candidate",
    )


def test_complete_execution_scope_is_frozen_without_omission() -> None:
    plan = default_c008c_experiment_plan()
    scope = plan.execution_scope_policy
    pairs = scope.execution_pairs()
    assert len(scope.dataset_case_ids) == 20
    assert len(scope.variant_ids) == 26
    assert len(scope.oos_dataset_case_ids) == 5
    assert scope.expected_execution_pair_count == 520
    assert len(pairs) == len(set(pairs)) == 520
    for case_id in scope.dataset_case_ids:
        assert scope.variants_for_case(case_id) == scope.variant_ids
    for variant_id in scope.variant_ids:
        assert scope.cases_for_variant(variant_id) == scope.dataset_case_ids
    for case_id in scope.oos_dataset_case_ids:
        assert scope.variants_for_case(case_id) == scope.variant_ids


def test_replay_and_fixed_cutoff_scopes_are_predeclared() -> None:
    plan = default_c008c_experiment_plan()
    validation_ids = tuple(
        item.dataset_case_id
        for item in build_c008c_synthetic_dataset().cases
        if item.partition is DatasetPartition.VALIDATION
    )
    assert plan.baseline_replay_policy.expected_sample_count == 20
    assert plan.baseline_replay_policy.comparison_scope == "COMPLETE_TO_DICT"
    assert len(plan.baseline_replay_policy.sample_pairs()) == 20
    assert plan.variant_replay_policy.dataset_case_ids == validation_ids
    assert len(plan.variant_replay_policy.variant_ids) == 25
    assert plan.variant_replay_policy.expected_sample_count == 125
    assert plan.variant_replay_policy.comparison_scope == "COMPLETE_TO_DICT"
    assert len(plan.variant_replay_policy.sample_pairs()) == 125
    assert (
        plan.fixed_cutoff_policy.dataset_case_ids
        == plan.execution_scope_policy.dataset_case_ids
    )
    assert plan.fixed_cutoff_policy.cutoff_scope == (
        "EVERY_FORMAL_CAUSAL_ASOF"
    )
    assert plan.fixed_cutoff_policy.compared_payload_kinds == (
        "core_run",
        "causal_audit_report",
        "metric_evaluation_report",
    )
    assert plan.fixed_cutoff_policy.comparison_scope == "COMPLETE_TO_DICT"


def test_oos_coverage_thresholds_are_exact() -> None:
    policy = _by_code()["OOS_SAMPLE_COVERAGE"].policy
    actual = {
        item.metric_code: (item.denominator_kind, item.minimum_count)
        for item in policy.sample_coverage_rules
    }
    assert actual == {
        "CONFIRMATION_DELAY_BARS": ("MATURED", 10),
        "CONFIRMATION_DELAY_ATR": ("MATURED", 10),
        "FALSE_TURN_RATE": ("RESOLVED_OR_MATURED", 5),
        "CONTINUED_BREAK_RATE": ("MATURED", 5),
        "TREND_CAPTURE_RATIO": ("MATURED", 5),
        "MFE": ("MATURED", 20),
        "MAE": ("MATURED", 20),
        "FIRST_TOUCH_REACTION": ("MATURED", 20),
        "BOX_CHURN": ("BOX_EPISODES", 5),
        "RESONANCE_LIFT": ("MATCHED_PAIRS", 3),
    }
    for item in policy.sample_coverage_rules:
        assert item.excluded_statuses == ("CENSORED", "UNAVAILABLE")
        assert item.duplication_allowed is False
        assert item.scope == "SYNTHETIC_OOS"


def test_all_ten_degeneration_rules_are_frozen() -> None:
    policy = _by_code()["NO_NEIGHBORHOOD_DEGENERATION"].policy
    assert tuple(item.rule_code for item in policy.degeneration_rules) == (
        "PIPELINE_EXECUTION_FAILURE",
        "CAUSAL_AUDIT_FAILURE",
        "METRIC_SOURCE_BIND_FAILURE",
        "BATCH_REPLAY_MISMATCH",
        "FUTURE_PREFIX_REWRITE",
        "STRUCTURE_EVENT_COLLAPSE",
        "BOX_EPISODE_COLLAPSE",
        "MULTI_METRIC_COVERAGE_COLLAPSE",
        "AGGREGATE_SET_INCOMPLETE",
        "INVALID_OR_REPAIRED_CONFIG",
    )
    multi_metric = policy.degeneration_rules[7]
    assert {item.name: item.value for item in multi_metric.parameters} == {
        "minimum_metric_count": 5,
        "decline_fraction_exclusive": Decimal("0.90"),
    }
    labels = {item.name: item.value for item in policy.parameters}
    assert labels == {
        "non_degenerate_large_change_label": "SENSITIVE",
        "sensitive_implies_better": False,
        "parameter_selection_allowed": False,
    }


def test_policy_contracts_are_frozen() -> None:
    policy = _by_code()["OOS_SAMPLE_COVERAGE"].policy
    with pytest.raises(FrozenInstanceError):
        policy.policy_code = "changed"  # type: ignore[misc]
