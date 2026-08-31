"""Outcome contracts owned exclusively by C-008C-C locked synthetic OOS."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, ClassVar, Self

from msa.validation.contracts import SyntheticScenarioKind, ValidationMetricName
from msa.validation.experiments.contracts import ExperimentKind, VariantLevel
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseStatus,
    ExperimentFailureStage,
    ExperimentFixedCutoffCheckpoint,
    FixedCutoffStatus,
    MetricAggregateSnapshot,
    MetricDeltaStatus,
    ReplayComparisonStatus,
)
from msa.validation.experiments.identity import semantic_id
from msa.validation.metrics import MetricAggregateStatus


SCHEMA_VERSION = 1


class C008CCContractError(ValueError):
    """Fail-closed C-008C-C outcome-contract error."""


class C008CCPartition(str, Enum):
    """The sole partition that a C-008C-C outcome may represent."""

    LOCKED_OOS = "LOCKED_OOS"


def _text(value: object, field_name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value:
        raise C008CCContractError(f"{field_name} must be non-empty text")


def _count(value: object, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise C008CCContractError(f"{field_name} must be non-negative integer")


def _boolean(value: object, field_name: str) -> None:
    if type(value) is not bool:
        raise C008CCContractError(f"{field_name} must be bool")


def _optional_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise C008CCContractError(f"{field_name} must be finite Decimal or None")
    return value


def _parse_optional_decimal(value: object, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise C008CCContractError(f"{field_name} must be Decimal text or None")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise C008CCContractError(
            f"{field_name} contains invalid Decimal text"
        ) from exc
    return _optional_decimal(parsed, field_name)


@dataclass(frozen=True, slots=True)
class C008CCCaseResult:
    """One seed-3 locked-OOS outcome, isolated from C-008C-B CaseResult."""

    case_result_id: str
    execution_pair_id: str
    dataset_case_id: str
    variant_id: str
    experiment_kind: ExperimentKind
    level: VariantLevel
    partition: C008CCPartition
    scenario: SyntheticScenarioKind
    seed: int
    execution_status: ExperimentCaseStatus
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

    _PREFIX: ClassVar[str] = "c008c-c-case-result-v1-"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise C008CCContractError("C CaseResult schema_version must be 1")
        for field_name in (
            "case_result_id",
            "execution_pair_id",
            "dataset_case_id",
            "variant_id",
            "source_input_payload_digest",
            "core_config_payload_digest",
            "metric_config_payload_digest",
        ):
            _text(getattr(self, field_name), field_name)
        if not isinstance(self.experiment_kind, ExperimentKind):
            raise C008CCContractError("experiment_kind must be ExperimentKind")
        if not isinstance(self.level, VariantLevel):
            raise C008CCContractError("level must be VariantLevel")
        if self.partition is not C008CCPartition.LOCKED_OOS:
            raise C008CCContractError("C CaseResult partition must be LOCKED_OOS")
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise C008CCContractError("scenario must be SyntheticScenarioKind")
        if type(self.seed) is not int or self.seed != 3:
            raise C008CCContractError("C CaseResult seed must be 3")
        if not isinstance(self.execution_status, ExperimentCaseStatus):
            raise C008CCContractError(
                "execution_status must be ExperimentCaseStatus"
            )
        for field_name in (
            "run_id",
            "run_payload_digest",
            "audit_report_id",
            "audit_payload_digest",
            "metric_report_id",
            "metric_report_payload_digest",
            "failure_error_type",
        ):
            _text(getattr(self, field_name), field_name, optional=True)
        if self.audit_passed is not None and type(self.audit_passed) is not bool:
            raise C008CCContractError("audit_passed must be bool or None")
        if self.failure_stage is not None and not isinstance(
            self.failure_stage, ExperimentFailureStage
        ):
            raise C008CCContractError(
                "failure_stage must be ExperimentFailureStage or None"
            )
        if not isinstance(self.aggregates, tuple) or any(
            not isinstance(item, MetricAggregateSnapshot)
            for item in self.aggregates
        ):
            raise C008CCContractError(
                "aggregates must be tuple[MetricAggregateSnapshot, ...]"
            )
        for field_name in (
            "event_count",
            "box_episode_count",
            "matured_count",
            "censored_count",
            "unavailable_count",
        ):
            _count(getattr(self, field_name), field_name)

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
        if self.execution_status is ExperimentCaseStatus.PASSED:
            if (
                any(item is None for item in (*run_fields, *audit_fields, *metric_fields))
                or self.audit_passed is not True
                or len(self.aggregates) != 10
                or self.failure_stage is not None
                or self.failure_error_type is not None
            ):
                raise C008CCContractError(
                    "PASSED C result requires complete successful OOS payload"
                )
        elif self.failure_stage is None or self.failure_error_type is None:
            raise C008CCContractError(
                "failed C result requires bounded failure metadata"
            )
        if self.execution_status is ExperimentCaseStatus.PIPELINE_FAILED and (
            any(item is not None for item in (*run_fields, *audit_fields, *metric_fields))
            or self.aggregates
            or self.failure_stage is not ExperimentFailureStage.PIPELINE
        ):
            raise C008CCContractError(
                "PIPELINE_FAILED C result contains forbidden payload"
            )
        if self.execution_status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED and (
            any(item is None for item in run_fields)
            or any(item is not None for item in metric_fields)
            or self.aggregates
            or self.failure_stage is not ExperimentFailureStage.CAUSAL_AUDIT
        ):
            raise C008CCContractError(
                "CAUSAL_AUDIT_FAILED C payload is inconsistent"
            )
        if self.execution_status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED and not (
            all(item is None for item in audit_fields)
            or (
                all(item is not None for item in audit_fields)
                and self.audit_passed is False
            )
        ):
            raise C008CCContractError(
                "C causal audit failure must carry no report or a complete failure"
            )
        if self.execution_status is ExperimentCaseStatus.METRIC_EVALUATION_FAILED and (
            any(item is None for item in (*run_fields, *audit_fields))
            or any(item is not None for item in metric_fields)
            or self.aggregates
            or self.audit_passed is not True
            or self.failure_stage is not ExperimentFailureStage.METRIC_EVALUATION
        ):
            raise C008CCContractError(
                "METRIC_EVALUATION_FAILED C payload is inconsistent"
            )
        if self.execution_status is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED and (
            any(item is None for item in (*run_fields, *audit_fields, *metric_fields))
            or self.audit_passed is not True
            or self.aggregates
            or self.failure_stage is not ExperimentFailureStage.METRIC_SOURCE_BIND
        ):
            raise C008CCContractError(
                "METRIC_SOURCE_BIND_FAILED C payload is inconsistent"
            )
        expected_id = semantic_id(self._PREFIX, self._identity_payload())
        if self.case_result_id != expected_id:
            raise C008CCContractError("C CaseResult identity is not canonical")

    @property
    def status(self) -> ExperimentCaseStatus:
        """Compatibility projection for unchanged gate logic."""

        return self.execution_status

    def _identity_payload(self) -> dict[str, object]:
        payload = self.to_dict()
        del payload["case_result_id"]
        return payload

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
            "execution_status": self.execution_status.value,
            "source_input_payload_digest": self.source_input_payload_digest,
            "core_config_payload_digest": self.core_config_payload_digest,
            "metric_config_payload_digest": self.metric_config_payload_digest,
            "run_id": self.run_id,
            "run_payload_digest": self.run_payload_digest,
            "audit_report_id": self.audit_report_id,
            "audit_payload_digest": self.audit_payload_digest,
            "audit_passed": self.audit_passed,
            "metric_report_id": self.metric_report_id,
            "metric_report_payload_digest": self.metric_report_payload_digest,
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
    def create(cls, **kwargs: object) -> Self:
        payload = {
            key: value.value if isinstance(value, Enum) else value
            for key, value in kwargs.items()
        }
        payload["aggregates"] = [
            item.to_dict() for item in kwargs.get("aggregates", ())  # type: ignore[union-attr]
        ]
        payload["failure_stage"] = (
            None
            if kwargs.get("failure_stage") is None
            else kwargs["failure_stage"].value  # type: ignore[union-attr]
        )
        return cls(
            case_result_id=semantic_id(cls._PREFIX, payload),
            **kwargs,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        expected = {item.name for item in fields(cls)}
        if set(payload) != expected:
            raise C008CCContractError("serialized C CaseResult fields are invalid")
        try:
            return cls(
                case_result_id=payload["case_result_id"],
                execution_pair_id=payload["execution_pair_id"],
                dataset_case_id=payload["dataset_case_id"],
                variant_id=payload["variant_id"],
                experiment_kind=ExperimentKind(payload["experiment_kind"]),
                level=VariantLevel(payload["level"]),
                partition=C008CCPartition(payload["partition"]),
                scenario=SyntheticScenarioKind(payload["scenario"]),
                seed=payload["seed"],
                execution_status=ExperimentCaseStatus(
                    payload["execution_status"]
                ),
                source_input_payload_digest=payload[
                    "source_input_payload_digest"
                ],
                core_config_payload_digest=payload[
                    "core_config_payload_digest"
                ],
                metric_config_payload_digest=payload[
                    "metric_config_payload_digest"
                ],
                run_id=payload["run_id"],
                run_payload_digest=payload["run_payload_digest"],
                audit_report_id=payload["audit_report_id"],
                audit_payload_digest=payload["audit_payload_digest"],
                audit_passed=payload["audit_passed"],
                metric_report_id=payload["metric_report_id"],
                metric_report_payload_digest=payload[
                    "metric_report_payload_digest"
                ],
                aggregates=tuple(
                    MetricAggregateSnapshot.from_dict(item)
                    for item in payload["aggregates"]
                ),
                event_count=payload["event_count"],
                box_episode_count=payload["box_episode_count"],
                matured_count=payload["matured_count"],
                censored_count=payload["censored_count"],
                unavailable_count=payload["unavailable_count"],
                failure_stage=(
                    None
                    if payload["failure_stage"] is None
                    else ExperimentFailureStage(payload["failure_stage"])
                ),
                failure_error_type=payload["failure_error_type"],
                schema_version=payload["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, C008CCContractError):
                raise
            raise C008CCContractError(
                "serialized C CaseResult is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class C008CCMetricDelta:
    """One descriptive locked-OOS metric delta owned by C-008C-C."""

    metric_delta_id: str
    dataset_case_id: str
    partition: C008CCPartition
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

    _PREFIX: ClassVar[str] = "c008c-c-metric-delta-v1-"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise C008CCContractError(
                "C MetricDelta schema_version must be 1"
            )
        for field_name in (
            "metric_delta_id",
            "dataset_case_id",
            "variant_id",
            "baseline_variant_id",
            "formula_id",
        ):
            _text(getattr(self, field_name), field_name)
        if self.variant_id == self.baseline_variant_id:
            raise C008CCContractError(
                "C metric delta variant must be non-Baseline"
            )
        if self.partition is not C008CCPartition.LOCKED_OOS:
            raise C008CCContractError(
                "C MetricDelta partition must be LOCKED_OOS"
            )
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise C008CCContractError("scenario must be SyntheticScenarioKind")
        if not isinstance(self.metric_name, ValidationMetricName):
            raise C008CCContractError(
                "metric_name must be ValidationMetricName"
            )
        for field_name in (
            "baseline_aggregate_status",
            "variant_aggregate_status",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(
                value, MetricAggregateStatus
            ):
                raise C008CCContractError(
                    f"{field_name} must be MetricAggregateStatus or None"
                )
        baseline = _optional_decimal(self.baseline_value, "baseline_value")
        variant = _optional_decimal(self.variant_value, "variant_value")
        delta = _optional_decimal(self.absolute_delta, "absolute_delta")
        if not isinstance(self.delta_status, MetricDeltaStatus):
            raise C008CCContractError(
                "delta_status must be MetricDeltaStatus"
            )
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
            raise C008CCContractError(
                "delta status contradicts aggregate availability"
            )
        if expected_status is MetricDeltaStatus.COMPARABLE:
            if delta != variant - baseline:
                raise C008CCContractError(
                    "absolute_delta must equal variant minus baseline"
                )
        elif delta is not None:
            raise C008CCContractError("unavailable delta must be None")
        if self.metric_delta_id != semantic_id(
            self._PREFIX, self._identity_payload()
        ):
            raise C008CCContractError(
                "C MetricDelta identity is not canonical"
            )

    def _identity_payload(self) -> dict[str, object]:
        payload = self.to_dict()
        del payload["metric_delta_id"]
        return payload

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
    def create(cls, **kwargs: object) -> Self:
        payload = {
            "dataset_case_id": kwargs["dataset_case_id"],
            "partition": kwargs["partition"].value,  # type: ignore[union-attr]
            "scenario": kwargs["scenario"].value,  # type: ignore[union-attr]
            "variant_id": kwargs["variant_id"],
            "baseline_variant_id": kwargs["baseline_variant_id"],
            "metric_name": kwargs["metric_name"].value,  # type: ignore[union-attr]
            "formula_id": kwargs["formula_id"],
            "baseline_aggregate_status": (
                None
                if kwargs["baseline_aggregate_status"] is None
                else kwargs["baseline_aggregate_status"].value  # type: ignore[union-attr]
            ),
            "variant_aggregate_status": (
                None
                if kwargs["variant_aggregate_status"] is None
                else kwargs["variant_aggregate_status"].value  # type: ignore[union-attr]
            ),
            "baseline_value": (
                None
                if kwargs["baseline_value"] is None
                else str(kwargs["baseline_value"])
            ),
            "variant_value": (
                None
                if kwargs["variant_value"] is None
                else str(kwargs["variant_value"])
            ),
            "absolute_delta": (
                None
                if kwargs["absolute_delta"] is None
                else str(kwargs["absolute_delta"])
            ),
            "delta_status": kwargs["delta_status"].value,  # type: ignore[union-attr]
            "schema_version": kwargs.get("schema_version", SCHEMA_VERSION),
        }
        return cls(
            metric_delta_id=semantic_id(cls._PREFIX, payload),
            **kwargs,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        if set(payload) != {item.name for item in fields(cls)}:
            raise C008CCContractError(
                "serialized C MetricDelta fields are invalid"
            )
        try:
            return cls(
                metric_delta_id=payload["metric_delta_id"],
                dataset_case_id=payload["dataset_case_id"],
                partition=C008CCPartition(payload["partition"]),
                scenario=SyntheticScenarioKind(payload["scenario"]),
                variant_id=payload["variant_id"],
                baseline_variant_id=payload["baseline_variant_id"],
                metric_name=ValidationMetricName(payload["metric_name"]),
                formula_id=payload["formula_id"],
                baseline_aggregate_status=(
                    None
                    if payload["baseline_aggregate_status"] is None
                    else MetricAggregateStatus(
                        payload["baseline_aggregate_status"]
                    )
                ),
                variant_aggregate_status=(
                    None
                    if payload["variant_aggregate_status"] is None
                    else MetricAggregateStatus(
                        payload["variant_aggregate_status"]
                    )
                ),
                baseline_value=_parse_optional_decimal(
                    payload["baseline_value"], "baseline_value"
                ),
                variant_value=_parse_optional_decimal(
                    payload["variant_value"], "variant_value"
                ),
                absolute_delta=_parse_optional_decimal(
                    payload["absolute_delta"], "absolute_delta"
                ),
                delta_status=MetricDeltaStatus(payload["delta_status"]),
                schema_version=payload["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, C008CCContractError):
                raise
            raise C008CCContractError(
                "serialized C MetricDelta is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class C008CCMetricDeltaSummary:
    """All 50 locked-OOS metric deltas for one non-Baseline Variant."""

    metric_delta_summary_id: str
    partition: C008CCPartition
    variant_id: str
    baseline_variant_id: str
    metric_deltas: tuple[C008CCMetricDelta, ...]
    comparable_count: int
    equal_count: int
    non_zero_count: int
    unavailable_count: int
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-c-metric-delta-summary-v1-"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise C008CCContractError(
                "C MetricDeltaSummary schema_version must be 1"
            )
        for field_name in (
            "metric_delta_summary_id",
            "variant_id",
            "baseline_variant_id",
        ):
            _text(getattr(self, field_name), field_name)
        if self.variant_id == self.baseline_variant_id:
            raise C008CCContractError(
                "C metric delta summary variant must be non-Baseline"
            )
        if self.partition is not C008CCPartition.LOCKED_OOS:
            raise C008CCContractError(
                "C MetricDeltaSummary partition must be LOCKED_OOS"
            )
        if (
            not isinstance(self.metric_deltas, tuple)
            or len(self.metric_deltas) != 50
            or any(
                not isinstance(item, C008CCMetricDelta)
                for item in self.metric_deltas
            )
        ):
            raise C008CCContractError(
                "C metric delta summary must contain 50 MetricDeltas"
            )
        if any(
            item.partition is not self.partition
            or item.variant_id != self.variant_id
            or item.baseline_variant_id != self.baseline_variant_id
            for item in self.metric_deltas
        ):
            raise C008CCContractError(
                "C metric delta summary contains source-inconsistent delta"
            )
        case_ids = {item.dataset_case_id for item in self.metric_deltas}
        metric_names = {item.metric_name for item in self.metric_deltas}
        case_metrics = {
            (item.dataset_case_id, item.metric_name)
            for item in self.metric_deltas
        }
        if (
            len(case_ids) != 5
            or len(metric_names) != 10
            or len(case_metrics) != 50
        ):
            raise C008CCContractError(
                "C metric delta summary must bind five cases x ten metrics"
            )
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
            _count(getattr(self, field_name), field_name)
            if getattr(self, field_name) != expected_value:
                raise C008CCContractError(
                    f"{field_name} contradicts metric_deltas"
                )
        if self.metric_delta_summary_id != semantic_id(
            self._PREFIX, self._identity_payload()
        ):
            raise C008CCContractError(
                "C MetricDeltaSummary identity is not canonical"
            )

    def _identity_payload(self) -> dict[str, object]:
        payload = self.to_dict()
        del payload["metric_delta_summary_id"]
        return payload

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
    def create(cls, **kwargs: object) -> Self:
        payload = {
            "partition": kwargs["partition"].value,  # type: ignore[union-attr]
            "variant_id": kwargs["variant_id"],
            "baseline_variant_id": kwargs["baseline_variant_id"],
            "metric_deltas": [
                item.to_dict()
                for item in kwargs["metric_deltas"]  # type: ignore[union-attr]
            ],
            "comparable_count": kwargs["comparable_count"],
            "equal_count": kwargs["equal_count"],
            "non_zero_count": kwargs["non_zero_count"],
            "unavailable_count": kwargs["unavailable_count"],
            "schema_version": kwargs.get("schema_version", SCHEMA_VERSION),
        }
        return cls(
            metric_delta_summary_id=semantic_id(cls._PREFIX, payload),
            **kwargs,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        if set(payload) != {item.name for item in fields(cls)}:
            raise C008CCContractError(
                "serialized C MetricDeltaSummary fields are invalid"
            )
        try:
            return cls(
                metric_delta_summary_id=payload["metric_delta_summary_id"],
                partition=C008CCPartition(payload["partition"]),
                variant_id=payload["variant_id"],
                baseline_variant_id=payload["baseline_variant_id"],
                metric_deltas=tuple(
                    C008CCMetricDelta.from_dict(item)
                    for item in payload["metric_deltas"]
                ),
                comparable_count=payload["comparable_count"],
                equal_count=payload["equal_count"],
                non_zero_count=payload["non_zero_count"],
                unavailable_count=payload["unavailable_count"],
                schema_version=payload["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, C008CCContractError):
                raise
            raise C008CCContractError(
                "serialized C MetricDeltaSummary is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class C008CCReplayComparison:
    """One seed-3 locked-OOS Replay outcome owned by C-008C-C."""

    replay_comparison_id: str
    replay_sample_id: str
    scope: str
    dataset_case_id: str
    variant_id: str
    partition: C008CCPartition
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

    _PREFIX: ClassVar[str] = "c008c-c-replay-comparison-v1-"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise C008CCContractError(
                "C ReplayComparison schema_version must be 1"
            )
        for field_name in (
            "replay_comparison_id",
            "replay_sample_id",
            "scope",
            "dataset_case_id",
            "variant_id",
        ):
            _text(getattr(self, field_name), field_name)
        if self.scope != "BASELINE":
            raise C008CCContractError("C ReplayComparison scope must be BASELINE")
        if self.partition is not C008CCPartition.LOCKED_OOS:
            raise C008CCContractError(
                "C ReplayComparison partition must be LOCKED_OOS"
            )
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise C008CCContractError("scenario must be SyntheticScenarioKind")
        if type(self.seed) is not int or self.seed != 3:
            raise C008CCContractError("C ReplayComparison seed must be 3")
        if not isinstance(self.status, ReplayComparisonStatus):
            raise C008CCContractError(
                "status must be ReplayComparisonStatus"
            )
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
            _text(getattr(self, field_name), field_name, optional=True)
        _boolean(self.full_run_payload_equal, "full_run_payload_equal")
        _boolean(self.full_metric_payload_equal, "full_metric_payload_equal")
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
                raise C008CCContractError(
                    "MATCH C ReplayComparison requires complete equal payloads"
                )
        elif self.status is ReplayComparisonStatus.MISMATCH:
            if (
                any(item is None for item in payload_fields)
                or (
                    self.full_run_payload_equal
                    and self.full_metric_payload_equal
                )
                or self.failure_error_type is not None
            ):
                raise C008CCContractError(
                    "MISMATCH C ReplayComparison payload is inconsistent"
                )
        elif self.failure_error_type is None:
            raise C008CCContractError(
                "EXECUTION_FAILED C ReplayComparison requires bounded error type"
            )
        if self.replay_comparison_id != semantic_id(
            self._PREFIX, self._identity_payload()
        ):
            raise C008CCContractError(
                "C ReplayComparison identity is not canonical"
            )

    def _identity_payload(self) -> dict[str, object]:
        payload = self.to_dict()
        del payload["replay_comparison_id"]
        return payload

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
    def create(cls, **kwargs: object) -> Self:
        payload = dict(kwargs)
        payload["partition"] = kwargs["partition"].value  # type: ignore[union-attr]
        payload["scenario"] = kwargs["scenario"].value  # type: ignore[union-attr]
        payload["status"] = kwargs["status"].value  # type: ignore[union-attr]
        return cls(
            replay_comparison_id=semantic_id(cls._PREFIX, payload),
            **kwargs,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        if set(payload) != {item.name for item in fields(cls)}:
            raise C008CCContractError(
                "serialized C ReplayComparison fields are invalid"
            )
        try:
            return cls(
                replay_comparison_id=payload["replay_comparison_id"],
                replay_sample_id=payload["replay_sample_id"],
                scope=payload["scope"],
                dataset_case_id=payload["dataset_case_id"],
                variant_id=payload["variant_id"],
                partition=C008CCPartition(payload["partition"]),
                scenario=SyntheticScenarioKind(payload["scenario"]),
                seed=payload["seed"],
                status=ReplayComparisonStatus(payload["status"]),
                batch_run_id=payload["batch_run_id"],
                batch_run_payload_digest=payload["batch_run_payload_digest"],
                replay_run_id=payload["replay_run_id"],
                replay_run_payload_digest=payload[
                    "replay_run_payload_digest"
                ],
                comparison_audit_id=payload["comparison_audit_id"],
                comparison_audit_payload_digest=payload[
                    "comparison_audit_payload_digest"
                ],
                batch_metric_report_id=payload["batch_metric_report_id"],
                batch_metric_payload_digest=payload[
                    "batch_metric_payload_digest"
                ],
                replay_metric_report_id=payload["replay_metric_report_id"],
                replay_metric_payload_digest=payload[
                    "replay_metric_payload_digest"
                ],
                full_run_payload_equal=payload["full_run_payload_equal"],
                full_metric_payload_equal=payload[
                    "full_metric_payload_equal"
                ],
                failure_error_type=payload["failure_error_type"],
                schema_version=payload["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, C008CCContractError):
                raise
            raise C008CCContractError(
                "serialized C ReplayComparison is invalid"
            ) from exc


@dataclass(frozen=True, slots=True)
class C008CCFixedCutoffComparison:
    """One seed-3 locked-OOS Fixed-Cutoff outcome owned by C-008C-C."""

    fixed_cutoff_comparison_id: str
    dataset_case_id: str
    baseline_variant_id: str
    partition: C008CCPartition
    scenario: SyntheticScenarioKind
    seed: int
    status: FixedCutoffStatus
    checkpoints: tuple[ExperimentFixedCutoffCheckpoint, ...]
    stable_checkpoint_count: int
    rewrite_count: int
    failure_error_type: str | None
    schema_version: int = SCHEMA_VERSION

    _PREFIX: ClassVar[str] = "c008c-c-fixed-cutoff-comparison-v1-"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise C008CCContractError(
                "C FixedCutoffComparison schema_version must be 1"
            )
        for field_name in (
            "fixed_cutoff_comparison_id",
            "dataset_case_id",
            "baseline_variant_id",
        ):
            _text(getattr(self, field_name), field_name)
        if self.partition is not C008CCPartition.LOCKED_OOS:
            raise C008CCContractError(
                "C FixedCutoffComparison partition must be LOCKED_OOS"
            )
        if not isinstance(self.scenario, SyntheticScenarioKind):
            raise C008CCContractError("scenario must be SyntheticScenarioKind")
        if type(self.seed) is not int or self.seed != 3:
            raise C008CCContractError(
                "C FixedCutoffComparison seed must be 3"
            )
        if not isinstance(self.status, FixedCutoffStatus):
            raise C008CCContractError("status must be FixedCutoffStatus")
        if not isinstance(self.checkpoints, tuple) or any(
            not isinstance(item, ExperimentFixedCutoffCheckpoint)
            for item in self.checkpoints
        ):
            raise C008CCContractError(
                "checkpoints must be tuple[ExperimentFixedCutoffCheckpoint, ...]"
            )
        for field_name in ("stable_checkpoint_count", "rewrite_count"):
            _count(getattr(self, field_name), field_name)
        if (
            self.stable_checkpoint_count
            != sum(item.stable for item in self.checkpoints)
            or self.rewrite_count
            != sum(not item.stable for item in self.checkpoints)
        ):
            raise C008CCContractError(
                "C FixedCutoffComparison counts contradict checkpoints"
            )
        _text(self.failure_error_type, "failure_error_type", optional=True)
        if self.status is FixedCutoffStatus.STABLE and (
            not self.checkpoints
            or self.rewrite_count != 0
            or self.failure_error_type is not None
        ):
            raise C008CCContractError(
                "STABLE C FixedCutoffComparison is inconsistent"
            )
        if self.status is FixedCutoffStatus.REWRITE_DETECTED and (
            self.rewrite_count == 0 or self.failure_error_type is not None
        ):
            raise C008CCContractError(
                "REWRITE_DETECTED C FixedCutoffComparison requires a rewrite"
            )
        if self.status is FixedCutoffStatus.EXECUTION_FAILED and (
            self.failure_error_type is None
        ):
            raise C008CCContractError(
                "EXECUTION_FAILED C FixedCutoffComparison requires bounded error type"
            )
        if self.fixed_cutoff_comparison_id != semantic_id(
            self._PREFIX, self._identity_payload()
        ):
            raise C008CCContractError(
                "C FixedCutoffComparison identity is not canonical"
            )

    def _identity_payload(self) -> dict[str, object]:
        payload = self.to_dict()
        del payload["fixed_cutoff_comparison_id"]
        return payload

    def to_dict(self) -> dict[str, object]:
        return {
            "fixed_cutoff_comparison_id": self.fixed_cutoff_comparison_id,
            "dataset_case_id": self.dataset_case_id,
            "baseline_variant_id": self.baseline_variant_id,
            "partition": self.partition.value,
            "scenario": self.scenario.value,
            "seed": self.seed,
            "status": self.status.value,
            "checkpoints": [item.to_dict() for item in self.checkpoints],
            "stable_checkpoint_count": self.stable_checkpoint_count,
            "rewrite_count": self.rewrite_count,
            "failure_error_type": self.failure_error_type,
            "schema_version": self.schema_version,
        }

    @classmethod
    def create(cls, **kwargs: object) -> Self:
        payload = dict(kwargs)
        payload["partition"] = kwargs["partition"].value  # type: ignore[union-attr]
        payload["scenario"] = kwargs["scenario"].value  # type: ignore[union-attr]
        payload["status"] = kwargs["status"].value  # type: ignore[union-attr]
        payload["checkpoints"] = [
            item.to_dict() for item in kwargs["checkpoints"]  # type: ignore[union-attr]
        ]
        return cls(
            fixed_cutoff_comparison_id=semantic_id(cls._PREFIX, payload),
            **kwargs,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        if set(payload) != {item.name for item in fields(cls)}:
            raise C008CCContractError(
                "serialized C FixedCutoffComparison fields are invalid"
            )
        try:
            return cls(
                fixed_cutoff_comparison_id=payload[
                    "fixed_cutoff_comparison_id"
                ],
                dataset_case_id=payload["dataset_case_id"],
                baseline_variant_id=payload["baseline_variant_id"],
                partition=C008CCPartition(payload["partition"]),
                scenario=SyntheticScenarioKind(payload["scenario"]),
                seed=payload["seed"],
                status=FixedCutoffStatus(payload["status"]),
                checkpoints=tuple(
                    ExperimentFixedCutoffCheckpoint.from_dict(item)
                    for item in payload["checkpoints"]
                ),
                stable_checkpoint_count=payload["stable_checkpoint_count"],
                rewrite_count=payload["rewrite_count"],
                failure_error_type=payload["failure_error_type"],
                schema_version=payload["schema_version"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, C008CCContractError):
                raise
            raise C008CCContractError(
                "serialized C FixedCutoffComparison is invalid"
            ) from exc


__all__ = [
    "C008CCCaseResult",
    "C008CCContractError",
    "C008CCFixedCutoffComparison",
    "C008CCMetricDelta",
    "C008CCMetricDeltaSummary",
    "C008CCPartition",
    "C008CCReplayComparison",
]
