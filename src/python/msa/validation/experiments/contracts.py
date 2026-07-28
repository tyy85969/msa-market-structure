"""Immutable public contracts for the predeclared C-008C experiment plan."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Self

from msa.data import Timeframe
from msa.reference import (
    core_alpha_v1_config,
    core_alpha_v1_profile,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)
from msa.research.msa_core import MSACoreConfig
from msa.research.msa_core.contracts import validate_source_input
from msa.research.resonance import ResonanceFrameInput
from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.metrics.contracts import StructuralMetricConfig

from .errors import (
    ExperimentConfigurationError,
    ExperimentDatasetError,
    ExperimentGateError,
    ExperimentPlanError,
    ExperimentProtectedSourceError,
    ExperimentSerializationError,
)
from .identity import digest, require_semantic_id
from .policy_contracts import (
    ExperimentExecutionScopePolicy,
    ExperimentFixedCutoffPolicy,
    ExperimentGatePolicy,
    ExperimentReplayPolicy,
)


SCHEMA_VERSION = 1
EXECUTION_BASE_COMMIT = "6f4ebef19164156728438b480867660db3b1cd65"
CORE_REFERENCE_COMMIT = "d72c18f7994afd506e6ecf044571ccffbc695631"


class _ExperimentEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


class ExperimentKind(_ExperimentEnum):
    BASELINE = "BASELINE"
    MODEL_SENSITIVITY = "MODEL_SENSITIVITY"
    METRIC_SENSITIVITY = "METRIC_SENSITIVITY"
    ABLATION = "ABLATION"
    INCREMENT = "INCREMENT"
    OOS_BASELINE = "OOS_BASELINE"
    OOS_VARIANT = "OOS_VARIANT"
    DETERMINISM = "DETERMINISM"
    REPLAY_PARITY = "REPLAY_PARITY"


class DatasetPartition(_ExperimentEnum):
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    OOS = "OOS"


class ParameterAxisKind(_ExperimentEnum):
    MODEL = "MODEL"
    METRIC = "METRIC"


class VariantLevel(_ExperimentEnum):
    LOW = "LOW"
    BASELINE = "BASELINE"
    HIGH = "HIGH"
    NEUTRALIZED = "NEUTRALIZED"
    INCREMENT = "INCREMENT"


class AblationSupportStatus(_ExperimentEnum):
    SUPPORTED_BY_PUBLIC_CONFIG = "SUPPORTED_BY_PUBLIC_CONFIG"
    UNSUPPORTED_BY_PUBLIC_CONFIG = "UNSUPPORTED_BY_PUBLIC_CONFIG"


class GateSeverity(_ExperimentEnum):
    HARD = "HARD"
    INFORMATIONAL = "INFORMATIONAL"


class RealMarketOOSStatus(_ExperimentEnum):
    NOT_RUN_NO_APPROVED_DATASET = "NOT_RUN_NO_APPROVED_DATASET"
    APPROVED_DATASET_AVAILABLE_NOT_RUN = (
        "APPROVED_DATASET_AVAILABLE_NOT_RUN"
    )


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


def _roundtrip(
    value: object,
    expected: type[Any],
    field: str,
    error: type[ValueError],
) -> Any:
    if not isinstance(value, expected):
        raise error(f"{field} has an invalid formal type")
    try:
        payload = value.to_dict()
        restored = expected.from_dict(payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise error(f"{field} is not formally valid") from exc
    if restored != value or restored.to_dict() != payload:
        raise error(f"{field} must round-trip exactly")
    return value


def _ids(
    values: tuple[Any, ...],
    field: str,
    identity: str,
    error: type[ValueError],
) -> tuple[str, ...]:
    try:
        result = tuple(getattr(item, identity) for item in values)
    except (AttributeError, TypeError) as exc:
        raise error(f"{field} contains an invalid item") from exc
    if any(not isinstance(item, str) or not item for item in result):
        raise error(f"{field} contains an invalid identity")
    if len(set(result)) != len(result):
        raise error(f"{field} identities must be unique")
    return result


@dataclass(frozen=True, slots=True)
class CoreExperimentBaseline:
    baseline_id: str
    execution_base_commit: str
    core_reference_commit: str
    core_profile_semantic_id: str
    core_profile_id: str
    core_profile_version: str
    core_config_payload_digest: str
    core_config_snapshot: MSACoreConfig
    metric_config_payload_digest: str
    metric_config_snapshot: StructuralMetricConfig
    metric_definition_ids: tuple[str, ...]
    metric_formula_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    provenance: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {k: v for k, v in self.to_dict().items() if k != "baseline_id"}

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ExperimentConfigurationError)
        for field in (
            "baseline_id",
            "execution_base_commit",
            "core_reference_commit",
            "core_profile_semantic_id",
            "core_profile_id",
            "core_profile_version",
            "core_config_payload_digest",
            "metric_config_payload_digest",
        ):
            _text(getattr(self, field), field, ExperimentConfigurationError)
        if self.execution_base_commit != EXECUTION_BASE_COMMIT:
            raise ExperimentConfigurationError("unauthorized execution base")
        profile = validate_core_alpha_v1_profile(core_alpha_v1_profile())
        if (
            self.core_reference_commit != profile.reference_commit_sha
            or self.core_profile_semantic_id != profile.profile_semantic_id
            or self.core_profile_id != profile.profile_id
            or self.core_profile_version != profile.profile_version
        ):
            raise ExperimentConfigurationError("profile authority mismatch")
        validate_core_alpha_v1_config(self.core_config_snapshot)
        if self.core_config_snapshot != profile.core_config:
            raise ExperimentConfigurationError(
                "Core snapshot must come from the authorized Profile"
            )
        if self.core_config_payload_digest != digest(
            self.core_config_snapshot.to_dict()
        ):
            raise ExperimentConfigurationError("Core snapshot digest mismatch")
        _roundtrip(
            self.metric_config_snapshot,
            StructuralMetricConfig,
            "metric_config_snapshot",
            ExperimentConfigurationError,
        )
        if self.metric_config_snapshot != StructuralMetricConfig():
            raise ExperimentConfigurationError(
                "metric snapshot must be the formal default"
            )
        if self.metric_config_payload_digest != digest(
            self.metric_config_snapshot.to_dict()
        ):
            raise ExperimentConfigurationError("metric snapshot digest mismatch")
        from msa.validation.metric_registry import default_metric_registry
        from msa.validation.metrics.formula_registry import (
            default_metric_formula_registry,
        )

        if self.metric_definition_ids != tuple(
            item.metric_definition_id for item in default_metric_registry()
        ):
            raise ExperimentConfigurationError("metric definition order mismatch")
        if self.metric_formula_ids != tuple(
            item.metric_formula_id
            for item in default_metric_formula_registry()
        ):
            raise ExperimentConfigurationError("metric formula order mismatch")
        _texts(self.assumptions, "assumptions", ExperimentConfigurationError)
        _texts(self.provenance, "provenance", ExperimentConfigurationError)
        require_semantic_id(
            self.baseline_id,
            prefix="c008c-core-experiment-baseline-v1-",
            payload=self._identity_payload(),
            field_name="baseline_id",
            error_type=ExperimentConfigurationError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "baseline_id": self.baseline_id,
            "execution_base_commit": self.execution_base_commit,
            "core_reference_commit": self.core_reference_commit,
            "core_profile_semantic_id": self.core_profile_semantic_id,
            "core_profile_id": self.core_profile_id,
            "core_profile_version": self.core_profile_version,
            "core_config_payload_digest": self.core_config_payload_digest,
            "core_config_snapshot": self.core_config_snapshot.to_dict(),
            "metric_config_payload_digest": self.metric_config_payload_digest,
            "metric_config_snapshot": self.metric_config_snapshot.to_dict(),
            "metric_definition_ids": list(self.metric_definition_ids),
            "metric_formula_ids": list(self.metric_formula_ids),
            "assumptions": list(self.assumptions),
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CoreExperimentBaseline:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                baseline_id=data["baseline_id"],
                execution_base_commit=data["execution_base_commit"],
                core_reference_commit=data["core_reference_commit"],
                core_profile_semantic_id=data["core_profile_semantic_id"],
                core_profile_id=data["core_profile_id"],
                core_profile_version=data["core_profile_version"],
                core_config_payload_digest=data["core_config_payload_digest"],
                core_config_snapshot=MSACoreConfig.from_dict(
                    data["core_config_snapshot"]
                ),
                metric_config_payload_digest=data[
                    "metric_config_payload_digest"
                ],
                metric_config_snapshot=StructuralMetricConfig.from_dict(
                    data["metric_config_snapshot"]
                ),
                metric_definition_ids=tuple(
                    _ordered(data, cls.__name__, "metric_definition_ids")
                ),
                metric_formula_ids=tuple(
                    _ordered(data, cls.__name__, "metric_formula_ids")
                ),
                assumptions=tuple(_ordered(data, cls.__name__, "assumptions")),
                provenance=tuple(_ordered(data, cls.__name__, "provenance")),
                schema_version=data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentParameterValue:
    level: VariantLevel
    value: Decimal | int
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentConfigurationError)
        if not isinstance(self.level, VariantLevel):
            raise ExperimentConfigurationError("invalid parameter value level")
        if isinstance(self.value, bool) or not isinstance(
            self.value, (Decimal, int)
        ):
            raise ExperimentConfigurationError(
                "parameter value must be Decimal or integer"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "level": self.level.value,
            "value": str(self.value) if isinstance(self.value, Decimal) else self.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentParameterValue:
        data = _exact(payload, cls.__name__, {"level", "value"})
        try:
            raw = data["value"]
            value: Decimal | int
            if isinstance(raw, str):
                value = Decimal(raw)
            elif type(raw) is int:
                value = raw
            else:
                raise ExperimentSerializationError("invalid parameter value")
            return cls(
                VariantLevel(data["level"]), value, data["schema_version"]
            )
        except (TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentParameterAxis:
    axis_id: str
    code: str
    kind: ParameterAxisKind
    field_path: str
    values: tuple[ExperimentParameterValue, ...]
    purpose: str
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {k: v for k, v in self.to_dict().items() if k != "axis_id"}

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentConfigurationError)
        for field in ("axis_id", "code", "field_path", "purpose"):
            _text(getattr(self, field), field, ExperimentConfigurationError)
        if not isinstance(self.kind, ParameterAxisKind):
            raise ExperimentConfigurationError("invalid axis kind")
        if (
            not isinstance(self.values, tuple)
            or len(self.values) != 3
            or any(
                not isinstance(item, ExperimentParameterValue)
                for item in self.values
            )
            or tuple(item.level for item in self.values)
            != (VariantLevel.LOW, VariantLevel.BASELINE, VariantLevel.HIGH)
        ):
            raise ExperimentConfigurationError(
                "axis values must be exact LOW/BASELINE/HIGH"
            )
        _texts(self.assumptions, "assumptions", ExperimentConfigurationError)
        require_semantic_id(
            self.axis_id,
            prefix="c008c-parameter-axis-v1-",
            payload=self._identity_payload(),
            field_name="axis_id",
            error_type=ExperimentConfigurationError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "axis_id": self.axis_id,
            "code": self.code,
            "kind": self.kind.value,
            "field_path": self.field_path,
            "values": [item.to_dict() for item in self.values],
            "purpose": self.purpose,
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentParameterAxis:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["axis_id"],
                data["code"],
                ParameterAxisKind(data["kind"]),
                data["field_path"],
                tuple(
                    ExperimentParameterValue.from_dict(item)
                    for item in _ordered(data, cls.__name__, "values")
                ),
                data["purpose"],
                tuple(_ordered(data, cls.__name__, "assumptions")),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentVariant:
    variant_id: str
    code: str
    experiment_kind: ExperimentKind
    level: VariantLevel
    axis_id: str | None
    changed_field_paths: tuple[str, ...]
    core_config_snapshot: MSACoreConfig
    metric_config_snapshot: StructuralMetricConfig
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {k: v for k, v in self.to_dict().items() if k != "variant_id"}

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        _text(self.variant_id, "variant_id", ExperimentPlanError)
        _text(self.code, "code", ExperimentPlanError)
        if not isinstance(self.experiment_kind, ExperimentKind) or not isinstance(
            self.level, VariantLevel
        ):
            raise ExperimentPlanError("invalid variant enum")
        if self.axis_id is not None:
            _text(self.axis_id, "axis_id", ExperimentPlanError)
        _texts(
            self.changed_field_paths,
            "changed_field_paths",
            ExperimentPlanError,
            non_empty=False,
        )
        _roundtrip(
            self.core_config_snapshot,
            MSACoreConfig,
            "core_config_snapshot",
            ExperimentPlanError,
        )
        _roundtrip(
            self.metric_config_snapshot,
            StructuralMetricConfig,
            "metric_config_snapshot",
            ExperimentPlanError,
        )
        _texts(self.assumptions, "assumptions", ExperimentPlanError)
        if self.experiment_kind is ExperimentKind.BASELINE and (
            self.level is not VariantLevel.BASELINE
            or self.axis_id is not None
            or self.changed_field_paths
            or self.core_config_snapshot != core_alpha_v1_config()
            or self.metric_config_snapshot != StructuralMetricConfig()
        ):
            raise ExperimentPlanError("baseline variant is not exact")
        if self.experiment_kind in (
            ExperimentKind.MODEL_SENSITIVITY,
            ExperimentKind.METRIC_SENSITIVITY,
        ) and (self.axis_id is None or len(self.changed_field_paths) != 1):
            raise ExperimentPlanError(
                "sensitivity variant must change exactly one axis"
            )
        require_semantic_id(
            self.variant_id,
            prefix="c008c-experiment-variant-v1-",
            payload=self._identity_payload(),
            field_name="variant_id",
            error_type=ExperimentPlanError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "code": self.code,
            "experiment_kind": self.experiment_kind.value,
            "level": self.level.value,
            "axis_id": self.axis_id,
            "changed_field_paths": list(self.changed_field_paths),
            "core_config_snapshot": self.core_config_snapshot.to_dict(),
            "metric_config_snapshot": self.metric_config_snapshot.to_dict(),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentVariant:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["variant_id"],
                data["code"],
                ExperimentKind(data["experiment_kind"]),
                VariantLevel(data["level"]),
                data["axis_id"],
                tuple(_ordered(data, cls.__name__, "changed_field_paths")),
                MSACoreConfig.from_dict(data["core_config_snapshot"]),
                StructuralMetricConfig.from_dict(data["metric_config_snapshot"]),
                tuple(_ordered(data, cls.__name__, "assumptions")),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentAblation:
    ablation_id: str
    code: str
    target: str
    hypothesis: str
    field_paths: tuple[str, ...]
    baseline_values: tuple[ExperimentParameterValue, ...]
    neutralized_values: tuple[ExperimentParameterValue, ...]
    support_status: AblationSupportStatus
    reason: str
    core_config_snapshot: MSACoreConfig | None
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {k: v for k, v in self.to_dict().items() if k != "ablation_id"}

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        for field in ("ablation_id", "code", "target", "hypothesis", "reason"):
            _text(getattr(self, field), field, ExperimentPlanError)
        _texts(self.field_paths, "field_paths", ExperimentPlanError)
        if (
            not isinstance(self.support_status, AblationSupportStatus)
            or not isinstance(self.baseline_values, tuple)
            or not isinstance(self.neutralized_values, tuple)
            or len(self.baseline_values) != len(self.field_paths)
            or len(self.neutralized_values) != len(self.field_paths)
            or any(
                not isinstance(item, ExperimentParameterValue)
                for item in (*self.baseline_values, *self.neutralized_values)
            )
        ):
            raise ExperimentPlanError("invalid ablation values or status")
        if (
            self.support_status
            is AblationSupportStatus.SUPPORTED_BY_PUBLIC_CONFIG
        ):
            _roundtrip(
                self.core_config_snapshot,
                MSACoreConfig,
                "core_config_snapshot",
                ExperimentPlanError,
            )
        elif self.core_config_snapshot is not None:
            raise ExperimentPlanError(
                "unsupported ablation must not invent a config"
            )
        require_semantic_id(
            self.ablation_id,
            prefix="c008c-experiment-ablation-v1-",
            payload=self._identity_payload(),
            field_name="ablation_id",
            error_type=ExperimentPlanError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ablation_id": self.ablation_id,
            "code": self.code,
            "target": self.target,
            "hypothesis": self.hypothesis,
            "field_paths": list(self.field_paths),
            "baseline_values": [item.to_dict() for item in self.baseline_values],
            "neutralized_values": [
                item.to_dict() for item in self.neutralized_values
            ],
            "support_status": self.support_status.value,
            "reason": self.reason,
            "core_config_snapshot": (
                None
                if self.core_config_snapshot is None
                else self.core_config_snapshot.to_dict()
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentAblation:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            snapshot = data["core_config_snapshot"]
            return cls(
                data["ablation_id"],
                data["code"],
                data["target"],
                data["hypothesis"],
                tuple(_ordered(data, cls.__name__, "field_paths")),
                tuple(
                    ExperimentParameterValue.from_dict(item)
                    for item in _ordered(data, cls.__name__, "baseline_values")
                ),
                tuple(
                    ExperimentParameterValue.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "neutralized_values"
                    )
                ),
                AblationSupportStatus(data["support_status"]),
                data["reason"],
                None if snapshot is None else MSACoreConfig.from_dict(snapshot),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentIncrementStep:
    increment_step_id: str
    step_index: int
    code: str
    restored_contribution: str
    changed_field_paths: tuple[str, ...]
    core_config_snapshot: MSACoreConfig
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            k: v for k, v in self.to_dict().items() if k != "increment_step_id"
        }

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        _text(self.increment_step_id, "increment_step_id", ExperimentPlanError)
        if type(self.step_index) is not int or self.step_index < 0:
            raise ExperimentPlanError("step_index must be non-negative integer")
        _text(self.code, "code", ExperimentPlanError)
        _text(
            self.restored_contribution,
            "restored_contribution",
            ExperimentPlanError,
        )
        _texts(
            self.changed_field_paths,
            "changed_field_paths",
            ExperimentPlanError,
            non_empty=self.step_index != 0,
        )
        _roundtrip(
            self.core_config_snapshot,
            MSACoreConfig,
            "core_config_snapshot",
            ExperimentPlanError,
        )
        require_semantic_id(
            self.increment_step_id,
            prefix="c008c-increment-step-v1-",
            payload=self._identity_payload(),
            field_name="increment_step_id",
            error_type=ExperimentPlanError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "increment_step_id": self.increment_step_id,
            "step_index": self.step_index,
            "code": self.code,
            "restored_contribution": self.restored_contribution,
            "changed_field_paths": list(self.changed_field_paths),
            "core_config_snapshot": self.core_config_snapshot.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentIncrementStep:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["increment_step_id"],
                data["step_index"],
                data["code"],
                data["restored_contribution"],
                tuple(_ordered(data, cls.__name__, "changed_field_paths")),
                MSACoreConfig.from_dict(data["core_config_snapshot"]),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDatasetCase:
    dataset_case_id: str
    scenario_kind: SyntheticScenarioKind
    seed: int
    partition: DatasetPartition
    symbol: str
    reference_timeframe: Timeframe
    source_input: ResonanceFrameInput
    source_input_payload_digest: str
    expected_causal_properties: tuple[str, ...]
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            k: v for k, v in self.to_dict().items() if k != "dataset_case_id"
        }

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentDatasetError)
        _text(self.dataset_case_id, "dataset_case_id", ExperimentDatasetError)
        if not isinstance(self.scenario_kind, SyntheticScenarioKind):
            raise ExperimentDatasetError("invalid scenario kind")
        if type(self.seed) is not int or self.seed not in (0, 1, 2, 3):
            raise ExperimentDatasetError("seed must be one of 0, 1, 2, 3")
        if not isinstance(self.partition, DatasetPartition):
            raise ExperimentDatasetError("invalid partition")
        expected_partition = (
            DatasetPartition.DEVELOPMENT
            if self.seed in (0, 1)
            else DatasetPartition.VALIDATION
            if self.seed == 2
            else DatasetPartition.OOS
        )
        if self.partition is not expected_partition:
            raise ExperimentDatasetError("partition does not match seed rule")
        if self.symbol != "XAUUSD" or self.reference_timeframe is not Timeframe.H1:
            raise ExperimentDatasetError(
                "synthetic case must use XAUUSD/H1"
            )
        _roundtrip(
            self.source_input,
            ResonanceFrameInput,
            "source_input",
            ExperimentDatasetError,
        )
        try:
            validate_source_input(self.source_input, core_alpha_v1_config())
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentDatasetError(
                "source_input is not a formal Core input"
            ) from exc
        if self.source_input_payload_digest != digest(
            self.source_input.to_dict()
        ):
            raise ExperimentDatasetError("source input digest mismatch")
        _texts(
            self.expected_causal_properties,
            "expected_causal_properties",
            ExperimentDatasetError,
        )
        _texts(self.assumptions, "assumptions", ExperimentDatasetError)
        require_semantic_id(
            self.dataset_case_id,
            prefix="c008c-dataset-case-v1-",
            payload=self._identity_payload(),
            field_name="dataset_case_id",
            error_type=ExperimentDatasetError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_case_id": self.dataset_case_id,
            "scenario_kind": self.scenario_kind.value,
            "seed": self.seed,
            "partition": self.partition.value,
            "symbol": self.symbol,
            "reference_timeframe": self.reference_timeframe.value,
            "source_input": self.source_input.to_dict(),
            "source_input_payload_digest": self.source_input_payload_digest,
            "expected_causal_properties": list(
                self.expected_causal_properties
            ),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentDatasetCase:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["dataset_case_id"],
                SyntheticScenarioKind(data["scenario_kind"]),
                data["seed"],
                DatasetPartition(data["partition"]),
                data["symbol"],
                Timeframe(data["reference_timeframe"]),
                ResonanceFrameInput.from_dict(data["source_input"]),
                data["source_input_payload_digest"],
                tuple(
                    _ordered(
                        data, cls.__name__, "expected_causal_properties"
                    )
                ),
                tuple(_ordered(data, cls.__name__, "assumptions")),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentDatasetManifest:
    dataset_manifest_id: str
    cases: tuple[ExperimentDatasetCase, ...]
    scenario_order: tuple[SyntheticScenarioKind, ...]
    partition_order: tuple[DatasetPartition, ...]
    seed_partition_rules: tuple[str, ...]
    real_market_oos_status: RealMarketOOSStatus
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            k: v
            for k, v in self.to_dict().items()
            if k != "dataset_manifest_id"
        }

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentDatasetError)
        _text(
            self.dataset_manifest_id,
            "dataset_manifest_id",
            ExperimentDatasetError,
        )
        if (
            not isinstance(self.cases, tuple)
            or len(self.cases) != 20
            or any(
                not isinstance(item, ExperimentDatasetCase)
                for item in self.cases
            )
        ):
            raise ExperimentDatasetError(
                "manifest must contain exactly 20 cases"
            )
        _ids(self.cases, "cases", "dataset_case_id", ExperimentDatasetError)
        source_digests = tuple(
            item.source_input_payload_digest for item in self.cases
        )
        if len(set(source_digests)) != 20:
            raise ExperimentDatasetError(
                "source input digests must be unique"
            )
        if self.scenario_order != tuple(SyntheticScenarioKind):
            raise ExperimentDatasetError("invalid scenario order")
        if self.partition_order != (
            DatasetPartition.DEVELOPMENT,
            DatasetPartition.VALIDATION,
            DatasetPartition.OOS,
        ):
            raise ExperimentDatasetError("invalid partition order")
        expected_order = tuple(
            (kind, seed)
            for kind in self.scenario_order
            for seed in (0, 1, 2, 3)
        )
        if tuple(
            (case.scenario_kind, case.seed) for case in self.cases
        ) != expected_order:
            raise ExperimentDatasetError(
                "case order must be scenario then seed"
            )
        for kind in self.scenario_order:
            if {
                item.partition
                for item in self.cases
                if item.scenario_kind is kind
            } != set(self.partition_order):
                raise ExperimentDatasetError(
                    "every scenario must cover all partitions"
                )
        _texts(
            self.seed_partition_rules,
            "seed_partition_rules",
            ExperimentDatasetError,
        )
        if (
            self.real_market_oos_status
            is not RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET
        ):
            raise ExperimentDatasetError(
                "real-market OOS has not been approved or run"
            )
        _texts(self.assumptions, "assumptions", ExperimentDatasetError)
        require_semantic_id(
            self.dataset_manifest_id,
            prefix="c008c-dataset-manifest-v1-",
            payload=self._identity_payload(),
            field_name="dataset_manifest_id",
            error_type=ExperimentDatasetError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_manifest_id": self.dataset_manifest_id,
            "cases": [item.to_dict() for item in self.cases],
            "scenario_order": [item.value for item in self.scenario_order],
            "partition_order": [item.value for item in self.partition_order],
            "seed_partition_rules": list(self.seed_partition_rules),
            "real_market_oos_status": self.real_market_oos_status.value,
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentDatasetManifest:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["dataset_manifest_id"],
                tuple(
                    ExperimentDatasetCase.from_dict(item)
                    for item in _ordered(data, cls.__name__, "cases")
                ),
                tuple(
                    SyntheticScenarioKind(item)
                    for item in _ordered(
                        data, cls.__name__, "scenario_order"
                    )
                ),
                tuple(
                    DatasetPartition(item)
                    for item in _ordered(
                        data, cls.__name__, "partition_order"
                    )
                ),
                tuple(
                    _ordered(
                        data, cls.__name__, "seed_partition_rules"
                    )
                ),
                RealMarketOOSStatus(data["real_market_oos_status"]),
                tuple(_ordered(data, cls.__name__, "assumptions")),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentGateDefinition:
    gate_definition_id: str
    code: str
    severity: GateSeverity
    subject_kind: str
    description: str
    policy: ExperimentGatePolicy
    pass_rule: str
    failure_rule: str
    required_evidence_kinds: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            k: v
            for k, v in self.to_dict().items()
            if k != "gate_definition_id"
        }

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentGateError)
        for field in (
            "gate_definition_id",
            "code",
            "subject_kind",
            "description",
            "pass_rule",
            "failure_rule",
        ):
            _text(getattr(self, field), field, ExperimentGateError)
        if not isinstance(self.severity, GateSeverity):
            raise ExperimentGateError("invalid gate severity")
        _roundtrip(
            self.policy,
            ExperimentGatePolicy,
            "policy",
            ExperimentGateError,
        )
        if (
            self.pass_rule != self.policy.pass_condition
            or self.failure_rule != self.policy.failure_condition
        ):
            raise ExperimentGateError(
                "gate rules must equal the machine-readable policy"
            )
        _texts(
            self.required_evidence_kinds,
            "required_evidence_kinds",
            ExperimentGateError,
        )
        require_semantic_id(
            self.gate_definition_id,
            prefix="c008c-gate-definition-v1-",
            payload=self._identity_payload(),
            field_name="gate_definition_id",
            error_type=ExperimentGateError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "gate_definition_id": self.gate_definition_id,
            "code": self.code,
            "severity": self.severity.value,
            "subject_kind": self.subject_kind,
            "description": self.description,
            "policy": self.policy.to_dict(),
            "pass_rule": self.pass_rule,
            "failure_rule": self.failure_rule,
            "required_evidence_kinds": list(self.required_evidence_kinds),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ExperimentGateDefinition:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["gate_definition_id"],
                data["code"],
                GateSeverity(data["severity"]),
                data["subject_kind"],
                data["description"],
                ExperimentGatePolicy.from_dict(data["policy"]),
                data["pass_rule"],
                data["failure_rule"],
                tuple(
                    _ordered(
                        data, cls.__name__, "required_evidence_kinds"
                    )
                ),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    experiment_plan_id: str
    baseline_id: str
    dataset_manifest_id: str
    axes: tuple[ExperimentParameterAxis, ...]
    variants: tuple[ExperimentVariant, ...]
    ablations: tuple[ExperimentAblation, ...]
    increment_steps: tuple[ExperimentIncrementStep, ...]
    gate_definitions: tuple[ExperimentGateDefinition, ...]
    execution_scope_policy: ExperimentExecutionScopePolicy
    baseline_replay_policy: ExperimentReplayPolicy
    variant_replay_policy: ExperimentReplayPolicy
    fixed_cutoff_policy: ExperimentFixedCutoffPolicy
    partition_rules: tuple[str, ...]
    scenario_seed_rules: tuple[str, ...]
    metric_definition_ids: tuple[str, ...]
    metric_formula_ids: tuple[str, ...]
    execution_order: tuple[str, ...]
    real_market_oos_status: RealMarketOOSStatus
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            k: v
            for k, v in self.to_dict().items()
            if k != "experiment_plan_id"
        }

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ExperimentPlanError)
        for field in (
            "experiment_plan_id",
            "baseline_id",
            "dataset_manifest_id",
        ):
            _text(getattr(self, field), field, ExperimentPlanError)
        if (
            not isinstance(self.axes, tuple)
            or len(self.axes) != 8
            or any(
                not isinstance(item, ExperimentParameterAxis)
                for item in self.axes
            )
        ):
            raise ExperimentPlanError("plan must contain exactly eight axes")
        axis_ids = set(_ids(self.axes, "axes", "axis_id", ExperimentPlanError))
        if not isinstance(self.variants, tuple) or any(
            not isinstance(item, ExperimentVariant) for item in self.variants
        ):
            raise ExperimentPlanError("invalid variants tuple")
        _ids(self.variants, "variants", "variant_id", ExperimentPlanError)
        baseline = tuple(
            item
            for item in self.variants
            if item.experiment_kind is ExperimentKind.BASELINE
        )
        low = tuple(
            item for item in self.variants if item.level is VariantLevel.LOW
        )
        high = tuple(
            item for item in self.variants if item.level is VariantLevel.HIGH
        )
        if len(baseline) != 1 or len(low) != 8 or len(high) != 8:
            raise ExperimentPlanError(
                "variant universe requires one baseline and eight LOW/HIGH"
            )
        if any(item.axis_id not in axis_ids for item in (*low, *high)):
            raise ExperimentPlanError(
                "sensitivity variant references unknown axis"
            )
        if not isinstance(self.ablations, tuple) or any(
            not isinstance(item, ExperimentAblation)
            for item in self.ablations
        ):
            raise ExperimentPlanError("invalid ablations tuple")
        _ids(
            self.ablations,
            "ablations",
            "ablation_id",
            ExperimentPlanError,
        )
        supported = tuple(
            item
            for item in self.ablations
            if item.support_status
            is AblationSupportStatus.SUPPORTED_BY_PUBLIC_CONFIG
        )
        unsupported = tuple(
            item
            for item in self.ablations
            if item.support_status
            is AblationSupportStatus.UNSUPPORTED_BY_PUBLIC_CONFIG
        )
        if len(supported) != 4 or len(unsupported) < 4:
            raise ExperimentPlanError(
                "plan requires four supported and four unsupported ablations"
            )
        if (
            not isinstance(self.increment_steps, tuple)
            or len(self.increment_steps) != 5
            or any(
                not isinstance(item, ExperimentIncrementStep)
                for item in self.increment_steps
            )
            or tuple(item.step_index for item in self.increment_steps)
            != (0, 1, 2, 3, 4)
            or self.increment_steps[-1].core_config_snapshot
            != core_alpha_v1_config()
        ):
            raise ExperimentPlanError("invalid increment ladder")
        _ids(
            self.increment_steps,
            "increment_steps",
            "increment_step_id",
            ExperimentPlanError,
        )
        if (
            not isinstance(self.gate_definitions, tuple)
            or not self.gate_definitions
            or any(
                not isinstance(item, ExperimentGateDefinition)
                for item in self.gate_definitions
            )
        ):
            raise ExperimentPlanError("gate definitions must not be empty")
        _ids(
            self.gate_definitions,
            "gate_definitions",
            "gate_definition_id",
            ExperimentPlanError,
        )
        if len({item.code for item in self.gate_definitions}) != len(
            self.gate_definitions
        ):
            raise ExperimentPlanError("gate codes must be unique")
        _roundtrip(
            self.execution_scope_policy,
            ExperimentExecutionScopePolicy,
            "execution_scope_policy",
            ExperimentPlanError,
        )
        _roundtrip(
            self.baseline_replay_policy,
            ExperimentReplayPolicy,
            "baseline_replay_policy",
            ExperimentPlanError,
        )
        _roundtrip(
            self.variant_replay_policy,
            ExperimentReplayPolicy,
            "variant_replay_policy",
            ExperimentPlanError,
        )
        _roundtrip(
            self.fixed_cutoff_policy,
            ExperimentFixedCutoffPolicy,
            "fixed_cutoff_policy",
            ExperimentPlanError,
        )
        variant_ids = tuple(item.variant_id for item in self.variants)
        if self.execution_scope_policy.variant_ids != variant_ids:
            raise ExperimentPlanError(
                "execution scope variants must equal the plan variants"
            )
        if (
            self.baseline_replay_policy.variant_ids != (baseline[0].variant_id,)
            or self.baseline_replay_policy.expected_sample_count != 20
            or self.baseline_replay_policy.dataset_case_ids
            != self.execution_scope_policy.dataset_case_ids
            or self.variant_replay_policy.variant_ids != variant_ids[1:]
            or self.variant_replay_policy.expected_sample_count != 125
            or len(self.variant_replay_policy.dataset_case_ids) != 5
            or not set(self.variant_replay_policy.dataset_case_ids).issubset(
                self.execution_scope_policy.dataset_case_ids
            )
            or self.fixed_cutoff_policy.baseline_variant_id
            != baseline[0].variant_id
            or self.fixed_cutoff_policy.dataset_case_ids
            != self.execution_scope_policy.dataset_case_ids
        ):
            raise ExperimentPlanError("replay or cutoff policy mismatch")
        for field in (
            "partition_rules",
            "scenario_seed_rules",
            "metric_definition_ids",
            "metric_formula_ids",
            "execution_order",
            "assumptions",
        ):
            _texts(getattr(self, field), field, ExperimentPlanError)
        if (
            self.real_market_oos_status
            is not RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET
        ):
            raise ExperimentPlanError(
                "C-008C-A cannot contain a real-market OOS result"
            )
        require_semantic_id(
            self.experiment_plan_id,
            prefix="c008c-experiment-plan-v1-",
            payload=self._identity_payload(),
            field_name="experiment_plan_id",
            error_type=ExperimentPlanError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_plan_id": self.experiment_plan_id,
            "baseline_id": self.baseline_id,
            "dataset_manifest_id": self.dataset_manifest_id,
            "axes": [item.to_dict() for item in self.axes],
            "variants": [item.to_dict() for item in self.variants],
            "ablations": [item.to_dict() for item in self.ablations],
            "increment_steps": [
                item.to_dict() for item in self.increment_steps
            ],
            "gate_definitions": [
                item.to_dict() for item in self.gate_definitions
            ],
            "execution_scope_policy": self.execution_scope_policy.to_dict(),
            "baseline_replay_policy": self.baseline_replay_policy.to_dict(),
            "variant_replay_policy": self.variant_replay_policy.to_dict(),
            "fixed_cutoff_policy": self.fixed_cutoff_policy.to_dict(),
            "partition_rules": list(self.partition_rules),
            "scenario_seed_rules": list(self.scenario_seed_rules),
            "metric_definition_ids": list(self.metric_definition_ids),
            "metric_formula_ids": list(self.metric_formula_ids),
            "execution_order": list(self.execution_order),
            "real_market_oos_status": self.real_market_oos_status.value,
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ExperimentPlan:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["experiment_plan_id"],
                data["baseline_id"],
                data["dataset_manifest_id"],
                tuple(
                    ExperimentParameterAxis.from_dict(item)
                    for item in _ordered(data, cls.__name__, "axes")
                ),
                tuple(
                    ExperimentVariant.from_dict(item)
                    for item in _ordered(data, cls.__name__, "variants")
                ),
                tuple(
                    ExperimentAblation.from_dict(item)
                    for item in _ordered(data, cls.__name__, "ablations")
                ),
                tuple(
                    ExperimentIncrementStep.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "increment_steps"
                    )
                ),
                tuple(
                    ExperimentGateDefinition.from_dict(item)
                    for item in _ordered(
                        data, cls.__name__, "gate_definitions"
                    )
                ),
                ExperimentExecutionScopePolicy.from_dict(
                    data["execution_scope_policy"]
                ),
                ExperimentReplayPolicy.from_dict(
                    data["baseline_replay_policy"]
                ),
                ExperimentReplayPolicy.from_dict(
                    data["variant_replay_policy"]
                ),
                ExperimentFixedCutoffPolicy.from_dict(
                    data["fixed_cutoff_policy"]
                ),
                tuple(_ordered(data, cls.__name__, "partition_rules")),
                tuple(_ordered(data, cls.__name__, "scenario_seed_rules")),
                tuple(_ordered(data, cls.__name__, "metric_definition_ids")),
                tuple(_ordered(data, cls.__name__, "metric_formula_ids")),
                tuple(_ordered(data, cls.__name__, "execution_order")),
                RealMarketOOSStatus(data["real_market_oos_status"]),
                tuple(_ordered(data, cls.__name__, "assumptions")),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ProtectedSourceFile:
    relative_path: str
    byte_size: int
    sha256: str
    category: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(
            self.schema_version,
            type(self).__name__,
            ExperimentProtectedSourceError,
        )
        _text(
            self.relative_path,
            "relative_path",
            ExperimentProtectedSourceError,
        )
        path = PurePosixPath(self.relative_path)
        if (
            path.is_absolute()
            or "\\" in self.relative_path
            or ".." in path.parts
            or str(path) != self.relative_path
        ):
            raise ExperimentProtectedSourceError(
                "relative_path must be normalized repository-relative POSIX"
            )
        if type(self.byte_size) is not int or self.byte_size < 0:
            raise ExperimentProtectedSourceError("invalid byte_size")
        _text(self.sha256, "sha256", ExperimentProtectedSourceError)
        if len(self.sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.sha256
        ):
            raise ExperimentProtectedSourceError("invalid SHA-256")
        _text(self.category, "category", ExperimentProtectedSourceError)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "relative_path": self.relative_path,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProtectedSourceFile:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["relative_path"],
                data["byte_size"],
                data["sha256"],
                data["category"],
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


@dataclass(frozen=True, slots=True)
class ProtectedSourceManifest:
    protected_source_manifest_id: str
    execution_base_commit: str
    core_reference_commit: str
    files: tuple[ProtectedSourceFile, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            k: v
            for k, v in self.to_dict().items()
            if k != "protected_source_manifest_id"
        }

    def __post_init__(self) -> None:
        _schema(
            self.schema_version,
            type(self).__name__,
            ExperimentProtectedSourceError,
        )
        _text(
            self.protected_source_manifest_id,
            "protected_source_manifest_id",
            ExperimentProtectedSourceError,
        )
        if (
            self.execution_base_commit != EXECUTION_BASE_COMMIT
            or self.core_reference_commit != CORE_REFERENCE_COMMIT
        ):
            raise ExperimentProtectedSourceError(
                "protected source commit authority mismatch"
            )
        if (
            not isinstance(self.files, tuple)
            or not self.files
            or any(
                not isinstance(item, ProtectedSourceFile)
                for item in self.files
            )
        ):
            raise ExperimentProtectedSourceError("invalid protected files")
        paths = tuple(item.relative_path for item in self.files)
        if len(set(paths)) != len(paths) or paths != tuple(sorted(paths)):
            raise ExperimentProtectedSourceError(
                "protected paths must be unique and sorted"
            )
        if any(
            path.startswith("src/python/msa/validation/experiments/")
            for path in paths
        ):
            raise ExperimentProtectedSourceError(
                "experiments package must not protect itself"
            )
        require_semantic_id(
            self.protected_source_manifest_id,
            prefix="c008c-protected-source-manifest-v1-",
            payload=self._identity_payload(),
            field_name="protected_source_manifest_id",
            error_type=ExperimentProtectedSourceError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protected_source_manifest_id": (
                self.protected_source_manifest_id
            ),
            "execution_base_commit": self.execution_base_commit,
            "core_reference_commit": self.core_reference_commit,
            "files": [item.to_dict() for item in self.files],
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> ProtectedSourceManifest:
        data = _exact(
            payload,
            cls.__name__,
            {item.name for item in fields(cls)} - {"schema_version"},
        )
        try:
            return cls(
                data["protected_source_manifest_id"],
                data["execution_base_commit"],
                data["core_reference_commit"],
                tuple(
                    ProtectedSourceFile.from_dict(item)
                    for item in _ordered(data, cls.__name__, "files")
                ),
                data["schema_version"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ExperimentSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc
