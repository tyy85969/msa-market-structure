"""Versioned contracts for corrected C-008C-B-v2 harness semantics.

The original v1 contracts remain the parser for the committed historical B
evidence.  Nothing in this module changes or upgrades those payloads in place.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, ClassVar, Self

from ..identity import digest, require_semantic_id, semantic_id
from .contracts import (
    C008CBExecutionManifest,
    DegenerationStatus,
    GateEvaluationStatus,
    ReplayComparisonStatus,
)
from .errors import (
    C008CBComparisonError,
    C008CBDegenerationError,
    C008CBGateError,
    C008CBManifestError,
)


B_V2_SCHEMA_VERSION = 2
B_V2_EXECUTION_SEMANTICS = "C-008C-B-v2"


class _V2Enum(str, Enum):
    def __str__(self) -> str:
        return self.value


class DeterminismEvidenceKind(_V2Enum):
    SAME_CONTEXT_REPEAT = "SAME_CONTEXT_REPEAT"
    DECIMAL_CONTEXT_PERTURBATION = "DECIMAL_CONTEXT_PERTURBATION"


class DegenerationEvidenceScope(_V2Enum):
    VARIANT_DIRECT = "VARIANT_DIRECT"
    VARIANT_EVIDENCE_UNAVAILABLE = "VARIANT_EVIDENCE_UNAVAILABLE"
    BASELINE_GLOBAL = "BASELINE_GLOBAL"


def _text(value: object, label: str, error: type[ValueError]) -> str:
    if not isinstance(value, str) or not value:
        raise error(f"{label} must be non-empty text")
    return value


def _bool(value: object, label: str, error: type[ValueError]) -> bool:
    if type(value) is not bool:
        raise error(f"{label} must be bool")
    return value


def _texts(
    value: object,
    label: str,
    error: type[ValueError],
    *,
    non_empty: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, tuple) or (non_empty and not value):
        raise error(f"{label} must be tuple")
    if any(not isinstance(item, str) or not item for item in value):
        raise error(f"{label} must contain non-empty text")
    if len(set(value)) != len(value):
        raise error(f"{label} must be unique")
    return value


def _schema(value: object, label: str, error: type[ValueError]) -> None:
    if type(value) is not int or value != B_V2_SCHEMA_VERSION:
        raise error(f"{label}.schema_version must equal 2")


def _exact(
    payload: object,
    cls: type,
    error: type[ValueError],
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise error(f"{cls.__name__} payload must be mapping")
    expected = {item.name for item in fields(cls)}
    if set(payload) != expected:
        raise error(f"{cls.__name__} fields mismatch")
    return payload


def _identity(
    instance: object,
    *,
    id_field: str,
    prefix: str,
    error: type[ValueError],
) -> None:
    payload = instance.to_dict()
    require_semantic_id(
        getattr(instance, id_field),
        prefix=prefix,
        payload={key: value for key, value in payload.items() if key != id_field},
        field_name=id_field,
        error_type=error,
    )


@dataclass(frozen=True, slots=True)
class C008CBV2ExecutionContract:
    execution_contract_id: str
    execution_semantics: str
    historical_execution_manifest_id: str
    executable_pair_ids: tuple[str, ...]
    deferred_oos_pair_ids: tuple[str, ...]
    execution_result_labels: tuple[str, ...]
    deterministic_repeat_evidence_kind: DeterminismEvidenceKind
    decimal_context_independence_evidence_kind: DeterminismEvidenceKind
    baseline_rewrite_evidence_scope: DegenerationEvidenceScope
    variant_rewrite_evidence_scope: DegenerationEvidenceScope
    historical_evidence_superseded: bool
    outcome_execution_performed: bool
    formal_gate_recalculation_performed: bool
    oos_executed: bool
    schema_version: int = B_V2_SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-v2-execution-contract-v2-"

    def __post_init__(self) -> None:
        error = C008CBManifestError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.execution_contract_id, "execution_contract_id", error)
        if self.execution_semantics != B_V2_EXECUTION_SEMANTICS:
            raise error("execution_semantics must identify C-008C-B-v2")
        _text(
            self.historical_execution_manifest_id,
            "historical_execution_manifest_id",
            error,
        )
        if len(
            _texts(self.executable_pair_ids, "executable_pair_ids", error)
        ) != 390:
            raise error("B-v2 must retain exactly 390 executable B-stage pairs")
        if len(
            _texts(self.deferred_oos_pair_ids, "deferred_oos_pair_ids", error)
        ) != 130:
            raise error("B-v2 must keep exactly 130 OOS pairs deferred")
        if set(self.executable_pair_ids) & set(self.deferred_oos_pair_ids):
            raise error("executable and deferred pair IDs must be disjoint")
        if self.execution_result_labels != (
            "NORMAL_A",
            "NORMAL_B",
            "ALTERED_DECIMAL_CONTEXT",
        ):
            raise error("B-v2 requires three independent execution result labels")
        if (
            self.deterministic_repeat_evidence_kind
            is not DeterminismEvidenceKind.SAME_CONTEXT_REPEAT
            or self.decimal_context_independence_evidence_kind
            is not DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
        ):
            raise error("B-v2 Gate evidence bindings are incorrect")
        if (
            self.baseline_rewrite_evidence_scope
            is not DegenerationEvidenceScope.BASELINE_GLOBAL
            or self.variant_rewrite_evidence_scope
            is not DegenerationEvidenceScope.VARIANT_EVIDENCE_UNAVAILABLE
        ):
            raise error("B-v2 rewrite evidence scopes are incorrect")
        for name in (
            "historical_evidence_superseded",
            "outcome_execution_performed",
            "formal_gate_recalculation_performed",
            "oos_executed",
        ):
            if _bool(getattr(self, name), name, error):
                raise error(f"{name} must remain false in the H1 contract")
        _identity(
            self,
            id_field="execution_contract_id",
            prefix=self._PREFIX,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_contract_id": self.execution_contract_id,
            "execution_semantics": self.execution_semantics,
            "historical_execution_manifest_id": (
                self.historical_execution_manifest_id
            ),
            "executable_pair_ids": list(self.executable_pair_ids),
            "deferred_oos_pair_ids": list(self.deferred_oos_pair_ids),
            "execution_result_labels": list(self.execution_result_labels),
            "deterministic_repeat_evidence_kind": (
                self.deterministic_repeat_evidence_kind.value
            ),
            "decimal_context_independence_evidence_kind": (
                self.decimal_context_independence_evidence_kind.value
            ),
            "baseline_rewrite_evidence_scope": (
                self.baseline_rewrite_evidence_scope.value
            ),
            "variant_rewrite_evidence_scope": (
                self.variant_rewrite_evidence_scope.value
            ),
            "historical_evidence_superseded": self.historical_evidence_superseded,
            "outcome_execution_performed": self.outcome_execution_performed,
            "formal_gate_recalculation_performed": (
                self.formal_gate_recalculation_performed
            ),
            "oos_executed": self.oos_executed,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBManifestError)
        try:
            return cls(
                execution_contract_id=data["execution_contract_id"],
                execution_semantics=data["execution_semantics"],
                historical_execution_manifest_id=data[
                    "historical_execution_manifest_id"
                ],
                executable_pair_ids=tuple(data["executable_pair_ids"]),
                deferred_oos_pair_ids=tuple(data["deferred_oos_pair_ids"]),
                execution_result_labels=tuple(data["execution_result_labels"]),
                deterministic_repeat_evidence_kind=DeterminismEvidenceKind(
                    data["deterministic_repeat_evidence_kind"]
                ),
                decimal_context_independence_evidence_kind=DeterminismEvidenceKind(
                    data["decimal_context_independence_evidence_kind"]
                ),
                baseline_rewrite_evidence_scope=DegenerationEvidenceScope(
                    data["baseline_rewrite_evidence_scope"]
                ),
                variant_rewrite_evidence_scope=DegenerationEvidenceScope(
                    data["variant_rewrite_evidence_scope"]
                ),
                historical_evidence_superseded=data[
                    "historical_evidence_superseded"
                ],
                outcome_execution_performed=data["outcome_execution_performed"],
                formal_gate_recalculation_performed=data[
                    "formal_gate_recalculation_performed"
                ],
                oos_executed=data["oos_executed"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBManifestError("invalid serialized B-v2 contract") from exc


def build_c008c_b_v2_execution_contract(
    manifest: C008CBExecutionManifest,
) -> C008CBV2ExecutionContract:
    """Build the outcome-free contract over the historical frozen schedule."""

    if not isinstance(manifest, C008CBExecutionManifest):
        raise C008CBManifestError("manifest must be historical C008CBExecutionManifest")
    kwargs = {
        "execution_semantics": B_V2_EXECUTION_SEMANTICS,
        "historical_execution_manifest_id": manifest.execution_manifest_id,
        "executable_pair_ids": tuple(
            item.execution_pair_id for item in manifest.execution_pairs
        ),
        "deferred_oos_pair_ids": tuple(
            item.execution_pair_id for item in manifest.deferred_oos_pairs
        ),
        "execution_result_labels": (
            "NORMAL_A",
            "NORMAL_B",
            "ALTERED_DECIMAL_CONTEXT",
        ),
        "deterministic_repeat_evidence_kind": (
            DeterminismEvidenceKind.SAME_CONTEXT_REPEAT
        ),
        "decimal_context_independence_evidence_kind": (
            DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
        ),
        "baseline_rewrite_evidence_scope": (
            DegenerationEvidenceScope.BASELINE_GLOBAL
        ),
        "variant_rewrite_evidence_scope": (
            DegenerationEvidenceScope.VARIANT_EVIDENCE_UNAVAILABLE
        ),
        "historical_evidence_superseded": False,
        "outcome_execution_performed": False,
        "formal_gate_recalculation_performed": False,
        "oos_executed": False,
        "schema_version": B_V2_SCHEMA_VERSION,
    }
    payload = {
        key: value.value
        if isinstance(value, Enum)
        else list(value)
        if isinstance(value, tuple)
        else value
        for key, value in kwargs.items()
    }
    return C008CBV2ExecutionContract(
        execution_contract_id=semantic_id(
            C008CBV2ExecutionContract._PREFIX, payload
        ),
        **kwargs,
    )


@dataclass(frozen=True, slots=True)
class ExperimentDeterminismComparisonV2:
    determinism_comparison_id: str
    execution_semantics: str
    comparison_kind: DeterminismEvidenceKind
    execution_pair_id: str
    dataset_case_id: str
    variant_id: str
    status: ReplayComparisonStatus
    normal_a_case_result_id: str
    compared_case_result_id: str
    normal_a_payload_digest: str
    compared_payload_digest: str
    run_payload_equal: bool
    audit_payload_equal: bool
    metric_payload_equal: bool
    case_result_payload_equal: bool
    decimal_context_changed: bool
    schema_version: int = B_V2_SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-v2-determinism-comparison-v2-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        if self.execution_semantics != B_V2_EXECUTION_SEMANTICS:
            raise error("comparison must use B-v2 execution semantics")
        if not isinstance(self.comparison_kind, DeterminismEvidenceKind):
            raise error("comparison_kind must be DeterminismEvidenceKind")
        for name in (
            "determinism_comparison_id",
            "execution_pair_id",
            "dataset_case_id",
            "variant_id",
            "normal_a_case_result_id",
            "compared_case_result_id",
            "normal_a_payload_digest",
            "compared_payload_digest",
        ):
            _text(getattr(self, name), name, error)
        if self.status not in (
            ReplayComparisonStatus.MATCH,
            ReplayComparisonStatus.MISMATCH,
        ):
            raise error("B-v2 determinism comparison must be MATCH or MISMATCH")
        for name in (
            "run_payload_equal",
            "audit_payload_equal",
            "metric_payload_equal",
            "case_result_payload_equal",
            "decimal_context_changed",
        ):
            _bool(getattr(self, name), name, error)
        expected_context_changed = (
            self.comparison_kind
            is DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION
        )
        if self.decimal_context_changed is not expected_context_changed:
            raise error("comparison kind contradicts Decimal-context flag")
        all_equal = (
            self.run_payload_equal
            and self.audit_payload_equal
            and self.metric_payload_equal
            and self.case_result_payload_equal
            and self.normal_a_payload_digest == self.compared_payload_digest
        )
        if (self.status is ReplayComparisonStatus.MATCH) is not all_equal:
            raise error("comparison status contradicts payload equality")
        _identity(
            self,
            id_field="determinism_comparison_id",
            prefix=self._PREFIX,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "determinism_comparison_id": self.determinism_comparison_id,
            "execution_semantics": self.execution_semantics,
            "comparison_kind": self.comparison_kind.value,
            "execution_pair_id": self.execution_pair_id,
            "dataset_case_id": self.dataset_case_id,
            "variant_id": self.variant_id,
            "status": self.status.value,
            "normal_a_case_result_id": self.normal_a_case_result_id,
            "compared_case_result_id": self.compared_case_result_id,
            "normal_a_payload_digest": self.normal_a_payload_digest,
            "compared_payload_digest": self.compared_payload_digest,
            "run_payload_equal": self.run_payload_equal,
            "audit_payload_equal": self.audit_payload_equal,
            "metric_payload_equal": self.metric_payload_equal,
            "case_result_payload_equal": self.case_result_payload_equal,
            "decimal_context_changed": self.decimal_context_changed,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                determinism_comparison_id=data["determinism_comparison_id"],
                execution_semantics=data["execution_semantics"],
                comparison_kind=DeterminismEvidenceKind(data["comparison_kind"]),
                execution_pair_id=data["execution_pair_id"],
                dataset_case_id=data["dataset_case_id"],
                variant_id=data["variant_id"],
                status=ReplayComparisonStatus(data["status"]),
                normal_a_case_result_id=data["normal_a_case_result_id"],
                compared_case_result_id=data["compared_case_result_id"],
                normal_a_payload_digest=data["normal_a_payload_digest"],
                compared_payload_digest=data["compared_payload_digest"],
                run_payload_equal=data["run_payload_equal"],
                audit_payload_equal=data["audit_payload_equal"],
                metric_payload_equal=data["metric_payload_equal"],
                case_result_payload_equal=data["case_result_payload_equal"],
                decimal_context_changed=data["decimal_context_changed"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentDeterminismComparisonV2"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDegenerationFindingV2:
    degeneration_finding_id: str
    execution_semantics: str
    variant_id: str
    evidence_subject_id: str
    evidence_scope: DegenerationEvidenceScope
    evidence_source_ids: tuple[str, ...]
    rule_code: str
    triggered: bool
    status: DegenerationStatus
    validation_case_ids: tuple[str, ...]
    facts: tuple[str, ...]
    schema_version: int = B_V2_SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-v2-degeneration-finding-v2-"

    def __post_init__(self) -> None:
        error = C008CBDegenerationError
        _schema(self.schema_version, type(self).__name__, error)
        if self.execution_semantics != B_V2_EXECUTION_SEMANTICS:
            raise error("finding must use B-v2 execution semantics")
        for name in (
            "degeneration_finding_id",
            "variant_id",
            "evidence_subject_id",
            "rule_code",
        ):
            _text(getattr(self, name), name, error)
        if self.evidence_subject_id != self.variant_id:
            raise error("Variant finding must bind its own Variant subject")
        if self.evidence_scope is DegenerationEvidenceScope.BASELINE_GLOBAL:
            raise error("Baseline/global evidence cannot be a Variant finding")
        _texts(
            self.evidence_source_ids,
            "evidence_source_ids",
            error,
            non_empty=False,
        )
        _bool(self.triggered, "triggered", error)
        if self.triggered != (self.status is DegenerationStatus.DEGENERATED):
            raise error("finding trigger/status mismatch")
        if len(
            _texts(self.validation_case_ids, "validation_case_ids", error)
        ) != 5:
            raise error("Variant finding must bind five Validation cases")
        _texts(self.facts, "facts", error)
        if self.rule_code == "FUTURE_PREFIX_REWRITE":
            if (
                self.evidence_scope
                is not DegenerationEvidenceScope.VARIANT_EVIDENCE_UNAVAILABLE
                or self.triggered
                or self.status is not DegenerationStatus.INSUFFICIENT_EVIDENCE
                or self.evidence_source_ids
            ):
                raise error(
                    "Variant FUTURE_PREFIX_REWRITE requires unavailable direct evidence"
                )
        elif self.evidence_scope is not DegenerationEvidenceScope.VARIANT_DIRECT:
            raise error("non-rewrite Variant findings require direct evidence")
        _identity(
            self,
            id_field="degeneration_finding_id",
            prefix=self._PREFIX,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "degeneration_finding_id": self.degeneration_finding_id,
            "execution_semantics": self.execution_semantics,
            "variant_id": self.variant_id,
            "evidence_subject_id": self.evidence_subject_id,
            "evidence_scope": self.evidence_scope.value,
            "evidence_source_ids": list(self.evidence_source_ids),
            "rule_code": self.rule_code,
            "triggered": self.triggered,
            "status": self.status.value,
            "validation_case_ids": list(self.validation_case_ids),
            "facts": list(self.facts),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBDegenerationError)
        try:
            return cls(
                degeneration_finding_id=data["degeneration_finding_id"],
                execution_semantics=data["execution_semantics"],
                variant_id=data["variant_id"],
                evidence_subject_id=data["evidence_subject_id"],
                evidence_scope=DegenerationEvidenceScope(
                    data["evidence_scope"]
                ),
                evidence_source_ids=tuple(data["evidence_source_ids"]),
                rule_code=data["rule_code"],
                triggered=data["triggered"],
                status=DegenerationStatus(data["status"]),
                validation_case_ids=tuple(data["validation_case_ids"]),
                facts=tuple(data["facts"]),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBDegenerationError(
                "invalid serialized ExperimentDegenerationFindingV2"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDegenerationSummaryV2:
    degeneration_summary_id: str
    execution_semantics: str
    variant_id: str
    status: DegenerationStatus
    findings: tuple[ExperimentDegenerationFindingV2, ...]
    triggered_rule_codes: tuple[str, ...]
    non_zero_validation_delta_count: int
    schema_version: int = B_V2_SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-v2-degeneration-summary-v2-"

    def __post_init__(self) -> None:
        error = C008CBDegenerationError
        _schema(self.schema_version, type(self).__name__, error)
        if self.execution_semantics != B_V2_EXECUTION_SEMANTICS:
            raise error("summary must use B-v2 execution semantics")
        _text(self.degeneration_summary_id, "degeneration_summary_id", error)
        _text(self.variant_id, "variant_id", error)
        if (
            not isinstance(self.findings, tuple)
            or len(self.findings) != 10
            or any(
                not isinstance(item, ExperimentDegenerationFindingV2)
                or item.variant_id != self.variant_id
                for item in self.findings
            )
            or len({item.rule_code for item in self.findings}) != 10
        ):
            raise error("B-v2 summary requires ten subject-bound findings")
        triggered = tuple(
            item.rule_code for item in self.findings if item.triggered
        )
        _texts(
            self.triggered_rule_codes,
            "triggered_rule_codes",
            error,
            non_empty=False,
        )
        if self.triggered_rule_codes != triggered:
            raise error("triggered_rule_codes contradict findings")
        if type(self.non_zero_validation_delta_count) is not int or (
            self.non_zero_validation_delta_count < 0
        ):
            raise error("non_zero_validation_delta_count must be non-negative int")
        insufficient = any(
            item.status is DegenerationStatus.INSUFFICIENT_EVIDENCE
            for item in self.findings
        )
        expected = (
            DegenerationStatus.DEGENERATED
            if triggered
            else DegenerationStatus.INSUFFICIENT_EVIDENCE
            if insufficient
            else DegenerationStatus.SENSITIVE
            if self.non_zero_validation_delta_count
            else DegenerationStatus.NOT_DEGENERATED
        )
        if self.status is not expected:
            raise error("summary status contradicts subject-bound findings")
        _identity(
            self,
            id_field="degeneration_summary_id",
            prefix=self._PREFIX,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "degeneration_summary_id": self.degeneration_summary_id,
            "execution_semantics": self.execution_semantics,
            "variant_id": self.variant_id,
            "status": self.status.value,
            "findings": [item.to_dict() for item in self.findings],
            "triggered_rule_codes": list(self.triggered_rule_codes),
            "non_zero_validation_delta_count": (
                self.non_zero_validation_delta_count
            ),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBDegenerationError)
        try:
            return cls(
                degeneration_summary_id=data["degeneration_summary_id"],
                execution_semantics=data["execution_semantics"],
                variant_id=data["variant_id"],
                status=DegenerationStatus(data["status"]),
                findings=tuple(
                    ExperimentDegenerationFindingV2.from_dict(item)
                    for item in data["findings"]
                ),
                triggered_rule_codes=tuple(data["triggered_rule_codes"]),
                non_zero_validation_delta_count=data[
                    "non_zero_validation_delta_count"
                ],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBDegenerationError(
                "invalid serialized ExperimentDegenerationSummaryV2"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentGlobalDegenerationEvidenceV2:
    global_evidence_id: str
    execution_semantics: str
    baseline_variant_id: str
    evidence_subject_id: str
    evidence_scope: DegenerationEvidenceScope
    evidence_source_ids: tuple[str, ...]
    rule_code: str
    triggered: bool
    status: DegenerationStatus
    facts: tuple[str, ...]
    schema_version: int = B_V2_SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-v2-global-degeneration-evidence-v2-"

    def __post_init__(self) -> None:
        error = C008CBDegenerationError
        _schema(self.schema_version, type(self).__name__, error)
        if self.execution_semantics != B_V2_EXECUTION_SEMANTICS:
            raise error("global evidence must use B-v2 execution semantics")
        for name in (
            "global_evidence_id",
            "baseline_variant_id",
            "evidence_subject_id",
            "rule_code",
        ):
            _text(getattr(self, name), name, error)
        if (
            self.evidence_subject_id != self.baseline_variant_id
            or self.evidence_scope is not DegenerationEvidenceScope.BASELINE_GLOBAL
            or self.rule_code != "FUTURE_PREFIX_REWRITE"
        ):
            raise error("global rewrite evidence must bind Baseline only")
        if len(
            _texts(self.evidence_source_ids, "evidence_source_ids", error)
        ) != 15:
            raise error("global rewrite evidence must bind 15 Baseline cutoff results")
        _bool(self.triggered, "triggered", error)
        expected = (
            DegenerationStatus.DEGENERATED
            if self.triggered
            else DegenerationStatus.NOT_DEGENERATED
        )
        if self.status is not expected:
            raise error("global rewrite status contradicts trigger")
        _texts(self.facts, "facts", error)
        _identity(
            self,
            id_field="global_evidence_id",
            prefix=self._PREFIX,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "global_evidence_id": self.global_evidence_id,
            "execution_semantics": self.execution_semantics,
            "baseline_variant_id": self.baseline_variant_id,
            "evidence_subject_id": self.evidence_subject_id,
            "evidence_scope": self.evidence_scope.value,
            "evidence_source_ids": list(self.evidence_source_ids),
            "rule_code": self.rule_code,
            "triggered": self.triggered,
            "status": self.status.value,
            "facts": list(self.facts),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBDegenerationError)
        try:
            return cls(
                global_evidence_id=data["global_evidence_id"],
                execution_semantics=data["execution_semantics"],
                baseline_variant_id=data["baseline_variant_id"],
                evidence_subject_id=data["evidence_subject_id"],
                evidence_scope=DegenerationEvidenceScope(
                    data["evidence_scope"]
                ),
                evidence_source_ids=tuple(data["evidence_source_ids"]),
                rule_code=data["rule_code"],
                triggered=data["triggered"],
                status=DegenerationStatus(data["status"]),
                facts=tuple(data["facts"]),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBDegenerationError(
                "invalid serialized ExperimentGlobalDegenerationEvidenceV2"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentGateResultV2:
    gate_result_id: str
    execution_semantics: str
    gate_definition_id: str
    gate_code: str
    status: GateEvaluationStatus
    evidence_kind: str
    evidence_ids: tuple[str, ...]
    evidence_payload_digest: str
    rationale: str
    schema_version: int = B_V2_SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-v2-gate-result-v2-"

    def __post_init__(self) -> None:
        error = C008CBGateError
        _schema(self.schema_version, type(self).__name__, error)
        if self.execution_semantics != B_V2_EXECUTION_SEMANTICS:
            raise error("Gate result must use B-v2 execution semantics")
        for name in (
            "gate_result_id",
            "gate_definition_id",
            "gate_code",
            "evidence_kind",
            "evidence_payload_digest",
            "rationale",
        ):
            _text(getattr(self, name), name, error)
        if not isinstance(self.status, GateEvaluationStatus):
            raise error("status must be GateEvaluationStatus")
        _texts(self.evidence_ids, "evidence_ids", error, non_empty=False)
        _identity(
            self,
            id_field="gate_result_id",
            prefix=self._PREFIX,
            error=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "gate_result_id": self.gate_result_id,
            "execution_semantics": self.execution_semantics,
            "gate_definition_id": self.gate_definition_id,
            "gate_code": self.gate_code,
            "status": self.status.value,
            "evidence_kind": self.evidence_kind,
            "evidence_ids": list(self.evidence_ids),
            "evidence_payload_digest": self.evidence_payload_digest,
            "rationale": self.rationale,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBGateError)
        try:
            return cls(
                gate_result_id=data["gate_result_id"],
                execution_semantics=data["execution_semantics"],
                gate_definition_id=data["gate_definition_id"],
                gate_code=data["gate_code"],
                status=GateEvaluationStatus(data["status"]),
                evidence_kind=data["evidence_kind"],
                evidence_ids=tuple(data["evidence_ids"]),
                evidence_payload_digest=data["evidence_payload_digest"],
                rationale=data["rationale"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBGateError(
                "invalid serialized ExperimentGateResultV2"
            ) from exc


def v2_payload_id(prefix: str, payload: Mapping[str, object]) -> str:
    """Small public helper used by the v2 harness constructors."""

    return semantic_id(prefix, dict(payload))


def v2_payload_digest(payload: object) -> str:
    return digest(payload)


__all__ = [
    "B_V2_EXECUTION_SEMANTICS",
    "B_V2_SCHEMA_VERSION",
    "C008CBV2ExecutionContract",
    "DegenerationEvidenceScope",
    "DeterminismEvidenceKind",
    "ExperimentDegenerationFindingV2",
    "ExperimentDegenerationSummaryV2",
    "ExperimentDeterminismComparisonV2",
    "ExperimentGateResultV2",
    "ExperimentGlobalDegenerationEvidenceV2",
    "build_c008c_b_v2_execution_contract",
    "v2_payload_digest",
    "v2_payload_id",
]
