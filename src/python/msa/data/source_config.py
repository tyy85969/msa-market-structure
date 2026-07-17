"""Explicit source schema and semantics for market-data adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from enum import Enum
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from msa.data.contracts import Timeframe, VolumeType


class SourceConfigurationError(ValueError):
    """Raised when source semantics are missing, ambiguous, or inconsistent."""


class TimestampSemantics(str, Enum):
    """Meaning of the configured source timestamp column."""

    OPEN_TIME = "OPEN_TIME"
    CLOSE_TIME = "CLOSE_TIME"


class CompletedBarPolicy(str, Enum):
    """How a source proves whether each row is a completed bar."""

    ALL_ROWS_ARE_CLOSED = "ALL_ROWS_ARE_CLOSED"
    EXPLICIT_COLUMN = "EXPLICIT_COLUMN"


_OFFSET_PATTERN = re.compile(
    r"^(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2})$"
)


def _non_empty_text(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceConfigurationError(
            f"{field_name} must be a non-empty string"
        )
    return value


def resolve_source_timezone(value: str) -> tzinfo:
    """Resolve an explicit IANA zone or numeric UTC offset."""

    _non_empty_text("source_timezone", value)
    if value in {"UTC", "Z", "+00:00", "-00:00"}:
        return timezone.utc

    offset_match = _OFFSET_PATTERN.fullmatch(value)
    if offset_match is not None:
        hours = int(offset_match.group("hours"))
        minutes = int(offset_match.group("minutes"))
        if hours > 23 or minutes > 59:
            raise SourceConfigurationError(
                "source_timezone contains an invalid UTC offset"
            )
        delta = timedelta(hours=hours, minutes=minutes)
        if offset_match.group("sign") == "-":
            delta = -delta
        try:
            return timezone(delta)
        except ValueError as exc:
            raise SourceConfigurationError(
                "source_timezone contains an invalid UTC offset"
            ) from exc

    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise SourceConfigurationError(
            f"source_timezone is not a known IANA zone or UTC offset: {value!r}"
        ) from exc


@dataclass(frozen=True, slots=True)
class SourceDataConfig:
    """Immutable, source-specific mapping into the canonical bar contract.

    The configuration deliberately has no implicit symbol mapping, timestamp
    semantics, volume meaning, completion policy, or availability lag.
    """

    source: str
    source_timezone: str
    source_symbol: str
    canonical_symbol: str
    timeframe: Timeframe
    timestamp_column: str
    timestamp_semantics: TimestampSemantics
    timestamp_format: str
    open_column: str
    high_column: str
    low_column: str
    close_column: str
    volume_column: str | None
    volume_type: VolumeType
    completed_bar_policy: CompletedBarPolicy
    availability_lag: timedelta
    session_id: str | None
    boundary_policy: str | None
    end_time_column: str | None
    symbol_column: str | None = None
    open_time_column: str | None = None
    complete_column: str | None = None
    complete_true_values: tuple[str, ...] = ()
    complete_false_values: tuple[str, ...] = ()
    delimiter: str = ","
    strict: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "source",
            "source_timezone",
            "source_symbol",
            "canonical_symbol",
            "timestamp_column",
            "timestamp_format",
            "open_column",
            "high_column",
            "low_column",
            "close_column",
        ):
            _non_empty_text(field_name, getattr(self, field_name))

        for field_name in (
            "volume_column",
            "session_id",
            "boundary_policy",
            "end_time_column",
            "symbol_column",
            "open_time_column",
            "complete_column",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _non_empty_text(field_name, value)

        if not isinstance(self.timeframe, Timeframe):
            raise SourceConfigurationError("timeframe must be a Timeframe")
        if not isinstance(self.timestamp_semantics, TimestampSemantics):
            raise SourceConfigurationError(
                "timestamp_semantics must be a TimestampSemantics"
            )
        if not isinstance(self.volume_type, VolumeType):
            raise SourceConfigurationError("volume_type must be a VolumeType")
        if not isinstance(self.completed_bar_policy, CompletedBarPolicy):
            raise SourceConfigurationError(
                "completed_bar_policy must be a CompletedBarPolicy"
            )
        if not isinstance(self.availability_lag, timedelta):
            raise SourceConfigurationError(
                "availability_lag must be an explicit timedelta"
            )
        if self.availability_lag < timedelta(0):
            raise SourceConfigurationError(
                "availability_lag must be greater than or equal to zero"
            )
        if not isinstance(self.strict, bool):
            raise SourceConfigurationError("strict must be a bool")
        if not isinstance(self.delimiter, str) or len(self.delimiter) != 1:
            raise SourceConfigurationError(
                "delimiter must be exactly one character"
            )
        if self.delimiter in {"\r", "\n"}:
            raise SourceConfigurationError("delimiter cannot be a newline")

        resolve_source_timezone(self.source_timezone)
        self._validate_volume_mapping()
        self._validate_completion_mapping()
        self._validate_interval_mapping()
        self._validate_distinct_columns()

    def _validate_volume_mapping(self) -> None:
        if self.volume_type is VolumeType.UNAVAILABLE:
            if self.volume_column is not None:
                raise SourceConfigurationError(
                    "volume_type=UNAVAILABLE requires volume_column=None"
                )
        elif self.volume_column is None:
            raise SourceConfigurationError(
                "REAL and TICK volume require an explicit volume_column"
            )

    def _validate_completion_mapping(self) -> None:
        if self.completed_bar_policy is CompletedBarPolicy.ALL_ROWS_ARE_CLOSED:
            if self.complete_column is not None:
                raise SourceConfigurationError(
                    "ALL_ROWS_ARE_CLOSED requires complete_column=None"
                )
            if self.complete_true_values or self.complete_false_values:
                raise SourceConfigurationError(
                    "ALL_ROWS_ARE_CLOSED cannot define completion value mappings"
                )
            return

        if self.complete_column is None:
            raise SourceConfigurationError(
                "EXPLICIT_COLUMN requires an explicit complete_column"
            )
        if not self.complete_true_values or not self.complete_false_values:
            raise SourceConfigurationError(
                "EXPLICIT_COLUMN requires explicit true and false value mappings"
            )
        for value in self.complete_true_values + self.complete_false_values:
            _non_empty_text("completion mapping value", value)
        overlap = set(self.complete_true_values) & set(self.complete_false_values)
        if overlap:
            raise SourceConfigurationError(
                "completion true and false value mappings must be disjoint"
            )

    def _validate_interval_mapping(self) -> None:
        if self.timestamp_semantics is TimestampSemantics.OPEN_TIME:
            if self.open_time_column is not None:
                raise SourceConfigurationError(
                    "OPEN_TIME cannot also define open_time_column"
                )
            if self.timeframe.requires_boundary_policy:
                if self.end_time_column is None or self.boundary_policy is None:
                    raise SourceConfigurationError(
                        f"{self.timeframe.value} OPEN_TIME requires explicit "
                        "end_time_column and boundary_policy"
                    )
        else:
            if self.end_time_column is not None:
                raise SourceConfigurationError(
                    "CLOSE_TIME cannot also define end_time_column"
                )
            if self.timeframe.requires_boundary_policy:
                if self.open_time_column is None or self.boundary_policy is None:
                    raise SourceConfigurationError(
                        f"{self.timeframe.value} CLOSE_TIME requires explicit "
                        "open_time_column and boundary_policy"
                    )

    def _validate_distinct_columns(self) -> None:
        columns = self.required_columns()
        if len(columns) != len(set(columns)):
            raise SourceConfigurationError(
                "each configured source field must map to a distinct column"
            )

    def required_columns(self) -> tuple[str, ...]:
        """Return the complete explicit input schema in deterministic order."""

        columns = [
            self.timestamp_column,
            self.open_column,
            self.high_column,
            self.low_column,
            self.close_column,
        ]
        for column in (
            self.volume_column,
            self.symbol_column,
            self.open_time_column,
            self.end_time_column,
            self.complete_column,
        ):
            if column is not None:
                columns.append(column)
        return tuple(columns)

    def timezone(self) -> tzinfo:
        """Return the validated source timezone implementation."""

        return resolve_source_timezone(self.source_timezone)

    def assumptions(self) -> tuple[str, ...]:
        """Return auditable assumptions recorded in each quality report."""

        return (
            f"explicit symbol mapping {self.source_symbol} -> "
            f"{self.canonical_symbol}",
            f"source timestamp semantics: {self.timestamp_semantics.value}",
            f"source timezone: {self.source_timezone}",
            f"completed-bar policy: {self.completed_bar_policy.value}",
            f"availability lag: {self.availability_lag.total_seconds()} seconds",
        )
