"""Strict machine-readable policies frozen by the C-008C experiment plan."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Self

from .errors import (
    ExperimentGateError,
    ExperimentPlanError,
    ExperimentSerializationError,
)


SCHEMA_VERSION = 1


class GateParameterKind(str, Enum):
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    TEXT = "TEXT"
    TEXT_SEQUENCE = "TEXT_SEQUENCE"


def _schema(value: object, name: str, error: type[ValueError]) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise error(f"{name}.schema_version must equal {SCHEMA_VERSION}")


def _text(value: object, field: str, error: type[ValueError]) -> str:
    if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
        raise error(f"{field} must be non-empty single-line text")
    return value


def _texts(
    value: object,
    field: str,
    error: type[ValueError],
    *,
    non_empty: bool = True,
) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple)
        or (non_empty and not value)
        or any(
            not isinstance(item, str)
            or not item
            or "\r" in item
            or "\n" in item
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise error(f"{field} must be an ordered tuple of unique text")
    return value


def _exact(
    payload: object, name: str, names: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or any(
        not isinstance(key, str) for key in payload
    ):
        raise ExperimentSerializationError(f"{name} payload must be a mapping")
    expected = names | {"schema_version"}
    if set(payload) != expected:
        raise ExperimentSerializationError(
            f"{name} payload fields must equal {sorted(expected)}"
        )
    _schema(payload["schema_version"], name, ExperimentSerializationError)
    return payload


def _ordered(data: Mapping[str, Any], name: str, field: str) -> list[Any]:
    value = data[field]
    if not isinstance(value, list):
        raise ExperimentSerializationError(
            f"{name}.{field} must be an ordered list"
        )
    return value


@dataclass(frozen=True, slots=True)
class ExperimentGateParameter:
    name: str
    value_kind: GateParameterKind
    value: bool | int | Decimal | str | tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentGateError)
        _text(self.name, "name", ExperimentGateError)
        if not isinstance(self.value_kind, GateParameterKind):
            raise ExperimentGateError("invalid gate parameter kind")
        valid = (
            self.value_kind is GateParameterKind.BOOLEAN
            and type(self.value) is bool
        ) or (
            self.value_kind is GateParameterKind.INTEGER
            and type(self.value) is int
        ) or (
            self.value_kind is GateParameterKind.DECIMAL
            and isinstance(self.value, Decimal)
            and self.value.is_finite()
        ) or (
            self.value_kind is GateParameterKind.TEXT
            and isinstance(self.value, str)
        ) or (
            self.value_kind is GateParameterKind.TEXT_SEQUENCE
            and isinstance(self.value, tuple)
        )
        if not valid:
            raise ExperimentGateError(
                "gate parameter value does not match its declared kind"
            )
        if self.value_kind is GateParameterKind.TEXT:
            _text(self.value, "value", ExperimentGateError)
        elif self.value_kind is GateParameterKind.TEXT_SEQUENCE:
            _texts(self.value, "value", ExperimentGateError)

    def to_dict(self) -> dict[str, object]:
        value: object = self.value
        if isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, tuple):
            value = list(value)
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "value_kind": self.value_kind.value,
            "value": value,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentGateParameter:
        data = _exact(payload, cls.__name__, {"name", "value_kind", "value"})
        try:
            kind = GateParameterKind(data["value_kind"])
            raw = data["value"]
            value: bool | int | Decimal | str | tuple[str, ...]
            if kind is GateParameterKind.DECIMAL:
                if not isinstance(raw, str):
                    raise ExperimentSerializationError(
                        "Decimal gate parameter must serialize as text"
                    )
                value = Decimal(raw)
            elif kind is GateParameterKind.TEXT_SEQUENCE:
                value = tuple(_ordered(data, cls.__name__, "value"))
            else:
                value = raw
            return cls(
                data["name"],
                kind,
                value,
                data["schema_version"],
            )
        except (
            AttributeError,
            InvalidOperation,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentSampleCoverageRule:
    metric_code: str
    denominator_kind: str
    minimum_count: int
    excluded_statuses: tuple[str, ...]
    duplication_allowed: bool
    scope: str
    interpretation: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentGateError)
        for field in (
            "metric_code",
            "denominator_kind",
            "scope",
            "interpretation",
        ):
            _text(getattr(self, field), field, ExperimentGateError)
        if type(self.minimum_count) is not int or self.minimum_count < 1:
            raise ExperimentGateError("minimum_count must be a positive integer")
        _texts(
            self.excluded_statuses,
            "excluded_statuses",
            ExperimentGateError,
        )
        if type(self.duplication_allowed) is not bool:
            raise ExperimentGateError("duplication_allowed must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_code": self.metric_code,
            "denominator_kind": self.denominator_kind,
            "minimum_count": self.minimum_count,
            "excluded_statuses": list(self.excluded_statuses),
            "duplication_allowed": self.duplication_allowed,
            "scope": self.scope,
            "interpretation": self.interpretation,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentSampleCoverageRule:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["metric_code"],
                data["denominator_kind"],
                data["minimum_count"],
                tuple(_ordered(data, cls.__name__, "excluded_statuses")),
                data["duplication_allowed"],
                data["scope"],
                data["interpretation"],
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDegenerationRule:
    rule_code: str
    description: str
    parameters: tuple[ExperimentGateParameter, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentGateError)
        _text(self.rule_code, "rule_code", ExperimentGateError)
        _text(self.description, "description", ExperimentGateError)
        if not isinstance(self.parameters, tuple) or any(
            not isinstance(item, ExperimentGateParameter)
            for item in self.parameters
        ):
            raise ExperimentGateError("invalid degeneration parameters")
        names = tuple(item.name for item in self.parameters)
        if len(set(names)) != len(names):
            raise ExperimentGateError(
                "degeneration parameter names must be unique"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rule_code": self.rule_code,
            "description": self.description,
            "parameters": [item.to_dict() for item in self.parameters],
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentDegenerationRule:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["rule_code"],
                data["description"],
                tuple(
                    ExperimentGateParameter.from_dict(item)
                    for item in _ordered(data, cls.__name__, "parameters")
                ),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentGatePolicy:
    policy_code: str
    parameters: tuple[ExperimentGateParameter, ...]
    sample_coverage_rules: tuple[ExperimentSampleCoverageRule, ...]
    degeneration_rules: tuple[ExperimentDegenerationRule, ...]
    pass_condition: str
    failure_condition: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentGateError)
        _text(self.policy_code, "policy_code", ExperimentGateError)
        _text(self.pass_condition, "pass_condition", ExperimentGateError)
        _text(self.failure_condition, "failure_condition", ExperimentGateError)
        if not isinstance(self.parameters, tuple) or any(
            not isinstance(item, ExperimentGateParameter)
            for item in self.parameters
        ):
            raise ExperimentGateError("invalid gate policy parameters")
        if not isinstance(self.sample_coverage_rules, tuple) or any(
            not isinstance(item, ExperimentSampleCoverageRule)
            for item in self.sample_coverage_rules
        ):
            raise ExperimentGateError("invalid sample coverage rules")
        if not isinstance(self.degeneration_rules, tuple) or any(
            not isinstance(item, ExperimentDegenerationRule)
            for item in self.degeneration_rules
        ):
            raise ExperimentGateError("invalid degeneration rules")
        names = tuple(item.name for item in self.parameters)
        if len(set(names)) != len(names):
            raise ExperimentGateError("gate parameter names must be unique")
        metrics = tuple(
            item.metric_code for item in self.sample_coverage_rules
        )
        if len(set(metrics)) != len(metrics):
            raise ExperimentGateError("coverage metric codes must be unique")
        rules = tuple(item.rule_code for item in self.degeneration_rules)
        if len(set(rules)) != len(rules):
            raise ExperimentGateError("degeneration rule codes must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_code": self.policy_code,
            "parameters": [item.to_dict() for item in self.parameters],
            "sample_coverage_rules": [
                item.to_dict() for item in self.sample_coverage_rules
            ],
            "degeneration_rules": [
                item.to_dict() for item in self.degeneration_rules
            ],
            "pass_condition": self.pass_condition,
            "failure_condition": self.failure_condition,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentGatePolicy:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["policy_code"],
                tuple(
                    ExperimentGateParameter.from_dict(item)
                    for item in _ordered(data, cls.__name__, "parameters")
                ),
                tuple(
                    ExperimentSampleCoverageRule.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "sample_coverage_rules"
                    )
                ),
                tuple(
                    ExperimentDegenerationRule.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "degeneration_rules"
                    )
                ),
                data["pass_condition"],
                data["failure_condition"],
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentExecutionScopePolicy:
    dataset_case_ids: tuple[str, ...]
    variant_ids: tuple[str, ...]
    oos_dataset_case_ids: tuple[str, ...]
    expected_execution_pair_count: int
    all_pairs_required: bool
    oos_all_variants_required: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        _texts(self.dataset_case_ids, "dataset_case_ids", ExperimentPlanError)
        _texts(self.variant_ids, "variant_ids", ExperimentPlanError)
        _texts(
            self.oos_dataset_case_ids,
            "oos_dataset_case_ids",
            ExperimentPlanError,
        )
        if len(self.dataset_case_ids) != 20 or len(self.variant_ids) != 26:
            raise ExperimentPlanError(
                "execution scope must bind 20 cases and 26 variants"
            )
        if (
            len(self.oos_dataset_case_ids) != 5
            or not set(self.oos_dataset_case_ids).issubset(
                self.dataset_case_ids
            )
        ):
            raise ExperimentPlanError("execution scope must bind five OOS cases")
        calculated = len(self.dataset_case_ids) * len(self.variant_ids)
        if (
            type(self.expected_execution_pair_count) is not int
            or self.expected_execution_pair_count != calculated
            or calculated != 520
        ):
            raise ExperimentPlanError(
                "execution scope must contain exactly 520 pairs"
            )
        if (
            self.all_pairs_required is not True
            or self.oos_all_variants_required is not True
        ):
            raise ExperimentPlanError(
                "all pairs and all OOS variants must be required"
            )

    def execution_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (case_id, variant_id)
            for case_id in self.dataset_case_ids
            for variant_id in self.variant_ids
        )

    def variants_for_case(self, case_id: str) -> tuple[str, ...]:
        if case_id not in self.dataset_case_ids:
            raise ExperimentPlanError("case is outside execution scope")
        return self.variant_ids

    def cases_for_variant(self, variant_id: str) -> tuple[str, ...]:
        if variant_id not in self.variant_ids:
            raise ExperimentPlanError("variant is outside execution scope")
        return self.dataset_case_ids

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_case_ids": list(self.dataset_case_ids),
            "variant_ids": list(self.variant_ids),
            "oos_dataset_case_ids": list(self.oos_dataset_case_ids),
            "expected_execution_pair_count": (
                self.expected_execution_pair_count
            ),
            "all_pairs_required": self.all_pairs_required,
            "oos_all_variants_required": self.oos_all_variants_required,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentExecutionScopePolicy:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                tuple(_ordered(data, cls.__name__, "dataset_case_ids")),
                tuple(_ordered(data, cls.__name__, "variant_ids")),
                tuple(_ordered(data, cls.__name__, "oos_dataset_case_ids")),
                data["expected_execution_pair_count"],
                data["all_pairs_required"],
                data["oos_all_variants_required"],
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentReplayPolicy:
    policy_code: str
    variant_ids: tuple[str, ...]
    dataset_case_ids: tuple[str, ...]
    expected_sample_count: int
    compared_payload_kinds: tuple[str, ...]
    comparison_scope: str
    selection_frozen_before_outcomes: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        _text(self.policy_code, "policy_code", ExperimentPlanError)
        _texts(self.variant_ids, "variant_ids", ExperimentPlanError)
        _texts(self.dataset_case_ids, "dataset_case_ids", ExperimentPlanError)
        _texts(
            self.compared_payload_kinds,
            "compared_payload_kinds",
            ExperimentPlanError,
        )
        _text(self.comparison_scope, "comparison_scope", ExperimentPlanError)
        calculated = len(self.variant_ids) * len(self.dataset_case_ids)
        if (
            type(self.expected_sample_count) is not int
            or self.expected_sample_count != calculated
        ):
            raise ExperimentPlanError("replay sample count mismatch")
        if self.selection_frozen_before_outcomes is not True:
            raise ExperimentPlanError(
                "replay selection must be frozen before outcomes"
            )

    def sample_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (variant_id, case_id)
            for variant_id in self.variant_ids
            for case_id in self.dataset_case_ids
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_code": self.policy_code,
            "variant_ids": list(self.variant_ids),
            "dataset_case_ids": list(self.dataset_case_ids),
            "expected_sample_count": self.expected_sample_count,
            "compared_payload_kinds": list(self.compared_payload_kinds),
            "comparison_scope": self.comparison_scope,
            "selection_frozen_before_outcomes": (
                self.selection_frozen_before_outcomes
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentReplayPolicy:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["policy_code"],
                tuple(_ordered(data, cls.__name__, "variant_ids")),
                tuple(_ordered(data, cls.__name__, "dataset_case_ids")),
                data["expected_sample_count"],
                tuple(
                    _ordered(data, cls.__name__, "compared_payload_kinds")
                ),
                data["comparison_scope"],
                data["selection_frozen_before_outcomes"],
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentFixedCutoffPolicy:
    policy_code: str
    baseline_variant_id: str
    dataset_case_ids: tuple[str, ...]
    cutoff_scope: str
    compared_payload_kinds: tuple[str, ...]
    comparison_scope: str
    future_append_must_preserve_prefix: bool
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        _text(self.policy_code, "policy_code", ExperimentPlanError)
        _text(
            self.baseline_variant_id,
            "baseline_variant_id",
            ExperimentPlanError,
        )
        _texts(self.dataset_case_ids, "dataset_case_ids", ExperimentPlanError)
        if len(self.dataset_case_ids) != 20:
            raise ExperimentPlanError(
                "fixed-cutoff policy must bind all 20 cases"
            )
        _text(self.cutoff_scope, "cutoff_scope", ExperimentPlanError)
        _texts(
            self.compared_payload_kinds,
            "compared_payload_kinds",
            ExperimentPlanError,
        )
        _text(self.comparison_scope, "comparison_scope", ExperimentPlanError)
        if self.future_append_must_preserve_prefix is not True:
            raise ExperimentPlanError(
                "future appends must preserve fixed-cutoff payloads"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_code": self.policy_code,
            "baseline_variant_id": self.baseline_variant_id,
            "dataset_case_ids": list(self.dataset_case_ids),
            "cutoff_scope": self.cutoff_scope,
            "compared_payload_kinds": list(self.compared_payload_kinds),
            "comparison_scope": self.comparison_scope,
            "future_append_must_preserve_prefix": (
                self.future_append_must_preserve_prefix
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentFixedCutoffPolicy:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["policy_code"],
                data["baseline_variant_id"],
                tuple(_ordered(data, cls.__name__, "dataset_case_ids")),
                data["cutoff_scope"],
                tuple(
                    _ordered(data, cls.__name__, "compared_payload_kinds")
                ),
                data["comparison_scope"],
                data["future_append_must_preserve_prefix"],
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


__all__ = [
    "ExperimentDegenerationRule",
    "ExperimentExecutionScopePolicy",
    "ExperimentFixedCutoffPolicy",
    "ExperimentGateParameter",
    "ExperimentGatePolicy",
    "ExperimentReplayPolicy",
    "ExperimentSampleCoverageRule",
    "GateParameterKind",
]
