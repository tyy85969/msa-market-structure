"""Frozen hard-gate registry for later C-008C execution."""

from __future__ import annotations

from .contracts import ExperimentGateDefinition, GateSeverity
from .identity import semantic_id


_GATES = (
    ("BASE_COMMIT_MATCH", "authority", "Execution base equals the frozen C-008C-A commit"),
    ("CORE_PROFILE_AUTHORIZED", "authority", "Core Profile equals the formal authority"),
    ("PROTECTED_SOURCE_UNCHANGED", "source", "Every protected source byte remains unchanged"),
    ("DATASET_MANIFEST_VALID", "dataset", "Dataset manifest passes the strict contract"),
    ("DATASET_PARTITIONS_DISJOINT", "dataset", "Source inputs are disjoint across partitions"),
    ("ALL_SCENARIOS_PRESENT", "dataset", "Every frozen scenario is present in every partition"),
    ("PLAN_PREDECLARED", "plan", "Plan identity exists before any outcome"),
    ("PLAN_OUTCOME_INDEPENDENT", "plan", "Plan payload contains no outcome input"),
    ("MODEL_VARIANTS_OAT", "variant", "Every model sensitivity changes exactly one axis"),
    ("METRIC_VARIANTS_OAT", "variant", "Every metric sensitivity changes exactly one axis"),
    ("ABLATION_PUBLIC_CONFIG_ONLY", "ablation", "Supported ablations use only public Config"),
    ("INCREMENT_ENDS_AT_BASELINE", "increment", "Final increment equals the complete baseline"),
    ("ALL_CASES_MUST_EXECUTE", "execution", "Every declared dataset case is executed"),
    ("ALL_CORE_RUNS_MUST_AUDIT", "execution", "Every Core Run passes the formal causal audit"),
    ("ALL_METRIC_REPORTS_MUST_SOURCE_BIND", "metrics", "Every report is source-bound to its Run"),
    ("BASELINE_BATCH_REPLAY_PARITY", "replay", "Baseline Batch and Replay payloads are equal"),
    ("VARIANT_REPLAY_SAMPLE_PARITY", "replay", "Frozen variant replay samples preserve parity"),
    ("FIXED_CUTOFF_STABILITY", "lookahead", "Earlier cutoffs remain byte-stable"),
    ("DETERMINISTIC_REPEAT", "determinism", "Repeated execution produces identical payloads"),
    ("DECIMAL_CONTEXT_INDEPENDENCE", "determinism", "Global Decimal context cannot alter payloads"),
    ("TEN_AGGREGATES_ALWAYS_PRESENT", "metrics", "All ten formal aggregates are present"),
    ("OOS_SAMPLE_COVERAGE", "dataset", "Every scenario has a locked OOS sample"),
    ("NO_NEIGHBORHOOD_DEGENERATION", "sensitivity", "Every LOW and HIGH differs from baseline"),
    ("NO_PARAMETER_OPTIMIZATION", "governance", "No outcome selects or changes parameters"),
    ("NO_TRADING_FIELDS", "governance", "No trading or execution field is introduced"),
    ("EVIDENCE_REPRODUCIBLE", "evidence", "Evidence regenerates byte-for-byte"),
    ("FREEZE_SOURCE_BOUND", "freeze", "Any later freeze recommendation binds protected source"),
)


def _definition(
    code: str, subject: str, description: str
) -> ExperimentGateDefinition:
    evidence = (
        "authority_snapshot",
        "dataset_manifest",
        "experiment_plan",
        "protected_source_manifest",
    )
    pass_rule = f"{code} required evidence satisfies its frozen exact rule"
    failure_rule = f"{code} required evidence is absent or differs"
    payload = {
        "code": code,
        "severity": GateSeverity.HARD.value,
        "subject_kind": subject,
        "description": description,
        "pass_rule": pass_rule,
        "failure_rule": failure_rule,
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
        pass_rule=pass_rule,
        failure_rule=failure_rule,
        required_evidence_kinds=evidence,
    )


def default_c008c_gate_registry() -> tuple[
    ExperimentGateDefinition, ...
]:
    return tuple(_definition(*item) for item in _GATES)
