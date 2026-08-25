"""Outcome contracts owned exclusively by C-008C-C locked synthetic OOS."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, ClassVar, Self

from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.experiments.contracts import ExperimentKind, VariantLevel
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseStatus,
    ExperimentFailureStage,
    MetricAggregateSnapshot,
)
from msa.validation.experiments.identity import semantic_id


SCHEMA_VERSION = 1


class C008CCContractError(ValueError):
    """Fail-closed C-008C-C outcome-contract error."""


class C008CCPartition(str, Enum):
    """The sole partition that a C-008C-C CaseResult may represent."""

    LOCKED_OOS = "LOCKED_OOS"


def _text(value: object, field_name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value:
        raise C008CCContractError(f"{field_name} must be non-empty text")


def _count(value: object, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise C008CCContractError(f"{field_name} must be non-negative integer")


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


__all__ = [
    "C008CCCaseResult",
    "C008CCContractError",
    "C008CCPartition",
]
