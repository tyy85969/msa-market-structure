"""Immutable public contracts for independent causal validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Self

from .errors import (
    ValidationConfigurationError,
    ValidationInputError,
    ValidationSerializationError,
)
from .identity import require_semantic_id


SCHEMA_VERSION = 1
FORMULA_STATUS_RESERVED = "RESERVED_FOR_C008B"
_MAX_TEXT_LENGTH = 512


def _exact(
    payload: Mapping[str, Any],
    name: str,
    field_names: set[str],
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValidationSerializationError(f"{name} payload must be a mapping")
    expected = {"schema_version", *field_names}
    if set(payload) != expected:
        raise ValidationSerializationError(
            f"{name} payload fields must be exactly {sorted(expected)}"
        )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValidationSerializationError(
            f"{name}.schema_version must be {SCHEMA_VERSION}"
        )
    return payload


def _schema(value: object, name: str, error: type[ValueError]) -> int:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise error(f"{name}.schema_version must be {SCHEMA_VERSION}")
    return value


def _text(
    value: object,
    field_name: str,
    error: type[ValueError],
    *,
    max_length: int = _MAX_TEXT_LENGTH,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
    ):
        raise error(
            f"{field_name} must be a non-empty string of at most "
            f"{max_length} characters"
        )
    return value


def _integer(
    value: object,
    field_name: str,
    error: type[ValueError],
    *,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        raise error(f"{field_name} must be an integer >= {minimum}")
    return value


def _boolean(
    value: object,
    field_name: str,
    error: type[ValueError],
) -> bool:
    if type(value) is not bool:
        raise error(f"{field_name} must be a bool")
    return value


def _utc_time(
    value: object,
    field_name: str,
    error: type[ValueError],
) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset().total_seconds() != 0
    ):
        raise error(f"{field_name} must be an aware UTC datetime")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationSerializationError(
            f"{field_name} must be an ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationSerializationError(
            f"{field_name} must be an ISO-8601 string"
        ) from exc
    return _utc_time(parsed, field_name, ValidationSerializationError)


def _optional_time(
    value: object,
    field_name: str,
    error: type[ValueError],
) -> datetime | None:
    if value is None:
        return None
    return _utc_time(value, field_name, error)


def _parse_optional_time(
    value: object, field_name: str
) -> datetime | None:
    if value is None:
        return None
    return _parse_time(value, field_name)


def _ordered(payload: Mapping[str, Any], name: str, field_name: str) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise ValidationSerializationError(
            f"{name}.{field_name} must be an ordered list"
        )
    return value


def _text_tuple(
    value: object,
    field_name: str,
    error: type[ValueError],
    *,
    non_empty: bool = False,
    unique: bool = False,
    max_items: int | None = None,
) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise error(f"{field_name} must be a tuple of non-empty strings")
    if non_empty and not value:
        raise error(f"{field_name} must not be empty")
    if unique and len(set(value)) != len(value):
        raise error(f"{field_name} must contain unique values")
    if max_items is not None and len(value) > max_items:
        raise error(f"{field_name} must contain at most {max_items} values")
    if any(len(item) > _MAX_TEXT_LENGTH for item in value):
        raise error(f"{field_name} contains an overlong value")
    return value


class _ValidationEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


class AuditSeverity(_ValidationEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFORMATIONAL = "INFORMATIONAL"


class CausalAuditCode(_ValidationEnum):
    FORMAL_CONTRACT_INVALID = "FORMAL_CONTRACT_INVALID"
    PROCESSING_TIME_INVALID = "PROCESSING_TIME_INVALID"
    DUPLICATE_ASOF = "DUPLICATE_ASOF"
    STAGE_FRAME_COUNT_MISMATCH = "STAGE_FRAME_COUNT_MISMATCH"
    STAGE_ASOF_MISMATCH = "STAGE_ASOF_MISMATCH"
    SCORE_SOURCE_MISMATCH = "SCORE_SOURCE_MISMATCH"
    SELECTION_SOURCE_MISMATCH = "SELECTION_SOURCE_MISMATCH"
    FUTURE_EVIDENCE = "FUTURE_EVIDENCE"
    FUTURE_CONTEXT_STATE = "FUTURE_CONTEXT_STATE"
    FUTURE_REFERENCE_BAR = "FUTURE_REFERENCE_BAR"
    ORIGIN_USED_AS_VISIBILITY = "ORIGIN_USED_AS_VISIBILITY"
    ACTIVE_BOX_ASOF_MISMATCH = "ACTIVE_BOX_ASOF_MISMATCH"
    EVENT_TIME_MISMATCH = "EVENT_TIME_MISMATCH"
    PROJECTION_TIME_MISMATCH = "PROJECTION_TIME_MISMATCH"
    EPISODE_CREATED_TIME_MISMATCH = "EPISODE_CREATED_TIME_MISMATCH"
    EVENT_LEDGER_MISMATCH = "EVENT_LEDGER_MISMATCH"
    FROZEN_LEDGER_MISMATCH = "FROZEN_LEDGER_MISMATCH"
    FROZEN_EPISODE_REACTIVATED = "FROZEN_EPISODE_REACTIVATED"
    RETAIN_PROJECTION_CHANGED = "RETAIN_PROJECTION_CHANGED"
    EPISODE_KEY_CHANGED = "EPISODE_KEY_CHANGED"
    FINAL_BUNDLE_MISMATCH = "FINAL_BUNDLE_MISMATCH"
    REPORT_COUNT_MISMATCH = "REPORT_COUNT_MISMATCH"
    SOURCE_REPLAY_MISMATCH = "SOURCE_REPLAY_MISMATCH"
    SCORE_REBUILD_MISMATCH = "SCORE_REBUILD_MISMATCH"
    ACTIVE_BOX_REBUILD_MISMATCH = "ACTIVE_BOX_REBUILD_MISMATCH"
    BATCH_REPLAY_MISMATCH = "BATCH_REPLAY_MISMATCH"
    PREFIX_REWRITE = "PREFIX_REWRITE"
    SHARED_ASOF_REWRITE = "SHARED_ASOF_REWRITE"
    UNSUPPORTED_TRADING_FIELD = "UNSUPPORTED_TRADING_FIELD"


class CausalAuditKind(_ValidationEnum):
    SINGLE_RUN = "SINGLE_RUN"
    BATCH_REPLAY = "BATCH_REPLAY"
    PREFIX_STABILITY = "PREFIX_STABILITY"
    SHARED_ASOF_STABILITY = "SHARED_ASOF_STABILITY"
    PIPELINE_CAUSALITY = "PIPELINE_CAUSALITY"


class ValidationMetricName(_ValidationEnum):
    CONFIRMATION_DELAY_BARS = "CONFIRMATION_DELAY_BARS"
    CONFIRMATION_DELAY_ATR = "CONFIRMATION_DELAY_ATR"
    FALSE_TURN_RATE = "FALSE_TURN_RATE"
    CONTINUED_BREAK_RATE = "CONTINUED_BREAK_RATE"
    TREND_CAPTURE_RATIO = "TREND_CAPTURE_RATIO"
    MFE = "MFE"
    MAE = "MAE"
    BOX_CHURN = "BOX_CHURN"
    FIRST_TOUCH_REACTION = "FIRST_TOUCH_REACTION"
    RESONANCE_LIFT = "RESONANCE_LIFT"


class ValidationMetricUnit(_ValidationEnum):
    BARS = "BARS"
    ATR = "ATR"
    RATIO = "RATIO"
    PRICE = "PRICE"
    COUNT = "COUNT"
    DIMENSIONLESS = "DIMENSIONLESS"


class ValidationMetricInterpretation(_ValidationEnum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    DESCRIPTIVE = "DESCRIPTIVE"


class SyntheticScenarioKind(_ValidationEnum):
    SINGLE_TREND = "SINGLE_TREND"
    RANGE = "RANGE"
    V_REVERSAL = "V_REVERSAL"
    FALSE_BREAK = "FALSE_BREAK"
    GAP_SHOCK = "GAP_SHOCK"


@dataclass(frozen=True, slots=True)
class CausalAuditConfig:
    warning_codes: tuple[CausalAuditCode, ...] = ()
    informational_codes: tuple[CausalAuditCode, ...] = ()
    max_object_ids: int = 8
    max_facts: int = 8
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(
            self.schema_version,
            type(self).__name__,
            ValidationConfigurationError,
        )
        for field_name in ("warning_codes", "informational_codes"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or any(
                not isinstance(item, CausalAuditCode) for item in value
            ):
                raise ValidationConfigurationError(
                    f"{field_name} must be a CausalAuditCode tuple"
                )
            if len(set(value)) != len(value):
                raise ValidationConfigurationError(
                    f"{field_name} must contain unique codes"
                )
        if set(self.warning_codes) & set(self.informational_codes):
            raise ValidationConfigurationError(
                "warning and informational codes must be disjoint"
            )
        _integer(
            self.max_object_ids,
            "max_object_ids",
            ValidationConfigurationError,
            minimum=1,
        )
        if self.max_object_ids > 8:
            raise ValidationConfigurationError(
                "max_object_ids must not exceed the bounded limit of 8"
            )
        _integer(
            self.max_facts,
            "max_facts",
            ValidationConfigurationError,
            minimum=1,
        )
        if self.max_facts > 8:
            raise ValidationConfigurationError(
                "max_facts must not exceed the bounded limit of 8"
            )
        _boolean(
            self.strict, "strict", ValidationConfigurationError
        )
        if self.strict is not True:
            raise ValidationConfigurationError(
                "CausalAuditConfig.strict must be True"
            )

    def severity_for(self, code: CausalAuditCode) -> AuditSeverity:
        if not isinstance(code, CausalAuditCode):
            raise ValidationConfigurationError(
                "severity_for code must be CausalAuditCode"
            )
        if code in self.warning_codes:
            return AuditSeverity.WARNING
        if code in self.informational_codes:
            return AuditSeverity.INFORMATIONAL
        return AuditSeverity.ERROR

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "warning_codes": [item.value for item in self.warning_codes],
            "informational_codes": [
                item.value for item in self.informational_codes
            ],
            "max_object_ids": self.max_object_ids,
            "max_facts": self.max_facts,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CausalAuditConfig:
        data = _exact(
            payload,
            cls.__name__,
            {
                "warning_codes",
                "informational_codes",
                "max_object_ids",
                "max_facts",
                "strict",
            },
        )
        try:
            return cls(
                warning_codes=tuple(
                    CausalAuditCode(item)
                    for item in _ordered(data, cls.__name__, "warning_codes")
                ),
                informational_codes=tuple(
                    CausalAuditCode(item)
                    for item in _ordered(
                        data, cls.__name__, "informational_codes"
                    )
                ),
                max_object_ids=data["max_object_ids"],
                max_facts=data["max_facts"],
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except ValidationConfigurationError as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class CausalAuditFact:
    key: str
    value: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ValidationInputError)
        _text(self.key, f"{name}.key", ValidationInputError, max_length=96)
        _text(self.value, f"{name}.value", ValidationInputError)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "key": self.key,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CausalAuditFact:
        data = _exact(payload, cls.__name__, {"key", "value"})
        try:
            return cls(
                key=data["key"],
                value=data["value"],
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class CausalAuditFinding:
    finding_id: str
    code: CausalAuditCode
    severity: AuditSeverity
    stage: str
    as_of_time: datetime | None
    object_ids: tuple[str, ...]
    facts: tuple[CausalAuditFact, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "stage": self.stage,
            "as_of_time": (
                None if self.as_of_time is None else self.as_of_time.isoformat()
            ),
            "object_ids": list(self.object_ids),
            "facts": [item.to_dict() for item in self.facts],
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ValidationInputError)
        if not isinstance(self.code, CausalAuditCode):
            raise ValidationInputError(f"{name}.code must be CausalAuditCode")
        if not isinstance(self.severity, AuditSeverity):
            raise ValidationInputError(
                f"{name}.severity must be AuditSeverity"
            )
        _text(self.stage, f"{name}.stage", ValidationInputError, max_length=96)
        object.__setattr__(
            self,
            "as_of_time",
            _optional_time(
                self.as_of_time, f"{name}.as_of_time", ValidationInputError
            ),
        )
        _text_tuple(
            self.object_ids,
            f"{name}.object_ids",
            ValidationInputError,
            non_empty=True,
            unique=True,
            max_items=8,
        )
        if not isinstance(self.facts, tuple) or any(
            not isinstance(item, CausalAuditFact) for item in self.facts
        ):
            raise ValidationInputError(
                f"{name}.facts must be a CausalAuditFact tuple"
            )
        if not self.facts or len(self.facts) > 8:
            raise ValidationInputError(
                f"{name}.facts must contain from 1 to 8 facts"
            )
        require_semantic_id(
            self.finding_id,
            prefix="causal-audit-finding-v1-",
            payload=self._identity_payload(),
            field_name="finding_id",
            error_type=ValidationInputError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "finding_id": self.finding_id,
            "code": self.code.value,
            "severity": self.severity.value,
            "stage": self.stage,
            "as_of_time": (
                None if self.as_of_time is None else self.as_of_time.isoformat()
            ),
            "object_ids": list(self.object_ids),
            "facts": [item.to_dict() for item in self.facts],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CausalAuditFinding:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                finding_id=data["finding_id"],
                code=CausalAuditCode(data["code"]),
                severity=AuditSeverity(data["severity"]),
                stage=data["stage"],
                as_of_time=_parse_optional_time(
                    data["as_of_time"], "as_of_time"
                ),
                object_ids=tuple(
                    _ordered(data, cls.__name__, "object_ids")
                ),
                facts=tuple(
                    CausalAuditFact.from_dict(item)
                    for item in _ordered(data, cls.__name__, "facts")
                ),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class CausalAuditCheckResult:
    check_result_id: str
    check_name: str
    passed: bool
    finding_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "finding_ids": list(self.finding_ids),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ValidationInputError)
        _text(
            self.check_name,
            f"{name}.check_name",
            ValidationInputError,
            max_length=96,
        )
        _boolean(self.passed, f"{name}.passed", ValidationInputError)
        _text_tuple(
            self.finding_ids,
            f"{name}.finding_ids",
            ValidationInputError,
            unique=True,
        )
        if self.passed != (not self.finding_ids):
            raise ValidationInputError(
                "check passed must equal absence of findings"
            )
        require_semantic_id(
            self.check_result_id,
            prefix="causal-audit-check-v1-",
            payload=self._identity_payload(),
            field_name="check_result_id",
            error_type=ValidationInputError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "check_result_id": self.check_result_id,
            "check_name": self.check_name,
            "passed": self.passed,
            "finding_ids": list(self.finding_ids),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> CausalAuditCheckResult:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                check_result_id=data["check_result_id"],
                check_name=data["check_name"],
                passed=data["passed"],
                finding_ids=tuple(
                    _ordered(data, cls.__name__, "finding_ids")
                ),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class CausalAuditReport:
    audit_report_id: str
    audit_kind: CausalAuditKind
    subject_ids: tuple[str, ...]
    started_as_of_time: datetime
    ended_as_of_time: datetime
    executed_checks: tuple[CausalAuditCheckResult, ...]
    findings: tuple[CausalAuditFinding, ...]
    passed: bool
    error_count: int
    warning_count: int
    informational_count: int
    config_snapshot: CausalAuditConfig
    assumptions: tuple[str, ...]
    provenance: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "audit_kind": self.audit_kind.value,
            "subject_ids": list(self.subject_ids),
            "started_as_of_time": self.started_as_of_time.isoformat(),
            "ended_as_of_time": self.ended_as_of_time.isoformat(),
            "executed_checks": [
                item.to_dict() for item in self.executed_checks
            ],
            "findings": [item.to_dict() for item in self.findings],
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "informational_count": self.informational_count,
            "config_snapshot": self.config_snapshot.to_dict(),
            "assumptions": list(self.assumptions),
            "provenance": list(self.provenance),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ValidationInputError)
        if not isinstance(self.audit_kind, CausalAuditKind):
            raise ValidationInputError(
                f"{name}.audit_kind must be CausalAuditKind"
            )
        _text_tuple(
            self.subject_ids,
            f"{name}.subject_ids",
            ValidationInputError,
            non_empty=True,
            unique=True,
        )
        start = _utc_time(
            self.started_as_of_time,
            f"{name}.started_as_of_time",
            ValidationInputError,
        )
        end = _utc_time(
            self.ended_as_of_time,
            f"{name}.ended_as_of_time",
            ValidationInputError,
        )
        if end < start:
            raise ValidationInputError(
                "ended_as_of_time cannot precede started_as_of_time"
            )
        object.__setattr__(self, "started_as_of_time", start)
        object.__setattr__(self, "ended_as_of_time", end)
        if not isinstance(self.executed_checks, tuple) or not self.executed_checks:
            raise ValidationInputError(
                "executed_checks must be a non-empty tuple"
            )
        if any(
            not isinstance(item, CausalAuditCheckResult)
            for item in self.executed_checks
        ):
            raise ValidationInputError(
                "executed_checks must contain CausalAuditCheckResult"
            )
        if not isinstance(self.findings, tuple) or any(
            not isinstance(item, CausalAuditFinding)
            for item in self.findings
        ):
            raise ValidationInputError(
                "findings must be a CausalAuditFinding tuple"
            )
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValidationInputError("finding IDs must be unique")
        referenced = tuple(
            finding_id
            for check in self.executed_checks
            for finding_id in check.finding_ids
        )
        if sorted(referenced) != sorted(finding_ids):
            raise ValidationInputError(
                "executed checks must reference every finding exactly once"
            )
        expected = {
            AuditSeverity.ERROR: sum(
                item.severity is AuditSeverity.ERROR for item in self.findings
            ),
            AuditSeverity.WARNING: sum(
                item.severity is AuditSeverity.WARNING
                for item in self.findings
            ),
            AuditSeverity.INFORMATIONAL: sum(
                item.severity is AuditSeverity.INFORMATIONAL
                for item in self.findings
            ),
        }
        _boolean(self.passed, f"{name}.passed", ValidationInputError)
        for field_name in (
            "error_count",
            "warning_count",
            "informational_count",
        ):
            _integer(
                getattr(self, field_name),
                f"{name}.{field_name}",
                ValidationInputError,
            )
        if (
            self.error_count != expected[AuditSeverity.ERROR]
            or self.warning_count != expected[AuditSeverity.WARNING]
            or self.informational_count
            != expected[AuditSeverity.INFORMATIONAL]
            or self.passed != (self.error_count == 0)
        ):
            raise ValidationInputError(
                "report pass/count facts contradict findings"
            )
        if not isinstance(self.config_snapshot, CausalAuditConfig):
            raise ValidationInputError(
                "config_snapshot must be CausalAuditConfig"
            )
        if any(
            item.severity
            is not self.config_snapshot.severity_for(item.code)
            for item in self.findings
        ):
            raise ValidationInputError(
                "finding severity contradicts config_snapshot"
            )
        _text_tuple(
            self.assumptions,
            f"{name}.assumptions",
            ValidationInputError,
            non_empty=True,
            unique=True,
        )
        _text_tuple(
            self.provenance,
            f"{name}.provenance",
            ValidationInputError,
            non_empty=True,
            unique=True,
        )
        require_semantic_id(
            self.audit_report_id,
            prefix="causal-audit-report-v1-",
            payload=self._identity_payload(),
            field_name="audit_report_id",
            error_type=ValidationInputError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "audit_report_id": self.audit_report_id,
            "audit_kind": self.audit_kind.value,
            "subject_ids": list(self.subject_ids),
            "started_as_of_time": self.started_as_of_time.isoformat(),
            "ended_as_of_time": self.ended_as_of_time.isoformat(),
            "executed_checks": [
                item.to_dict() for item in self.executed_checks
            ],
            "findings": [item.to_dict() for item in self.findings],
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "informational_count": self.informational_count,
            "config_snapshot": self.config_snapshot.to_dict(),
            "assumptions": list(self.assumptions),
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CausalAuditReport:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                audit_report_id=data["audit_report_id"],
                audit_kind=CausalAuditKind(data["audit_kind"]),
                subject_ids=tuple(
                    _ordered(data, cls.__name__, "subject_ids")
                ),
                started_as_of_time=_parse_time(
                    data["started_as_of_time"], "started_as_of_time"
                ),
                ended_as_of_time=_parse_time(
                    data["ended_as_of_time"], "ended_as_of_time"
                ),
                executed_checks=tuple(
                    CausalAuditCheckResult.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "executed_checks"
                    )
                ),
                findings=tuple(
                    CausalAuditFinding.from_dict(item)
                    for item in _ordered(data, cls.__name__, "findings")
                ),
                passed=data["passed"],
                error_count=data["error_count"],
                warning_count=data["warning_count"],
                informational_count=data["informational_count"],
                config_snapshot=CausalAuditConfig.from_dict(
                    data["config_snapshot"]
                ),
                assumptions=tuple(
                    _ordered(data, cls.__name__, "assumptions")
                ),
                provenance=tuple(
                    _ordered(data, cls.__name__, "provenance")
                ),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_definition_id: str
    name: ValidationMetricName
    unit: ValidationMetricUnit
    description: str
    interpretation: ValidationMetricInterpretation
    required_inputs: tuple[str, ...]
    formula_status: str = FORMULA_STATUS_RESERVED
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "unit": self.unit.value,
            "description": self.description,
            "interpretation": self.interpretation.value,
            "required_inputs": list(self.required_inputs),
            "formula_status": self.formula_status,
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ValidationInputError)
        if not isinstance(self.name, ValidationMetricName):
            raise ValidationInputError(
                "MetricDefinition.name must be ValidationMetricName"
            )
        if not isinstance(self.unit, ValidationMetricUnit):
            raise ValidationInputError(
                "MetricDefinition.unit must be ValidationMetricUnit"
            )
        if not isinstance(
            self.interpretation, ValidationMetricInterpretation
        ):
            raise ValidationInputError(
                "MetricDefinition.interpretation is invalid"
            )
        _text(self.description, "description", ValidationInputError)
        _text_tuple(
            self.required_inputs,
            "required_inputs",
            ValidationInputError,
            non_empty=True,
            unique=True,
        )
        if self.formula_status != FORMULA_STATUS_RESERVED:
            raise ValidationInputError(
                f"formula_status must be {FORMULA_STATUS_RESERVED}"
            )
        require_semantic_id(
            self.metric_definition_id,
            prefix="validation-metric-v1-",
            payload=self._identity_payload(),
            field_name="metric_definition_id",
            error_type=ValidationInputError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "metric_definition_id": self.metric_definition_id,
            "name": self.name.value,
            "unit": self.unit.value,
            "description": self.description,
            "interpretation": self.interpretation.value,
            "required_inputs": list(self.required_inputs),
            "formula_status": self.formula_status,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MetricDefinition:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                metric_definition_id=data["metric_definition_id"],
                name=ValidationMetricName(data["name"]),
                unit=ValidationMetricUnit(data["unit"]),
                description=data["description"],
                interpretation=ValidationMetricInterpretation(
                    data["interpretation"]
                ),
                required_inputs=tuple(
                    _ordered(data, cls.__name__, "required_inputs")
                ),
                formula_status=data["formula_status"],
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class SyntheticScenarioDescriptor:
    scenario_descriptor_id: str
    scenario_id: str
    kind: SyntheticScenarioKind
    seed: int
    symbol: str
    timeframe: str
    bar_count: int
    assumptions: tuple[str, ...]
    expected_causal_properties: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "kind": self.kind.value,
            "seed": self.seed,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bar_count": self.bar_count,
            "assumptions": list(self.assumptions),
            "expected_causal_properties": list(
                self.expected_causal_properties
            ),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ValidationInputError)
        _text(self.scenario_id, "scenario_id", ValidationInputError)
        if not isinstance(self.kind, SyntheticScenarioKind):
            raise ValidationInputError(
                "kind must be SyntheticScenarioKind"
            )
        _integer(self.seed, "seed", ValidationInputError)
        _text(self.symbol, "symbol", ValidationInputError)
        _text(self.timeframe, "timeframe", ValidationInputError)
        _integer(self.bar_count, "bar_count", ValidationInputError, minimum=1)
        _text_tuple(
            self.assumptions,
            "assumptions",
            ValidationInputError,
            non_empty=True,
            unique=True,
        )
        _text_tuple(
            self.expected_causal_properties,
            "expected_causal_properties",
            ValidationInputError,
            non_empty=True,
            unique=True,
        )
        require_semantic_id(
            self.scenario_descriptor_id,
            prefix="synthetic-scenario-v1-",
            payload=self._identity_payload(),
            field_name="scenario_descriptor_id",
            error_type=ValidationInputError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scenario_descriptor_id": self.scenario_descriptor_id,
            "scenario_id": self.scenario_id,
            "kind": self.kind.value,
            "seed": self.seed,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bar_count": self.bar_count,
            "assumptions": list(self.assumptions),
            "expected_causal_properties": list(
                self.expected_causal_properties
            ),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> SyntheticScenarioDescriptor:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        try:
            return cls(
                scenario_descriptor_id=data["scenario_descriptor_id"],
                scenario_id=data["scenario_id"],
                kind=SyntheticScenarioKind(data["kind"]),
                seed=data["seed"],
                symbol=data["symbol"],
                timeframe=data["timeframe"],
                bar_count=data["bar_count"],
                assumptions=tuple(
                    _ordered(data, cls.__name__, "assumptions")
                ),
                expected_causal_properties=tuple(
                    _ordered(
                        data,
                        cls.__name__,
                        "expected_causal_properties",
                    )
                ),
                schema_version=data["schema_version"],
            )
        except (TypeError, ValueError) as exc:
            raise ValidationSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc
