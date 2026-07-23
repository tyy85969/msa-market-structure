"""Immutable C-007D contracts for the composed MSA Core Alpha run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any, TypeVar

from msa.domain import ProvenanceRef
from msa.research.active_box import (
    ActiveBoxEventType,
    ActiveBoxSelectionConfig,
    ActiveBoxSelectionFrame,
    ActiveBoxSelectionHistory,
)
from msa.research.resonance import (
    ResonanceFrame,
    ResonanceFrameConfig,
    ResonanceFrameHistory,
    ResonanceFrameInput,
    ResonanceScoreFrame,
    ResonanceScoreHistory,
    ResonanceScoringConfig,
)

from .errors import (
    MSACoreConfigurationError,
    MSACoreInputError,
    MSACoreIntegrationError,
    MSACoreSerializationError,
)
from .identity import digest, require_semantic_id, semantic_id


SCHEMA_VERSION = 1
_PIPELINE_MODULE = "msa.research.msa_core.pipeline"
_REPORT_ASSUMPTIONS = (
    "C-007A ResonanceFrameHistory is authoritative for causal evidence",
    "C-007B ResonanceScoreHistory is authoritative for zones and scores",
    "C-007C ActiveBoxSelectionHistory is authoritative for box state",
    "MSA Core composes and audits stages without changing their algorithms",
)
_ROUNDTRIP_ERRORS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    AssertionError,
    RuntimeError,
)
T = TypeVar("T")


def _schema(value: object, name: str, error_type: type[Exception]) -> int:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error_type(f"{name}.schema_version must be {SCHEMA_VERSION}")
    return SCHEMA_VERSION


def _text(value: object, field_name: str, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def _integer(
    value: object,
    field_name: str,
    error_type: type[Exception],
    *,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise error_type(f"{field_name} must be an integer >= {minimum}")
    return value


def _boolean(value: object, field_name: str, error_type: type[Exception]) -> bool:
    if not isinstance(value, bool):
        raise error_type(f"{field_name} must be a bool")
    return value


def _time(value: object, field_name: str, error_type: type[Exception]) -> datetime:
    if not isinstance(value, datetime):
        raise error_type(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error_type(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise MSACoreSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise MSACoreSerializationError(
            f"{field_name} must be an aware ISO-8601 string"
        ) from exc
    return _time(parsed, field_name, MSACoreSerializationError)


def _optional_text(
    value: object, field_name: str, error_type: type[Exception]
) -> str | None:
    return None if value is None else _text(value, field_name, error_type)


def _text_tuple(
    value: object,
    field_name: str,
    error_type: type[Exception],
    *,
    unique: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise error_type(f"{field_name} must be a tuple")
    normalized = tuple(
        _text(item, f"{field_name}[{index}]", error_type)
        for index, item in enumerate(value)
    )
    if unique and len(set(normalized)) != len(normalized):
        raise error_type(f"{field_name} must contain unique values")
    return normalized


def _exact_payload(
    payload: Mapping[str, Any], object_name: str, expected_fields: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise MSACoreSerializationError(
            f"{object_name} payload must be a mapping"
        )
    expected = expected_fields | {"schema_version"}
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing:
        raise MSACoreSerializationError(
            f"{object_name} payload missing fields: {sorted(missing)}"
        )
    if unknown:
        raise MSACoreSerializationError(
            f"{object_name} payload has unknown fields: {sorted(unknown)}"
        )
    _schema(payload["schema_version"], object_name, MSACoreSerializationError)
    return payload


def _ordered_list(
    payload: Mapping[str, Any], object_name: str, field_name: str
) -> list[Any]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise MSACoreSerializationError(
            f"{object_name}.{field_name} must be an ordered list"
        )
    return value


def _formal_roundtrip(
    value: object,
    expected_type: type[T],
    field_name: str,
    error_type: type[Exception],
) -> T:
    if not isinstance(value, expected_type):
        raise error_type(f"{field_name} must be a {expected_type.__name__}")
    try:
        restored = expected_type.from_dict(value.to_dict())
    except _ROUNDTRIP_ERRORS as exc:
        raise error_type(f"{field_name} is not a formally valid contract") from exc
    if restored != value:
        raise error_type(f"{field_name} payload is not formally self-consistent")
    return value


def _engine_note(engine_id: str) -> tuple[str, ...]:
    return (f"engine_id={engine_id}",)


def _validate_provenance(
    value: object,
    *,
    object_name: str,
    object_id: str,
    config: MSACoreConfig,
    parents: tuple[str, ...],
) -> ProvenanceRef:
    if not isinstance(value, ProvenanceRef):
        raise MSACoreIntegrationError(
            f"{object_name}.provenance must be a ProvenanceRef"
        )
    try:
        restored = ProvenanceRef.from_dict(value.to_dict())
    except _ROUNDTRIP_ERRORS as exc:
        raise MSACoreIntegrationError(
            f"{object_name}.provenance is not formally valid"
        ) from exc
    expected = ProvenanceRef(
        source_module=_PIPELINE_MODULE,
        source_version=config.engine_version,
        source_object_id=object_id,
        policy_id=config.policy_id,
        parent_object_ids=parents,
        notes=_engine_note(config.engine_id),
    )
    if restored != value or value != expected:
        raise MSACoreIntegrationError(
            f"{object_name}.provenance must exactly bind authoritative parents"
        )
    return value


@dataclass(frozen=True, slots=True)
class MSACoreConfig:
    engine_id: str
    engine_version: str
    policy_id: str
    frame_config: ResonanceFrameConfig
    scoring_config: ResonanceScoringConfig
    active_box_config: ActiveBoxSelectionConfig
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MSACoreConfigurationError)
        _text(self.engine_id, f"{name}.engine_id", MSACoreConfigurationError)
        _text(
            self.engine_version,
            f"{name}.engine_version",
            MSACoreConfigurationError,
        )
        _text(self.policy_id, f"{name}.policy_id", MSACoreConfigurationError)
        _boolean(self.strict, f"{name}.strict", MSACoreConfigurationError)
        if self.strict is not True:
            raise MSACoreConfigurationError(
                "MSACoreConfig.strict must be True"
            )
        _formal_roundtrip(
            self.frame_config,
            ResonanceFrameConfig,
            "frame_config",
            MSACoreConfigurationError,
        )
        _formal_roundtrip(
            self.scoring_config,
            ResonanceScoringConfig,
            "scoring_config",
            MSACoreConfigurationError,
        )
        _formal_roundtrip(
            self.active_box_config,
            ActiveBoxSelectionConfig,
            "active_box_config",
            MSACoreConfigurationError,
        )
        if self.frame_config.symbol != self.active_box_config.symbol:
            raise MSACoreConfigurationError(
                "frame_config.symbol must equal active_box_config.symbol"
            )
        frame_contexts = set(self.frame_config.contexts)
        scoring_contexts = {
            item.context for item in self.scoring_config.context_weights
        }
        if scoring_contexts != frame_contexts:
            raise MSACoreConfigurationError(
                "scoring context weights must exactly cover frame contexts"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "policy_id": self.policy_id,
            "frame_config": self.frame_config.to_dict(),
            "scoring_config": self.scoring_config.to_dict(),
            "active_box_config": self.active_box_config.to_dict(),
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MSACoreConfig:
        data = _exact_payload(
            payload,
            cls.__name__,
            {
                "engine_id",
                "engine_version",
                "policy_id",
                "frame_config",
                "scoring_config",
                "active_box_config",
                "strict",
            },
        )
        try:
            return cls(
                engine_id=data["engine_id"],
                engine_version=data["engine_version"],
                policy_id=data["policy_id"],
                frame_config=ResonanceFrameConfig.from_dict(
                    data["frame_config"]
                ),
                scoring_config=ResonanceScoringConfig.from_dict(
                    data["scoring_config"]
                ),
                active_box_config=ActiveBoxSelectionConfig.from_dict(
                    data["active_box_config"]
                ),
                strict=data["strict"],
                schema_version=data["schema_version"],
            )
        except MSACoreSerializationError:
            raise
        except _ROUNDTRIP_ERRORS as exc:
            raise MSACoreSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def validate_source_input(
    value: object, config: MSACoreConfig
) -> ResonanceFrameInput:
    _formal_roundtrip(
        value,
        ResonanceFrameInput,
        "source_input",
        MSACoreInputError,
    )
    source = value
    reference_config = source.reference_price_data.source_config
    if reference_config.canonical_symbol != config.frame_config.symbol:
        raise MSACoreInputError(
            "source_input reference symbol conflicts with MSACoreConfig"
        )
    if (
        reference_config.timeframe
        != config.frame_config.reference_price_timeframe
    ):
        raise MSACoreInputError(
            "source_input reference timeframe conflicts with MSACoreConfig"
        )
    history_by_context = {
        (
            item.config_snapshot.target_timeframe,
            item.config_snapshot.target_scale,
        ): item
        for item in source.timeframe_state_histories
    }
    expected_contexts = tuple(
        (item.timeframe, item.scale)
        for item in config.frame_config.contexts
    )
    if (
        len(history_by_context) != len(source.timeframe_state_histories)
        or set(history_by_context) != set(expected_contexts)
    ):
        raise MSACoreInputError(
            "source_input TimeframeState histories must exactly cover frame contexts"
        )
    canonical_histories = tuple(
        history_by_context[item] for item in expected_contexts
    )
    if canonical_histories == source.timeframe_state_histories:
        return source
    try:
        return ResonanceFrameInput(
            lifecycle_history=source.lifecycle_history,
            timeframe_state_histories=canonical_histories,
            reference_price_data=source.reference_price_data,
            schema_version=source.schema_version,
        )
    except _ROUNDTRIP_ERRORS as exc:
        raise MSACoreInputError(
            "source_input context histories cannot be canonically represented"
        ) from exc


@dataclass(frozen=True, slots=True)
class MSACoreFrameBundle:
    bundle_id: str
    as_of_time: datetime
    resonance_frame: ResonanceFrame
    score_frame: ResonanceScoreFrame
    selection_frame: ActiveBoxSelectionFrame
    config_snapshot: MSACoreConfig
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "as_of_time": self.as_of_time.isoformat(),
            "resonance_frame_id": self.resonance_frame.frame_id,
            "score_frame_id": self.score_frame.score_frame_id,
            "selection_frame_id": self.selection_frame.selection_frame_id,
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MSACoreIntegrationError)
        object.__setattr__(
            self,
            "as_of_time",
            _time(self.as_of_time, "as_of_time", MSACoreIntegrationError),
        )
        _formal_roundtrip(
            self.config_snapshot,
            MSACoreConfig,
            "config_snapshot",
            MSACoreIntegrationError,
        )
        _formal_roundtrip(
            self.resonance_frame,
            ResonanceFrame,
            "resonance_frame",
            MSACoreIntegrationError,
        )
        _formal_roundtrip(
            self.score_frame,
            ResonanceScoreFrame,
            "score_frame",
            MSACoreIntegrationError,
        )
        _formal_roundtrip(
            self.selection_frame,
            ActiveBoxSelectionFrame,
            "selection_frame",
            MSACoreIntegrationError,
        )
        if (
            self.resonance_frame.as_of_time != self.as_of_time
            or self.score_frame.as_of_time != self.as_of_time
            or self.selection_frame.as_of_time != self.as_of_time
        ):
            raise MSACoreIntegrationError(
                "all Bundle Frames must have exactly the same AsOf time"
            )
        if (
            self.score_frame.source_frame_id
            != self.resonance_frame.frame_id
            or self.score_frame.source_frame != self.resonance_frame
        ):
            raise MSACoreIntegrationError(
                "ScoreFrame must exactly consume the Bundle ResonanceFrame"
            )
        if (
            self.selection_frame.source_score_frame_id
            != self.score_frame.score_frame_id
            or self.selection_frame.source_score_frame != self.score_frame
        ):
            raise MSACoreIntegrationError(
                "SelectionFrame must exactly consume the Bundle ScoreFrame"
            )
        if (
            self.resonance_frame.config_snapshot
            != self.config_snapshot.frame_config
            or self.score_frame.config_snapshot
            != self.config_snapshot.scoring_config
            or self.selection_frame.config_snapshot
            != self.config_snapshot.active_box_config
        ):
            raise MSACoreIntegrationError(
                "Bundle stage configs must equal MSACoreConfig child configs"
            )
        if any(
            evidence.state_confirm_time > self.as_of_time
            for evidence in self.resonance_frame.evidence
        ):
            raise MSACoreIntegrationError(
                "Bundle contains Lifecycle evidence from the future"
            )
        if any(
            context.state.confirm_time > self.as_of_time
            for context in self.resonance_frame.context_states
        ):
            raise MSACoreIntegrationError(
                "Bundle contains TimeframeState from the future"
            )
        if (
            self.resonance_frame.reference_price.canonical_bar.available_time
            > self.as_of_time
        ):
            raise MSACoreIntegrationError(
                "Bundle contains a future reference bar"
            )
        if any(
            event.event_confirm_time != self.as_of_time
            for event in self.selection_frame.emitted_events
        ):
            raise MSACoreIntegrationError(
                "Active Box event time must equal Bundle AsOf"
            )
        current = self.selection_frame.active_box_snapshot
        if (
            current is not None
            and current.active_box.as_of_time != self.as_of_time
        ):
            raise MSACoreIntegrationError(
                "current Active Box AsOf must equal Bundle AsOf"
            )
        require_semantic_id(
            self.bundle_id,
            prefix="msa-core-bundle-v1-",
            payload=self._identity_payload(),
            field_name="bundle_id",
            error_type=MSACoreIntegrationError,
        )
        _validate_provenance(
            self.provenance,
            object_name=name,
            object_id=self.bundle_id,
            config=self.config_snapshot,
            parents=(
                self.resonance_frame.frame_id,
                self.score_frame.score_frame_id,
                self.selection_frame.selection_frame_id,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "as_of_time": self.as_of_time.isoformat(),
            "resonance_frame": self.resonance_frame.to_dict(),
            "score_frame": self.score_frame.to_dict(),
            "selection_frame": self.selection_frame.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MSACoreFrameBundle:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                bundle_id=data["bundle_id"],
                as_of_time=_parse_time(data["as_of_time"], "as_of_time"),
                resonance_frame=ResonanceFrame.from_dict(
                    data["resonance_frame"]
                ),
                score_frame=ResonanceScoreFrame.from_dict(data["score_frame"]),
                selection_frame=ActiveBoxSelectionFrame.from_dict(
                    data["selection_frame"]
                ),
                config_snapshot=MSACoreConfig.from_dict(
                    data["config_snapshot"]
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except MSACoreSerializationError:
            raise
        except _ROUNDTRIP_ERRORS as exc:
            raise MSACoreSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


@dataclass(frozen=True, slots=True)
class MSACoreRunReport:
    start_time: datetime
    end_time: datetime
    frame_count: int
    score_frame_count: int
    selection_frame_count: int
    evidence_count: int
    zone_count: int
    created_event_count: int
    frozen_event_count: int
    frozen_box_count: int
    active_box_frame_count: int
    no_box_frame_count: int
    final_has_active_box: bool
    final_active_box_key_id: str | None
    frame_engine_id: str
    scoring_engine_id: str
    active_box_engine_id: str
    integration_engine_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MSACoreIntegrationError)
        object.__setattr__(
            self,
            "start_time",
            _time(self.start_time, "start_time", MSACoreIntegrationError),
        )
        object.__setattr__(
            self,
            "end_time",
            _time(self.end_time, "end_time", MSACoreIntegrationError),
        )
        if self.end_time < self.start_time:
            raise MSACoreIntegrationError(
                "MSACoreRunReport.end_time cannot precede start_time"
            )
        for field_name in (
            "frame_count",
            "score_frame_count",
            "selection_frame_count",
            "evidence_count",
            "zone_count",
            "created_event_count",
            "frozen_event_count",
            "frozen_box_count",
            "active_box_frame_count",
            "no_box_frame_count",
        ):
            _integer(
                getattr(self, field_name),
                field_name,
                MSACoreIntegrationError,
            )
        _boolean(
            self.final_has_active_box,
            "final_has_active_box",
            MSACoreIntegrationError,
        )
        _optional_text(
            self.final_active_box_key_id,
            "final_active_box_key_id",
            MSACoreIntegrationError,
        )
        for field_name in (
            "frame_engine_id",
            "scoring_engine_id",
            "active_box_engine_id",
            "integration_engine_id",
        ):
            _text(
                getattr(self, field_name),
                field_name,
                MSACoreIntegrationError,
            )
        _text_tuple(
            self.assumptions,
            "assumptions",
            MSACoreIntegrationError,
        )
        _text_tuple(self.warnings, "warnings", MSACoreIntegrationError)
        _text_tuple(self.errors, "errors", MSACoreIntegrationError)
        if self.assumptions != _REPORT_ASSUMPTIONS:
            raise MSACoreIntegrationError(
                "MSACoreRunReport assumptions must equal the C-007D contract"
            )
        if self.warnings or self.errors:
            raise MSACoreIntegrationError(
                "a successful MSACoreRunReport must have no warnings or errors"
            )
        if (
            self.frame_count != self.score_frame_count
            or self.frame_count != self.selection_frame_count
            or self.active_box_frame_count + self.no_box_frame_count
            != self.frame_count
        ):
            raise MSACoreIntegrationError(
                "MSACoreRunReport stage/frame counts are inconsistent"
            )
        if self.final_has_active_box != (
            self.final_active_box_key_id is not None
        ):
            raise MSACoreIntegrationError(
                "final Active Box report facts are inconsistent"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "frame_count": self.frame_count,
            "score_frame_count": self.score_frame_count,
            "selection_frame_count": self.selection_frame_count,
            "evidence_count": self.evidence_count,
            "zone_count": self.zone_count,
            "created_event_count": self.created_event_count,
            "frozen_event_count": self.frozen_event_count,
            "frozen_box_count": self.frozen_box_count,
            "active_box_frame_count": self.active_box_frame_count,
            "no_box_frame_count": self.no_box_frame_count,
            "final_has_active_box": self.final_has_active_box,
            "final_active_box_key_id": self.final_active_box_key_id,
            "frame_engine_id": self.frame_engine_id,
            "scoring_engine_id": self.scoring_engine_id,
            "active_box_engine_id": self.active_box_engine_id,
            "integration_engine_id": self.integration_engine_id,
            "assumptions": list(self.assumptions),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MSACoreRunReport:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                start_time=_parse_time(data["start_time"], "start_time"),
                end_time=_parse_time(data["end_time"], "end_time"),
                frame_count=data["frame_count"],
                score_frame_count=data["score_frame_count"],
                selection_frame_count=data["selection_frame_count"],
                evidence_count=data["evidence_count"],
                zone_count=data["zone_count"],
                created_event_count=data["created_event_count"],
                frozen_event_count=data["frozen_event_count"],
                frozen_box_count=data["frozen_box_count"],
                active_box_frame_count=data["active_box_frame_count"],
                no_box_frame_count=data["no_box_frame_count"],
                final_has_active_box=data["final_has_active_box"],
                final_active_box_key_id=data["final_active_box_key_id"],
                frame_engine_id=data["frame_engine_id"],
                scoring_engine_id=data["scoring_engine_id"],
                active_box_engine_id=data["active_box_engine_id"],
                integration_engine_id=data["integration_engine_id"],
                assumptions=tuple(
                    _ordered_list(data, cls.__name__, "assumptions")
                ),
                warnings=tuple(
                    _ordered_list(data, cls.__name__, "warnings")
                ),
                errors=tuple(_ordered_list(data, cls.__name__, "errors")),
                schema_version=data["schema_version"],
            )
        except MSACoreSerializationError:
            raise
        except _ROUNDTRIP_ERRORS as exc:
            raise MSACoreSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc


def build_run_report(
    config: MSACoreConfig,
    resonance_history: ResonanceFrameHistory,
    score_history: ResonanceScoreHistory,
    active_box_history: ActiveBoxSelectionHistory,
) -> MSACoreRunReport:
    final_snapshot = active_box_history.final_frame.active_box_snapshot
    created = sum(
        event.event_type is ActiveBoxEventType.CREATED
        for event in active_box_history.events
    )
    frozen = sum(
        event.event_type is ActiveBoxEventType.FROZEN
        for event in active_box_history.events
    )
    active_count = sum(
        frame.active_box_snapshot is not None
        for frame in active_box_history.frames
    )
    return MSACoreRunReport(
        start_time=resonance_history.frames[0].as_of_time,
        end_time=resonance_history.frames[-1].as_of_time,
        frame_count=len(resonance_history.frames),
        score_frame_count=len(score_history.frames),
        selection_frame_count=len(active_box_history.frames),
        evidence_count=sum(
            len(frame.evidence) for frame in resonance_history.frames
        ),
        zone_count=sum(len(frame.zones) for frame in score_history.frames),
        created_event_count=created,
        frozen_event_count=frozen,
        frozen_box_count=len(active_box_history.frozen_boxes),
        active_box_frame_count=active_count,
        no_box_frame_count=len(active_box_history.frames) - active_count,
        final_has_active_box=final_snapshot is not None,
        final_active_box_key_id=(
            None if final_snapshot is None else final_snapshot.box_key_id
        ),
        frame_engine_id=config.frame_config.engine_id,
        scoring_engine_id=config.scoring_config.engine_id,
        active_box_engine_id=config.active_box_config.engine_id,
        integration_engine_id=config.engine_id,
        assumptions=_REPORT_ASSUMPTIONS,
        warnings=(),
        errors=(),
    )


@dataclass(frozen=True, slots=True)
class MSACoreRun:
    run_id: str
    source_input: ResonanceFrameInput
    processing_times: tuple[datetime, ...]
    resonance_history: ResonanceFrameHistory
    score_history: ResonanceScoreHistory
    active_box_history: ActiveBoxSelectionHistory
    frame_bundles: tuple[MSACoreFrameBundle, ...]
    final_bundle: MSACoreFrameBundle
    report: MSACoreRunReport
    config_snapshot: MSACoreConfig
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def _digest_ids(self) -> tuple[str, str, str, str]:
        return (
            semantic_id(
                "msa-core-source-input-v1-", self.source_input.to_dict()
            ),
            semantic_id(
                "msa-core-resonance-history-v1-",
                self.resonance_history.to_dict(),
            ),
            semantic_id(
                "msa-core-score-history-v1-", self.score_history.to_dict()
            ),
            semantic_id(
                "msa-core-active-box-history-v1-",
                self.active_box_history.to_dict(),
            ),
        )

    def _identity_payload(self) -> dict[str, object]:
        source_id, resonance_id, score_id, active_id = self._digest_ids()
        return {
            "config_snapshot": self.config_snapshot.to_dict(),
            "source_input_digest_id": source_id,
            "processing_times": [
                item.isoformat() for item in self.processing_times
            ],
            "resonance_history_digest_id": resonance_id,
            "score_history_digest_id": score_id,
            "active_box_history_digest_id": active_id,
            "bundle_ids": [item.bundle_id for item in self.frame_bundles],
            "report": self.report.to_dict(),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, MSACoreIntegrationError)
        _formal_roundtrip(
            self.config_snapshot,
            MSACoreConfig,
            "config_snapshot",
            MSACoreIntegrationError,
        )
        canonical_source = validate_source_input(
            self.source_input, self.config_snapshot
        )
        object.__setattr__(self, "source_input", canonical_source)
        _formal_roundtrip(
            self.resonance_history,
            ResonanceFrameHistory,
            "resonance_history",
            MSACoreIntegrationError,
        )
        _formal_roundtrip(
            self.score_history,
            ResonanceScoreHistory,
            "score_history",
            MSACoreIntegrationError,
        )
        _formal_roundtrip(
            self.active_box_history,
            ActiveBoxSelectionHistory,
            "active_box_history",
            MSACoreIntegrationError,
        )
        if not isinstance(self.processing_times, tuple) or not self.processing_times:
            raise MSACoreIntegrationError(
                "processing_times must be a non-empty tuple"
            )
        normalized_times = tuple(
            _time(item, f"processing_times[{index}]", MSACoreIntegrationError)
            for index, item in enumerate(self.processing_times)
        )
        if any(
            current <= previous
            for previous, current in zip(
                normalized_times, normalized_times[1:]
            )
        ):
            raise MSACoreIntegrationError(
                "processing_times must be strictly increasing and unique"
            )
        object.__setattr__(self, "processing_times", normalized_times)
        if normalized_times != tuple(
            frame.as_of_time for frame in self.resonance_history.frames
        ):
            raise MSACoreIntegrationError(
                "processing_times must exactly match ResonanceFrame AsOf values"
            )
        if (
            self.resonance_history.config_snapshot
            != self.config_snapshot.frame_config
            or self.score_history.config_snapshot
            != self.config_snapshot.scoring_config
            or self.active_box_history.config_snapshot
            != self.config_snapshot.active_box_config
        ):
            raise MSACoreIntegrationError(
                "Run History configs must equal MSACoreConfig child configs"
            )
        if self.score_history.source_history != self.resonance_history:
            raise MSACoreIntegrationError(
                "ScoreHistory.source_history must equal ResonanceHistory"
            )
        if (
            self.active_box_history.source_score_history
            != self.score_history
        ):
            raise MSACoreIntegrationError(
                "ActiveBoxHistory source must equal ScoreHistory"
            )
        if (
            not isinstance(self.frame_bundles, tuple)
            or not self.frame_bundles
            or any(
                not isinstance(item, MSACoreFrameBundle)
                for item in self.frame_bundles
            )
        ):
            raise MSACoreIntegrationError(
                "frame_bundles must be a non-empty MSACoreFrameBundle tuple"
            )
        if len(self.frame_bundles) != len(normalized_times):
            raise MSACoreIntegrationError(
                "Run must contain one Bundle per processing time"
            )
        for index, bundle in enumerate(self.frame_bundles):
            if bundle.config_snapshot != self.config_snapshot:
                raise MSACoreIntegrationError(
                    "Bundle config must equal Run config"
                )
            if (
                bundle.as_of_time != normalized_times[index]
                or bundle.resonance_frame
                != self.resonance_history.frames[index]
                or bundle.score_frame != self.score_history.frames[index]
                or bundle.selection_frame
                != self.active_box_history.frames[index]
            ):
                raise MSACoreIntegrationError(
                    "Bundle index must map exactly across all Histories"
                )
        if (
            not isinstance(self.final_bundle, MSACoreFrameBundle)
            or self.final_bundle != self.frame_bundles[-1]
        ):
            raise MSACoreIntegrationError(
                "final_bundle must equal frame_bundles[-1]"
            )
        expected_report = build_run_report(
            self.config_snapshot,
            self.resonance_history,
            self.score_history,
            self.active_box_history,
        )
        if (
            not isinstance(self.report, MSACoreRunReport)
            or self.report != expected_report
        ):
            raise MSACoreIntegrationError(
                "Run report must exactly recompute from authoritative Histories"
            )
        require_semantic_id(
            self.run_id,
            prefix="msa-core-run-v1-",
            payload=self._identity_payload(),
            field_name="run_id",
            error_type=MSACoreIntegrationError,
        )
        source_id, resonance_id, score_id, active_id = self._digest_ids()
        _validate_provenance(
            self.provenance,
            object_name=name,
            object_id=self.run_id,
            config=self.config_snapshot,
            parents=(
                source_id,
                resonance_id,
                score_id,
                active_id,
                self.final_bundle.bundle_id,
                f"msa-core-report-v1-{digest(self.report.to_dict())}",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "source_input": self.source_input.to_dict(),
            "processing_times": [
                item.isoformat() for item in self.processing_times
            ],
            "resonance_history": self.resonance_history.to_dict(),
            "score_history": self.score_history.to_dict(),
            "active_box_history": self.active_box_history.to_dict(),
            "frame_bundles": [
                item.to_dict() for item in self.frame_bundles
            ],
            "final_bundle": self.final_bundle.to_dict(),
            "report": self.report.to_dict(),
            "config_snapshot": self.config_snapshot.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MSACoreRun:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                run_id=data["run_id"],
                source_input=ResonanceFrameInput.from_dict(
                    data["source_input"]
                ),
                processing_times=tuple(
                    _parse_time(item, f"processing_times[{index}]")
                    for index, item in enumerate(
                        _ordered_list(
                            data, cls.__name__, "processing_times"
                        )
                    )
                ),
                resonance_history=ResonanceFrameHistory.from_dict(
                    data["resonance_history"]
                ),
                score_history=ResonanceScoreHistory.from_dict(
                    data["score_history"]
                ),
                active_box_history=ActiveBoxSelectionHistory.from_dict(
                    data["active_box_history"]
                ),
                frame_bundles=tuple(
                    MSACoreFrameBundle.from_dict(item)
                    for item in _ordered_list(
                        data, cls.__name__, "frame_bundles"
                    )
                ),
                final_bundle=MSACoreFrameBundle.from_dict(
                    data["final_bundle"]
                ),
                report=MSACoreRunReport.from_dict(data["report"]),
                config_snapshot=MSACoreConfig.from_dict(
                    data["config_snapshot"]
                ),
                provenance=ProvenanceRef.from_dict(data["provenance"]),
                schema_version=data["schema_version"],
            )
        except MSACoreSerializationError:
            raise
        except _ROUNDTRIP_ERRORS as exc:
            raise MSACoreSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc
