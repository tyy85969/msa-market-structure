"""Strict compact contracts for frozen C-008C-B execution evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, ClassVar, Self

from msa.validation.contracts import (
    SyntheticScenarioKind,
    ValidationMetricName,
)
from msa.validation.metrics import MetricAggregateStatus

from ..contracts import (
    DatasetPartition,
    ExperimentKind,
    VariantLevel,
)
from ..identity import digest, require_semantic_id
from .errors import (
    C008CBCaseError,
    C008CBComparisonError,
    C008CBDegenerationError,
    C008CBGateError,
    C008CBManifestError,
    C008CBReportError,
)


SCHEMA_VERSION = 1
REPOSITORY_BASE_COMMIT = "ea6c641472e13f3273afdb73ccf1ff3580e10800"
FROZEN_EXECUTION_BASE_COMMIT = "6f4ebef19164156728438b480867660db3b1cd65"
CORE_REFERENCE_COMMIT = "d72c18f7994afd506e6ecf044571ccffbc695631"


class _ExecutionEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ExperimentCaseStatus(_ExecutionEnum):
    PASSED = "PASSED"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    CAUSAL_AUDIT_FAILED = "CAUSAL_AUDIT_FAILED"
    METRIC_EVALUATION_FAILED = "METRIC_EVALUATION_FAILED"
    METRIC_SOURCE_BIND_FAILED = "METRIC_SOURCE_BIND_FAILED"


class MetricDeltaStatus(_ExecutionEnum):
    COMPARABLE = "COMPARABLE"
    BASELINE_UNAVAILABLE = "BASELINE_UNAVAILABLE"
    VARIANT_UNAVAILABLE = "VARIANT_UNAVAILABLE"
    BOTH_UNAVAILABLE = "BOTH_UNAVAILABLE"


class ReplayComparisonStatus(_ExecutionEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class FixedCutoffStatus(_ExecutionEnum):
    STABLE = "STABLE"
    REWRITE_DETECTED = "REWRITE_DETECTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class DegenerationStatus(_ExecutionEnum):
    NOT_DEGENERATED = "NOT_DEGENERATED"
    DEGENERATED = "DEGENERATED"
    SENSITIVE = "SENSITIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class GateEvaluationStatus(_ExecutionEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL_PASS_DEFERRED_OOS = "PARTIAL_PASS_DEFERRED_OOS"
    DEFERRED_TO_C008C_C = "DEFERRED_TO_C008C_C"


class C008CBStageStatus(_ExecutionEnum):
    READY_FOR_LOCKED_OOS = "READY_FOR_LOCKED_OOS"
    BLOCKED_BEFORE_OOS = "BLOCKED_BEFORE_OOS"


class ExperimentFailureStage(_ExecutionEnum):
    PIPELINE = "PIPELINE"
    CAUSAL_AUDIT = "CAUSAL_AUDIT"
    METRIC_EVALUATION = "METRIC_EVALUATION"
    METRIC_SOURCE_BIND = "METRIC_SOURCE_BIND"


def _schema(value: object, label: str, error_type: type[ValueError]) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise error_type(f"{label}.schema_version must equal 1")


def _text(
    value: object,
    label: str,
    error_type: type[ValueError],
    *,
    optional: bool = False,
) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value:
        raise error_type(f"{label} must be non-empty text")
    return value


def _integer(
    value: object,
    label: str,
    error_type: type[ValueError],
    *,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        raise error_type(f"{label} must be an integer >= {minimum}")
    return value


def _boolean(
    value: object,
    label: str,
    error_type: type[ValueError],
) -> bool:
    if type(value) is not bool:
        raise error_type(f"{label} must be bool")
    return value


def _texts(
    value: object,
    label: str,
    error_type: type[ValueError],
    *,
    non_empty: bool = True,
    unique: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise error_type(f"{label} must be tuple")
    if non_empty and not value:
        raise error_type(f"{label} must not be empty")
    if any(not isinstance(item, str) or not item for item in value):
        raise error_type(f"{label} must contain non-empty text")
    if unique and len(set(value)) != len(value):
        raise error_type(f"{label} must be unique")
    return value


def _objects(
    value: object,
    item_type: type,
    label: str,
    error_type: type[ValueError],
    *,
    non_empty: bool = True,
) -> tuple:
    if (
        not isinstance(value, tuple)
        or (non_empty and not value)
        or any(not isinstance(item, item_type) for item in value)
    ):
        raise error_type(f"{label} must be a {item_type.__name__} tuple")
    return value


def _decimal(
    value: object,
    label: str,
    error_type: type[ValueError],
    *,
    optional: bool = False,
) -> Decimal | None:
    if optional and value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise error_type(f"{label} must be finite Decimal")
    return value


def _parse_optional_decimal(
    value: object,
    label: str,
    error_type: type[ValueError],
) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise error_type(f"{label} must be Decimal text or null")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise error_type(f"{label} contains invalid Decimal text") from exc
    return _decimal(parsed, label, error_type, optional=True)


def _time(
    value: object,
    label: str,
    error_type: type[ValueError],
) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset().total_seconds() != 0
    ):
        raise error_type(f"{label} must be aware UTC datetime")
    return value


def _parse_time(
    value: object,
    label: str,
    error_type: type[ValueError],
) -> datetime:
    if not isinstance(value, str) or not value:
        raise error_type(f"{label} must be ISO datetime text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise error_type(f"{label} contains invalid datetime") from exc
    return _time(parsed, label, error_type)


def _exact(
    payload: object,
    cls: type,
    error_type: type[ValueError],
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise error_type(f"{cls.__name__} payload must be mapping")
    expected = {item.name for item in fields(cls)}
    if set(payload) != expected:
        missing = sorted(expected - set(payload))
        unknown = sorted(set(payload) - expected)
        raise error_type(
            f"{cls.__name__} fields mismatch missing={missing} unknown={unknown}"
        )
    return payload


def _ordered(
    payload: Mapping[str, Any],
    key: str,
    label: str,
    error_type: type[ValueError],
) -> list[Any]:
    value = payload[key]
    if not isinstance(value, list):
        raise error_type(f"{label}.{key} must be ordered list")
    return value


def _optional_enum(
    enum_type: type[Enum],
    value: object,
    label: str,
    error_type: type[ValueError],
) -> Enum | None:
    if value is None:
        return None
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise error_type(f"{label} contains invalid enum value") from exc


def _require_identity(
    instance: object,
    *,
    id_field: str,
    prefix: str,
    error_type: type[ValueError],
) -> None:
    payload = instance.to_dict()
    identity_payload = {
        key: value for key, value in payload.items() if key != id_field
    }
    require_semantic_id(
        getattr(instance, id_field),
        prefix=prefix,
        payload=identity_payload,
        field_name=id_field,
        error_type=error_type,
    )


@dataclass(frozen=True, slots=True)
class C008CBExecutionPair:
    execution_pair_id: str
    dataset_case_id: str
    variant_id: str
    partition: DatasetPartition
    scenario: SyntheticScenarioKind
    seed: int
    schedule_index: int
    source_input_payload_digest: str
    core_config_payload_digest: str
    metric_config_payload_digest: str
    deferred_to_c008c_c: bool
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-execution-pair-v1-"

    def __post_init__(self) -> None:
        error = C008CBManifestError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "execution_pair_id",
            "dataset_case_id",
            "variant_id",
            "source_input_payload_digest",
            "core_config_payload_digest",
            "metric_config_payload_digest",
        ):
            _text(getattr(self, field_name), field_name, error)
        if not isinstance(self.partition, DatasetPartition):
            raise error("partition must be DatasetPartition")
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise error("scenario must be SyntheticScenarioKind")
        _integer(self.seed, "seed", error)
        if self.seed not in (0, 1, 2, 3):
            raise error("seed must be frozen seed 0..3")
        _integer(self.schedule_index, "schedule_index", error)
        _boolean(self.deferred_to_c008c_c, "deferred_to_c008c_c", error)
        expected_partition = (
            DatasetPartition.DEVELOPMENT
            if self.seed in (0, 1)
            else DatasetPartition.VALIDATION
            if self.seed == 2
            else DatasetPartition.OOS
        )
        if self.partition is not expected_partition:
            raise error("pair partition contradicts seed")
        if self.deferred_to_c008c_c != (self.seed == 3):
            raise error("only seed=3 pairs may be deferred")
        _require_identity(
            self,
            id_field="execution_pair_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_pair_id": self.execution_pair_id,
            "dataset_case_id": self.dataset_case_id,
            "variant_id": self.variant_id,
            "partition": self.partition.value,
            "scenario": self.scenario.value,
            "seed": self.seed,
            "schedule_index": self.schedule_index,
            "source_input_payload_digest": self.source_input_payload_digest,
            "core_config_payload_digest": self.core_config_payload_digest,
            "metric_config_payload_digest": self.metric_config_payload_digest,
            "deferred_to_c008c_c": self.deferred_to_c008c_c,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBManifestError)
        try:
            return cls(
                execution_pair_id=data["execution_pair_id"],
                dataset_case_id=data["dataset_case_id"],
                variant_id=data["variant_id"],
                partition=DatasetPartition(data["partition"]),
                scenario=SyntheticScenarioKind(data["scenario"]),
                seed=data["seed"],
                schedule_index=data["schedule_index"],
                source_input_payload_digest=data[
                    "source_input_payload_digest"
                ],
                core_config_payload_digest=data[
                    "core_config_payload_digest"
                ],
                metric_config_payload_digest=data[
                    "metric_config_payload_digest"
                ],
                deferred_to_c008c_c=data["deferred_to_c008c_c"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBManifestError(
                "invalid serialized C008CBExecutionPair"
            ) from exc


@dataclass(frozen=True, slots=True)
class C008CBExecutionManifest:
    execution_manifest_id: str
    repository_base_commit: str
    frozen_execution_base_commit: str
    core_reference_commit: str
    baseline_id: str
    dataset_manifest_id: str
    experiment_plan_id: str
    protected_source_manifest_id: str
    gate_definition_ids: tuple[str, ...]
    variant_ids: tuple[str, ...]
    frozen_case_ids: tuple[str, ...]
    executable_case_ids: tuple[str, ...]
    deferred_oos_case_ids: tuple[str, ...]
    execution_pairs: tuple[C008CBExecutionPair, ...]
    deferred_oos_pairs: tuple[C008CBExecutionPair, ...]
    variant_replay_sample_ids: tuple[str, ...]
    baseline_replay_sample_ids: tuple[str, ...]
    deferred_baseline_replay_sample_ids: tuple[str, ...]
    fixed_cutoff_case_ids: tuple[str, ...]
    deferred_fixed_cutoff_case_ids: tuple[str, ...]
    execution_schedule_digest: str
    variant_replay_schedule_digest: str
    baseline_replay_schedule_digest: str
    fixed_cutoff_schedule_digest: str
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-execution-manifest-v1-"

    def __post_init__(self) -> None:
        error = C008CBManifestError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "execution_manifest_id",
            "baseline_id",
            "dataset_manifest_id",
            "experiment_plan_id",
            "protected_source_manifest_id",
            "execution_schedule_digest",
            "variant_replay_schedule_digest",
            "baseline_replay_schedule_digest",
            "fixed_cutoff_schedule_digest",
        ):
            _text(getattr(self, field_name), field_name, error)
        if self.repository_base_commit != REPOSITORY_BASE_COMMIT:
            raise error("repository_base_commit authority mismatch")
        if self.frozen_execution_base_commit != FROZEN_EXECUTION_BASE_COMMIT:
            raise error("frozen_execution_base_commit authority mismatch")
        if self.core_reference_commit != CORE_REFERENCE_COMMIT:
            raise error("core_reference_commit authority mismatch")
        for field_name, count in (
            ("gate_definition_ids", 27),
            ("variant_ids", 26),
            ("frozen_case_ids", 20),
            ("executable_case_ids", 15),
            ("deferred_oos_case_ids", 5),
            ("variant_replay_sample_ids", 125),
            ("baseline_replay_sample_ids", 15),
            ("deferred_baseline_replay_sample_ids", 5),
            ("fixed_cutoff_case_ids", 15),
            ("deferred_fixed_cutoff_case_ids", 5),
        ):
            values = _texts(
                getattr(self, field_name),
                field_name,
                error,
                unique=True,
            )
            if len(values) != count:
                raise error(f"{field_name} must contain exactly {count} values")
        _objects(
            self.execution_pairs,
            C008CBExecutionPair,
            "execution_pairs",
            error,
        )
        _objects(
            self.deferred_oos_pairs,
            C008CBExecutionPair,
            "deferred_oos_pairs",
            error,
        )
        if len(self.execution_pairs) != 390:
            raise error("execution_pairs must contain exactly 390 pairs")
        if len(self.deferred_oos_pairs) != 130:
            raise error("deferred_oos_pairs must contain exactly 130 pairs")
        all_pairs = (*self.execution_pairs, *self.deferred_oos_pairs)
        pair_ids = tuple(item.execution_pair_id for item in all_pairs)
        if len(set(pair_ids)) != 520:
            raise error("all 520 execution pair IDs must be unique")
        if tuple(item.schedule_index for item in self.execution_pairs) != tuple(
            range(390)
        ):
            raise error("B execution pair order must be complete and frozen")
        if tuple(item.schedule_index for item in self.deferred_oos_pairs) != tuple(
            range(390, 520)
        ):
            raise error("deferred pair order must follow executable schedule")
        if any(item.deferred_to_c008c_c for item in self.execution_pairs):
            raise error("executable scope cannot contain deferred OOS pair")
        if any(
            not item.deferred_to_c008c_c for item in self.deferred_oos_pairs
        ):
            raise error("all seed=3 pairs must be deferred")
        if set(self.executable_case_ids) & set(self.deferred_oos_case_ids):
            raise error("B and OOS case sets must be disjoint")
        if set(self.executable_case_ids) | set(
            self.deferred_oos_case_ids
        ) != set(self.frozen_case_ids):
            raise error("B and OOS case sets must exactly cover frozen cases")
        if self.fixed_cutoff_case_ids != self.executable_case_ids:
            raise error("fixed cutoff B cases must equal executable cases")
        if (
            self.deferred_fixed_cutoff_case_ids
            != self.deferred_oos_case_ids
        ):
            raise error("deferred cutoff cases must equal OOS cases")
        _texts(self.assumptions, "assumptions", error, unique=True)
        if self.execution_schedule_digest != digest(
            [item.to_dict() for item in self.execution_pairs]
        ):
            raise error("execution schedule digest mismatch")
        if self.variant_replay_schedule_digest != digest(
            list(self.variant_replay_sample_ids)
        ):
            raise error("variant replay schedule digest mismatch")
        if self.baseline_replay_schedule_digest != digest(
            {
                "executed": list(self.baseline_replay_sample_ids),
                "deferred": list(
                    self.deferred_baseline_replay_sample_ids
                ),
            }
        ):
            raise error("baseline replay schedule digest mismatch")
        if self.fixed_cutoff_schedule_digest != digest(
            {
                "executed": list(self.fixed_cutoff_case_ids),
                "deferred": list(self.deferred_fixed_cutoff_case_ids),
            }
        ):
            raise error("fixed cutoff schedule digest mismatch")
        _require_identity(
            self,
            id_field="execution_manifest_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_manifest_id": self.execution_manifest_id,
            "repository_base_commit": self.repository_base_commit,
            "frozen_execution_base_commit": (
                self.frozen_execution_base_commit
            ),
            "core_reference_commit": self.core_reference_commit,
            "baseline_id": self.baseline_id,
            "dataset_manifest_id": self.dataset_manifest_id,
            "experiment_plan_id": self.experiment_plan_id,
            "protected_source_manifest_id": (
                self.protected_source_manifest_id
            ),
            "gate_definition_ids": list(self.gate_definition_ids),
            "variant_ids": list(self.variant_ids),
            "frozen_case_ids": list(self.frozen_case_ids),
            "executable_case_ids": list(self.executable_case_ids),
            "deferred_oos_case_ids": list(self.deferred_oos_case_ids),
            "execution_pairs": [
                item.to_dict() for item in self.execution_pairs
            ],
            "deferred_oos_pairs": [
                item.to_dict() for item in self.deferred_oos_pairs
            ],
            "variant_replay_sample_ids": list(
                self.variant_replay_sample_ids
            ),
            "baseline_replay_sample_ids": list(
                self.baseline_replay_sample_ids
            ),
            "deferred_baseline_replay_sample_ids": list(
                self.deferred_baseline_replay_sample_ids
            ),
            "fixed_cutoff_case_ids": list(self.fixed_cutoff_case_ids),
            "deferred_fixed_cutoff_case_ids": list(
                self.deferred_fixed_cutoff_case_ids
            ),
            "execution_schedule_digest": self.execution_schedule_digest,
            "variant_replay_schedule_digest": (
                self.variant_replay_schedule_digest
            ),
            "baseline_replay_schedule_digest": (
                self.baseline_replay_schedule_digest
            ),
            "fixed_cutoff_schedule_digest": (
                self.fixed_cutoff_schedule_digest
            ),
            "assumptions": list(self.assumptions),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBManifestError)
        try:
            return cls(
                execution_manifest_id=data["execution_manifest_id"],
                repository_base_commit=data["repository_base_commit"],
                frozen_execution_base_commit=data[
                    "frozen_execution_base_commit"
                ],
                core_reference_commit=data["core_reference_commit"],
                baseline_id=data["baseline_id"],
                dataset_manifest_id=data["dataset_manifest_id"],
                experiment_plan_id=data["experiment_plan_id"],
                protected_source_manifest_id=data[
                    "protected_source_manifest_id"
                ],
                gate_definition_ids=tuple(
                    _ordered(data, "gate_definition_ids", cls.__name__, C008CBManifestError)
                ),
                variant_ids=tuple(
                    _ordered(data, "variant_ids", cls.__name__, C008CBManifestError)
                ),
                frozen_case_ids=tuple(
                    _ordered(data, "frozen_case_ids", cls.__name__, C008CBManifestError)
                ),
                executable_case_ids=tuple(
                    _ordered(data, "executable_case_ids", cls.__name__, C008CBManifestError)
                ),
                deferred_oos_case_ids=tuple(
                    _ordered(data, "deferred_oos_case_ids", cls.__name__, C008CBManifestError)
                ),
                execution_pairs=tuple(
                    C008CBExecutionPair.from_dict(item)
                    for item in _ordered(
                        data,
                        "execution_pairs",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                deferred_oos_pairs=tuple(
                    C008CBExecutionPair.from_dict(item)
                    for item in _ordered(
                        data,
                        "deferred_oos_pairs",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                variant_replay_sample_ids=tuple(
                    _ordered(
                        data,
                        "variant_replay_sample_ids",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                baseline_replay_sample_ids=tuple(
                    _ordered(
                        data,
                        "baseline_replay_sample_ids",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                deferred_baseline_replay_sample_ids=tuple(
                    _ordered(
                        data,
                        "deferred_baseline_replay_sample_ids",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                fixed_cutoff_case_ids=tuple(
                    _ordered(
                        data,
                        "fixed_cutoff_case_ids",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                deferred_fixed_cutoff_case_ids=tuple(
                    _ordered(
                        data,
                        "deferred_fixed_cutoff_case_ids",
                        cls.__name__,
                        C008CBManifestError,
                    )
                ),
                execution_schedule_digest=data["execution_schedule_digest"],
                variant_replay_schedule_digest=data[
                    "variant_replay_schedule_digest"
                ],
                baseline_replay_schedule_digest=data[
                    "baseline_replay_schedule_digest"
                ],
                fixed_cutoff_schedule_digest=data[
                    "fixed_cutoff_schedule_digest"
                ],
                assumptions=tuple(
                    _ordered(data, "assumptions", cls.__name__, C008CBManifestError)
                ),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBManifestError(
                "invalid serialized C008CBExecutionManifest"
            ) from exc


@dataclass(frozen=True, slots=True)
class MetricAggregateSnapshot:
    aggregate_snapshot_id: str
    metric_name: ValidationMetricName
    formula_id: str
    aggregate_status: MetricAggregateStatus
    value: Decimal | None
    eligible_count: int
    matured_count: int
    censored_count: int
    unavailable_count: int
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-metric-aggregate-snapshot-v1-"

    def __post_init__(self) -> None:
        error = C008CBCaseError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.aggregate_snapshot_id, "aggregate_snapshot_id", error)
        if not isinstance(self.metric_name, ValidationMetricName):
            raise error("metric_name must be ValidationMetricName")
        _text(self.formula_id, "formula_id", error)
        if not isinstance(self.aggregate_status, MetricAggregateStatus):
            raise error("aggregate_status must be MetricAggregateStatus")
        value = _decimal(self.value, "value", error, optional=True)
        for field_name in (
            "eligible_count",
            "matured_count",
            "censored_count",
            "unavailable_count",
        ):
            _integer(getattr(self, field_name), field_name, error)
        if self.eligible_count != (
            self.matured_count
            + self.censored_count
            + self.unavailable_count
        ):
            raise error("aggregate snapshot counts are inconsistent")
        if (
            self.aggregate_status is MetricAggregateStatus.AVAILABLE
        ) != (value is not None):
            raise error("aggregate status/value mismatch")
        _require_identity(
            self,
            id_field="aggregate_snapshot_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "aggregate_snapshot_id": self.aggregate_snapshot_id,
            "metric_name": self.metric_name.value,
            "formula_id": self.formula_id,
            "aggregate_status": self.aggregate_status.value,
            "value": None if self.value is None else str(self.value),
            "eligible_count": self.eligible_count,
            "matured_count": self.matured_count,
            "censored_count": self.censored_count,
            "unavailable_count": self.unavailable_count,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBCaseError)
        try:
            return cls(
                aggregate_snapshot_id=data["aggregate_snapshot_id"],
                metric_name=ValidationMetricName(data["metric_name"]),
                formula_id=data["formula_id"],
                aggregate_status=MetricAggregateStatus(
                    data["aggregate_status"]
                ),
                value=_parse_optional_decimal(
                    data["value"], "value", C008CBCaseError
                ),
                eligible_count=data["eligible_count"],
                matured_count=data["matured_count"],
                censored_count=data["censored_count"],
                unavailable_count=data["unavailable_count"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBCaseError(
                "invalid serialized MetricAggregateSnapshot"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentCaseResult:
    case_result_id: str
    execution_pair_id: str
    dataset_case_id: str
    variant_id: str
    experiment_kind: ExperimentKind
    level: VariantLevel
    partition: DatasetPartition
    scenario: SyntheticScenarioKind
    seed: int
    status: ExperimentCaseStatus
    source_input_payload_digest: str
    core_config_payload_digest: str
    metric_config_payload_digest: str
    run_id: str | None
    run_payload_digest: str | None
    audit_report_id: str | None
    audit_payload_digest: str | None
    audit_passed: bool | None
    metric_report_id: str | None
    metric_report_payload_digest: str | None
    aggregates: tuple[MetricAggregateSnapshot, ...]
    event_count: int
    box_episode_count: int
    matured_count: int
    censored_count: int
    unavailable_count: int
    failure_stage: ExperimentFailureStage | None
    failure_error_type: str | None
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-case-result-v1-"

    def __post_init__(self) -> None:
        error = C008CBCaseError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "case_result_id",
            "execution_pair_id",
            "dataset_case_id",
            "variant_id",
            "source_input_payload_digest",
            "core_config_payload_digest",
            "metric_config_payload_digest",
        ):
            _text(getattr(self, field_name), field_name, error)
        if not isinstance(self.experiment_kind, ExperimentKind):
            raise error("experiment_kind must be ExperimentKind")
        if not isinstance(self.level, VariantLevel):
            raise error("level must be VariantLevel")
        if not isinstance(self.partition, DatasetPartition):
            raise error("partition must be DatasetPartition")
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise error("scenario must be SyntheticScenarioKind")
        _integer(self.seed, "seed", error)
        if self.seed == 3 or self.partition is DatasetPartition.OOS:
            raise error("C-008C-B CaseResult must never contain OOS outcome")
        if not isinstance(self.status, ExperimentCaseStatus):
            raise error("status must be ExperimentCaseStatus")
        for field_name in (
            "run_id",
            "run_payload_digest",
            "audit_report_id",
            "audit_payload_digest",
            "metric_report_id",
            "metric_report_payload_digest",
            "failure_error_type",
        ):
            _text(
                getattr(self, field_name),
                field_name,
                error,
                optional=True,
            )
        if self.audit_passed is not None:
            _boolean(self.audit_passed, "audit_passed", error)
        if self.failure_stage is not None and not isinstance(
            self.failure_stage, ExperimentFailureStage
        ):
            raise error("failure_stage must be ExperimentFailureStage or None")
        _objects(
            self.aggregates,
            MetricAggregateSnapshot,
            "aggregates",
            error,
            non_empty=False,
        )
        for field_name in (
            "event_count",
            "box_episode_count",
            "matured_count",
            "censored_count",
            "unavailable_count",
        ):
            _integer(getattr(self, field_name), field_name, error)
        run_fields = (self.run_id, self.run_payload_digest)
        audit_fields = (
            self.audit_report_id,
            self.audit_payload_digest,
            self.audit_passed,
        )
        metric_fields = (
            self.metric_report_id,
            self.metric_report_payload_digest,
        )
        if self.status is ExperimentCaseStatus.PASSED:
            if (
                any(item is None for item in (*run_fields, *audit_fields, *metric_fields))
                or self.audit_passed is not True
                or len(self.aggregates) != 10
                or self.failure_stage is not None
                or self.failure_error_type is not None
            ):
                raise error("PASSED result requires complete successful payload")
        elif self.failure_stage is None or self.failure_error_type is None:
            raise error("failed result requires bounded failure metadata")
        if self.status is ExperimentCaseStatus.PIPELINE_FAILED and (
            any(item is not None for item in (*run_fields, *audit_fields, *metric_fields))
            or self.aggregates
            or self.failure_stage is not ExperimentFailureStage.PIPELINE
        ):
            raise error("PIPELINE_FAILED result contains forbidden payload")
        if self.status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED and (
            any(item is None for item in run_fields)
            or any(item is not None for item in metric_fields)
            or self.aggregates
            or self.failure_stage is not ExperimentFailureStage.CAUSAL_AUDIT
        ):
            raise error("CAUSAL_AUDIT_FAILED payload is inconsistent")
        if self.status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED and not (
            (
                all(item is None for item in audit_fields)
            )
            or (
                all(item is not None for item in audit_fields)
                and self.audit_passed is False
            )
        ):
            raise error(
                "causal audit failure must carry either no report or a "
                "complete non-passing report"
            )
        if self.status is ExperimentCaseStatus.METRIC_EVALUATION_FAILED and (
            any(item is None for item in (*run_fields, *audit_fields))
            or any(item is not None for item in metric_fields)
            or self.aggregates
            or self.audit_passed is not True
            or self.failure_stage is not ExperimentFailureStage.METRIC_EVALUATION
        ):
            raise error("METRIC_EVALUATION_FAILED payload is inconsistent")
        if self.status is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED and (
            any(item is None for item in (*run_fields, *audit_fields, *metric_fields))
            or self.audit_passed is not True
            or self.aggregates
            or self.failure_stage is not ExperimentFailureStage.METRIC_SOURCE_BIND
        ):
            raise error("METRIC_SOURCE_BIND_FAILED payload is inconsistent")
        _require_identity(
            self,
            id_field="case_result_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_result_id": self.case_result_id,
            "execution_pair_id": self.execution_pair_id,
            "dataset_case_id": self.dataset_case_id,
            "variant_id": self.variant_id,
            "experiment_kind": self.experiment_kind.value,
            "level": self.level.value,
            "partition": self.partition.value,
            "scenario": self.scenario.value,
            "seed": self.seed,
            "status": self.status.value,
            "source_input_payload_digest": self.source_input_payload_digest,
            "core_config_payload_digest": self.core_config_payload_digest,
            "metric_config_payload_digest": self.metric_config_payload_digest,
            "run_id": self.run_id,
            "run_payload_digest": self.run_payload_digest,
            "audit_report_id": self.audit_report_id,
            "audit_payload_digest": self.audit_payload_digest,
            "audit_passed": self.audit_passed,
            "metric_report_id": self.metric_report_id,
            "metric_report_payload_digest": (
                self.metric_report_payload_digest
            ),
            "aggregates": [item.to_dict() for item in self.aggregates],
            "event_count": self.event_count,
            "box_episode_count": self.box_episode_count,
            "matured_count": self.matured_count,
            "censored_count": self.censored_count,
            "unavailable_count": self.unavailable_count,
            "failure_stage": (
                None if self.failure_stage is None else self.failure_stage.value
            ),
            "failure_error_type": self.failure_error_type,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBCaseError)
        try:
            return cls(
                case_result_id=data["case_result_id"],
                execution_pair_id=data["execution_pair_id"],
                dataset_case_id=data["dataset_case_id"],
                variant_id=data["variant_id"],
                experiment_kind=ExperimentKind(data["experiment_kind"]),
                level=VariantLevel(data["level"]),
                partition=DatasetPartition(data["partition"]),
                scenario=SyntheticScenarioKind(data["scenario"]),
                seed=data["seed"],
                status=ExperimentCaseStatus(data["status"]),
                source_input_payload_digest=data[
                    "source_input_payload_digest"
                ],
                core_config_payload_digest=data[
                    "core_config_payload_digest"
                ],
                metric_config_payload_digest=data[
                    "metric_config_payload_digest"
                ],
                run_id=data["run_id"],
                run_payload_digest=data["run_payload_digest"],
                audit_report_id=data["audit_report_id"],
                audit_payload_digest=data["audit_payload_digest"],
                audit_passed=data["audit_passed"],
                metric_report_id=data["metric_report_id"],
                metric_report_payload_digest=data[
                    "metric_report_payload_digest"
                ],
                aggregates=tuple(
                    MetricAggregateSnapshot.from_dict(item)
                    for item in _ordered(
                        data, "aggregates", cls.__name__, C008CBCaseError
                    )
                ),
                event_count=data["event_count"],
                box_episode_count=data["box_episode_count"],
                matured_count=data["matured_count"],
                censored_count=data["censored_count"],
                unavailable_count=data["unavailable_count"],
                failure_stage=_optional_enum(
                    ExperimentFailureStage,
                    data["failure_stage"],
                    "failure_stage",
                    C008CBCaseError,
                ),
                failure_error_type=data["failure_error_type"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBCaseError(
                "invalid serialized ExperimentCaseResult"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentMetricDelta:
    metric_delta_id: str
    dataset_case_id: str
    partition: DatasetPartition
    scenario: SyntheticScenarioKind
    variant_id: str
    baseline_variant_id: str
    metric_name: ValidationMetricName
    formula_id: str
    baseline_aggregate_status: MetricAggregateStatus | None
    variant_aggregate_status: MetricAggregateStatus | None
    baseline_value: Decimal | None
    variant_value: Decimal | None
    absolute_delta: Decimal | None
    delta_status: MetricDeltaStatus
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-metric-delta-v1-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "metric_delta_id",
            "dataset_case_id",
            "variant_id",
            "baseline_variant_id",
            "formula_id",
        ):
            _text(getattr(self, field_name), field_name, error)
        if self.variant_id == self.baseline_variant_id:
            raise error("metric delta variant must be non-Baseline")
        if not isinstance(self.partition, DatasetPartition) or (
            self.partition is DatasetPartition.OOS
        ):
            raise error("metric delta partition must be DEVELOPMENT/VALIDATION")
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise error("scenario must be SyntheticScenarioKind")
        if not isinstance(self.metric_name, ValidationMetricName):
            raise error("metric_name must be ValidationMetricName")
        for field_name in (
            "baseline_aggregate_status",
            "variant_aggregate_status",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(
                value, MetricAggregateStatus
            ):
                raise error(
                    f"{field_name} must be MetricAggregateStatus or None"
                )
        baseline = _decimal(
            self.baseline_value,
            "baseline_value",
            error,
            optional=True,
        )
        variant = _decimal(
            self.variant_value,
            "variant_value",
            error,
            optional=True,
        )
        delta = _decimal(
            self.absolute_delta,
            "absolute_delta",
            error,
            optional=True,
        )
        if not isinstance(self.delta_status, MetricDeltaStatus):
            raise error("delta_status must be MetricDeltaStatus")
        baseline_available = (
            self.baseline_aggregate_status is MetricAggregateStatus.AVAILABLE
            and baseline is not None
        )
        variant_available = (
            self.variant_aggregate_status is MetricAggregateStatus.AVAILABLE
            and variant is not None
        )
        expected_status = (
            MetricDeltaStatus.COMPARABLE
            if baseline_available and variant_available
            else MetricDeltaStatus.BASELINE_UNAVAILABLE
            if not baseline_available and variant_available
            else MetricDeltaStatus.VARIANT_UNAVAILABLE
            if baseline_available and not variant_available
            else MetricDeltaStatus.BOTH_UNAVAILABLE
        )
        if self.delta_status is not expected_status:
            raise error("delta status contradicts aggregate availability")
        if expected_status is MetricDeltaStatus.COMPARABLE:
            if delta != variant - baseline:
                raise error("absolute_delta must equal variant minus baseline")
        elif delta is not None:
            raise error("unavailable delta must be None")
        _require_identity(
            self,
            id_field="metric_delta_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_delta_id": self.metric_delta_id,
            "dataset_case_id": self.dataset_case_id,
            "partition": self.partition.value,
            "scenario": self.scenario.value,
            "variant_id": self.variant_id,
            "baseline_variant_id": self.baseline_variant_id,
            "metric_name": self.metric_name.value,
            "formula_id": self.formula_id,
            "baseline_aggregate_status": (
                None
                if self.baseline_aggregate_status is None
                else self.baseline_aggregate_status.value
            ),
            "variant_aggregate_status": (
                None
                if self.variant_aggregate_status is None
                else self.variant_aggregate_status.value
            ),
            "baseline_value": (
                None if self.baseline_value is None else str(self.baseline_value)
            ),
            "variant_value": (
                None if self.variant_value is None else str(self.variant_value)
            ),
            "absolute_delta": (
                None if self.absolute_delta is None else str(self.absolute_delta)
            ),
            "delta_status": self.delta_status.value,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                metric_delta_id=data["metric_delta_id"],
                dataset_case_id=data["dataset_case_id"],
                partition=DatasetPartition(data["partition"]),
                scenario=SyntheticScenarioKind(data["scenario"]),
                variant_id=data["variant_id"],
                baseline_variant_id=data["baseline_variant_id"],
                metric_name=ValidationMetricName(data["metric_name"]),
                formula_id=data["formula_id"],
                baseline_aggregate_status=_optional_enum(
                    MetricAggregateStatus,
                    data["baseline_aggregate_status"],
                    "baseline_aggregate_status",
                    C008CBComparisonError,
                ),
                variant_aggregate_status=_optional_enum(
                    MetricAggregateStatus,
                    data["variant_aggregate_status"],
                    "variant_aggregate_status",
                    C008CBComparisonError,
                ),
                baseline_value=_parse_optional_decimal(
                    data["baseline_value"],
                    "baseline_value",
                    C008CBComparisonError,
                ),
                variant_value=_parse_optional_decimal(
                    data["variant_value"],
                    "variant_value",
                    C008CBComparisonError,
                ),
                absolute_delta=_parse_optional_decimal(
                    data["absolute_delta"],
                    "absolute_delta",
                    C008CBComparisonError,
                ),
                delta_status=MetricDeltaStatus(data["delta_status"]),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentMetricDelta"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentMetricDeltaSummary:
    metric_delta_summary_id: str
    partition: DatasetPartition
    variant_id: str
    baseline_variant_id: str
    metric_deltas: tuple[ExperimentMetricDelta, ...]
    comparable_count: int
    equal_count: int
    non_zero_count: int
    unavailable_count: int
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-metric-delta-summary-v1-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "metric_delta_summary_id",
            "variant_id",
            "baseline_variant_id",
        ):
            _text(getattr(self, field_name), field_name, error)
        if not isinstance(self.partition, DatasetPartition) or (
            self.partition is DatasetPartition.OOS
        ):
            raise error("delta summary partition must be B-stage partition")
        _objects(
            self.metric_deltas,
            ExperimentMetricDelta,
            "metric_deltas",
            error,
        )
        expected_case_count = (
            10
            if self.partition is DatasetPartition.DEVELOPMENT
            else 5
        )
        if len(self.metric_deltas) != expected_case_count * 10:
            raise error("delta summary must contain ten metrics per case")
        if any(
            item.partition is not self.partition
            or item.variant_id != self.variant_id
            or item.baseline_variant_id != self.baseline_variant_id
            for item in self.metric_deltas
        ):
            raise error("delta summary contains source-inconsistent delta")
        comparable = tuple(
            item
            for item in self.metric_deltas
            if item.delta_status is MetricDeltaStatus.COMPARABLE
        )
        expected = {
            "comparable_count": len(comparable),
            "equal_count": sum(
                item.absolute_delta == Decimal("0") for item in comparable
            ),
            "non_zero_count": sum(
                item.absolute_delta != Decimal("0") for item in comparable
            ),
            "unavailable_count": len(self.metric_deltas) - len(comparable),
        }
        for field_name, expected_value in expected.items():
            _integer(getattr(self, field_name), field_name, error)
            if getattr(self, field_name) != expected_value:
                raise error(f"{field_name} contradicts metric_deltas")
        _require_identity(
            self,
            id_field="metric_delta_summary_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_delta_summary_id": self.metric_delta_summary_id,
            "partition": self.partition.value,
            "variant_id": self.variant_id,
            "baseline_variant_id": self.baseline_variant_id,
            "metric_deltas": [
                item.to_dict() for item in self.metric_deltas
            ],
            "comparable_count": self.comparable_count,
            "equal_count": self.equal_count,
            "non_zero_count": self.non_zero_count,
            "unavailable_count": self.unavailable_count,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                metric_delta_summary_id=data["metric_delta_summary_id"],
                partition=DatasetPartition(data["partition"]),
                variant_id=data["variant_id"],
                baseline_variant_id=data["baseline_variant_id"],
                metric_deltas=tuple(
                    ExperimentMetricDelta.from_dict(item)
                    for item in _ordered(
                        data,
                        "metric_deltas",
                        cls.__name__,
                        C008CBComparisonError,
                    )
                ),
                comparable_count=data["comparable_count"],
                equal_count=data["equal_count"],
                non_zero_count=data["non_zero_count"],
                unavailable_count=data["unavailable_count"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentMetricDeltaSummary"
            ) from exc


@dataclass(frozen=True, slots=True)
class MetricDeltaCountSnapshot:
    metric_delta_count_id: str
    metric_name: ValidationMetricName
    comparable_count: int
    equal_count: int
    non_zero_count: int
    unavailable_count: int
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-metric-delta-count-v1-"

    def __post_init__(self) -> None:
        error = C008CBReportError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.metric_delta_count_id, "metric_delta_count_id", error)
        if not isinstance(self.metric_name, ValidationMetricName):
            raise error("metric_name must be ValidationMetricName")
        for field_name in (
            "comparable_count",
            "equal_count",
            "non_zero_count",
            "unavailable_count",
        ):
            _integer(getattr(self, field_name), field_name, error)
        if self.comparable_count != self.equal_count + self.non_zero_count:
            raise error("metric delta comparable counts are inconsistent")
        _require_identity(
            self,
            id_field="metric_delta_count_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_delta_count_id": self.metric_delta_count_id,
            "metric_name": self.metric_name.value,
            "comparable_count": self.comparable_count,
            "equal_count": self.equal_count,
            "non_zero_count": self.non_zero_count,
            "unavailable_count": self.unavailable_count,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBReportError)
        try:
            return cls(
                metric_delta_count_id=data["metric_delta_count_id"],
                metric_name=ValidationMetricName(data["metric_name"]),
                comparable_count=data["comparable_count"],
                equal_count=data["equal_count"],
                non_zero_count=data["non_zero_count"],
                unavailable_count=data["unavailable_count"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBReportError(
                "invalid serialized MetricDeltaCountSnapshot"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentVariantSummary:
    variant_summary_id: str
    partition: DatasetPartition
    variant_id: str
    executed_case_count: int
    passed_count: int
    failed_count: int
    audit_failure_count: int
    metric_failure_count: int
    metric_source_bind_failure_count: int
    metric_counts: tuple[MetricDeltaCountSnapshot, ...]
    structure_event_count: int
    box_episode_count: int
    aggregate_complete_count: int
    replay_status: ReplayComparisonStatus
    degeneration_status: DegenerationStatus
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-variant-summary-v1-"

    def __post_init__(self) -> None:
        error = C008CBReportError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.variant_summary_id, "variant_summary_id", error)
        _text(self.variant_id, "variant_id", error)
        if not isinstance(self.partition, DatasetPartition) or (
            self.partition is DatasetPartition.OOS
        ):
            raise error("variant summary partition must be B-stage")
        expected_cases = (
            10
            if self.partition is DatasetPartition.DEVELOPMENT
            else 5
        )
        for field_name in (
            "executed_case_count",
            "passed_count",
            "failed_count",
            "audit_failure_count",
            "metric_failure_count",
            "metric_source_bind_failure_count",
            "structure_event_count",
            "box_episode_count",
            "aggregate_complete_count",
        ):
            _integer(getattr(self, field_name), field_name, error)
        if (
            self.executed_case_count != expected_cases
            or self.passed_count + self.failed_count != expected_cases
            or self.aggregate_complete_count > expected_cases
        ):
            raise error("variant summary execution counts are inconsistent")
        _objects(
            self.metric_counts,
            MetricDeltaCountSnapshot,
            "metric_counts",
            error,
        )
        if len(self.metric_counts) != 10 or len(
            {item.metric_name for item in self.metric_counts}
        ) != 10:
            raise error("variant summary must contain ten metric counts")
        if not isinstance(self.replay_status, ReplayComparisonStatus):
            raise error("replay_status must be ReplayComparisonStatus")
        if not isinstance(self.degeneration_status, DegenerationStatus):
            raise error("degeneration_status must be DegenerationStatus")
        _require_identity(
            self,
            id_field="variant_summary_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "variant_summary_id": self.variant_summary_id,
            "partition": self.partition.value,
            "variant_id": self.variant_id,
            "executed_case_count": self.executed_case_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "audit_failure_count": self.audit_failure_count,
            "metric_failure_count": self.metric_failure_count,
            "metric_source_bind_failure_count": (
                self.metric_source_bind_failure_count
            ),
            "metric_counts": [
                item.to_dict() for item in self.metric_counts
            ],
            "structure_event_count": self.structure_event_count,
            "box_episode_count": self.box_episode_count,
            "aggregate_complete_count": self.aggregate_complete_count,
            "replay_status": self.replay_status.value,
            "degeneration_status": self.degeneration_status.value,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBReportError)
        try:
            return cls(
                variant_summary_id=data["variant_summary_id"],
                partition=DatasetPartition(data["partition"]),
                variant_id=data["variant_id"],
                executed_case_count=data["executed_case_count"],
                passed_count=data["passed_count"],
                failed_count=data["failed_count"],
                audit_failure_count=data["audit_failure_count"],
                metric_failure_count=data["metric_failure_count"],
                metric_source_bind_failure_count=data[
                    "metric_source_bind_failure_count"
                ],
                metric_counts=tuple(
                    MetricDeltaCountSnapshot.from_dict(item)
                    for item in _ordered(
                        data,
                        "metric_counts",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                structure_event_count=data["structure_event_count"],
                box_episode_count=data["box_episode_count"],
                aggregate_complete_count=data["aggregate_complete_count"],
                replay_status=ReplayComparisonStatus(data["replay_status"]),
                degeneration_status=DegenerationStatus(
                    data["degeneration_status"]
                ),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBReportError(
                "invalid serialized ExperimentVariantSummary"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentPartitionSummary:
    partition_summary_id: str
    partition: DatasetPartition
    variant_summaries: tuple[ExperimentVariantSummary, ...]
    execution_pair_count: int
    passed_case_count: int
    failed_case_count: int
    metric_delta_count: int
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-partition-summary-v1-"

    def __post_init__(self) -> None:
        error = C008CBReportError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.partition_summary_id, "partition_summary_id", error)
        if not isinstance(self.partition, DatasetPartition) or (
            self.partition is DatasetPartition.OOS
        ):
            raise error("partition summary must be DEVELOPMENT/VALIDATION")
        _objects(
            self.variant_summaries,
            ExperimentVariantSummary,
            "variant_summaries",
            error,
        )
        if len(self.variant_summaries) != 26 or len(
            {item.variant_id for item in self.variant_summaries}
        ) != 26:
            raise error("partition summary must contain 26 variants")
        if any(
            item.partition is not self.partition
            for item in self.variant_summaries
        ):
            raise error("partition summary contains wrong partition")
        expected_pairs = (
            260
            if self.partition is DatasetPartition.DEVELOPMENT
            else 130
        )
        expected_deltas = (
            2500
            if self.partition is DatasetPartition.DEVELOPMENT
            else 1250
        )
        for field_name in (
            "execution_pair_count",
            "passed_case_count",
            "failed_case_count",
            "metric_delta_count",
        ):
            _integer(getattr(self, field_name), field_name, error)
        if (
            self.execution_pair_count != expected_pairs
            or self.passed_case_count + self.failed_case_count != expected_pairs
            or self.metric_delta_count != expected_deltas
        ):
            raise error("partition summary counts are inconsistent")
        _require_identity(
            self,
            id_field="partition_summary_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "partition_summary_id": self.partition_summary_id,
            "partition": self.partition.value,
            "variant_summaries": [
                item.to_dict() for item in self.variant_summaries
            ],
            "execution_pair_count": self.execution_pair_count,
            "passed_case_count": self.passed_case_count,
            "failed_case_count": self.failed_case_count,
            "metric_delta_count": self.metric_delta_count,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBReportError)
        try:
            return cls(
                partition_summary_id=data["partition_summary_id"],
                partition=DatasetPartition(data["partition"]),
                variant_summaries=tuple(
                    ExperimentVariantSummary.from_dict(item)
                    for item in _ordered(
                        data,
                        "variant_summaries",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                execution_pair_count=data["execution_pair_count"],
                passed_case_count=data["passed_case_count"],
                failed_case_count=data["failed_case_count"],
                metric_delta_count=data["metric_delta_count"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBReportError(
                "invalid serialized ExperimentPartitionSummary"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentReplayComparison:
    replay_comparison_id: str
    replay_sample_id: str
    scope: str
    dataset_case_id: str
    variant_id: str
    partition: DatasetPartition
    scenario: SyntheticScenarioKind
    seed: int
    status: ReplayComparisonStatus
    batch_run_id: str | None
    batch_run_payload_digest: str | None
    replay_run_id: str | None
    replay_run_payload_digest: str | None
    comparison_audit_id: str | None
    comparison_audit_payload_digest: str | None
    batch_metric_report_id: str | None
    batch_metric_payload_digest: str | None
    replay_metric_report_id: str | None
    replay_metric_payload_digest: str | None
    full_run_payload_equal: bool
    full_metric_payload_equal: bool
    failure_error_type: str | None
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-replay-comparison-v1-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "replay_comparison_id",
            "replay_sample_id",
            "scope",
            "dataset_case_id",
            "variant_id",
        ):
            _text(getattr(self, field_name), field_name, error)
        if self.scope not in ("BASELINE", "VARIANT"):
            raise error("scope must be BASELINE or VARIANT")
        if not isinstance(self.partition, DatasetPartition) or (
            self.partition is DatasetPartition.OOS
        ):
            raise error("replay comparison cannot contain OOS outcome")
        if self.scope == "VARIANT" and (
            self.partition is not DatasetPartition.VALIDATION or self.seed != 2
        ):
            raise error("variant replay sample must be seed-2 Validation")
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise error("scenario must be SyntheticScenarioKind")
        _integer(self.seed, "seed", error)
        if not isinstance(self.status, ReplayComparisonStatus):
            raise error("status must be ReplayComparisonStatus")
        for field_name in (
            "batch_run_id",
            "batch_run_payload_digest",
            "replay_run_id",
            "replay_run_payload_digest",
            "comparison_audit_id",
            "comparison_audit_payload_digest",
            "batch_metric_report_id",
            "batch_metric_payload_digest",
            "replay_metric_report_id",
            "replay_metric_payload_digest",
            "failure_error_type",
        ):
            _text(
                getattr(self, field_name),
                field_name,
                error,
                optional=True,
            )
        _boolean(self.full_run_payload_equal, "full_run_payload_equal", error)
        _boolean(
            self.full_metric_payload_equal,
            "full_metric_payload_equal",
            error,
        )
        payload_fields = (
            self.batch_run_id,
            self.batch_run_payload_digest,
            self.replay_run_id,
            self.replay_run_payload_digest,
            self.comparison_audit_id,
            self.comparison_audit_payload_digest,
            self.batch_metric_report_id,
            self.batch_metric_payload_digest,
            self.replay_metric_report_id,
            self.replay_metric_payload_digest,
        )
        if self.status is ReplayComparisonStatus.MATCH:
            if (
                any(item is None for item in payload_fields)
                or not self.full_run_payload_equal
                or not self.full_metric_payload_equal
                or self.failure_error_type is not None
            ):
                raise error("MATCH replay requires complete equal payloads")
        elif self.status is ReplayComparisonStatus.MISMATCH:
            if (
                any(item is None for item in payload_fields)
                or (
                    self.full_run_payload_equal
                    and self.full_metric_payload_equal
                )
                or self.failure_error_type is not None
            ):
                raise error("MISMATCH replay payload is inconsistent")
        elif self.failure_error_type is None:
            raise error("EXECUTION_FAILED replay requires bounded error type")
        _require_identity(
            self,
            id_field="replay_comparison_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "replay_comparison_id": self.replay_comparison_id,
            "replay_sample_id": self.replay_sample_id,
            "scope": self.scope,
            "dataset_case_id": self.dataset_case_id,
            "variant_id": self.variant_id,
            "partition": self.partition.value,
            "scenario": self.scenario.value,
            "seed": self.seed,
            "status": self.status.value,
            "batch_run_id": self.batch_run_id,
            "batch_run_payload_digest": self.batch_run_payload_digest,
            "replay_run_id": self.replay_run_id,
            "replay_run_payload_digest": self.replay_run_payload_digest,
            "comparison_audit_id": self.comparison_audit_id,
            "comparison_audit_payload_digest": (
                self.comparison_audit_payload_digest
            ),
            "batch_metric_report_id": self.batch_metric_report_id,
            "batch_metric_payload_digest": self.batch_metric_payload_digest,
            "replay_metric_report_id": self.replay_metric_report_id,
            "replay_metric_payload_digest": (
                self.replay_metric_payload_digest
            ),
            "full_run_payload_equal": self.full_run_payload_equal,
            "full_metric_payload_equal": self.full_metric_payload_equal,
            "failure_error_type": self.failure_error_type,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                replay_comparison_id=data["replay_comparison_id"],
                replay_sample_id=data["replay_sample_id"],
                scope=data["scope"],
                dataset_case_id=data["dataset_case_id"],
                variant_id=data["variant_id"],
                partition=DatasetPartition(data["partition"]),
                scenario=SyntheticScenarioKind(data["scenario"]),
                seed=data["seed"],
                status=ReplayComparisonStatus(data["status"]),
                batch_run_id=data["batch_run_id"],
                batch_run_payload_digest=data[
                    "batch_run_payload_digest"
                ],
                replay_run_id=data["replay_run_id"],
                replay_run_payload_digest=data[
                    "replay_run_payload_digest"
                ],
                comparison_audit_id=data["comparison_audit_id"],
                comparison_audit_payload_digest=data[
                    "comparison_audit_payload_digest"
                ],
                batch_metric_report_id=data["batch_metric_report_id"],
                batch_metric_payload_digest=data[
                    "batch_metric_payload_digest"
                ],
                replay_metric_report_id=data["replay_metric_report_id"],
                replay_metric_payload_digest=data[
                    "replay_metric_payload_digest"
                ],
                full_run_payload_equal=data["full_run_payload_equal"],
                full_metric_payload_equal=data[
                    "full_metric_payload_equal"
                ],
                failure_error_type=data["failure_error_type"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentReplayComparison"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentFixedCutoffCheckpoint:
    cutoff_checkpoint_id: str
    cutoff_as_of_time: datetime
    prefix_run_payload_digest: str
    extended_run_payload_digest: str
    comparison_audit_id: str
    comparison_audit_payload_digest: str
    prefix_metric_payload_digest: str
    extended_metric_payload_digest: str
    stable: bool
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-fixed-cutoff-checkpoint-v1-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.cutoff_checkpoint_id, "cutoff_checkpoint_id", error)
        _time(self.cutoff_as_of_time, "cutoff_as_of_time", error)
        for field_name in (
            "prefix_run_payload_digest",
            "extended_run_payload_digest",
            "comparison_audit_id",
            "comparison_audit_payload_digest",
            "prefix_metric_payload_digest",
            "extended_metric_payload_digest",
        ):
            _text(getattr(self, field_name), field_name, error)
        _boolean(self.stable, "stable", error)
        _require_identity(
            self,
            id_field="cutoff_checkpoint_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "cutoff_checkpoint_id": self.cutoff_checkpoint_id,
            "cutoff_as_of_time": self.cutoff_as_of_time.isoformat(),
            "prefix_run_payload_digest": self.prefix_run_payload_digest,
            "extended_run_payload_digest": self.extended_run_payload_digest,
            "comparison_audit_id": self.comparison_audit_id,
            "comparison_audit_payload_digest": (
                self.comparison_audit_payload_digest
            ),
            "prefix_metric_payload_digest": (
                self.prefix_metric_payload_digest
            ),
            "extended_metric_payload_digest": (
                self.extended_metric_payload_digest
            ),
            "stable": self.stable,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                cutoff_checkpoint_id=data["cutoff_checkpoint_id"],
                cutoff_as_of_time=_parse_time(
                    data["cutoff_as_of_time"],
                    "cutoff_as_of_time",
                    C008CBComparisonError,
                ),
                prefix_run_payload_digest=data[
                    "prefix_run_payload_digest"
                ],
                extended_run_payload_digest=data[
                    "extended_run_payload_digest"
                ],
                comparison_audit_id=data["comparison_audit_id"],
                comparison_audit_payload_digest=data[
                    "comparison_audit_payload_digest"
                ],
                prefix_metric_payload_digest=data[
                    "prefix_metric_payload_digest"
                ],
                extended_metric_payload_digest=data[
                    "extended_metric_payload_digest"
                ],
                stable=data["stable"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentFixedCutoffCheckpoint"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentFixedCutoffComparison:
    fixed_cutoff_comparison_id: str
    dataset_case_id: str
    baseline_variant_id: str
    partition: DatasetPartition
    scenario: SyntheticScenarioKind
    seed: int
    status: FixedCutoffStatus
    checkpoints: tuple[ExperimentFixedCutoffCheckpoint, ...]
    stable_checkpoint_count: int
    rewrite_count: int
    failure_error_type: str | None
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-fixed-cutoff-comparison-v1-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "fixed_cutoff_comparison_id",
            "dataset_case_id",
            "baseline_variant_id",
        ):
            _text(getattr(self, field_name), field_name, error)
        if not isinstance(self.partition, DatasetPartition) or (
            self.partition is DatasetPartition.OOS
        ):
            raise error("fixed cutoff comparison cannot contain OOS")
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise error("scenario must be SyntheticScenarioKind")
        _integer(self.seed, "seed", error)
        if not isinstance(self.status, FixedCutoffStatus):
            raise error("status must be FixedCutoffStatus")
        _objects(
            self.checkpoints,
            ExperimentFixedCutoffCheckpoint,
            "checkpoints",
            error,
            non_empty=False,
        )
        for field_name in ("stable_checkpoint_count", "rewrite_count"):
            _integer(getattr(self, field_name), field_name, error)
        if (
            self.stable_checkpoint_count
            != sum(item.stable for item in self.checkpoints)
            or self.rewrite_count
            != sum(not item.stable for item in self.checkpoints)
        ):
            raise error("cutoff summary counts contradict checkpoints")
        _text(
            self.failure_error_type,
            "failure_error_type",
            error,
            optional=True,
        )
        if self.status is FixedCutoffStatus.STABLE and (
            not self.checkpoints
            or self.rewrite_count != 0
            or self.failure_error_type is not None
        ):
            raise error("STABLE cutoff result is inconsistent")
        if self.status is FixedCutoffStatus.REWRITE_DETECTED and (
            self.rewrite_count == 0 or self.failure_error_type is not None
        ):
            raise error("REWRITE_DETECTED requires a failed checkpoint")
        if self.status is FixedCutoffStatus.EXECUTION_FAILED and (
            self.failure_error_type is None
        ):
            raise error("EXECUTION_FAILED cutoff requires bounded error type")
        _require_identity(
            self,
            id_field="fixed_cutoff_comparison_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "fixed_cutoff_comparison_id": self.fixed_cutoff_comparison_id,
            "dataset_case_id": self.dataset_case_id,
            "baseline_variant_id": self.baseline_variant_id,
            "partition": self.partition.value,
            "scenario": self.scenario.value,
            "seed": self.seed,
            "status": self.status.value,
            "checkpoints": [
                item.to_dict() for item in self.checkpoints
            ],
            "stable_checkpoint_count": self.stable_checkpoint_count,
            "rewrite_count": self.rewrite_count,
            "failure_error_type": self.failure_error_type,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                fixed_cutoff_comparison_id=data[
                    "fixed_cutoff_comparison_id"
                ],
                dataset_case_id=data["dataset_case_id"],
                baseline_variant_id=data["baseline_variant_id"],
                partition=DatasetPartition(data["partition"]),
                scenario=SyntheticScenarioKind(data["scenario"]),
                seed=data["seed"],
                status=FixedCutoffStatus(data["status"]),
                checkpoints=tuple(
                    ExperimentFixedCutoffCheckpoint.from_dict(item)
                    for item in _ordered(
                        data,
                        "checkpoints",
                        cls.__name__,
                        C008CBComparisonError,
                    )
                ),
                stable_checkpoint_count=data["stable_checkpoint_count"],
                rewrite_count=data["rewrite_count"],
                failure_error_type=data["failure_error_type"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentFixedCutoffComparison"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDeterminismComparison:
    determinism_comparison_id: str
    execution_pair_id: str
    dataset_case_id: str
    variant_id: str
    status: ReplayComparisonStatus
    first_case_result_id: str
    second_case_result_id: str
    first_case_payload_digest: str
    second_case_payload_digest: str
    run_payload_equal: bool
    audit_payload_equal: bool
    metric_payload_equal: bool
    case_result_payload_equal: bool
    decimal_context_changed: bool
    failure_error_type: str | None
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-determinism-comparison-v1-"

    def __post_init__(self) -> None:
        error = C008CBComparisonError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "determinism_comparison_id",
            "execution_pair_id",
            "dataset_case_id",
            "variant_id",
            "first_case_result_id",
            "second_case_result_id",
            "first_case_payload_digest",
            "second_case_payload_digest",
        ):
            _text(getattr(self, field_name), field_name, error)
        if not isinstance(self.status, ReplayComparisonStatus):
            raise error("status must be ReplayComparisonStatus")
        for field_name in (
            "run_payload_equal",
            "audit_payload_equal",
            "metric_payload_equal",
            "case_result_payload_equal",
            "decimal_context_changed",
        ):
            _boolean(getattr(self, field_name), field_name, error)
        _text(
            self.failure_error_type,
            "failure_error_type",
            error,
            optional=True,
        )
        all_equal = (
            self.run_payload_equal
            and self.audit_payload_equal
            and self.metric_payload_equal
            and self.case_result_payload_equal
            and self.first_case_payload_digest
            == self.second_case_payload_digest
        )
        if self.status is ReplayComparisonStatus.MATCH and (
            not all_equal
            or not self.decimal_context_changed
            or self.failure_error_type is not None
        ):
            raise error("MATCH determinism result is inconsistent")
        if self.status is ReplayComparisonStatus.MISMATCH and (
            all_equal or self.failure_error_type is not None
        ):
            raise error("MISMATCH determinism result is inconsistent")
        if self.status is ReplayComparisonStatus.EXECUTION_FAILED and (
            self.failure_error_type is None
        ):
            raise error(
                "EXECUTION_FAILED determinism requires bounded error type"
            )
        _require_identity(
            self,
            id_field="determinism_comparison_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "determinism_comparison_id": self.determinism_comparison_id,
            "execution_pair_id": self.execution_pair_id,
            "dataset_case_id": self.dataset_case_id,
            "variant_id": self.variant_id,
            "status": self.status.value,
            "first_case_result_id": self.first_case_result_id,
            "second_case_result_id": self.second_case_result_id,
            "first_case_payload_digest": self.first_case_payload_digest,
            "second_case_payload_digest": self.second_case_payload_digest,
            "run_payload_equal": self.run_payload_equal,
            "audit_payload_equal": self.audit_payload_equal,
            "metric_payload_equal": self.metric_payload_equal,
            "case_result_payload_equal": self.case_result_payload_equal,
            "decimal_context_changed": self.decimal_context_changed,
            "failure_error_type": self.failure_error_type,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBComparisonError)
        try:
            return cls(
                determinism_comparison_id=data[
                    "determinism_comparison_id"
                ],
                execution_pair_id=data["execution_pair_id"],
                dataset_case_id=data["dataset_case_id"],
                variant_id=data["variant_id"],
                status=ReplayComparisonStatus(data["status"]),
                first_case_result_id=data["first_case_result_id"],
                second_case_result_id=data["second_case_result_id"],
                first_case_payload_digest=data[
                    "first_case_payload_digest"
                ],
                second_case_payload_digest=data[
                    "second_case_payload_digest"
                ],
                run_payload_equal=data["run_payload_equal"],
                audit_payload_equal=data["audit_payload_equal"],
                metric_payload_equal=data["metric_payload_equal"],
                case_result_payload_equal=data[
                    "case_result_payload_equal"
                ],
                decimal_context_changed=data["decimal_context_changed"],
                failure_error_type=data["failure_error_type"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBComparisonError(
                "invalid serialized ExperimentDeterminismComparison"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDegenerationFinding:
    degeneration_finding_id: str
    variant_id: str
    rule_code: str
    triggered: bool
    status: DegenerationStatus
    validation_case_ids: tuple[str, ...]
    facts: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-degeneration-finding-v1-"

    def __post_init__(self) -> None:
        error = C008CBDegenerationError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "degeneration_finding_id",
            "variant_id",
            "rule_code",
        ):
            _text(getattr(self, field_name), field_name, error)
        _boolean(self.triggered, "triggered", error)
        if not isinstance(self.status, DegenerationStatus):
            raise error("status must be DegenerationStatus")
        if self.triggered != (
            self.status is DegenerationStatus.DEGENERATED
        ):
            raise error("finding trigger/status mismatch")
        if self.status not in (
            DegenerationStatus.DEGENERATED,
            DegenerationStatus.NOT_DEGENERATED,
            DegenerationStatus.INSUFFICIENT_EVIDENCE,
        ):
            raise error("individual rule finding cannot be SENSITIVE")
        values = _texts(
            self.validation_case_ids,
            "validation_case_ids",
            error,
            unique=True,
        )
        if len(values) != 5:
            raise error("degeneration finding must bind all five Validation cases")
        _texts(self.facts, "facts", error, unique=True)
        _require_identity(
            self,
            id_field="degeneration_finding_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "degeneration_finding_id": self.degeneration_finding_id,
            "variant_id": self.variant_id,
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
                variant_id=data["variant_id"],
                rule_code=data["rule_code"],
                triggered=data["triggered"],
                status=DegenerationStatus(data["status"]),
                validation_case_ids=tuple(
                    _ordered(
                        data,
                        "validation_case_ids",
                        cls.__name__,
                        C008CBDegenerationError,
                    )
                ),
                facts=tuple(
                    _ordered(
                        data,
                        "facts",
                        cls.__name__,
                        C008CBDegenerationError,
                    )
                ),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBDegenerationError(
                "invalid serialized ExperimentDegenerationFinding"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDegenerationSummary:
    degeneration_summary_id: str
    variant_id: str
    status: DegenerationStatus
    findings: tuple[ExperimentDegenerationFinding, ...]
    triggered_rule_codes: tuple[str, ...]
    non_zero_validation_delta_count: int
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-degeneration-summary-v1-"

    def __post_init__(self) -> None:
        error = C008CBDegenerationError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.degeneration_summary_id, "degeneration_summary_id", error)
        _text(self.variant_id, "variant_id", error)
        if not isinstance(self.status, DegenerationStatus):
            raise error("status must be DegenerationStatus")
        _objects(
            self.findings,
            ExperimentDegenerationFinding,
            "findings",
            error,
        )
        if len(self.findings) != 10 or len(
            {item.rule_code for item in self.findings}
        ) != 10:
            raise error("degeneration summary must contain ten frozen rules")
        if any(item.variant_id != self.variant_id for item in self.findings):
            raise error("degeneration summary contains wrong variant")
        triggered = tuple(
            item.rule_code for item in self.findings if item.triggered
        )
        _texts(
            self.triggered_rule_codes,
            "triggered_rule_codes",
            error,
            non_empty=False,
            unique=True,
        )
        if self.triggered_rule_codes != triggered:
            raise error("triggered_rule_codes contradict findings")
        _integer(
            self.non_zero_validation_delta_count,
            "non_zero_validation_delta_count",
            error,
        )
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
            if self.non_zero_validation_delta_count > 0
            else DegenerationStatus.NOT_DEGENERATED
        )
        if self.status is not expected:
            raise error("degeneration summary status contradicts findings")
        _require_identity(
            self,
            id_field="degeneration_summary_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "degeneration_summary_id": self.degeneration_summary_id,
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
                variant_id=data["variant_id"],
                status=DegenerationStatus(data["status"]),
                findings=tuple(
                    ExperimentDegenerationFinding.from_dict(item)
                    for item in _ordered(
                        data,
                        "findings",
                        cls.__name__,
                        C008CBDegenerationError,
                    )
                ),
                triggered_rule_codes=tuple(
                    _ordered(
                        data,
                        "triggered_rule_codes",
                        cls.__name__,
                        C008CBDegenerationError,
                    )
                ),
                non_zero_validation_delta_count=data[
                    "non_zero_validation_delta_count"
                ],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBDegenerationError(
                "invalid serialized ExperimentDegenerationSummary"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentGateResult:
    gate_result_id: str
    gate_definition_id: str
    gate_code: str
    status: GateEvaluationStatus
    evidence_ids: tuple[str, ...]
    evidence_payload_digest: str
    rationale: str
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-gate-result-v1-"

    def __post_init__(self) -> None:
        error = C008CBGateError
        _schema(self.schema_version, type(self).__name__, error)
        for field_name in (
            "gate_result_id",
            "gate_definition_id",
            "gate_code",
            "evidence_payload_digest",
            "rationale",
        ):
            _text(getattr(self, field_name), field_name, error)
        if not isinstance(self.status, GateEvaluationStatus):
            raise error("status must be GateEvaluationStatus")
        _texts(
            self.evidence_ids,
            "evidence_ids",
            error,
            non_empty=False,
            unique=True,
        )
        _require_identity(
            self,
            id_field="gate_result_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "gate_result_id": self.gate_result_id,
            "gate_definition_id": self.gate_definition_id,
            "gate_code": self.gate_code,
            "status": self.status.value,
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
                gate_definition_id=data["gate_definition_id"],
                gate_code=data["gate_code"],
                status=GateEvaluationStatus(data["status"]),
                evidence_ids=tuple(
                    _ordered(
                        data,
                        "evidence_ids",
                        cls.__name__,
                        C008CBGateError,
                    )
                ),
                evidence_payload_digest=data["evidence_payload_digest"],
                rationale=data["rationale"],
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBGateError(
                "invalid serialized ExperimentGateResult"
            ) from exc


@dataclass(frozen=True, slots=True)
class C008CBRunReport:
    run_report_id: str
    execution_manifest_id: str
    repository_base_commit: str
    case_results: tuple[ExperimentCaseResult, ...]
    determinism_comparisons: tuple[
        ExperimentDeterminismComparison, ...
    ]
    metric_delta_summaries: tuple[ExperimentMetricDeltaSummary, ...]
    partition_summaries: tuple[ExperimentPartitionSummary, ...]
    replay_comparisons: tuple[ExperimentReplayComparison, ...]
    fixed_cutoff_comparisons: tuple[
        ExperimentFixedCutoffComparison, ...
    ]
    degeneration_summaries: tuple[
        ExperimentDegenerationSummary, ...
    ]
    gate_results: tuple[ExperimentGateResult, ...]
    stage_status: C008CBStageStatus
    executed_pair_count: int
    deferred_oos_pair_count: int
    passed_case_count: int
    failed_case_count: int
    deterministic_match_count: int
    deterministic_mismatch_count: int
    variant_replay_match_count: int
    baseline_replay_match_count: int
    cutoff_stable_case_count: int
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-b-run-report-v1-"

    def __post_init__(self) -> None:
        error = C008CBReportError
        _schema(self.schema_version, type(self).__name__, error)
        _text(self.run_report_id, "run_report_id", error)
        _text(self.execution_manifest_id, "execution_manifest_id", error)
        if self.repository_base_commit != REPOSITORY_BASE_COMMIT:
            raise error("run report repository base mismatch")
        _objects(
            self.case_results,
            ExperimentCaseResult,
            "case_results",
            error,
        )
        _objects(
            self.determinism_comparisons,
            ExperimentDeterminismComparison,
            "determinism_comparisons",
            error,
        )
        _objects(
            self.metric_delta_summaries,
            ExperimentMetricDeltaSummary,
            "metric_delta_summaries",
            error,
        )
        _objects(
            self.partition_summaries,
            ExperimentPartitionSummary,
            "partition_summaries",
            error,
        )
        _objects(
            self.replay_comparisons,
            ExperimentReplayComparison,
            "replay_comparisons",
            error,
        )
        _objects(
            self.fixed_cutoff_comparisons,
            ExperimentFixedCutoffComparison,
            "fixed_cutoff_comparisons",
            error,
        )
        _objects(
            self.degeneration_summaries,
            ExperimentDegenerationSummary,
            "degeneration_summaries",
            error,
        )
        _objects(
            self.gate_results,
            ExperimentGateResult,
            "gate_results",
            error,
        )
        expected_lengths = (
            (self.case_results, 390, "case_results"),
            (
                self.determinism_comparisons,
                390,
                "determinism_comparisons",
            ),
            (self.metric_delta_summaries, 50, "metric_delta_summaries"),
            (self.partition_summaries, 2, "partition_summaries"),
            (self.replay_comparisons, 140, "replay_comparisons"),
            (
                self.fixed_cutoff_comparisons,
                15,
                "fixed_cutoff_comparisons",
            ),
            (
                self.degeneration_summaries,
                25,
                "degeneration_summaries",
            ),
            (self.gate_results, 27, "gate_results"),
        )
        for values, expected, label in expected_lengths:
            if len(values) != expected:
                raise error(f"{label} must contain exactly {expected} values")
        if len(
            {item.execution_pair_id for item in self.case_results}
        ) != 390:
            raise error("case results must bind 390 unique execution pairs")
        if len(
            {
                item.execution_pair_id
                for item in self.determinism_comparisons
            }
        ) != 390:
            raise error("determinism comparisons must bind 390 unique pairs")
        if len(
            {item.replay_sample_id for item in self.replay_comparisons}
        ) != 140:
            raise error("replay sample IDs must be unique")
        if len(
            {item.dataset_case_id for item in self.fixed_cutoff_comparisons}
        ) != 15:
            raise error("fixed cutoff comparisons must bind 15 unique cases")
        if len(
            {item.variant_id for item in self.degeneration_summaries}
        ) != 25:
            raise error("degeneration summaries must bind 25 variants")
        if len({item.gate_code for item in self.gate_results}) != 27:
            raise error("gate results must bind 27 unique gate codes")
        if not isinstance(self.stage_status, C008CBStageStatus):
            raise error("stage_status must be C008CBStageStatus")
        for field_name in (
            "executed_pair_count",
            "deferred_oos_pair_count",
            "passed_case_count",
            "failed_case_count",
            "deterministic_match_count",
            "deterministic_mismatch_count",
            "variant_replay_match_count",
            "baseline_replay_match_count",
            "cutoff_stable_case_count",
        ):
            _integer(getattr(self, field_name), field_name, error)
        expected_counts = {
            "executed_pair_count": 390,
            "deferred_oos_pair_count": 130,
            "passed_case_count": sum(
                item.status is ExperimentCaseStatus.PASSED
                for item in self.case_results
            ),
            "failed_case_count": sum(
                item.status is not ExperimentCaseStatus.PASSED
                for item in self.case_results
            ),
            "deterministic_match_count": sum(
                item.status is ReplayComparisonStatus.MATCH
                for item in self.determinism_comparisons
            ),
            "deterministic_mismatch_count": sum(
                item.status is ReplayComparisonStatus.MISMATCH
                for item in self.determinism_comparisons
            ),
            "variant_replay_match_count": sum(
                item.scope == "VARIANT"
                and item.status is ReplayComparisonStatus.MATCH
                for item in self.replay_comparisons
            ),
            "baseline_replay_match_count": sum(
                item.scope == "BASELINE"
                and item.status is ReplayComparisonStatus.MATCH
                for item in self.replay_comparisons
            ),
            "cutoff_stable_case_count": sum(
                item.status is FixedCutoffStatus.STABLE
                for item in self.fixed_cutoff_comparisons
            ),
        }
        for field_name, expected_value in expected_counts.items():
            if getattr(self, field_name) != expected_value:
                raise error(f"{field_name} contradicts report members")
        has_hard_failure = (
            self.failed_case_count > 0
            or self.deterministic_match_count != 390
            or self.variant_replay_match_count != 125
            or self.baseline_replay_match_count != 15
            or self.cutoff_stable_case_count != 15
            or any(
                item.status is DegenerationStatus.DEGENERATED
                for item in self.degeneration_summaries
            )
            or any(
                item.status is GateEvaluationStatus.FAIL
                for item in self.gate_results
            )
        )
        expected_stage = (
            C008CBStageStatus.BLOCKED_BEFORE_OOS
            if has_hard_failure
            else C008CBStageStatus.READY_FOR_LOCKED_OOS
        )
        if self.stage_status is not expected_stage:
            raise error("stage status contradicts hard B-stage evidence")
        _texts(self.assumptions, "assumptions", error, unique=True)
        _require_identity(
            self,
            id_field="run_report_id",
            prefix=self._PREFIX,
            error_type=error,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "run_report_id": self.run_report_id,
            "execution_manifest_id": self.execution_manifest_id,
            "repository_base_commit": self.repository_base_commit,
            "case_results": [
                item.to_dict() for item in self.case_results
            ],
            "determinism_comparisons": [
                item.to_dict() for item in self.determinism_comparisons
            ],
            "metric_delta_summaries": [
                item.to_dict() for item in self.metric_delta_summaries
            ],
            "partition_summaries": [
                item.to_dict() for item in self.partition_summaries
            ],
            "replay_comparisons": [
                item.to_dict() for item in self.replay_comparisons
            ],
            "fixed_cutoff_comparisons": [
                item.to_dict() for item in self.fixed_cutoff_comparisons
            ],
            "degeneration_summaries": [
                item.to_dict() for item in self.degeneration_summaries
            ],
            "gate_results": [
                item.to_dict() for item in self.gate_results
            ],
            "stage_status": self.stage_status.value,
            "executed_pair_count": self.executed_pair_count,
            "deferred_oos_pair_count": self.deferred_oos_pair_count,
            "passed_case_count": self.passed_case_count,
            "failed_case_count": self.failed_case_count,
            "deterministic_match_count": self.deterministic_match_count,
            "deterministic_mismatch_count": (
                self.deterministic_mismatch_count
            ),
            "variant_replay_match_count": self.variant_replay_match_count,
            "baseline_replay_match_count": (
                self.baseline_replay_match_count
            ),
            "cutoff_stable_case_count": self.cutoff_stable_case_count,
            "assumptions": list(self.assumptions),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls, C008CBReportError)
        try:
            return cls(
                run_report_id=data["run_report_id"],
                execution_manifest_id=data["execution_manifest_id"],
                repository_base_commit=data["repository_base_commit"],
                case_results=tuple(
                    ExperimentCaseResult.from_dict(item)
                    for item in _ordered(
                        data,
                        "case_results",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                determinism_comparisons=tuple(
                    ExperimentDeterminismComparison.from_dict(item)
                    for item in _ordered(
                        data,
                        "determinism_comparisons",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                metric_delta_summaries=tuple(
                    ExperimentMetricDeltaSummary.from_dict(item)
                    for item in _ordered(
                        data,
                        "metric_delta_summaries",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                partition_summaries=tuple(
                    ExperimentPartitionSummary.from_dict(item)
                    for item in _ordered(
                        data,
                        "partition_summaries",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                replay_comparisons=tuple(
                    ExperimentReplayComparison.from_dict(item)
                    for item in _ordered(
                        data,
                        "replay_comparisons",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                fixed_cutoff_comparisons=tuple(
                    ExperimentFixedCutoffComparison.from_dict(item)
                    for item in _ordered(
                        data,
                        "fixed_cutoff_comparisons",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                degeneration_summaries=tuple(
                    ExperimentDegenerationSummary.from_dict(item)
                    for item in _ordered(
                        data,
                        "degeneration_summaries",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                gate_results=tuple(
                    ExperimentGateResult.from_dict(item)
                    for item in _ordered(
                        data,
                        "gate_results",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                stage_status=C008CBStageStatus(data["stage_status"]),
                executed_pair_count=data["executed_pair_count"],
                deferred_oos_pair_count=data["deferred_oos_pair_count"],
                passed_case_count=data["passed_case_count"],
                failed_case_count=data["failed_case_count"],
                deterministic_match_count=data[
                    "deterministic_match_count"
                ],
                deterministic_mismatch_count=data[
                    "deterministic_mismatch_count"
                ],
                variant_replay_match_count=data[
                    "variant_replay_match_count"
                ],
                baseline_replay_match_count=data[
                    "baseline_replay_match_count"
                ],
                cutoff_stable_case_count=data["cutoff_stable_case_count"],
                assumptions=tuple(
                    _ordered(
                        data,
                        "assumptions",
                        cls.__name__,
                        C008CBReportError,
                    )
                ),
                schema_version=data["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C008CBReportError(
                "invalid serialized C008CBRunReport"
            ) from exc


__all__ = [
    "CORE_REFERENCE_COMMIT",
    "FROZEN_EXECUTION_BASE_COMMIT",
    "REPOSITORY_BASE_COMMIT",
    "C008CBExecutionManifest",
    "C008CBExecutionPair",
    "C008CBRunReport",
    "C008CBStageStatus",
    "DegenerationStatus",
    "ExperimentCaseResult",
    "ExperimentCaseStatus",
    "ExperimentDegenerationFinding",
    "ExperimentDegenerationSummary",
    "ExperimentDeterminismComparison",
    "ExperimentFailureStage",
    "ExperimentFixedCutoffCheckpoint",
    "ExperimentFixedCutoffComparison",
    "ExperimentGateResult",
    "ExperimentMetricDelta",
    "ExperimentMetricDeltaSummary",
    "ExperimentPartitionSummary",
    "ExperimentReplayComparison",
    "ExperimentVariantSummary",
    "FixedCutoffStatus",
    "GateEvaluationStatus",
    "MetricAggregateSnapshot",
    "MetricDeltaCountSnapshot",
    "MetricDeltaStatus",
    "ReplayComparisonStatus",
]
