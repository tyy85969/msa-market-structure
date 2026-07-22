"""Immutable C-007C Active Box selection and history contracts.

This module validates caller-supplied facts.  It deliberately does not iterate
``ResonanceScoreHistory`` or implement the C-007C state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping, Self

from msa.data import Timeframe
from msa.domain import (
    ActiveBox,
    ActiveBoxStatus,
    BoundarySide,
    ProvenanceRef,
    ScaleDescriptor,
    StructureCluster,
)
from msa.research.resonance import (
    ResonanceClass,
    ResonancePriceRelation,
    ResonanceScoreFrame,
    ResonanceScoreHistory,
)

from .errors import (
    ActiveBoxConfigurationError,
    ActiveBoxContractError,
    ActiveBoxSerializationError,
)
from .identity import require_semantic_id, semantic_id


SCHEMA_VERSION = 1
_CONTRACT_MODULE = "msa.research.active_box.contracts"
_POLICY_MODULE = "msa.research.active_box.policy"
_PROJECTION_MODULE = "msa.research.active_box.projection"


def _exact(payload: Mapping[str, Any], name: str, names: set[str]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ActiveBoxSerializationError(f"{name} payload must be a mapping")
    expected = names | {"schema_version"}
    missing, unknown = expected - set(payload), set(payload) - expected
    if missing:
        raise ActiveBoxSerializationError(f"{name} payload missing fields: {sorted(missing)}")
    if unknown:
        raise ActiveBoxSerializationError(f"{name} payload has unknown fields: {sorted(unknown)}")
    _schema(payload["schema_version"], name, ActiveBoxSerializationError)
    return payload


def _schema(value: object, name: str, error: type[Exception]) -> int:
    if isinstance(value, bool) or value != SCHEMA_VERSION:
        raise error(f"{name}.schema_version must be {SCHEMA_VERSION}")
    return SCHEMA_VERSION


def _text(value: object, field: str, error: type[Exception] = ActiveBoxContractError) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error(f"{field} must be a non-empty string")
    return value


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _decimal(value: object, field: str, *, non_negative: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ActiveBoxContractError(f"{field} must be a finite Decimal")
    if non_negative and value < 0:
        raise ActiveBoxContractError(f"{field} must be >= 0")
    return value


def _parse_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ActiveBoxSerializationError(f"{field} must be a Decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ActiveBoxSerializationError(f"{field} must be a Decimal string") from exc
    if not result.is_finite():
        raise ActiveBoxSerializationError(f"{field} must be finite")
    return result


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ActiveBoxContractError(f"{field} must be an aware datetime")
    return value.astimezone(timezone.utc)


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ActiveBoxSerializationError(f"{field} must be an aware ISO-8601 string")
    try:
        return _time(datetime.fromisoformat(value), field)
    except (ValueError, ActiveBoxContractError) as exc:
        raise ActiveBoxSerializationError(f"{field} must be an aware ISO-8601 string") from exc


def _ordered(payload: Mapping[str, Any], name: str, field: str) -> list[Any]:
    value = payload[field]
    if not isinstance(value, list):
        raise ActiveBoxSerializationError(f"{name}.{field} must be an ordered list")
    return value


def _string_tuple(value: object, field: str, *, unique: bool = False, canonical: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ActiveBoxContractError(f"{field} must be a tuple")
    result = tuple(_text(item, f"{field}[{index}]") for index, item in enumerate(value))
    if unique and len(set(result)) != len(result):
        raise ActiveBoxContractError(f"{field} must contain unique values")
    if canonical and result != tuple(sorted(result)):
        raise ActiveBoxContractError(f"{field} must be canonical")
    return result


def _engine_id(provenance: ProvenanceRef, name: str) -> str:
    values = tuple(note[10:] for note in provenance.notes if note.startswith("engine_id="))
    if len(values) != 1 or not values[0]:
        raise ActiveBoxContractError(f"{name} provenance must contain exactly one engine_id note")
    return values[0]


def _provenance(
    value: object,
    *,
    name: str,
    module: str,
    version: str,
    object_id: str,
    policy_id: str,
    engine_id: str,
    parents: tuple[str, ...],
) -> ProvenanceRef:
    if not isinstance(value, ProvenanceRef):
        raise ActiveBoxContractError(f"{name}.provenance must be a ProvenanceRef")
    expected = tuple(sorted(set(parents)))
    if (
        value.source_module != module
        or value.source_version != version
        or value.source_object_id != object_id
        or value.policy_id != policy_id
        or value.parent_object_ids != expected
        or value.notes != (f"engine_id={engine_id}",)
    ):
        raise ActiveBoxContractError(f"{name}.provenance is inconsistent")
    return value


class _ActiveBoxEnum(str, Enum):
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": SCHEMA_VERSION, "value": self.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _exact(payload, cls.__name__, {"value"})
        try:
            return cls(data["value"])
        except (TypeError, ValueError) as exc:
            raise ActiveBoxSerializationError(f"{cls.__name__}.value is unknown") from exc


class ActiveBoxSelectionPolicy(_ActiveBoxEnum):
    NEAREST_QUALIFIED_WITH_HYSTERESIS = "NEAREST_QUALIFIED_WITH_HYSTERESIS"


class ActiveBoxReplacementDistanceMode(_ActiveBoxEnum):
    ABSOLUTE = "ABSOLUTE"
    REFERENCE_FRACTION = "REFERENCE_FRACTION"


class ZoneEligibilityReason(_ActiveBoxEnum):
    PRICE_RELATION_NOT_EXPECTED = "PRICE_RELATION_NOT_EXPECTED"
    RESONANCE_CLASS_NOT_ALLOWED = "RESONANCE_CLASS_NOT_ALLOWED"
    QUALITY_BELOW_MINIMUM = "QUALITY_BELOW_MINIMUM"
    SELECTION_BELOW_MINIMUM = "SELECTION_BELOW_MINIMUM"
    DISTANCE_FACTOR_NOT_POSITIVE = "DISTANCE_FACTOR_NOT_POSITIVE"


class ActiveBoxSideAction(_ActiveBoxEnum):
    NONE = "NONE"
    SELECT = "SELECT"
    RETAIN = "RETAIN"
    REPLACE = "REPLACE"
    CLEAR = "CLEAR"


class ActiveBoxEventType(_ActiveBoxEnum):
    CREATED = "CREATED"
    FROZEN = "FROZEN"


class ActiveBoxEventReason(_ActiveBoxEnum):
    INITIAL_PAIR = "INITIAL_PAIR"
    PAIR_CHANGED = "PAIR_CHANGED"
    PAIR_UNAVAILABLE = "PAIR_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ActiveBoxSelectionConfig:
    engine_id: str
    engine_version: str
    policy_id: str
    symbol: str
    output_timeframe: Timeframe
    output_scale: ScaleDescriptor
    selection_policy: ActiveBoxSelectionPolicy
    minimum_quality_score: Decimal
    minimum_selection_score: Decimal
    allowed_resonance_classes: tuple[ResonanceClass, ...]
    replacement_distance_mode: ActiveBoxReplacementDistanceMode
    absolute_replacement_distance_margin: Decimal | None
    reference_replacement_distance_fraction: Decimal | None
    minimum_replacement_selection_score_improvement: Decimal
    require_expected_side: bool = True
    require_positive_distance_factor: bool = True
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ActiveBoxConfigurationError)
        for field in ("engine_id", "engine_version", "policy_id", "symbol"):
            _text(getattr(self, field), f"{name}.{field}", ActiveBoxConfigurationError)
        if not isinstance(self.output_timeframe, Timeframe) or not isinstance(self.output_scale, ScaleDescriptor):
            raise ActiveBoxConfigurationError("output timeframe/scale must be explicit")
        if self.selection_policy is not ActiveBoxSelectionPolicy.NEAREST_QUALIFIED_WITH_HYSTERESIS:
            raise ActiveBoxConfigurationError("unsupported Active Box selection policy")
        try:
            _decimal(self.minimum_quality_score, "minimum_quality_score", non_negative=True)
            _decimal(self.minimum_selection_score, "minimum_selection_score", non_negative=True)
            _decimal(self.minimum_replacement_selection_score_improvement, "minimum_replacement_selection_score_improvement", non_negative=True)
        except ActiveBoxContractError as exc:
            raise ActiveBoxConfigurationError(str(exc)) from exc
        allowed = self.allowed_resonance_classes
        if not isinstance(allowed, tuple) or not allowed:
            raise ActiveBoxConfigurationError("allowed_resonance_classes must be a non-empty tuple")
        if any(not isinstance(item, ResonanceClass) for item in allowed):
            raise ActiveBoxConfigurationError("allowed_resonance_classes contains an invalid class")
        if len(set(allowed)) != len(allowed):
            raise ActiveBoxConfigurationError("allowed_resonance_classes must be unique")
        canonical = tuple(sorted(allowed, key=lambda item: item.value))
        if allowed != canonical:
            raise ActiveBoxConfigurationError("allowed_resonance_classes must be canonical")
        try:
            if self.replacement_distance_mode is ActiveBoxReplacementDistanceMode.ABSOLUTE:
                _decimal(self.absolute_replacement_distance_margin, "absolute_replacement_distance_margin", non_negative=True)
                if self.reference_replacement_distance_fraction is not None:
                    raise ActiveBoxConfigurationError("reference fraction must be None in ABSOLUTE mode")
            elif self.replacement_distance_mode is ActiveBoxReplacementDistanceMode.REFERENCE_FRACTION:
                _decimal(self.reference_replacement_distance_fraction, "reference_replacement_distance_fraction", non_negative=True)
                if self.absolute_replacement_distance_margin is not None:
                    raise ActiveBoxConfigurationError("absolute margin must be None in REFERENCE_FRACTION mode")
            else:
                raise ActiveBoxConfigurationError("replacement_distance_mode is invalid")
        except ActiveBoxContractError as exc:
            raise ActiveBoxConfigurationError(str(exc)) from exc
        if self.require_expected_side is not True or self.require_positive_distance_factor is not True or self.strict is not True:
            raise ActiveBoxConfigurationError("C-007C requires expected-side, positive-distance, strict mode")

    def effective_distance_margin(self, reference_price: Decimal) -> Decimal:
        price = _decimal(reference_price, "reference_price", non_negative=True)
        if self.replacement_distance_mode is ActiveBoxReplacementDistanceMode.ABSOLUTE:
            return self.absolute_replacement_distance_margin  # type: ignore[return-value]
        return price * self.reference_replacement_distance_fraction  # type: ignore[operator]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id, "engine_version": self.engine_version,
            "policy_id": self.policy_id, "symbol": self.symbol,
            "output_timeframe": self.output_timeframe.value,
            "output_scale": self.output_scale.to_dict(),
            "selection_policy": self.selection_policy.value,
            "minimum_quality_score": str(self.minimum_quality_score),
            "minimum_selection_score": str(self.minimum_selection_score),
            "allowed_resonance_classes": [item.value for item in self.allowed_resonance_classes],
            "replacement_distance_mode": self.replacement_distance_mode.value,
            "absolute_replacement_distance_margin": None if self.absolute_replacement_distance_margin is None else str(self.absolute_replacement_distance_margin),
            "reference_replacement_distance_fraction": None if self.reference_replacement_distance_fraction is None else str(self.reference_replacement_distance_fraction),
            "minimum_replacement_selection_score_improvement": str(self.minimum_replacement_selection_score_improvement),
            "require_expected_side": self.require_expected_side,
            "require_positive_distance_factor": self.require_positive_distance_factor,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ActiveBoxSelectionConfig:
        names = {field.name for field in fields(cls)} - {"schema_version"}
        data = _exact(payload, cls.__name__, names)
        def optional_decimal(name: str) -> Decimal | None:
            return None if data[name] is None else _parse_decimal(data[name], name)
        try:
            return cls(
                engine_id=data["engine_id"], engine_version=data["engine_version"],
                policy_id=data["policy_id"], symbol=data["symbol"],
                output_timeframe=Timeframe(data["output_timeframe"]),
                output_scale=ScaleDescriptor.from_dict(data["output_scale"]),
                selection_policy=ActiveBoxSelectionPolicy(data["selection_policy"]),
                minimum_quality_score=_parse_decimal(data["minimum_quality_score"], "minimum_quality_score"),
                minimum_selection_score=_parse_decimal(data["minimum_selection_score"], "minimum_selection_score"),
                allowed_resonance_classes=tuple(ResonanceClass(item) for item in _ordered(data, cls.__name__, "allowed_resonance_classes")),
                replacement_distance_mode=ActiveBoxReplacementDistanceMode(data["replacement_distance_mode"]),
                absolute_replacement_distance_margin=optional_decimal("absolute_replacement_distance_margin"),
                reference_replacement_distance_fraction=optional_decimal("reference_replacement_distance_fraction"),
                minimum_replacement_selection_score_improvement=_parse_decimal(data["minimum_replacement_selection_score_improvement"], "minimum_replacement_selection_score_improvement"),
                require_expected_side=data["require_expected_side"],
                require_positive_distance_factor=data["require_positive_distance_factor"],
                strict=data["strict"], schema_version=data["schema_version"],
            )
        except ActiveBoxSerializationError:
            raise
        except (TypeError, ValueError, ActiveBoxContractError) as exc:
            raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ZoneEligibility:
    zone_key_id: str
    zone_snapshot_id: str
    side: BoundarySide
    resonance_class: ResonanceClass
    price_relation: ResonancePriceRelation
    quality_score: Decimal
    selection_score: Decimal
    distance: Decimal
    distance_factor: Decimal
    side_rank: int
    eligible: bool
    reasons: tuple[ZoneEligibilityReason, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ActiveBoxContractError)
        _text(self.zone_key_id, "zone_key_id"); _text(self.zone_snapshot_id, "zone_snapshot_id")
        if not isinstance(self.side, BoundarySide) or not isinstance(self.resonance_class, ResonanceClass) or not isinstance(self.price_relation, ResonancePriceRelation):
            raise ActiveBoxContractError("ZoneEligibility enum fact is invalid")
        for name in ("quality_score", "selection_score", "distance", "distance_factor"):
            _decimal(getattr(self, name), name)
        if isinstance(self.side_rank, bool) or not isinstance(self.side_rank, int) or self.side_rank < 1:
            raise ActiveBoxContractError("side_rank must be an integer >= 1")
        if not isinstance(self.eligible, bool) or not isinstance(self.reasons, tuple) or any(not isinstance(item, ZoneEligibilityReason) for item in self.reasons):
            raise ActiveBoxContractError("ZoneEligibility eligible/reasons are invalid")
        canonical = tuple(item for item in ZoneEligibilityReason if item in self.reasons)
        if self.reasons != canonical or len(set(self.reasons)) != len(self.reasons):
            raise ActiveBoxContractError("eligibility reasons must use fixed canonical order")
        if self.eligible != (not self.reasons):
            raise ActiveBoxContractError("eligible must be exactly equivalent to empty reasons")

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "zone_key_id": self.zone_key_id,
            "zone_snapshot_id": self.zone_snapshot_id, "side": self.side.value,
            "resonance_class": self.resonance_class.value, "price_relation": self.price_relation.value,
            "quality_score": str(self.quality_score), "selection_score": str(self.selection_score),
            "distance": str(self.distance), "distance_factor": str(self.distance_factor),
            "side_rank": self.side_rank, "eligible": self.eligible,
            "reasons": [item.value for item in self.reasons]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ZoneEligibility:
        names = {field.name for field in fields(cls)} - {"schema_version"}; data = _exact(payload, cls.__name__, names)
        try:
            return cls(zone_key_id=data["zone_key_id"], zone_snapshot_id=data["zone_snapshot_id"],
                side=BoundarySide(data["side"]), resonance_class=ResonanceClass(data["resonance_class"]),
                price_relation=ResonancePriceRelation(data["price_relation"]),
                quality_score=_parse_decimal(data["quality_score"], "quality_score"),
                selection_score=_parse_decimal(data["selection_score"], "selection_score"),
                distance=_parse_decimal(data["distance"], "distance"),
                distance_factor=_parse_decimal(data["distance_factor"], "distance_factor"),
                side_rank=data["side_rank"], eligible=data["eligible"],
                reasons=tuple(ZoneEligibilityReason(item) for item in _ordered(data, cls.__name__, "reasons")),
                schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError, ValueError, ActiveBoxContractError) as exc:
            raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ActiveBoxSelectionKey:
    distance: Decimal
    selection_score: Decimal
    quality_score: Decimal
    distinct_context_count: int
    distinct_source_type_count: int
    latest_evidence_confirm_time: datetime
    zone_key_id: str
    zone_snapshot_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version, type(self).__name__, ActiveBoxContractError)
        for name in ("distance", "selection_score", "quality_score"): _decimal(getattr(self, name), name)
        for name in ("distinct_context_count", "distinct_source_type_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1: raise ActiveBoxContractError(f"{name} must be >= 1")
        object.__setattr__(self, "latest_evidence_confirm_time", _time(self.latest_evidence_confirm_time, "latest_evidence_confirm_time"))
        _text(self.zone_key_id, "zone_key_id"); _text(self.zone_snapshot_id, "zone_snapshot_id")

    @property
    def sort_key(self) -> tuple[object, ...]:
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = self.latest_evidence_confirm_time - epoch
        micros = delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
        return (self.distance, -self.selection_score, -self.quality_score,
            -self.distinct_context_count, -self.distinct_source_type_count,
            -micros, self.zone_key_id, self.zone_snapshot_id)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "distance": str(self.distance),
            "selection_score": str(self.selection_score), "quality_score": str(self.quality_score),
            "distinct_context_count": self.distinct_context_count,
            "distinct_source_type_count": self.distinct_source_type_count,
            "latest_evidence_confirm_time": self.latest_evidence_confirm_time.isoformat(),
            "zone_key_id": self.zone_key_id, "zone_snapshot_id": self.zone_snapshot_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ActiveBoxSelectionKey:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            return cls(distance=_parse_decimal(data["distance"],"distance"), selection_score=_parse_decimal(data["selection_score"],"selection_score"),
                quality_score=_parse_decimal(data["quality_score"],"quality_score"), distinct_context_count=data["distinct_context_count"],
                distinct_source_type_count=data["distinct_source_type_count"], latest_evidence_confirm_time=_parse_time(data["latest_evidence_confirm_time"],"latest_evidence_confirm_time"),
                zone_key_id=data["zone_key_id"], zone_snapshot_id=data["zone_snapshot_id"], schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError, ValueError, ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ActiveBoxSideDecision:
    decision_id: str
    source_score_frame_id: str
    as_of_time: datetime
    side: BoundarySide
    action: ActiveBoxSideAction
    current_zone_key_id: str | None
    current_zone_snapshot_id: str | None
    selected_zone_key_id: str | None
    selected_zone_snapshot_id: str | None
    zone_evaluations: tuple[ZoneEligibility, ...]
    eligible_zone_key_ids_in_order: tuple[str, ...]
    challenger_zone_key_id: str | None
    effective_distance_margin: Decimal
    required_selection_score_improvement: Decimal
    distance_gain: Decimal | None
    selection_gain: Decimal | None
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {"source_score_frame_id":self.source_score_frame_id,"as_of_time":self.as_of_time.isoformat(),"side":self.side.value,
            "action":self.action.value,"current_zone_key_id":self.current_zone_key_id,"current_zone_snapshot_id":self.current_zone_snapshot_id,
            "selected_zone_key_id":self.selected_zone_key_id,"selected_zone_snapshot_id":self.selected_zone_snapshot_id,
            "zone_evaluations":[item.to_dict() for item in self.zone_evaluations],"eligible_zone_key_ids_in_order":list(self.eligible_zone_key_ids_in_order),
            "challenger_zone_key_id":self.challenger_zone_key_id,"effective_distance_margin":str(self.effective_distance_margin),
            "required_selection_score_improvement":str(self.required_selection_score_improvement),"distance_gain":None if self.distance_gain is None else str(self.distance_gain),
            "selection_gain":None if self.selection_gain is None else str(self.selection_gain),"schema_version":self.schema_version}

    def __post_init__(self) -> None:
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError); _text(self.source_score_frame_id,"source_score_frame_id")
        object.__setattr__(self,"as_of_time",_time(self.as_of_time,"as_of_time"))
        if not isinstance(self.side,BoundarySide) or not isinstance(self.action,ActiveBoxSideAction): raise ActiveBoxContractError("decision side/action invalid")
        for field_name in ("current_zone_key_id","current_zone_snapshot_id","selected_zone_key_id","selected_zone_snapshot_id","challenger_zone_key_id"): _optional_text(getattr(self,field_name),field_name)
        if not isinstance(self.zone_evaluations,tuple) or any(not isinstance(item,ZoneEligibility) for item in self.zone_evaluations): raise ActiveBoxContractError("zone_evaluations must be a tuple")
        if any(item.side is not self.side for item in self.zone_evaluations): raise ActiveBoxContractError("decision cannot reference the other side")
        if len({item.zone_key_id for item in self.zone_evaluations})!=len(self.zone_evaluations): raise ActiveBoxContractError("each side Zone must have exactly one evaluation")
        eligible=_string_tuple(self.eligible_zone_key_ids_in_order,"eligible_zone_key_ids_in_order",unique=True)
        actual={item.zone_key_id for item in self.zone_evaluations if item.eligible}
        if set(eligible)!=actual: raise ActiveBoxContractError("eligible ordering must exactly cover eligible evaluations")
        _decimal(self.effective_distance_margin,"effective_distance_margin",non_negative=True); _decimal(self.required_selection_score_improvement,"required_selection_score_improvement",non_negative=True)
        for gain in ("distance_gain","selection_gain"):
            if getattr(self,gain) is not None: _decimal(getattr(self,gain),gain)
        selected=self.selected_zone_key_id
        if self.action in (ActiveBoxSideAction.SELECT,ActiveBoxSideAction.REPLACE) and selected is None: raise ActiveBoxContractError("SELECT/REPLACE requires a selected Zone")
        if self.action is ActiveBoxSideAction.RETAIN and (selected is None or selected!=self.current_zone_key_id): raise ActiveBoxContractError("RETAIN must select current stable zone_key")
        if self.action in (ActiveBoxSideAction.NONE,ActiveBoxSideAction.CLEAR) and (selected is not None or self.selected_zone_snapshot_id is not None): raise ActiveBoxContractError("NONE/CLEAR cannot select a Zone")
        if (selected is None)!=(self.selected_zone_snapshot_id is None): raise ActiveBoxContractError("selected key/snapshot must be both present or absent")
        require_semantic_id(self.decision_id,"active-box-decision-v1-",self._identity_payload(),"decision_id",ActiveBoxContractError)
        engine=_engine_id(self.provenance,name)
        _provenance(self.provenance,name=name,module=_POLICY_MODULE,version=self.provenance.source_version,object_id=self.decision_id,
            policy_id=self.provenance.policy_id or "",engine_id=engine,parents=(self.source_score_frame_id,))

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"decision_id":self.decision_id,**{k:v for k,v in self._identity_payload().items() if k!="schema_version"},"provenance":self.provenance.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxSideDecision:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            def optdec(n:str)->Decimal|None: return None if data[n] is None else _parse_decimal(data[n],n)
            return cls(decision_id=data["decision_id"],source_score_frame_id=data["source_score_frame_id"],as_of_time=_parse_time(data["as_of_time"],"as_of_time"),
                side=BoundarySide(data["side"]),action=ActiveBoxSideAction(data["action"]),current_zone_key_id=data["current_zone_key_id"],current_zone_snapshot_id=data["current_zone_snapshot_id"],
                selected_zone_key_id=data["selected_zone_key_id"],selected_zone_snapshot_id=data["selected_zone_snapshot_id"],
                zone_evaluations=tuple(ZoneEligibility.from_dict(item) for item in _ordered(data,cls.__name__,"zone_evaluations")),
                eligible_zone_key_ids_in_order=tuple(_ordered(data,cls.__name__,"eligible_zone_key_ids_in_order")),challenger_zone_key_id=data["challenger_zone_key_id"],
                effective_distance_margin=_parse_decimal(data["effective_distance_margin"],"effective_distance_margin"),
                required_selection_score_improvement=_parse_decimal(data["required_selection_score_improvement"],"required_selection_score_improvement"),
                distance_gain=optdec("distance_gain"),selection_gain=optdec("selection_gain"),provenance=ProvenanceRef.from_dict(data["provenance"]),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ActiveBoxZoneProjection:
    projection_id: str
    source_score_frame_id: str
    source_zone_key_id: str
    source_zone_snapshot_id: str
    selection_confirm_time: datetime
    cluster: StructureCluster
    boundary: object
    provenance: ProvenanceRef
    config_snapshot: ActiveBoxSelectionConfig
    member_evidence_ids: tuple[str, ...]
    member_boundary_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "config": self.config_snapshot.to_dict(), "source_score_frame_id": self.source_score_frame_id,
            "source_zone_key_id": self.source_zone_key_id, "source_zone_snapshot_id": self.source_zone_snapshot_id,
            "selection_confirm_time": self.selection_confirm_time.isoformat(), "cluster": self.cluster.to_dict(),
            "boundary": self.boundary.to_dict(), "member_evidence_ids": list(self.member_evidence_ids),
            "member_boundary_ids": list(self.member_boundary_ids), "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        from msa.domain import BoundaryRef, LifecycleState, StructureObjectKind
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError)
        for item in ("source_score_frame_id","source_zone_key_id","source_zone_snapshot_id"): _text(getattr(self,item),item)
        object.__setattr__(self,"selection_confirm_time",_time(self.selection_confirm_time,"selection_confirm_time"))
        if not isinstance(self.config_snapshot,ActiveBoxSelectionConfig) or not isinstance(self.cluster,StructureCluster) or not isinstance(self.boundary,BoundaryRef):
            raise ActiveBoxContractError("projection config/cluster/boundary type is invalid")
        if self.boundary != self.cluster.to_boundary_ref() or self.boundary.object_kind is not StructureObjectKind.STRUCTURE_CLUSTER:
            raise ActiveBoxContractError("projection boundary must exactly equal cluster.to_boundary_ref()")
        if self.cluster.lifecycle_state is not LifecycleState.CONFIRMED or self.cluster.confirm_time != self.selection_confirm_time:
            raise ActiveBoxContractError("projection cluster must be aggregate CONFIRMED at selection time")
        if self.cluster.symbol != self.config_snapshot.symbol or self.cluster.timeframe is not self.config_snapshot.output_timeframe or self.cluster.scale != self.config_snapshot.output_scale:
            raise ActiveBoxContractError("projection output context must equal explicit config")
        evidence_ids=_string_tuple(self.member_evidence_ids,"member_evidence_ids",unique=True,canonical=True)
        boundary_ids=_string_tuple(self.member_boundary_ids,"member_boundary_ids",unique=True,canonical=True)
        if tuple(item.object_id for item in self.cluster.member_refs)!=boundary_ids:
            raise ActiveBoxContractError("projection member Boundary IDs must exactly cover cluster members")
        if any(item.confirm_time>self.selection_confirm_time for item in self.cluster.member_refs):
            raise ActiveBoxContractError("projection cannot include a future member")
        require_semantic_id(self.projection_id,"active-box-projection-v1-",self._identity_payload(),"projection_id",ActiveBoxContractError)
        parents=(self.source_score_frame_id,self.source_zone_snapshot_id,*evidence_ids,*boundary_ids)
        _provenance(self.provenance,name=name,module=_PROJECTION_MODULE,version=self.config_snapshot.engine_version,
            object_id=self.projection_id,policy_id=self.config_snapshot.policy_id,engine_id=self.config_snapshot.engine_id,parents=parents)

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"projection_id":self.projection_id,
            "source_score_frame_id":self.source_score_frame_id,"source_zone_key_id":self.source_zone_key_id,
            "source_zone_snapshot_id":self.source_zone_snapshot_id,"selection_confirm_time":self.selection_confirm_time.isoformat(),
            "cluster":self.cluster.to_dict(),"boundary":self.boundary.to_dict(),"provenance":self.provenance.to_dict(),
            "config_snapshot":self.config_snapshot.to_dict(),"member_evidence_ids":list(self.member_evidence_ids),
            "member_boundary_ids":list(self.member_boundary_ids)}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxZoneProjection:
        from msa.domain import BoundaryRef
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            return cls(projection_id=data["projection_id"],source_score_frame_id=data["source_score_frame_id"],source_zone_key_id=data["source_zone_key_id"],
                source_zone_snapshot_id=data["source_zone_snapshot_id"],selection_confirm_time=_parse_time(data["selection_confirm_time"],"selection_confirm_time"),
                cluster=StructureCluster.from_dict(data["cluster"]),boundary=BoundaryRef.from_dict(data["boundary"]),provenance=ProvenanceRef.from_dict(data["provenance"]),
                config_snapshot=ActiveBoxSelectionConfig.from_dict(data["config_snapshot"]),member_evidence_ids=tuple(_ordered(data,cls.__name__,"member_evidence_ids")),
                member_boundary_ids=tuple(_ordered(data,cls.__name__,"member_boundary_ids")),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


def _box_key_payload(config: ActiveBoxSelectionConfig, created_time: datetime, lower: ActiveBoxZoneProjection, upper: ActiveBoxZoneProjection, selection_price: Decimal) -> dict[str, object]:
    return {"engine_id":config.engine_id,"engine_version":config.engine_version,"policy_id":config.policy_id,
        "created_time":created_time.isoformat(),"symbol":config.symbol,"output_timeframe":config.output_timeframe.value,
        "output_scale":config.output_scale.to_dict(),"lower_zone_key_id":lower.source_zone_key_id,"upper_zone_key_id":upper.source_zone_key_id,
        "lower_projection_id":lower.projection_id,"upper_projection_id":upper.projection_id,"selection_price":str(selection_price),"schema_version":SCHEMA_VERSION}


@dataclass(frozen=True, slots=True)
class ActiveBoxSnapshot:
    box_key_id: str
    box_snapshot_id: str
    created_time: datetime
    source_score_frame_id: str
    observed_lower_zone_key_id: str
    observed_lower_zone_snapshot_id: str
    observed_upper_zone_key_id: str
    observed_upper_zone_snapshot_id: str
    lower_projection: ActiveBoxZoneProjection
    upper_projection: ActiveBoxZoneProjection
    active_box: ActiveBox
    provenance: ProvenanceRef
    config_snapshot: ActiveBoxSelectionConfig
    schema_version: int = SCHEMA_VERSION

    def _snapshot_payload(self)->dict[str,object]:
        return {"box_key_id":self.box_key_id,"source_score_frame_id":self.source_score_frame_id,"active_box":self.active_box.to_dict(),
            "observed_lower_zone_key_id":self.observed_lower_zone_key_id,"observed_lower_zone_snapshot_id":self.observed_lower_zone_snapshot_id,
            "observed_upper_zone_key_id":self.observed_upper_zone_key_id,"observed_upper_zone_snapshot_id":self.observed_upper_zone_snapshot_id,
            "status":self.active_box.status.value,"schema_version":self.schema_version}

    def __post_init__(self)->None:
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError)
        object.__setattr__(self,"created_time",_time(self.created_time,"created_time")); _text(self.source_score_frame_id,"source_score_frame_id")
        for n in ("observed_lower_zone_key_id","observed_lower_zone_snapshot_id","observed_upper_zone_key_id","observed_upper_zone_snapshot_id"): _text(getattr(self,n),n)
        if not isinstance(self.config_snapshot,ActiveBoxSelectionConfig) or not isinstance(self.lower_projection,ActiveBoxZoneProjection) or not isinstance(self.upper_projection,ActiveBoxZoneProjection) or not isinstance(self.active_box,ActiveBox):
            raise ActiveBoxContractError("ActiveBoxSnapshot nested type is invalid")
        if self.lower_projection.boundary.boundary_side is not BoundarySide.LOWER or self.upper_projection.boundary.boundary_side is not BoundarySide.UPPER:
            raise ActiveBoxContractError("snapshot projection sides are invalid")
        if self.observed_lower_zone_key_id!=self.lower_projection.source_zone_key_id or self.observed_upper_zone_key_id!=self.upper_projection.source_zone_key_id:
            raise ActiveBoxContractError("observed stable zone keys must match episode projections")
        expected_key=semantic_id("active-box-key-v1-",_box_key_payload(self.config_snapshot,self.created_time,self.lower_projection,self.upper_projection,self.active_box.selection_price))
        if self.box_key_id!=expected_key or self.active_box.box_id!=self.box_key_id: raise ActiveBoxContractError("box_key_id does not match stable episode identity")
        if self.active_box.status not in (ActiveBoxStatus.ACTIVE,ActiveBoxStatus.FROZEN): raise ActiveBoxContractError("C-007C supports ACTIVE/FROZEN only")
        if self.active_box.symbol!=self.config_snapshot.symbol or self.active_box.timeframe is not self.config_snapshot.output_timeframe or self.active_box.scale!=self.config_snapshot.output_scale:
            raise ActiveBoxContractError("Domain ActiveBox output context is inconsistent")
        if self.active_box.lower_boundary!=self.lower_projection.boundary or self.active_box.upper_boundary!=self.upper_projection.boundary:
            raise ActiveBoxContractError("Domain ActiveBox boundaries must equal projections")
        if self.active_box.origin_time!=min(self.active_box.lower_boundary.origin_time,self.active_box.upper_boundary.origin_time) or self.active_box.retired_time is not None:
            raise ActiveBoxContractError("Domain ActiveBox origin/retired facts are inconsistent")
        if self.active_box.status is ActiveBoxStatus.ACTIVE:
            if self.active_box.confirm_time!=self.created_time or self.active_box.frozen_time is not None: raise ActiveBoxContractError("ACTIVE box time facts are inconsistent")
        else:
            if self.active_box.confirm_time!=self.active_box.as_of_time or self.active_box.frozen_time!=self.active_box.confirm_time: raise ActiveBoxContractError("FROZEN box time facts are inconsistent")
        _provenance(self.active_box.provenance,name="ActiveBox",module=_CONTRACT_MODULE,version=self.config_snapshot.engine_version,
            object_id=self.box_key_id,policy_id=self.config_snapshot.policy_id,engine_id=self.config_snapshot.engine_id,
            parents=(self.lower_projection.boundary.object_id,self.upper_projection.boundary.object_id))
        require_semantic_id(self.box_snapshot_id,"active-box-snapshot-v1-",self._snapshot_payload(),"box_snapshot_id",ActiveBoxContractError)
        _provenance(self.provenance,name=name,module=_CONTRACT_MODULE,version=self.config_snapshot.engine_version,object_id=self.box_snapshot_id,
            policy_id=self.config_snapshot.policy_id,engine_id=self.config_snapshot.engine_id,parents=(self.source_score_frame_id,self.box_key_id,self.lower_projection.projection_id,self.upper_projection.projection_id))

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"box_key_id":self.box_key_id,"box_snapshot_id":self.box_snapshot_id,"created_time":self.created_time.isoformat(),
            "source_score_frame_id":self.source_score_frame_id,"observed_lower_zone_key_id":self.observed_lower_zone_key_id,"observed_lower_zone_snapshot_id":self.observed_lower_zone_snapshot_id,
            "observed_upper_zone_key_id":self.observed_upper_zone_key_id,"observed_upper_zone_snapshot_id":self.observed_upper_zone_snapshot_id,
            "lower_projection":self.lower_projection.to_dict(),"upper_projection":self.upper_projection.to_dict(),"active_box":self.active_box.to_dict(),
            "provenance":self.provenance.to_dict(),"config_snapshot":self.config_snapshot.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxSnapshot:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            return cls(box_key_id=data["box_key_id"],box_snapshot_id=data["box_snapshot_id"],created_time=_parse_time(data["created_time"],"created_time"),source_score_frame_id=data["source_score_frame_id"],
                observed_lower_zone_key_id=data["observed_lower_zone_key_id"],observed_lower_zone_snapshot_id=data["observed_lower_zone_snapshot_id"],
                observed_upper_zone_key_id=data["observed_upper_zone_key_id"],observed_upper_zone_snapshot_id=data["observed_upper_zone_snapshot_id"],
                lower_projection=ActiveBoxZoneProjection.from_dict(data["lower_projection"]),upper_projection=ActiveBoxZoneProjection.from_dict(data["upper_projection"]),
                active_box=ActiveBox.from_dict(data["active_box"]),provenance=ProvenanceRef.from_dict(data["provenance"]),
                config_snapshot=ActiveBoxSelectionConfig.from_dict(data["config_snapshot"]),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ActiveBoxEvent:
    event_id: str
    event_type: ActiveBoxEventType
    event_reason: ActiveBoxEventReason
    event_confirm_time: datetime
    source_score_frame_id: str
    box_key_id: str
    previous_box_snapshot_id: str | None
    resulting_box_snapshot_id: str
    lower_zone_key_id: str
    upper_zone_key_id: str
    previous_box_snapshot: ActiveBoxSnapshot | None
    resulting_box_snapshot: ActiveBoxSnapshot
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self)->dict[str,object]:
        return {"event_type":self.event_type.value,"event_reason":self.event_reason.value,"event_confirm_time":self.event_confirm_time.isoformat(),
            "source_score_frame_id":self.source_score_frame_id,"box_key_id":self.box_key_id,"previous_box_snapshot_id":self.previous_box_snapshot_id,
            "resulting_box_snapshot_id":self.resulting_box_snapshot_id,"lower_zone_key_id":self.lower_zone_key_id,"upper_zone_key_id":self.upper_zone_key_id,"schema_version":self.schema_version}

    def __post_init__(self)->None:
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError); object.__setattr__(self,"event_confirm_time",_time(self.event_confirm_time,"event_confirm_time"))
        for n in ("source_score_frame_id","box_key_id","resulting_box_snapshot_id","lower_zone_key_id","upper_zone_key_id"): _text(getattr(self,n),n)
        _optional_text(self.previous_box_snapshot_id,"previous_box_snapshot_id")
        if not isinstance(self.event_type,ActiveBoxEventType) or not isinstance(self.event_reason,ActiveBoxEventReason) or not isinstance(self.resulting_box_snapshot,ActiveBoxSnapshot): raise ActiveBoxContractError("event nested fact is invalid")
        result=self.resulting_box_snapshot
        if result.box_key_id!=self.box_key_id or result.box_snapshot_id!=self.resulting_box_snapshot_id or result.source_score_frame_id!=self.source_score_frame_id or result.active_box.confirm_time!=self.event_confirm_time:
            raise ActiveBoxContractError("event resulting snapshot chain is inconsistent")
        if (self.lower_zone_key_id,self.upper_zone_key_id)!=(result.observed_lower_zone_key_id,result.observed_upper_zone_key_id): raise ActiveBoxContractError("event zone keys contradict resulting snapshot")
        if self.event_type is ActiveBoxEventType.CREATED:
            if self.previous_box_snapshot_id is not None or self.previous_box_snapshot is not None or result.active_box.status is not ActiveBoxStatus.ACTIVE or self.event_reason not in (ActiveBoxEventReason.INITIAL_PAIR,ActiveBoxEventReason.PAIR_CHANGED): raise ActiveBoxContractError("CREATED event chain is invalid")
        else:
            previous=self.previous_box_snapshot
            if previous is None or self.previous_box_snapshot_id!=previous.box_snapshot_id or previous.active_box.status is not ActiveBoxStatus.ACTIVE or result.active_box.status is not ActiveBoxStatus.FROZEN or previous.box_key_id!=result.box_key_id or self.event_reason not in (ActiveBoxEventReason.PAIR_CHANGED,ActiveBoxEventReason.PAIR_UNAVAILABLE): raise ActiveBoxContractError("FROZEN event chain is invalid")
        require_semantic_id(self.event_id,"active-box-event-v1-",self._identity_payload(),"event_id",ActiveBoxContractError)
        config=result.config_snapshot
        parents=(self.source_score_frame_id,self.resulting_box_snapshot_id) if self.previous_box_snapshot_id is None else (self.source_score_frame_id,self.previous_box_snapshot_id,self.resulting_box_snapshot_id)
        _provenance(self.provenance,name=name,module=_CONTRACT_MODULE,version=config.engine_version,object_id=self.event_id,policy_id=config.policy_id,engine_id=config.engine_id,parents=parents)

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"event_id":self.event_id,**{k:v for k,v in self._identity_payload().items() if k!="schema_version"},
            "previous_box_snapshot":None if self.previous_box_snapshot is None else self.previous_box_snapshot.to_dict(),"resulting_box_snapshot":self.resulting_box_snapshot.to_dict(),"provenance":self.provenance.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxEvent:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            return cls(event_id=data["event_id"],event_type=ActiveBoxEventType(data["event_type"]),event_reason=ActiveBoxEventReason(data["event_reason"]),
                event_confirm_time=_parse_time(data["event_confirm_time"],"event_confirm_time"),source_score_frame_id=data["source_score_frame_id"],box_key_id=data["box_key_id"],
                previous_box_snapshot_id=data["previous_box_snapshot_id"],resulting_box_snapshot_id=data["resulting_box_snapshot_id"],lower_zone_key_id=data["lower_zone_key_id"],upper_zone_key_id=data["upper_zone_key_id"],
                previous_box_snapshot=None if data["previous_box_snapshot"] is None else ActiveBoxSnapshot.from_dict(data["previous_box_snapshot"]),
                resulting_box_snapshot=ActiveBoxSnapshot.from_dict(data["resulting_box_snapshot"]),provenance=ProvenanceRef.from_dict(data["provenance"]),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ActiveBoxSelectionReport:
    as_of_time: datetime
    source_score_frame_id: str
    upper_zone_count: int
    lower_zone_count: int
    eligible_upper_count: int
    eligible_lower_count: int
    selected_upper_zone_key_id: str | None
    selected_lower_zone_key_id: str | None
    lower_action: ActiveBoxSideAction
    upper_action: ActiveBoxSideAction
    has_active_box: bool
    active_box_key_id: str | None
    created_event_count: int
    frozen_event_count: int
    reference_price: Decimal
    engine_id: str
    engine_version: str
    policy_id: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self)->None:
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError); object.__setattr__(self,"as_of_time",_time(self.as_of_time,"as_of_time")); _text(self.source_score_frame_id,"source_score_frame_id")
        for n in ("upper_zone_count","lower_zone_count","eligible_upper_count","eligible_lower_count","created_event_count","frozen_event_count"):
            value=getattr(self,n)
            if isinstance(value,bool) or not isinstance(value,int) or value<0: raise ActiveBoxContractError(f"{n} must be a non-negative integer")
        if self.eligible_upper_count>self.upper_zone_count or self.eligible_lower_count>self.lower_zone_count: raise ActiveBoxContractError("eligible counts cannot exceed side counts")
        for n in ("selected_upper_zone_key_id","selected_lower_zone_key_id","active_box_key_id"): _optional_text(getattr(self,n),n)
        if not isinstance(self.lower_action,ActiveBoxSideAction) or not isinstance(self.upper_action,ActiveBoxSideAction) or not isinstance(self.has_active_box,bool): raise ActiveBoxContractError("report action/box facts invalid")
        if self.has_active_box!=(self.active_box_key_id is not None): raise ActiveBoxContractError("has_active_box contradicts active_box_key_id")
        _decimal(self.reference_price,"reference_price")
        for n in ("engine_id","engine_version","policy_id"): _text(getattr(self,n),n)
        for n in ("assumptions","warnings","errors"): _string_tuple(getattr(self,n),n)
        if self.warnings or self.errors: raise ActiveBoxContractError("successful C-007C report warnings/errors must be empty")

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"as_of_time":self.as_of_time.isoformat(),"source_score_frame_id":self.source_score_frame_id,
            "upper_zone_count":self.upper_zone_count,"lower_zone_count":self.lower_zone_count,"eligible_upper_count":self.eligible_upper_count,"eligible_lower_count":self.eligible_lower_count,
            "selected_upper_zone_key_id":self.selected_upper_zone_key_id,"selected_lower_zone_key_id":self.selected_lower_zone_key_id,"lower_action":self.lower_action.value,"upper_action":self.upper_action.value,
            "has_active_box":self.has_active_box,"active_box_key_id":self.active_box_key_id,"created_event_count":self.created_event_count,"frozen_event_count":self.frozen_event_count,
            "reference_price":str(self.reference_price),"engine_id":self.engine_id,"engine_version":self.engine_version,"policy_id":self.policy_id,
            "assumptions":list(self.assumptions),"warnings":list(self.warnings),"errors":list(self.errors)}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxSelectionReport:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            raw={n:data[n] for n in names-{"as_of_time","lower_action","upper_action","reference_price","assumptions","warnings","errors"}}
            return cls(**raw,as_of_time=_parse_time(data["as_of_time"],"as_of_time"),lower_action=ActiveBoxSideAction(data["lower_action"]),upper_action=ActiveBoxSideAction(data["upper_action"]),reference_price=_parse_decimal(data["reference_price"],"reference_price"),
                assumptions=tuple(_ordered(data,cls.__name__,"assumptions")),warnings=tuple(_ordered(data,cls.__name__,"warnings")),errors=tuple(_ordered(data,cls.__name__,"errors")),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


def _expected_report(
    score_frame: ResonanceScoreFrame,
    lower: ActiveBoxSideDecision,
    upper: ActiveBoxSideDecision,
    snapshot: ActiveBoxSnapshot | None,
    events: tuple[ActiveBoxEvent, ...],
    config: ActiveBoxSelectionConfig,
) -> ActiveBoxSelectionReport:
    return ActiveBoxSelectionReport(
        as_of_time=score_frame.as_of_time,
        source_score_frame_id=score_frame.score_frame_id,
        upper_zone_count=len(score_frame.upper_zones), lower_zone_count=len(score_frame.lower_zones),
        eligible_upper_count=sum(item.eligible for item in upper.zone_evaluations),
        eligible_lower_count=sum(item.eligible for item in lower.zone_evaluations),
        selected_upper_zone_key_id=upper.selected_zone_key_id,
        selected_lower_zone_key_id=lower.selected_zone_key_id,
        lower_action=lower.action, upper_action=upper.action,
        has_active_box=snapshot is not None,
        active_box_key_id=None if snapshot is None else snapshot.box_key_id,
        created_event_count=sum(item.event_type is ActiveBoxEventType.CREATED for item in events),
        frozen_event_count=sum(item.event_type is ActiveBoxEventType.FROZEN for item in events),
        reference_price=score_frame.source_frame.reference_price.price,
        engine_id=config.engine_id, engine_version=config.engine_version, policy_id=config.policy_id,
        assumptions=(
            "C-007B ResonanceScoreFrame is the authoritative scoring input",
            "nearest-qualified selection is a research policy, not a trading edge",
            "C-007C contracts do not execute a cross-Frame state machine",
        ), warnings=(), errors=(),
    )


@dataclass(frozen=True, slots=True)
class ActiveBoxSelectionFrame:
    selection_frame_id: str
    as_of_time: datetime
    source_score_frame_id: str
    source_score_frame: ResonanceScoreFrame
    lower_decision: ActiveBoxSideDecision
    upper_decision: ActiveBoxSideDecision
    active_box_snapshot: ActiveBoxSnapshot | None
    emitted_events: tuple[ActiveBoxEvent, ...]
    report: ActiveBoxSelectionReport
    config_snapshot: ActiveBoxSelectionConfig
    provenance: ProvenanceRef
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self)->dict[str,object]:
        return {"as_of_time":self.as_of_time.isoformat(),"source_score_frame_id":self.source_score_frame_id,
            "source_score_frame":self.source_score_frame.to_dict(),"lower_decision":self.lower_decision.to_dict(),"upper_decision":self.upper_decision.to_dict(),
            "active_box_snapshot":None if self.active_box_snapshot is None else self.active_box_snapshot.to_dict(),
            "emitted_events":[item.to_dict() for item in self.emitted_events],"report":self.report.to_dict(),"config_snapshot":self.config_snapshot.to_dict(),"schema_version":self.schema_version}

    def __post_init__(self)->None:
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError); object.__setattr__(self,"as_of_time",_time(self.as_of_time,"as_of_time")); _text(self.source_score_frame_id,"source_score_frame_id")
        if not isinstance(self.source_score_frame,ResonanceScoreFrame) or self.source_score_frame.score_frame_id!=self.source_score_frame_id or self.source_score_frame.as_of_time!=self.as_of_time:
            raise ActiveBoxContractError("SelectionFrame must align exactly to source ScoreFrame")
        if not isinstance(self.config_snapshot,ActiveBoxSelectionConfig) or self.config_snapshot.symbol!=self.source_score_frame.source_frame.config_snapshot.symbol:
            raise ActiveBoxContractError("SelectionFrame config symbol conflicts with source Frame")
        if not isinstance(self.lower_decision,ActiveBoxSideDecision) or not isinstance(self.upper_decision,ActiveBoxSideDecision) or self.lower_decision.side is not BoundarySide.LOWER or self.upper_decision.side is not BoundarySide.UPPER:
            raise ActiveBoxContractError("SelectionFrame requires exactly LOWER and UPPER decisions")
        for decision in (self.lower_decision,self.upper_decision):
            if decision.source_score_frame_id!=self.source_score_frame_id or decision.as_of_time!=self.as_of_time: raise ActiveBoxContractError("decision source mapping is inconsistent")
        from .policy import validate_side_decision
        validate_side_decision(self.source_score_frame,self.config_snapshot,self.lower_decision)
        validate_side_decision(self.source_score_frame,self.config_snapshot,self.upper_decision)
        selected=(self.lower_decision.selected_zone_key_id,self.upper_decision.selected_zone_key_id)
        if self.active_box_snapshot is None:
            if all(item is not None for item in selected): raise ActiveBoxContractError("complete selected pair requires an Active Box")
        else:
            if self.active_box_snapshot.active_box.status is not ActiveBoxStatus.ACTIVE or self.active_box_snapshot.source_score_frame_id!=self.source_score_frame_id:
                raise ActiveBoxContractError("current frame snapshot must be ACTIVE and source-aligned")
            if selected!=(self.active_box_snapshot.observed_lower_zone_key_id,self.active_box_snapshot.observed_upper_zone_key_id): raise ActiveBoxContractError("Active Box keys must match decisions")
            selected_snapshots=(self.lower_decision.selected_zone_snapshot_id,self.upper_decision.selected_zone_snapshot_id)
            if selected_snapshots!=(self.active_box_snapshot.observed_lower_zone_snapshot_id,self.active_box_snapshot.observed_upper_zone_snapshot_id): raise ActiveBoxContractError("Active Box observed Zone snapshots must match decisions")
            if self.active_box_snapshot.config_snapshot!=self.config_snapshot: raise ActiveBoxContractError("Active Box config must equal SelectionFrame config")
            price=self.source_score_frame.source_frame.reference_price.price
            if not self.active_box_snapshot.active_box.lower_boundary.price_range.high<=price<=self.active_box_snapshot.active_box.upper_boundary.price_range.low:
                raise ActiveBoxContractError("current reference price must be inside ACTIVE Box inner edges")
        if not isinstance(self.emitted_events,tuple) or any(not isinstance(item,ActiveBoxEvent) for item in self.emitted_events) or len(self.emitted_events)>2:
            raise ActiveBoxContractError("SelectionFrame emitted_events must contain 0, 1, or 2 events")
        if len(self.emitted_events)==2 and tuple(item.event_type for item in self.emitted_events)!=(ActiveBoxEventType.FROZEN,ActiveBoxEventType.CREATED): raise ActiveBoxContractError("replacement event order must be FROZEN then CREATED")
        if any(item.event_confirm_time!=self.as_of_time or item.source_score_frame_id!=self.source_score_frame_id for item in self.emitted_events): raise ActiveBoxContractError("event time/source must equal current Frame")
        created=tuple(item for item in self.emitted_events if item.event_type is ActiveBoxEventType.CREATED)
        if created and (self.active_box_snapshot is None or created[-1].resulting_box_snapshot!=self.active_box_snapshot): raise ActiveBoxContractError("CREATED event must result in current Active Box")
        current=(self.lower_decision.current_zone_key_id,self.upper_decision.current_zone_key_id)
        if (current[0] is None)!=(current[1] is None): raise ActiveBoxContractError("current Box state must have both sides or neither")
        complete=all(item is not None for item in selected)
        if current==(None,None):
            expected_pattern=() if not complete else ((ActiveBoxEventType.CREATED,ActiveBoxEventReason.INITIAL_PAIR),)
        elif not complete:
            expected_pattern=((ActiveBoxEventType.FROZEN,ActiveBoxEventReason.PAIR_UNAVAILABLE),)
        elif selected==current:
            expected_pattern=()
        else:
            expected_pattern=((ActiveBoxEventType.FROZEN,ActiveBoxEventReason.PAIR_CHANGED),(ActiveBoxEventType.CREATED,ActiveBoxEventReason.PAIR_CHANGED))
        actual_pattern=tuple((item.event_type,item.event_reason) for item in self.emitted_events)
        if actual_pattern!=expected_pattern: raise ActiveBoxContractError("SelectionFrame event pattern contradicts pair transition facts")
        if not isinstance(self.report,ActiveBoxSelectionReport) or self.report!=_expected_report(self.source_score_frame,self.lower_decision,self.upper_decision,self.active_box_snapshot,self.emitted_events,self.config_snapshot): raise ActiveBoxContractError("SelectionFrame report contradicts exact facts")
        require_semantic_id(self.selection_frame_id,"active-box-selection-frame-v1-",self._identity_payload(),"selection_frame_id",ActiveBoxContractError)
        parents=(self.source_score_frame_id,self.lower_decision.decision_id,self.upper_decision.decision_id,*(item.event_id for item in self.emitted_events))
        if self.active_box_snapshot is not None: parents=(*parents,self.active_box_snapshot.box_snapshot_id)
        _provenance(self.provenance,name=name,module=_CONTRACT_MODULE,version=self.config_snapshot.engine_version,object_id=self.selection_frame_id,policy_id=self.config_snapshot.policy_id,engine_id=self.config_snapshot.engine_id,parents=parents)

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"selection_frame_id":self.selection_frame_id,"as_of_time":self.as_of_time.isoformat(),"source_score_frame_id":self.source_score_frame_id,
            "source_score_frame":self.source_score_frame.to_dict(),"lower_decision":self.lower_decision.to_dict(),"upper_decision":self.upper_decision.to_dict(),
            "active_box_snapshot":None if self.active_box_snapshot is None else self.active_box_snapshot.to_dict(),"emitted_events":[item.to_dict() for item in self.emitted_events],
            "report":self.report.to_dict(),"config_snapshot":self.config_snapshot.to_dict(),"provenance":self.provenance.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxSelectionFrame:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            return cls(selection_frame_id=data["selection_frame_id"],as_of_time=_parse_time(data["as_of_time"],"as_of_time"),source_score_frame_id=data["source_score_frame_id"],
                source_score_frame=ResonanceScoreFrame.from_dict(data["source_score_frame"]),lower_decision=ActiveBoxSideDecision.from_dict(data["lower_decision"]),upper_decision=ActiveBoxSideDecision.from_dict(data["upper_decision"]),
                active_box_snapshot=None if data["active_box_snapshot"] is None else ActiveBoxSnapshot.from_dict(data["active_box_snapshot"]),
                emitted_events=tuple(ActiveBoxEvent.from_dict(item) for item in _ordered(data,cls.__name__,"emitted_events")),report=ActiveBoxSelectionReport.from_dict(data["report"]),
                config_snapshot=ActiveBoxSelectionConfig.from_dict(data["config_snapshot"]),provenance=ProvenanceRef.from_dict(data["provenance"]),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,RuntimeError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ActiveBoxSelectionHistory:
    frames: tuple[ActiveBoxSelectionFrame, ...]
    final_frame: ActiveBoxSelectionFrame
    events: tuple[ActiveBoxEvent, ...]
    frozen_boxes: tuple[ActiveBoxSnapshot, ...]
    source_score_history: ResonanceScoreHistory
    config_snapshot: ActiveBoxSelectionConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self)->None:
        name=type(self).__name__; _schema(self.schema_version,name,ActiveBoxContractError)
        if not isinstance(self.frames,tuple) or not self.frames or any(not isinstance(item,ActiveBoxSelectionFrame) for item in self.frames): raise ActiveBoxContractError("History frames must be a non-empty tuple")
        if any(current.as_of_time<=previous.as_of_time for previous,current in zip(self.frames,self.frames[1:])): raise ActiveBoxContractError("History Frame times must be strictly increasing")
        if self.final_frame!=self.frames[-1]: raise ActiveBoxContractError("final_frame must equal frames[-1]")
        if any(item.config_snapshot!=self.config_snapshot for item in self.frames): raise ActiveBoxContractError("History config must be identical")
        if not isinstance(self.source_score_history,ResonanceScoreHistory): raise ActiveBoxContractError("source_score_history type is invalid")
        if tuple(item.source_score_frame_id for item in self.frames)!=tuple(item.score_frame_id for item in self.source_score_history.frames): raise ActiveBoxContractError("History source ScoreFrame mapping must be exact")
        if any(item.source_score_frame!=source for item,source in zip(self.frames,self.source_score_history.frames)): raise ActiveBoxContractError("source ScoreFrame payload was modified")
        flattened=tuple(event for frame in self.frames for event in frame.emitted_events)
        if not isinstance(self.events,tuple) or self.events!=flattened: raise ActiveBoxContractError("History events must exactly flatten Frame events")
        if any(current.event_confirm_time<previous.event_confirm_time for previous,current in zip(self.events,self.events[1:])): raise ActiveBoxContractError("History event times must be monotonic")
        by_key:dict[str,list[ActiveBoxEvent]]={}
        for event in self.events: by_key.setdefault(event.box_key_id,[]).append(event)
        for box_key, ledger in by_key.items():
            if sum(item.event_type is ActiveBoxEventType.CREATED for item in ledger)!=1 or sum(item.event_type is ActiveBoxEventType.FROZEN for item in ledger)>1: raise ActiveBoxContractError(f"box {box_key} event ledger is invalid")
        frozen=tuple(item.resulting_box_snapshot for item in self.events if item.event_type is ActiveBoxEventType.FROZEN)
        if not isinstance(self.frozen_boxes,tuple) or self.frozen_boxes!=frozen or len({item.box_key_id for item in frozen})!=len(frozen): raise ActiveBoxContractError("frozen_boxes ledger must exactly match FROZEN events")
        frozen_at={item.box_key_id:item.active_box.confirm_time for item in frozen}
        for frame in self.frames:
            if frame.active_box_snapshot is not None and frame.active_box_snapshot.box_key_id in frozen_at and frame.as_of_time>=frozen_at[frame.active_box_snapshot.box_key_id]: raise ActiveBoxContractError("FROZEN Box cannot reactivate")
        for previous,current in zip(self.frames,self.frames[1:]):
            left,right=previous.active_box_snapshot,current.active_box_snapshot
            if left is not None and right is not None and left.box_key_id==right.box_key_id:
                if (left.lower_projection,left.upper_projection,left.created_time,left.active_box.selection_price)!=(right.lower_projection,right.upper_projection,right.created_time,right.active_box.selection_price):
                    raise ActiveBoxContractError("unchanged Box episode projections and creation facts must remain stable")

    def to_dict(self)->dict[str,object]:
        return {"schema_version":self.schema_version,"frames":[item.to_dict() for item in self.frames],"final_frame":self.final_frame.to_dict(),
            "events":[item.to_dict() for item in self.events],"frozen_boxes":[item.to_dict() for item in self.frozen_boxes],
            "source_score_history":self.source_score_history.to_dict(),"config_snapshot":self.config_snapshot.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->ActiveBoxSelectionHistory:
        names={field.name for field in fields(cls)}-{"schema_version"}; data=_exact(payload,cls.__name__,names)
        try:
            return cls(frames=tuple(ActiveBoxSelectionFrame.from_dict(item) for item in _ordered(data,cls.__name__,"frames")),final_frame=ActiveBoxSelectionFrame.from_dict(data["final_frame"]),
                events=tuple(ActiveBoxEvent.from_dict(item) for item in _ordered(data,cls.__name__,"events")),frozen_boxes=tuple(ActiveBoxSnapshot.from_dict(item) for item in _ordered(data,cls.__name__,"frozen_boxes")),
                source_score_history=ResonanceScoreHistory.from_dict(data["source_score_history"]),config_snapshot=ActiveBoxSelectionConfig.from_dict(data["config_snapshot"]),schema_version=data["schema_version"])
        except ActiveBoxSerializationError: raise
        except (TypeError,ValueError,RuntimeError,ActiveBoxContractError) as exc: raise ActiveBoxSerializationError(f"invalid serialized {cls.__name__}: {exc}") from exc


def _make_box_snapshot(
    *,
    source_score_frame: ResonanceScoreFrame,
    config: ActiveBoxSelectionConfig,
    created_time: datetime,
    lower_projection: ActiveBoxZoneProjection,
    upper_projection: ActiveBoxZoneProjection,
    observed_lower_zone_snapshot_id: str,
    observed_upper_zone_snapshot_id: str,
    selection_price: Decimal,
    status: ActiveBoxStatus,
) -> ActiveBoxSnapshot:
    if lower_projection.config_snapshot != config or upper_projection.config_snapshot != config:
        raise ActiveBoxContractError("Box projections must share exact config")
    box_key_id=semantic_id("active-box-key-v1-",_box_key_payload(config,created_time,lower_projection,upper_projection,selection_price))
    active_provenance=ProvenanceRef(source_module=_CONTRACT_MODULE,source_version=config.engine_version,source_object_id=box_key_id,
        policy_id=config.policy_id,parent_object_ids=(lower_projection.boundary.object_id,upper_projection.boundary.object_id),notes=(f"engine_id={config.engine_id}",))
    event_time=source_score_frame.as_of_time
    active_box=ActiveBox(box_id=box_key_id,symbol=config.symbol,timeframe=config.output_timeframe,scale=config.output_scale,
        lower_boundary=lower_projection.boundary,upper_boundary=upper_projection.boundary,selection_price=selection_price,status=status,
        origin_time=min(lower_projection.boundary.origin_time,upper_projection.boundary.origin_time),
        confirm_time=created_time if status is ActiveBoxStatus.ACTIVE else event_time,as_of_time=event_time,
        frozen_time=None if status is ActiveBoxStatus.ACTIVE else event_time,retired_time=None,provenance=active_provenance)
    snapshot_payload={"box_key_id":box_key_id,"source_score_frame_id":source_score_frame.score_frame_id,"active_box":active_box.to_dict(),
        "observed_lower_zone_key_id":lower_projection.source_zone_key_id,"observed_lower_zone_snapshot_id":observed_lower_zone_snapshot_id,
        "observed_upper_zone_key_id":upper_projection.source_zone_key_id,"observed_upper_zone_snapshot_id":observed_upper_zone_snapshot_id,
        "status":status.value,"schema_version":SCHEMA_VERSION}
    snapshot_id=semantic_id("active-box-snapshot-v1-",snapshot_payload)
    provenance=ProvenanceRef(source_module=_CONTRACT_MODULE,source_version=config.engine_version,source_object_id=snapshot_id,policy_id=config.policy_id,
        parent_object_ids=(source_score_frame.score_frame_id,box_key_id,lower_projection.projection_id,upper_projection.projection_id),notes=(f"engine_id={config.engine_id}",))
    return ActiveBoxSnapshot(box_key_id=box_key_id,box_snapshot_id=snapshot_id,created_time=created_time,source_score_frame_id=source_score_frame.score_frame_id,
        observed_lower_zone_key_id=lower_projection.source_zone_key_id,observed_lower_zone_snapshot_id=observed_lower_zone_snapshot_id,
        observed_upper_zone_key_id=upper_projection.source_zone_key_id,observed_upper_zone_snapshot_id=observed_upper_zone_snapshot_id,
        lower_projection=lower_projection,upper_projection=upper_projection,active_box=active_box,provenance=provenance,config_snapshot=config)


def create_active_box_snapshot(
    source_score_frame: ResonanceScoreFrame,
    lower_projection: ActiveBoxZoneProjection,
    upper_projection: ActiveBoxZoneProjection,
    config: ActiveBoxSelectionConfig,
) -> ActiveBoxSnapshot:
    """Construct one caller-requested ACTIVE episode snapshot; no selection occurs."""
    if lower_projection.selection_confirm_time!=source_score_frame.as_of_time or upper_projection.selection_confirm_time!=source_score_frame.as_of_time:
        raise ActiveBoxContractError("new Box projections must be confirmed at creation Frame")
    return _make_box_snapshot(source_score_frame=source_score_frame,config=config,created_time=source_score_frame.as_of_time,
        lower_projection=lower_projection,upper_projection=upper_projection,
        observed_lower_zone_snapshot_id=lower_projection.source_zone_snapshot_id,
        observed_upper_zone_snapshot_id=upper_projection.source_zone_snapshot_id,
        selection_price=source_score_frame.source_frame.reference_price.price,status=ActiveBoxStatus.ACTIVE)


def observe_active_box_snapshot(
    source_score_frame: ResonanceScoreFrame,
    previous: ActiveBoxSnapshot,
    lower_zone_snapshot_id: str,
    upper_zone_snapshot_id: str,
) -> ActiveBoxSnapshot:
    """Advance an unchanged episode observation without changing projections."""
    if previous.active_box.status is not ActiveBoxStatus.ACTIVE:
        raise ActiveBoxContractError("only an ACTIVE episode can be observed")
    return _make_box_snapshot(source_score_frame=source_score_frame,config=previous.config_snapshot,created_time=previous.created_time,
        lower_projection=previous.lower_projection,upper_projection=previous.upper_projection,
        observed_lower_zone_snapshot_id=_text(lower_zone_snapshot_id,"lower_zone_snapshot_id"),
        observed_upper_zone_snapshot_id=_text(upper_zone_snapshot_id,"upper_zone_snapshot_id"),
        selection_price=previous.active_box.selection_price,status=ActiveBoxStatus.ACTIVE)


def freeze_active_box_snapshot(source_score_frame: ResonanceScoreFrame, previous: ActiveBoxSnapshot) -> ActiveBoxSnapshot:
    """Construct a caller-requested terminal FROZEN snapshot; no policy decision occurs."""
    if previous.active_box.status is not ActiveBoxStatus.ACTIVE:
        raise ActiveBoxContractError("only an ACTIVE episode can be frozen")
    return _make_box_snapshot(source_score_frame=source_score_frame,config=previous.config_snapshot,created_time=previous.created_time,
        lower_projection=previous.lower_projection,upper_projection=previous.upper_projection,
        observed_lower_zone_snapshot_id=previous.observed_lower_zone_snapshot_id,
        observed_upper_zone_snapshot_id=previous.observed_upper_zone_snapshot_id,
        selection_price=previous.active_box.selection_price,status=ActiveBoxStatus.FROZEN)


def build_active_box_event(
    *,
    event_type: ActiveBoxEventType,
    event_reason: ActiveBoxEventReason,
    resulting_snapshot: ActiveBoxSnapshot,
    previous_snapshot: ActiveBoxSnapshot | None = None,
) -> ActiveBoxEvent:
    """Build one explicit event fact from caller-supplied snapshots."""
    payload={"event_type":event_type.value,"event_reason":event_reason.value,"event_confirm_time":resulting_snapshot.active_box.confirm_time.isoformat(),
        "source_score_frame_id":resulting_snapshot.source_score_frame_id,"box_key_id":resulting_snapshot.box_key_id,
        "previous_box_snapshot_id":None if previous_snapshot is None else previous_snapshot.box_snapshot_id,
        "resulting_box_snapshot_id":resulting_snapshot.box_snapshot_id,"lower_zone_key_id":resulting_snapshot.observed_lower_zone_key_id,
        "upper_zone_key_id":resulting_snapshot.observed_upper_zone_key_id,"schema_version":SCHEMA_VERSION}
    event_id=semantic_id("active-box-event-v1-",payload)
    parents=(resulting_snapshot.source_score_frame_id,resulting_snapshot.box_snapshot_id) if previous_snapshot is None else (resulting_snapshot.source_score_frame_id,previous_snapshot.box_snapshot_id,resulting_snapshot.box_snapshot_id)
    config=resulting_snapshot.config_snapshot
    provenance=ProvenanceRef(source_module=_CONTRACT_MODULE,source_version=config.engine_version,source_object_id=event_id,policy_id=config.policy_id,parent_object_ids=parents,notes=(f"engine_id={config.engine_id}",))
    return ActiveBoxEvent(event_id=event_id,event_type=event_type,event_reason=event_reason,event_confirm_time=resulting_snapshot.active_box.confirm_time,
        source_score_frame_id=resulting_snapshot.source_score_frame_id,box_key_id=resulting_snapshot.box_key_id,
        previous_box_snapshot_id=None if previous_snapshot is None else previous_snapshot.box_snapshot_id,resulting_box_snapshot_id=resulting_snapshot.box_snapshot_id,
        lower_zone_key_id=resulting_snapshot.observed_lower_zone_key_id,upper_zone_key_id=resulting_snapshot.observed_upper_zone_key_id,
        previous_box_snapshot=previous_snapshot,resulting_box_snapshot=resulting_snapshot,provenance=provenance)


def build_selection_frame(
    *,
    source_score_frame: ResonanceScoreFrame,
    lower_decision: ActiveBoxSideDecision,
    upper_decision: ActiveBoxSideDecision,
    active_box_snapshot: ActiveBoxSnapshot | None,
    emitted_events: tuple[ActiveBoxEvent, ...],
    config: ActiveBoxSelectionConfig,
) -> ActiveBoxSelectionFrame:
    """Bind explicit caller-supplied facts into one immutable SelectionFrame."""
    report=_expected_report(source_score_frame,lower_decision,upper_decision,active_box_snapshot,emitted_events,config)
    payload={"as_of_time":source_score_frame.as_of_time.isoformat(),"source_score_frame_id":source_score_frame.score_frame_id,
        "source_score_frame":source_score_frame.to_dict(),"lower_decision":lower_decision.to_dict(),"upper_decision":upper_decision.to_dict(),
        "active_box_snapshot":None if active_box_snapshot is None else active_box_snapshot.to_dict(),"emitted_events":[item.to_dict() for item in emitted_events],
        "report":report.to_dict(),"config_snapshot":config.to_dict(),"schema_version":SCHEMA_VERSION}
    frame_id=semantic_id("active-box-selection-frame-v1-",payload)
    parents=(source_score_frame.score_frame_id,lower_decision.decision_id,upper_decision.decision_id,*(item.event_id for item in emitted_events))
    if active_box_snapshot is not None: parents=(*parents,active_box_snapshot.box_snapshot_id)
    provenance=ProvenanceRef(source_module=_CONTRACT_MODULE,source_version=config.engine_version,source_object_id=frame_id,policy_id=config.policy_id,parent_object_ids=parents,notes=(f"engine_id={config.engine_id}",))
    return ActiveBoxSelectionFrame(selection_frame_id=frame_id,as_of_time=source_score_frame.as_of_time,source_score_frame_id=source_score_frame.score_frame_id,
        source_score_frame=source_score_frame,lower_decision=lower_decision,upper_decision=upper_decision,active_box_snapshot=active_box_snapshot,
        emitted_events=emitted_events,report=report,config_snapshot=config,provenance=provenance)
