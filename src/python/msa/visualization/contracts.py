"""Immutable contracts for the bounded MSA Core visual preview."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Self

from .errors import VisualContractError


SCHEMA_VERSION = 1
PREVIEW_LABEL = "Synthetic VALIDATION Preview"
OOS_LABEL = "Not OOS"
ADVICE_LABEL = "Not Trading Advice"
CORE_STATUS = "BLOCKED_BEFORE_OOS"


class _VisualEnum(str, Enum):
    @classmethod
    def parse(cls, value: object, field: str) -> Self:
        try:
            return cls(value)
        except (TypeError, ValueError) as exc:
            raise VisualContractError(f"{field} has an unsupported value") from exc


class BoundaryTier(_VisualEnum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"


class VisualLevel(_VisualEnum):
    MAJOR = "MAJOR"
    HIGH_TIMEFRAME = "HIGH_TIMEFRAME"


class DisplayState(_VisualEnum):
    ACTIVE = "ACTIVE"
    BROKEN = "BROKEN"
    RETIRED = "RETIRED"


def _mapping(value: object, name: str, fields: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VisualContractError(f"{name} payload must be a mapping")
    expected = fields | {"schema_version"}
    if set(value) != expected:
        raise VisualContractError(f"{name} payload fields must be exact")
    if value["schema_version"] != SCHEMA_VERSION:
        raise VisualContractError(f"{name}.schema_version must be 1")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualContractError(f"{field} must be non-empty text")
    return value


def _integer(value: object, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise VisualContractError(f"{field} must be an integer >= {minimum}")
    return value


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise VisualContractError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise VisualContractError(f"{field} must be finite")
    return value


def _decimal_from(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise VisualContractError(f"{field} must be a decimal string")
    try:
        return _decimal(Decimal(value), field)
    except InvalidOperation as exc:
        raise VisualContractError(f"{field} must be a decimal string") from exc


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise VisualContractError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _time_from(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise VisualContractError(f"{field} must be an ISO-8601 string")
    try:
        return _time(datetime.fromisoformat(value), field)
    except ValueError as exc:
        raise VisualContractError(f"{field} must be an ISO-8601 string") from exc


def _ids(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise VisualContractError(f"{field} must be a non-empty tuple")
    result = tuple(_text(item, field) for item in value)
    if len(set(result)) != len(result):
        raise VisualContractError(f"{field} must contain unique values")
    return result


def _list(payload: Mapping[str, Any], field: str) -> list[Any]:
    value = payload[field]
    if not isinstance(value, list):
        raise VisualContractError(f"{field} must be an ordered list")
    return value


@dataclass(frozen=True, slots=True)
class VisualCandle:
    source_id: str
    timestamp: datetime
    end_time: datetime
    available_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise VisualContractError("VisualCandle.schema_version must be 1")
        _text(self.source_id, "source_id")
        start = _time(self.timestamp, "timestamp")
        end = _time(self.end_time, "end_time")
        available = _time(self.available_time, "available_time")
        values = {name: _decimal(getattr(self, name), name) for name in ("open", "high", "low", "close")}
        if not start < end <= available:
            raise VisualContractError("candle times must satisfy timestamp < end_time <= available_time")
        if values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]):
            raise VisualContractError("candle OHLC range is invalid")
        object.__setattr__(self, "timestamp", start)
        object.__setattr__(self, "end_time", end)
        object.__setattr__(self, "available_time", available)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "source_id": self.source_id, "timestamp": self.timestamp.isoformat(), "end_time": self.end_time.isoformat(), "available_time": self.available_time.isoformat(), "open": str(self.open), "high": str(self.high), "low": str(self.low), "close": str(self.close)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _mapping(payload, cls.__name__, {"source_id", "timestamp", "end_time", "available_time", "open", "high", "low", "close"})
        return cls(source_id=data["source_id"], timestamp=_time_from(data["timestamp"], "timestamp"), end_time=_time_from(data["end_time"], "end_time"), available_time=_time_from(data["available_time"], "available_time"), open=_decimal_from(data["open"], "open"), high=_decimal_from(data["high"], "high"), low=_decimal_from(data["low"], "low"), close=_decimal_from(data["close"], "close"), schema_version=data["schema_version"])


@dataclass(frozen=True, slots=True)
class VisualBoundary:
    visual_boundary_id: str
    boundary_id: str
    subject_id: str
    side: str
    tier: BoundaryTier
    visual_level: VisualLevel
    lifecycle_state: str
    display_state: DisplayState
    timeframe: str
    scale_id: str
    price_low: Decimal
    price_high: Decimal
    origin_time: datetime
    confirm_time: datetime
    display_end_time: datetime
    show_origin_extension: bool
    source_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise VisualContractError("VisualBoundary.schema_version must be 1")
        for name in ("visual_boundary_id", "boundary_id", "subject_id", "side", "lifecycle_state", "timeframe", "scale_id"):
            _text(getattr(self, name), name)
        if not isinstance(self.tier, BoundaryTier) or not isinstance(self.visual_level, VisualLevel) or not isinstance(self.display_state, DisplayState):
            raise VisualContractError("boundary enums are invalid")
        low, high = _decimal(self.price_low, "price_low"), _decimal(self.price_high, "price_high")
        origin, confirm, end = _time(self.origin_time, "origin_time"), _time(self.confirm_time, "confirm_time"), _time(self.display_end_time, "display_end_time")
        if low > high or not origin <= confirm <= end:
            raise VisualContractError("boundary range or causal interval is invalid")
        if not isinstance(self.show_origin_extension, bool):
            raise VisualContractError("show_origin_extension must be a bool")
        _ids(self.source_ids, "source_ids")
        object.__setattr__(self, "origin_time", origin); object.__setattr__(self, "confirm_time", confirm); object.__setattr__(self, "display_end_time", end)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "visual_boundary_id": self.visual_boundary_id, "boundary_id": self.boundary_id, "subject_id": self.subject_id, "side": self.side, "tier": self.tier.value, "visual_level": self.visual_level.value, "lifecycle_state": self.lifecycle_state, "display_state": self.display_state.value, "timeframe": self.timeframe, "scale_id": self.scale_id, "price_low": str(self.price_low), "price_high": str(self.price_high), "origin_time": self.origin_time.isoformat(), "confirm_time": self.confirm_time.isoformat(), "display_end_time": self.display_end_time.isoformat(), "show_origin_extension": self.show_origin_extension, "source_ids": list(self.source_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        fields = {"visual_boundary_id", "boundary_id", "subject_id", "side", "tier", "visual_level", "lifecycle_state", "display_state", "timeframe", "scale_id", "price_low", "price_high", "origin_time", "confirm_time", "display_end_time", "show_origin_extension", "source_ids"}
        data = _mapping(payload, cls.__name__, fields)
        return cls(visual_boundary_id=data["visual_boundary_id"], boundary_id=data["boundary_id"], subject_id=data["subject_id"], side=data["side"], tier=BoundaryTier.parse(data["tier"], "tier"), visual_level=VisualLevel.parse(data["visual_level"], "visual_level"), lifecycle_state=data["lifecycle_state"], display_state=DisplayState.parse(data["display_state"], "display_state"), timeframe=data["timeframe"], scale_id=data["scale_id"], price_low=_decimal_from(data["price_low"], "price_low"), price_high=_decimal_from(data["price_high"], "price_high"), origin_time=_time_from(data["origin_time"], "origin_time"), confirm_time=_time_from(data["confirm_time"], "confirm_time"), display_end_time=_time_from(data["display_end_time"], "display_end_time"), show_origin_extension=data["show_origin_extension"], source_ids=tuple(_list(data, "source_ids")), schema_version=data["schema_version"])


@dataclass(frozen=True, slots=True)
class VisualZone:
    zone_key_id: str
    zone_snapshot_id: str
    side: str
    resonance_class: str
    price_low: Decimal
    price_high: Decimal
    origin_time: datetime
    confirm_time: datetime
    candidate_count: int
    confirmed_count: int
    source_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise VisualContractError("VisualZone.schema_version must be 1")
        for name in ("zone_key_id", "zone_snapshot_id", "side", "resonance_class"):
            _text(getattr(self, name), name)
        if _decimal(self.price_low, "price_low") > _decimal(self.price_high, "price_high"):
            raise VisualContractError("zone price range is invalid")
        origin, confirm = _time(self.origin_time, "origin_time"), _time(self.confirm_time, "confirm_time")
        if origin > confirm:
            raise VisualContractError("zone origin_time cannot follow confirm_time")
        _integer(self.candidate_count, "candidate_count"); _integer(self.confirmed_count, "confirmed_count"); _ids(self.source_ids, "source_ids")
        object.__setattr__(self, "origin_time", origin); object.__setattr__(self, "confirm_time", confirm)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "zone_key_id": self.zone_key_id, "zone_snapshot_id": self.zone_snapshot_id, "side": self.side, "resonance_class": self.resonance_class, "price_low": str(self.price_low), "price_high": str(self.price_high), "origin_time": self.origin_time.isoformat(), "confirm_time": self.confirm_time.isoformat(), "candidate_count": self.candidate_count, "confirmed_count": self.confirmed_count, "source_ids": list(self.source_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _mapping(payload, cls.__name__, {"zone_key_id", "zone_snapshot_id", "side", "resonance_class", "price_low", "price_high", "origin_time", "confirm_time", "candidate_count", "confirmed_count", "source_ids"})
        return cls(zone_key_id=data["zone_key_id"], zone_snapshot_id=data["zone_snapshot_id"], side=data["side"], resonance_class=data["resonance_class"], price_low=_decimal_from(data["price_low"], "price_low"), price_high=_decimal_from(data["price_high"], "price_high"), origin_time=_time_from(data["origin_time"], "origin_time"), confirm_time=_time_from(data["confirm_time"], "confirm_time"), candidate_count=data["candidate_count"], confirmed_count=data["confirmed_count"], source_ids=tuple(_list(data, "source_ids")), schema_version=data["schema_version"])


@dataclass(frozen=True, slots=True)
class VisualActiveBox:
    box_id: str
    status: str
    lower_low: Decimal
    lower_high: Decimal
    upper_low: Decimal
    upper_high: Decimal
    origin_time: datetime
    confirm_time: datetime
    source_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise VisualContractError("VisualActiveBox.schema_version must be 1")
        _text(self.box_id, "box_id"); _text(self.status, "status")
        ll, lh, ul, uh = (_decimal(getattr(self, name), name) for name in ("lower_low", "lower_high", "upper_low", "upper_high"))
        if not ll <= lh <= ul <= uh:
            raise VisualContractError("Active Box price bounds are invalid")
        origin, confirm = _time(self.origin_time, "origin_time"), _time(self.confirm_time, "confirm_time")
        if origin > confirm:
            raise VisualContractError("Active Box origin_time cannot follow confirm_time")
        _ids(self.source_ids, "source_ids")
        object.__setattr__(self, "origin_time", origin); object.__setattr__(self, "confirm_time", confirm)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "box_id": self.box_id, "status": self.status, "lower_low": str(self.lower_low), "lower_high": str(self.lower_high), "upper_low": str(self.upper_low), "upper_high": str(self.upper_high), "origin_time": self.origin_time.isoformat(), "confirm_time": self.confirm_time.isoformat(), "source_ids": list(self.source_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        data = _mapping(payload, cls.__name__, {"box_id", "status", "lower_low", "lower_high", "upper_low", "upper_high", "origin_time", "confirm_time", "source_ids"})
        return cls(box_id=data["box_id"], status=data["status"], lower_low=_decimal_from(data["lower_low"], "lower_low"), lower_high=_decimal_from(data["lower_high"], "lower_high"), upper_low=_decimal_from(data["upper_low"], "upper_low"), upper_high=_decimal_from(data["upper_high"], "upper_high"), origin_time=_time_from(data["origin_time"], "origin_time"), confirm_time=_time_from(data["confirm_time"], "confirm_time"), source_ids=tuple(_list(data, "source_ids")), schema_version=data["schema_version"])


@dataclass(frozen=True, slots=True)
class VisualScene:
    scenario: str
    seed: int
    partition: str
    as_of_time: datetime
    symbol: str
    reference_timeframe: str
    preview_label: str
    oos_label: str
    advice_label: str
    core_status: str
    candles: tuple[VisualCandle, ...]
    confirmed_boundaries: tuple[VisualBoundary, ...]
    candidate_boundaries: tuple[VisualBoundary, ...]
    resonance_zones: tuple[VisualZone, ...]
    active_box: VisualActiveBox | None
    source_ids: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise VisualContractError("VisualScene.schema_version must be 1")
        for name in ("scenario", "partition", "symbol", "reference_timeframe"):
            _text(getattr(self, name), name)
        if self.seed != 2 or self.partition != "VALIDATION":
            raise VisualContractError("visual preview accepts only VALIDATION seed 2")
        if (self.preview_label, self.oos_label, self.advice_label, self.core_status) != (PREVIEW_LABEL, OOS_LABEL, ADVICE_LABEL, CORE_STATUS):
            raise VisualContractError("visual preview status labels must be exact")
        as_of = _time(self.as_of_time, "as_of_time")
        typed = ((self.candles, VisualCandle, "candles"), (self.confirmed_boundaries, VisualBoundary, "confirmed_boundaries"), (self.candidate_boundaries, VisualBoundary, "candidate_boundaries"), (self.resonance_zones, VisualZone, "resonance_zones"))
        for values, expected, field in typed:
            if not isinstance(values, tuple) or any(not isinstance(item, expected) for item in values):
                raise VisualContractError(f"{field} has invalid items")
        if not self.candles:
            raise VisualContractError("scene must contain at least one candle")
        if any(item.available_time > as_of for item in self.candles):
            raise VisualContractError("scene contains a future candle")
        boundaries = self.confirmed_boundaries + self.candidate_boundaries
        if any(item.confirm_time > as_of or item.display_end_time > as_of for item in boundaries):
            raise VisualContractError("scene contains a future boundary state")
        if any(item.tier is not BoundaryTier.CONFIRMED for item in self.confirmed_boundaries) or any(item.tier is not BoundaryTier.CANDIDATE for item in self.candidate_boundaries):
            raise VisualContractError("boundary tier collections are inconsistent")
        if any(item.confirm_time > as_of for item in self.resonance_zones):
            raise VisualContractError("scene contains a future Zone")
        if self.active_box is not None and (not isinstance(self.active_box, VisualActiveBox) or self.active_box.confirm_time > as_of):
            raise VisualContractError("scene contains a future Active Box")
        _ids(self.source_ids, "source_ids")
        object.__setattr__(self, "as_of_time", as_of)

    @property
    def boundary_count(self) -> int:
        return len(self.confirmed_boundaries) + len(self.candidate_boundaries)

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "scenario": self.scenario, "seed": self.seed, "partition": self.partition, "as_of_time": self.as_of_time.isoformat(), "symbol": self.symbol, "reference_timeframe": self.reference_timeframe, "preview_label": self.preview_label, "oos_label": self.oos_label, "advice_label": self.advice_label, "core_status": self.core_status, "candles": [item.to_dict() for item in self.candles], "confirmed_boundaries": [item.to_dict() for item in self.confirmed_boundaries], "candidate_boundaries": [item.to_dict() for item in self.candidate_boundaries], "resonance_zones": [item.to_dict() for item in self.resonance_zones], "active_box": None if self.active_box is None else self.active_box.to_dict(), "source_ids": list(self.source_ids)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Self:
        fields = {"scenario", "seed", "partition", "as_of_time", "symbol", "reference_timeframe", "preview_label", "oos_label", "advice_label", "core_status", "candles", "confirmed_boundaries", "candidate_boundaries", "resonance_zones", "active_box", "source_ids"}
        data = _mapping(payload, cls.__name__, fields)
        box = data["active_box"]
        return cls(scenario=data["scenario"], seed=data["seed"], partition=data["partition"], as_of_time=_time_from(data["as_of_time"], "as_of_time"), symbol=data["symbol"], reference_timeframe=data["reference_timeframe"], preview_label=data["preview_label"], oos_label=data["oos_label"], advice_label=data["advice_label"], core_status=data["core_status"], candles=tuple(VisualCandle.from_dict(item) for item in _list(data, "candles")), confirmed_boundaries=tuple(VisualBoundary.from_dict(item) for item in _list(data, "confirmed_boundaries")), candidate_boundaries=tuple(VisualBoundary.from_dict(item) for item in _list(data, "candidate_boundaries")), resonance_zones=tuple(VisualZone.from_dict(item) for item in _list(data, "resonance_zones")), active_box=None if box is None else VisualActiveBox.from_dict(box), source_ids=tuple(_list(data, "source_ids")), schema_version=data["schema_version"])

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
