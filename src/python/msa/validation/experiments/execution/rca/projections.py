"""Explicit semantic projections for C-008C-B RCA payloads.

The exclusions below are deliberately limited to top-level wrapper identity,
content-address bindings, and source-run bindings.  Every other field,
including unknown future fields, remains semantic by default.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass

from .errors import C008CBRCADiagnosticError


@dataclass(frozen=True, slots=True)
class ExplicitProjection:
    semantic: object
    identity: object


# MSACoreRun.to_dict(): only the Run wrapper ID and its wrapper provenance are
# excluded.  Bundle, Candidate, Zone, Cluster, Boundary, Active Box, and every
# other domain-object identity remain semantic.
_CORE_WRAPPER_FIELDS = frozenset({"run_id", "provenance"})

# CausalAuditReport.to_dict(): report identity, report subjects, and the public
# provenance/source binding are wrappers.  Finding/check identities, finding
# code, kind, severity, object IDs, and facts remain semantic.
_AUDIT_WRAPPER_FIELDS = frozenset(
    {"audit_report_id", "subject_ids", "provenance"}
)

# MetricEvaluationReport.to_dict(): these are the only excluded wrapper/source
# bindings.  Formula IDs, event/observation/match/aggregate IDs, names, status,
# values, counts, facts, and cutoff-sensitive fields remain semantic.
_METRIC_WRAPPER_FIELDS = frozenset(
    {"metric_report_id", "source_run_id", "provenance"}
)

# ExperimentCaseResult.to_dict(): the result wrapper and upstream content/source
# bindings are derived identities.  Schedule facts, status, aggregates, counts,
# and bounded failure facts remain semantic.
_CASE_RESULT_WRAPPER_FIELDS = frozenset(
    {
        "case_result_id",
        "source_input_payload_digest",
        "core_config_payload_digest",
        "metric_config_payload_digest",
        "run_id",
        "run_payload_digest",
        "audit_report_id",
        "audit_payload_digest",
        "metric_report_id",
        "metric_report_payload_digest",
    }
)


def _split_top_level(
    payload: object, excluded_fields: frozenset[str], label: str
) -> ExplicitProjection:
    if payload is None:
        return ExplicitProjection(semantic=None, identity=None)
    if not isinstance(payload, Mapping):
        raise C008CBRCADiagnosticError(f"{label} payload must be a mapping or None")
    semantic: dict[str, object] = {}
    identity: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise C008CBRCADiagnosticError(f"{label} payload keys must be text")
        target = identity if key in excluded_fields else semantic
        target[key] = deepcopy(value)
    return ExplicitProjection(semantic=semantic, identity=identity)


def split_core_run_projection(payload: object) -> ExplicitProjection:
    return _split_top_level(payload, _CORE_WRAPPER_FIELDS, "Core Run")


def split_audit_projection(payload: object) -> ExplicitProjection:
    return _split_top_level(payload, _AUDIT_WRAPPER_FIELDS, "Audit")


def split_metric_projection(payload: object) -> ExplicitProjection:
    return _split_top_level(payload, _METRIC_WRAPPER_FIELDS, "Metric")


def split_case_result_projection(payload: object) -> ExplicitProjection:
    return _split_top_level(
        payload, _CASE_RESULT_WRAPPER_FIELDS, "Experiment CaseResult"
    )


def project_core_run_semantics(payload: object) -> object:
    return split_core_run_projection(payload).semantic


def project_audit_semantics(payload: object) -> object:
    return split_audit_projection(payload).semantic


def project_metric_semantics(payload: object) -> object:
    return split_metric_projection(payload).semantic


def project_case_result_semantics(payload: object) -> object:
    return split_case_result_projection(payload).semantic


__all__ = [
    "ExplicitProjection",
    "project_audit_semantics",
    "project_case_result_semantics",
    "project_core_run_semantics",
    "project_metric_semantics",
    "split_audit_projection",
    "split_case_result_projection",
    "split_core_run_projection",
    "split_metric_projection",
]
