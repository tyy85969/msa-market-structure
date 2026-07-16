"""Canonical market-data types and validation rules.

This module defines data contracts only. It intentionally contains no loading,
calendar, data-cleaning, or resampling implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Mapping


class ContractValidationError(ValueError):
    """Raised when market data violates the canonical contract."""


class IncompleteBarError(ContractValidationError):
    """Raised when an incomplete bar is requested from a confirmed stream."""


class Timeframe(str, Enum):
    """Approved stable timeframe codes for the MSA market-data boundary."""

    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H2 = "H2"
    H4 = "H4"
    H12 = "H12"
    D = "D"
    W = "W"

    @property
    def fixed_duration(self) -> timedelta | None:
        """Return the fixed duration, or ``None`` for calendar-bound periods."""

        return {
            Timeframe.M15: timedelta(minutes=15),
            Timeframe.M30: timedelta(minutes=30),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.H2: timedelta(hours=2),
            Timeframe.H4: timedelta(hours=4),
            Timeframe.H12: timedelta(hours=12),
            Timeframe.D: None,
            Timeframe.W: None,
        }[self]

    @property
    def is_fixed_duration(self) -> bool:
        """Whether bars can be bounded using a fixed elapsed duration."""

        return self.fixed_duration is not None

    @property
    def requires_boundary_policy(self) -> bool:
        """Whether a source/session policy must determine bar boundaries."""

        return not self.is_fixed_duration


class VolumeType(str, Enum):
    """Meaning of the volume observation attached to a bar."""

    REAL = "REAL"
    TICK = "TICK"
    UNAVAILABLE = "UNAVAILABLE"


def _normalize_utc_datetime(field_name: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ContractValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _decimal_value(field_name: str, value: object) -> Decimal:
    if isinstance(value, bool):
        raise ContractValidationError(f"{field_name} must be numeric, not bool")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    raise ContractValidationError(
        f"{field_name} must be Decimal, int, or float"
    )


def _non_empty_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalBar:
    """Immutable, validated OHLCV bar with explicit availability semantics.

    ``timestamp`` is the inclusive opening time and ``end_time`` is the
    exclusive interval end. All three datetime fields are normalized to UTC.
    ``available_time`` is retained separately because event availability is not
    implied by the historical bar timestamp.
    """

    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    volume_type: VolumeType
    source: str
    source_timezone: str
    is_complete: bool
    available_time: datetime
    session_id: str | None = None
    boundary_policy: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _non_empty_text("symbol", self.symbol))
        object.__setattr__(self, "source", _non_empty_text("source", self.source))
        object.__setattr__(
            self,
            "source_timezone",
            _non_empty_text("source_timezone", self.source_timezone),
        )

        if not isinstance(self.timeframe, Timeframe):
            raise ContractValidationError("timeframe must be a Timeframe")
        if not isinstance(self.volume_type, VolumeType):
            raise ContractValidationError("volume_type must be a VolumeType")
        if not isinstance(self.is_complete, bool):
            raise ContractValidationError("is_complete must be a bool")

        if self.session_id is not None:
            _non_empty_text("session_id", self.session_id)
        if self.boundary_policy is not None:
            _non_empty_text("boundary_policy", self.boundary_policy)

        timestamp = _normalize_utc_datetime("timestamp", self.timestamp)
        end_time = _normalize_utc_datetime("end_time", self.end_time)
        available_time = _normalize_utc_datetime(
            "available_time", self.available_time
        )
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "end_time", end_time)
        object.__setattr__(self, "available_time", available_time)

        if end_time <= timestamp:
            raise ContractValidationError("end_time must be later than timestamp")
        if available_time < timestamp:
            raise ContractValidationError(
                "available_time must not be earlier than timestamp"
            )

        duration = self.timeframe.fixed_duration
        if duration is not None and end_time != timestamp + duration:
            raise ContractValidationError(
                f"end_time must equal timestamp + {duration} for "
                f"{self.timeframe.value}"
            )
        if self.timeframe.requires_boundary_policy and self.boundary_policy is None:
            raise ContractValidationError(
                f"{self.timeframe.value} bars require an explicit boundary_policy"
            )
        if self.is_complete and available_time < end_time:
            raise ContractValidationError(
                "a completed bar's available_time must not be earlier than end_time"
            )

        prices: dict[str, Decimal] = {}
        for field_name in ("open", "high", "low", "close"):
            value = _decimal_value(field_name, getattr(self, field_name))
            if not value.is_finite():
                raise ContractValidationError(f"{field_name} must be finite")
            prices[field_name] = value
            object.__setattr__(self, field_name, value)

        if prices["high"] < prices["low"]:
            raise ContractValidationError("high must be greater than or equal to low")
        if prices["high"] < prices["open"]:
            raise ContractValidationError("high must be greater than or equal to open")
        if prices["high"] < prices["close"]:
            raise ContractValidationError("high must be greater than or equal to close")
        if prices["low"] > prices["open"]:
            raise ContractValidationError("low must be less than or equal to open")
        if prices["low"] > prices["close"]:
            raise ContractValidationError("low must be less than or equal to close")

        if self.volume is None:
            if self.volume_type is not VolumeType.UNAVAILABLE:
                raise ContractValidationError(
                    "volume=None requires volume_type=UNAVAILABLE"
                )
        else:
            volume = _decimal_value("volume", self.volume)
            if not volume.is_finite():
                raise ContractValidationError("volume must be finite")
            if volume < 0:
                raise ContractValidationError("volume must be greater than or equal to 0")
            if self.volume_type is VolumeType.UNAVAILABLE:
                raise ContractValidationError(
                    "volume_type=UNAVAILABLE requires volume=None"
                )
            object.__setattr__(self, "volume", volume)

    def is_confirmed_at(self, processing_time: datetime) -> bool:
        """Return whether this bar is safe for a confirmed stream at a time."""

        normalized_time = _normalize_utc_datetime(
            "processing_time", processing_time
        )
        return self.is_complete and normalized_time >= self.available_time

    def require_confirmed(self, processing_time: datetime) -> CanonicalBar:
        """Return this bar only when it is confirmed and causally available."""

        if not self.is_complete:
            raise IncompleteBarError(
                "incomplete bars cannot enter a confirmed/closed-bar stream"
            )
        if not self.is_confirmed_at(processing_time):
            raise ContractValidationError(
                "bar is not available to the confirmed stream at processing_time"
            )
        return self

    def to_dict(self) -> dict[str, object]:
        """Serialize to stable, JSON-compatible primitive values."""

        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp": self.timestamp.isoformat(),
            "end_time": self.end_time.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": None if self.volume is None else str(self.volume),
            "volume_type": self.volume_type.value,
            "source": self.source,
            "source_timezone": self.source_timezone,
            "is_complete": self.is_complete,
            "available_time": self.available_time.isoformat(),
            "session_id": self.session_id,
            "boundary_policy": self.boundary_policy,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CanonicalBar:
        """Deserialize a bar and re-run the complete contract validation."""

        try:
            is_complete = payload["is_complete"]
            if not isinstance(is_complete, bool):
                raise ContractValidationError("is_complete must be a bool")
            raw_volume = payload["volume"]
            volume = None if raw_volume is None else Decimal(str(raw_volume))
            return cls(
                symbol=payload["symbol"],
                timeframe=Timeframe(payload["timeframe"]),
                timestamp=datetime.fromisoformat(str(payload["timestamp"])),
                end_time=datetime.fromisoformat(str(payload["end_time"])),
                open=Decimal(str(payload["open"])),
                high=Decimal(str(payload["high"])),
                low=Decimal(str(payload["low"])),
                close=Decimal(str(payload["close"])),
                volume=volume,
                volume_type=VolumeType(payload["volume_type"]),
                source=payload["source"],
                source_timezone=payload["source_timezone"],
                is_complete=is_complete,
                available_time=datetime.fromisoformat(
                    str(payload["available_time"])
                ),
                session_id=payload["session_id"],
                boundary_policy=payload["boundary_policy"],
            )
        except ContractValidationError:
            raise
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise ContractValidationError(
                f"invalid serialized CanonicalBar: {exc}"
            ) from exc
