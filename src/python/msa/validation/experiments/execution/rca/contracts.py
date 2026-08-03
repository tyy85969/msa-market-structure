"""Strict compact contracts for C-008C-B root-cause evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from types import UnionType
from typing import Any, ClassVar, Self, Union, get_args, get_origin, get_type_hints

from ...identity import digest, require_semantic_id
from ..contracts import C008CBStageStatus
from .errors import C008CBRCAError


SCHEMA_VERSION = 1


class _RCAEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class DeterminismDiagnosticKind(_RCAEnum):
    SAME_CONTEXT_REPEAT = "SAME_CONTEXT_REPEAT"
    DECIMAL_CONTEXT_PERTURBATION = "DECIMAL_CONTEXT_PERTURBATION"


class MismatchLayer(_RCAEnum):
    NONE = "NONE"
    CONFIG_SNAPSHOT = "CONFIG_SNAPSHOT"
    CORE_RUN_SEMANTIC = "CORE_RUN_SEMANTIC"
    CORE_RUN_IDENTITY = "CORE_RUN_IDENTITY"
    AUDIT_SEMANTIC = "AUDIT_SEMANTIC"
    AUDIT_IDENTITY_OR_PROVENANCE = "AUDIT_IDENTITY_OR_PROVENANCE"
    METRIC_SEMANTIC = "METRIC_SEMANTIC"
    METRIC_IDENTITY_OR_PROVENANCE = "METRIC_IDENTITY_OR_PROVENANCE"
    CASE_RESULT_DERIVED = "CASE_RESULT_DERIVED"
    HARNESS_CONTRACT = "HARNESS_CONTRACT"
    UNKNOWN = "UNKNOWN"


class CutoffRewriteLayer(_RCAEnum):
    NONE = "NONE"
    PREFIX_SOURCE = "PREFIX_SOURCE"
    PROCESSING_SCHEDULE = "PROCESSING_SCHEDULE"
    FRAME_BUNDLE = "FRAME_BUNDLE"
    ACTIVE_BOX_LEDGER = "ACTIVE_BOX_LEDGER"
    COMPARISON_AUDIT = "COMPARISON_AUDIT"
    METRIC_OUTCOME = "METRIC_OUTCOME"
    IDENTITY_OR_SOURCE_BINDING = "IDENTITY_OR_SOURCE_BINDING"
    HARNESS_CONTRACT = "HARNESS_CONTRACT"
    UNKNOWN = "UNKNOWN"


class DegenerationEvidenceKind(_RCAEnum):
    VARIANT_DIRECT = "VARIANT_DIRECT"
    GLOBAL_BASELINE_PROPAGATION = "GLOBAL_BASELINE_PROPAGATION"
    SHARED_STATIC_EVIDENCE = "SHARED_STATIC_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RootCauseDisposition(_RCAEnum):
    HARNESS_CORRECTION_REQUIRED = "HARNESS_CORRECTION_REQUIRED"
    PROTECTED_CORE_REMEDIATION_REQUIRED = "PROTECTED_CORE_REMEDIATION_REQUIRED"
    MIXED_ROOT_CAUSE = "MIXED_ROOT_CAUSE"
    NO_ROOT_CAUSE_FOUND = "NO_ROOT_CAUSE_FOUND"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DifferenceKind(_RCAEnum):
    MISSING = "MISSING"
    EXTRA = "EXTRA"
    TYPE = "TYPE"
    VALUE = "VALUE"
    ORDER = "ORDER"


def _serialize(value: object) -> object:
    if isinstance(value, float):
        raise C008CBRCAError("RCA evidence must not contain float")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if is_dataclass(value) and hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def _convert(annotation: object, value: object) -> object:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is tuple:
        if not isinstance(value, list):
            raise C008CBRCAError("tuple field must be serialized as ordered list")
        return tuple(_convert(args[0], item) for item in value)
    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return None
        target = next(item for item in args if item is not type(None))
        return _convert(target, value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return annotation(value)
        except (TypeError, ValueError) as exc:
            raise C008CBRCAError(f"invalid {annotation.__name__}") from exc
    if isinstance(annotation, type) and hasattr(annotation, "from_dict"):
        return annotation.from_dict(value)
    return value


def _assert_type(annotation: object, value: object, label: str) -> None:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is tuple:
        if type(value) is not tuple:
            raise C008CBRCAError(f"{label} must be tuple")
        for index, item in enumerate(value):
            _assert_type(args[0], item, f"{label}[{index}]")
        return
    if origin in (Union, UnionType):
        if value is None and type(None) in args:
            return
        target = next(item for item in args if item is not type(None))
        _assert_type(target, value, label)
        return
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if not isinstance(value, annotation):
            raise C008CBRCAError(f"{label} has invalid enum type")
        return
    if annotation is bool and type(value) is not bool:
        raise C008CBRCAError(f"{label} must be bool")
    if annotation is int and (type(value) is not int or value < 0):
        raise C008CBRCAError(f"{label} must be non-negative integer")
    if annotation is str and (not isinstance(value, str) or not value):
        raise C008CBRCAError(f"{label} must be non-empty text")
    if (
        isinstance(annotation, type)
        and annotation not in (bool, int, str)
        and not isinstance(value, annotation)
    ):
        raise C008CBRCAError(f"{label} has invalid contract type")


class _StrictContract:
    _ID_FIELD: ClassVar[str]
    _PREFIX: ClassVar[str]

    def to_dict(self) -> dict[str, object]:
        return {
            item.name: _serialize(getattr(self, item.name))
            for item in fields(self)
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        if not isinstance(payload, Mapping):
            raise C008CBRCAError(f"{cls.__name__} payload must be mapping")
        expected = {item.name for item in fields(cls)}
        if set(payload) != expected:
            raise C008CBRCAError(
                f"{cls.__name__} fields mismatch missing="
                f"{sorted(expected - set(payload))} unknown="
                f"{sorted(set(payload) - expected)}"
            )
        hints = get_type_hints(cls)
        try:
            return cls(
                **{
                    item.name: _convert(hints[item.name], payload[item.name])
                    for item in fields(cls)
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBRCAError(
                f"invalid serialized {cls.__name__}"
            ) from exc

    def _validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise C008CBRCAError("schema_version must equal 1")
        hints = get_type_hints(type(self))
        for item in fields(self):
            _assert_type(
                hints[item.name], getattr(self, item.name), item.name
            )
        payload = self.to_dict()
        require_semantic_id(
            getattr(self, self._ID_FIELD),
            prefix=self._PREFIX,
            payload={
                key: value
                for key, value in payload.items()
                if key != self._ID_FIELD
            },
            field_name=self._ID_FIELD,
            error_type=C008CBRCAError,
        )


@dataclass(frozen=True, slots=True)
class C008CBRCADiagnosticPair(_StrictContract):
    diagnostic_pair_id: str
    execution_pair_id: str
    dataset_case_id: str
    variant_id: str
    partition: str
    scenario: str
    seed: int
    schedule_index: int
    selection_kind: str
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "diagnostic_pair_id"
    _PREFIX = "c008c-b-rca-diagnostic-pair-v1-"

    def __post_init__(self) -> None:
        if self.seed == 3 or self.partition == "OOS":
            raise C008CBRCAError("OOS pair is forbidden in RCA")
        if self.selection_kind not in (
            "BASELINE_ALL_B",
            "VARIANT_FIRST_VALIDATION",
        ):
            raise C008CBRCAError("invalid deterministic selection kind")
        self._validate()


@dataclass(frozen=True, slots=True)
class C008CBRCAManifest(_StrictContract):
    rca_manifest_id: str
    baseline_id: str
    dataset_manifest_id: str
    experiment_plan_id: str
    protected_source_manifest_id: str
    b_execution_manifest_id: str
    b_run_report_id: str
    b_manifest_sha256: str
    b_report_sha256: str
    diagnostic_pairs: tuple[C008CBRCADiagnosticPair, ...]
    cutoff_case_ids: tuple[str, ...]
    cutoff_as_of_times: tuple[str, ...]
    cutoff_checkpoint_indices: tuple[int, ...]
    cutoff_selection_kinds: tuple[str, ...]
    diagnostic_schedule_digest: str
    cutoff_schedule_digest: str
    same_context_runs_per_pair: int
    altered_decimal_runs_per_pair: int
    decimal_precision: int
    decimal_rounding: str
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "rca_manifest_id"
    _PREFIX = "c008c-b-rca-manifest-v1-"

    def __post_init__(self) -> None:
        if len(self.diagnostic_pairs) != 40:
            raise C008CBRCAError("RCA manifest requires exactly 40 pairs")
        schedules = (
            self.cutoff_case_ids,
            self.cutoff_as_of_times,
            self.cutoff_checkpoint_indices,
            self.cutoff_selection_kinds,
        )
        if any(len(value) != 15 for value in schedules):
            raise C008CBRCAError("RCA manifest requires 15 cutoff checkpoints")
        if (
            self.same_context_runs_per_pair,
            self.altered_decimal_runs_per_pair,
        ) != (2, 1):
            raise C008CBRCAError("RCA per-pair execution budget must be 2+1")
        if (self.decimal_precision, self.decimal_rounding) != (
            7,
            "ROUND_FLOOR",
        ):
            raise C008CBRCAError("RCA Decimal perturbation mismatch")
        for label, value in (
            ("b_manifest_sha256", self.b_manifest_sha256),
            ("b_report_sha256", self.b_report_sha256),
        ):
            if len(value) != 64 or any(x not in "0123456789abcdef" for x in value):
                raise C008CBRCAError(f"{label} must be lowercase SHA-256")
        if self.diagnostic_schedule_digest != digest(
            [item.to_dict() for item in self.diagnostic_pairs]
        ):
            raise C008CBRCAError("RCA diagnostic schedule digest mismatch")
        expected_cutoff_digest = digest([
            {
                "dataset_case_id": case_id,
                "cutoff_as_of_time": cutoff,
                "checkpoint_index": index,
                "selection_kind": kind,
            }
            for case_id, cutoff, index, kind in zip(
                self.cutoff_case_ids,
                self.cutoff_as_of_times,
                self.cutoff_checkpoint_indices,
                self.cutoff_selection_kinds,
                strict=True,
            )
        ])
        if self.cutoff_schedule_digest != expected_cutoff_digest:
            raise C008CBRCAError("RCA cutoff schedule digest mismatch")
        self._validate()


@dataclass(frozen=True, slots=True)
class PayloadDifference(_StrictContract):
    payload_difference_id: str
    path: str
    difference_kind: DifferenceKind
    left_type: str
    right_type: str
    left_value: str
    right_value: str
    left_subtree_digest: str
    right_subtree_digest: str
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "payload_difference_id"
    _PREFIX = "c008c-b-rca-payload-difference-v1-"

    def __post_init__(self) -> None:
        if len(self.left_value) > 256 or len(self.right_value) > 256:
            raise C008CBRCAError("payload difference representation is unbounded")
        self._validate()


@dataclass(frozen=True, slots=True)
class DeterminismDiagnosticResult(_StrictContract):
    diagnostic_result_id: str
    diagnostic_pair_id: str
    diagnostic_kind: DeterminismDiagnosticKind
    config_payload_equal: bool
    core_run_payload_equal: bool
    audit_payload_equal: bool
    metric_payload_equal: bool
    case_result_payload_equal: bool
    full_payload_equal: bool
    total_difference_count: int
    differences: tuple[PayloadDifference, ...]
    mismatch_layer: MismatchLayer
    first_semantic_difference_path: str | None
    core_semantic_mismatch: bool
    core_identity_only_mismatch: bool
    audit_semantic_mismatch: bool
    audit_identity_or_provenance_mismatch: bool
    metric_semantic_mismatch: bool
    metric_identity_or_provenance_mismatch: bool
    case_derived_only_mismatch: bool
    disposition: RootCauseDisposition
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "diagnostic_result_id"
    _PREFIX = "c008c-b-rca-determinism-result-v1-"

    def __post_init__(self) -> None:
        if len(self.differences) > 20:
            raise C008CBRCAError("at most 20 differences may be stored")
        if self.total_difference_count < len(self.differences):
            raise C008CBRCAError("difference count is inconsistent")
        self._validate()


@dataclass(frozen=True, slots=True)
class FixedCutoffComponentResult(_StrictContract):
    component_result_id: str
    component_name: str
    equal: bool
    total_difference_count: int
    differences: tuple[PayloadDifference, ...]
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "component_result_id"
    _PREFIX = "c008c-b-rca-cutoff-component-v1-"

    def __post_init__(self) -> None:
        if len(self.differences) > 20:
            raise C008CBRCAError("at most 20 component differences may be stored")
        self._validate()


@dataclass(frozen=True, slots=True)
class FixedCutoffDiagnosticResult(_StrictContract):
    cutoff_diagnostic_id: str
    dataset_case_id: str
    cutoff_as_of_time: str
    checkpoint_index: int
    selection_kind: str
    source_prefix_valid: bool
    processing_schedule_equal: bool
    shared_asof_audit_passed: bool
    prefix_audit_passed: bool
    frame_bundles_equal: bool
    active_box_events_equal: bool
    frozen_boxes_equal: bool
    metric_semantic_equal: bool
    metric_full_payload_equal: bool
    identity_only_difference: bool
    comparator_boundary_operator: str
    supplied_comparator_cutoff: str
    exact_cutoff_included: bool
    components: tuple[FixedCutoffComponentResult, ...]
    final_layer: CutoffRewriteLayer
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "cutoff_diagnostic_id"
    _PREFIX = "c008c-b-rca-cutoff-diagnostic-v1-"

    def __post_init__(self) -> None:
        if self.comparator_boundary_operator != "<":
            raise C008CBRCAError("comparator boundary must be recorded as <")
        self._validate()


@dataclass(frozen=True, slots=True)
class DegenerationRuleAttribution(_StrictContract):
    rule_attribution_id: str
    variant_id: str
    rule_code: str
    triggered: bool
    evidence_kind: DegenerationEvidenceKind
    evidence_direct_subject: str
    evidence_source_ids: tuple[str, ...]
    variant_specific: bool
    shared_baseline_evidence: bool
    derived_from_failed_gate: bool
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "rule_attribution_id"
    _PREFIX = "c008c-b-rca-degeneration-rule-v1-"

    def __post_init__(self) -> None:
        self._validate()


@dataclass(frozen=True, slots=True)
class VariantDegenerationAttribution(_StrictContract):
    variant_attribution_id: str
    variant_id: str
    formal_status: str
    attributions: tuple[DegenerationRuleAttribution, ...]
    direct_triggered_rule_codes: tuple[str, ...]
    global_propagated_rule_codes: tuple[str, ...]
    descriptive_status_without_global_propagation: str
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "variant_attribution_id"
    _PREFIX = "c008c-b-rca-variant-degeneration-v1-"

    def __post_init__(self) -> None:
        self._validate()


@dataclass(frozen=True, slots=True)
class C008CBRootCauseReport(_StrictContract):
    root_cause_report_id: str
    rca_manifest_id: str
    b_run_report_id: str
    original_stage_status: C008CBStageStatus
    determinism_results: tuple[DeterminismDiagnosticResult, ...]
    cutoff_results: tuple[FixedCutoffDiagnosticResult, ...]
    degeneration_attributions: tuple[VariantDegenerationAttribution, ...]
    same_context_mismatch_count: int
    decimal_context_mismatch_count: int
    core_semantic_mismatch_count: int
    core_identity_only_mismatch_count: int
    audit_semantic_mismatch_count: int
    audit_identity_or_provenance_mismatch_count: int
    metric_semantic_mismatch_count: int
    metric_identity_or_provenance_mismatch_count: int
    case_derived_only_mismatch_count: int
    prefix_source_invalid_count: int
    frame_bundle_rewrite_count: int
    active_box_ledger_rewrite_count: int
    metric_semantic_rewrite_count: int
    identity_only_cutoff_difference_count: int
    harness_contract_mismatch_count: int
    direct_degeneration_rule_count: int
    global_baseline_propagation_count: int
    disposition: RootCauseDisposition
    admitted_attribution_gaps: tuple[str, ...]
    recommendations: tuple[str, ...]
    original_b_evidence_modified: bool
    gate_results_modified: bool
    stage_status_modified: bool
    protected_source_modified: bool
    oos_executed: bool
    full_matrix_reexecuted: bool
    all_cutoffs_reexecuted: bool
    schema_version: int = SCHEMA_VERSION

    _ID_FIELD = "root_cause_report_id"
    _PREFIX = "c008c-b-root-cause-report-v1-"

    def __post_init__(self) -> None:
        if len(self.determinism_results) != 80:
            raise C008CBRCAError("RCA requires two diagnostics for each pair")
        if len(self.cutoff_results) != 15:
            raise C008CBRCAError("RCA requires 15 cutoff diagnostics")
        if len(self.degeneration_attributions) != 25:
            raise C008CBRCAError("RCA requires 25 degeneration attributions")
        forbidden = (
            self.original_b_evidence_modified,
            self.gate_results_modified,
            self.stage_status_modified,
            self.protected_source_modified,
            self.oos_executed,
            self.full_matrix_reexecuted,
            self.all_cutoffs_reexecuted,
        )
        if any(forbidden):
            raise C008CBRCAError("RCA crossed a frozen task boundary")
        self._validate()


__all__ = [
    "C008CBRCADiagnosticPair",
    "C008CBRCAManifest",
    "C008CBRootCauseReport",
    "CutoffRewriteLayer",
    "DegenerationEvidenceKind",
    "DegenerationRuleAttribution",
    "DeterminismDiagnosticKind",
    "DeterminismDiagnosticResult",
    "DifferenceKind",
    "FixedCutoffComponentResult",
    "FixedCutoffDiagnosticResult",
    "MismatchLayer",
    "PayloadDifference",
    "RootCauseDisposition",
    "VariantDegenerationAttribution",
]
