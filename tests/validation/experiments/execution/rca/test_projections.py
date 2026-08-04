from copy import deepcopy

from msa.validation.experiments.execution.rca.contracts import (
    DiagnosticLayer,
    DeterminismDiagnosticKind,
    MismatchLayer,
)
from msa.validation.experiments.execution.rca.determinism import (
    build_determinism_result,
)
from msa.validation.experiments.execution.rca.projections import (
    project_audit_semantics,
    project_core_run_semantics,
    project_metric_semantics,
)


def _payload():
    return {
        "config": {"precision": 28},
        "core_run": {
            "run_id": "run-a",
            "frame_bundles": [{"active_box_id": "box-a"}],
            "provenance": {"object_id": "run-a"},
        },
        "audit": {
            "audit_report_id": "audit-a",
            "subject_ids": ["run-a"],
            "audit_kind": "MSA_CORE_RUN",
            "findings": [
                {
                    "finding_id": "finding-a",
                    "code": "NO_FUTURE_FRAME_REWRITE",
                    "severity": "ERROR",
                    "facts": [{"key": "kind", "value": "stable"}],
                }
            ],
            "provenance": ["entry", "run_id=run-a"],
        },
        "metric": {
            "metric_report_id": "metric-a",
            "source_run_id": "run-a",
            "evaluation_as_of_time": "2026-01-01T00:00:00+00:00",
            "formula_registry": [
                {"metric_formula_id": "formula-a", "formula_status": "FROZEN"}
            ],
            "aggregates": [
                {
                    "metric_aggregate_id": "aggregate-a",
                    "formula_id": "formula-a",
                    "metric_name": "TURN_RESOLUTION_RATE",
                    "status": "AVAILABLE",
                    "value": "1",
                    "eligible_count": 1,
                    "matured_count": 1,
                    "censored_count": 0,
                    "unavailable_count": 0,
                }
            ],
            "provenance": ["entry", "source_run_id=run-a"],
        },
        "case_result": {
            "case_result_id": "case-a",
            "dataset_case_id": "dataset-a",
            "variant_id": "variant-a",
            "status": "PASSED",
            "run_id": "run-a",
            "run_payload_digest": "digest-a",
            "audit_report_id": "audit-a",
            "audit_payload_digest": "digest-b",
            "metric_report_id": "metric-a",
            "metric_report_payload_digest": "digest-c",
            "aggregates": [],
        },
    }


def _result(left, right):
    return build_determinism_result(
        "pair-a",
        DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION,
        left,
        right,
    )


def test_only_core_run_wrapper_id_is_identity_only():
    left = _payload()
    right = deepcopy(left)
    right["core_run"]["run_id"] = "run-b"
    result = _result(left, right)
    assert result.core_identity_only_mismatch
    assert not result.core_semantic_mismatch
    assert result.mismatch_layer is MismatchLayer.CORE_RUN_IDENTITY


def test_domain_object_id_is_core_semantic():
    left = _payload()
    right = deepcopy(left)
    right["core_run"]["frame_bundles"][0]["active_box_id"] = "box-b"
    result = _result(left, right)
    assert result.core_semantic_mismatch
    summary = next(
        item for item in result.layer_summaries if item.layer is DiagnosticLayer.CORE
    )
    assert summary.first_semantic_difference_path == "/frame_bundles/0/active_box_id"


def test_formula_id_value_and_coverage_are_metric_semantic():
    for key, value in (
        ("formula_id", "formula-b"),
        ("value", "0"),
        ("matured_count", 0),
        ("censored_count", 1),
    ):
        left = _payload()
        right = deepcopy(left)
        right["metric"]["aggregates"][0][key] = value
        result = _result(left, right)
        assert result.metric_semantic_mismatch, key


def test_audit_finding_code_is_semantic_but_report_id_is_identity():
    left = _payload()
    right = deepcopy(left)
    right["audit"]["findings"][0]["code"] = "PREFIX_CAUSALITY"
    assert _result(left, right).audit_semantic_mismatch
    right = deepcopy(left)
    right["audit"]["audit_report_id"] = "audit-b"
    result = _result(left, right)
    assert result.audit_identity_or_provenance_mismatch
    assert not result.audit_semantic_mismatch


def test_metric_source_binding_does_not_masquerade_as_outcome():
    left = _payload()
    right = deepcopy(left)
    right["metric"]["source_run_id"] = "run-b"
    result = _result(left, right)
    assert result.metric_identity_or_provenance_mismatch
    assert not result.metric_semantic_mismatch


def test_unknown_fields_default_to_semantic():
    assert project_core_run_semantics({"new_digest_policy": "a"}) != project_core_run_semantics(
        {"new_digest_policy": "b"}
    )
    assert project_audit_semantics({"new_id_policy": "a"}) != project_audit_semantics(
        {"new_id_policy": "b"}
    )
    assert project_metric_semantics({"future_provenance_rule": "a"}) != project_metric_semantics(
        {"future_provenance_rule": "b"}
    )


def test_layer_summary_survives_global_twenty_difference_limit():
    left = _payload()
    right = deepcopy(left)
    left["core_run"]["values"] = list(range(30))
    right["core_run"]["values"] = list(reversed(range(30)))
    right["metric"]["aggregates"][0]["formula_id"] = "formula-b"
    result = _result(left, right)
    assert len(result.differences) == 20
    metric = next(
        item for item in result.layer_summaries if item.layer is DiagnosticLayer.METRIC
    )
    assert metric.first_semantic_difference_path == "/aggregates/0/formula_id"
