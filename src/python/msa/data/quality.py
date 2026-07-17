"""Immutable market-data quality reports and sequence validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence

from msa.data.contracts import CanonicalBar, Timeframe


class IssueSeverity(str, Enum):
    """Severity of one traceable data-quality finding."""

    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    """One explainable finding tied to source row and field context."""

    code: str
    severity: IssueSeverity
    row_number: int
    field: str
    raw_value: str
    reason: str

    def __post_init__(self) -> None:
        if not self.code or not self.field or not self.reason:
            raise ValueError("quality issue code, field, and reason are required")
        if self.row_number < 1:
            raise ValueError("quality issue row_number must be positive")

    def __str__(self) -> str:
        return (
            f"row {self.row_number}, field {self.field!r}, "
            f"raw value {self.raw_value}: {self.reason}"
        )


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    """Immutable audit result for one source-configured load attempt.

    ``accepted_rows`` counts rows successfully converted to ``CanonicalBar``
    before the strict sequence gate. Strict mode still rejects the complete
    load when ``errors`` is non-empty.
    """

    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_count: int
    conflicting_duplicate_count: int
    out_of_order_count: int
    overlap_count: int
    gap_count: int
    invalid_ohlc_count: int
    invalid_timestamp_count: int
    invalid_volume_count: int
    symbol_mismatch_count: int
    timeframe: Timeframe
    source: str
    earliest_timestamp: datetime | None
    latest_timestamp: datetime | None
    warnings: tuple[DataQualityIssue, ...]
    errors: tuple[DataQualityIssue, ...]
    assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        count_fields = (
            "total_rows",
            "accepted_rows",
            "rejected_rows",
            "duplicate_count",
            "conflicting_duplicate_count",
            "out_of_order_count",
            "overlap_count",
            "gap_count",
            "invalid_ohlc_count",
            "invalid_timestamp_count",
            "invalid_volume_count",
            "symbol_mismatch_count",
        )
        if any(getattr(self, field_name) < 0 for field_name in count_fields):
            raise ValueError("data-quality counts cannot be negative")
        if self.total_rows != self.accepted_rows + self.rejected_rows:
            raise ValueError(
                "total_rows must equal accepted_rows + rejected_rows"
            )
        if not isinstance(self.timeframe, Timeframe):
            raise ValueError("quality report timeframe must be a Timeframe")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("quality report source must be non-empty")
        if self.warnings and any(
            issue.severity is not IssueSeverity.WARNING
            for issue in self.warnings
        ):
            raise ValueError("warnings may contain only WARNING issues")
        if self.errors and any(
            issue.severity is not IssueSeverity.ERROR for issue in self.errors
        ):
            raise ValueError("errors may contain only ERROR issues")

    @property
    def has_errors(self) -> bool:
        """Whether strict loading must fail."""

        return bool(self.errors)


def validate_bar_sequence(
    bars: Sequence[CanonicalBar],
    *,
    source: str,
    timeframe: Timeframe,
    row_numbers: Sequence[int] | None = None,
    total_rows: int | None = None,
    rejected_rows: int = 0,
    prior_issues: Sequence[DataQualityIssue] = (),
    invalid_ohlc_count: int = 0,
    invalid_timestamp_count: int = 0,
    invalid_volume_count: int = 0,
    symbol_mismatch_count: int = 0,
    assumptions: Sequence[str] = (),
) -> DataQualityReport:
    """Validate order, duplicates, conflicts, overlaps, and interval gaps.

    Input order is inspected exactly as supplied. This function never sorts,
    deduplicates, repairs, fills, or resamples bars.
    """

    if row_numbers is None:
        rows = tuple(range(1, len(bars) + 1))
    else:
        rows = tuple(row_numbers)
        if len(rows) != len(bars):
            raise ValueError("row_numbers length must match bars length")
        if any(row_number < 1 for row_number in rows):
            raise ValueError("row_numbers must be positive")

    warnings = [
        issue
        for issue in prior_issues
        if issue.severity is IssueSeverity.WARNING
    ]
    errors = [
        issue for issue in prior_issues if issue.severity is IssueSeverity.ERROR
    ]

    duplicate_count = 0
    conflicting_duplicate_count = 0
    out_of_order_count = 0
    overlap_count = 0
    gap_count = 0
    seen: dict[tuple[str, Timeframe, datetime], CanonicalBar] = {}

    for index, bar in enumerate(bars):
        row_number = rows[index]
        key = (bar.symbol, bar.timeframe, bar.timestamp)
        earlier = seen.get(key)
        if earlier is not None:
            duplicate_count += 1
            is_conflict = earlier != bar
            if is_conflict:
                conflicting_duplicate_count += 1
            errors.append(
                DataQualityIssue(
                    code=(
                        "conflicting_duplicate" if is_conflict else "duplicate"
                    ),
                    severity=IssueSeverity.ERROR,
                    row_number=row_number,
                    field="symbol+timeframe+timestamp",
                    raw_value=bar.timestamp.isoformat(),
                    reason=(
                        "same key has conflicting OHLCV or provenance"
                        if is_conflict
                        else "duplicate canonical bar key"
                    ),
                )
            )
        else:
            seen[key] = bar

        if index == 0:
            continue
        previous = bars[index - 1]
        if bar.timestamp < previous.timestamp:
            out_of_order_count += 1
            errors.append(
                DataQualityIssue(
                    code="out_of_order",
                    severity=IssueSeverity.ERROR,
                    row_number=row_number,
                    field="timestamp",
                    raw_value=bar.timestamp.isoformat(),
                    reason=(
                        "timestamp is earlier than the preceding input row "
                        f"({previous.timestamp.isoformat()})"
                    ),
                )
            )
            continue

        duration = timeframe.fixed_duration
        comparable = (
            duration is not None
            and bar.symbol == previous.symbol
            and bar.timeframe is previous.timeframe
            and bar.timestamp > previous.timestamp
        )
        if comparable and bar.timestamp < previous.end_time:
            overlap_count += 1
            errors.append(
                DataQualityIssue(
                    code="interval_overlap",
                    severity=IssueSeverity.ERROR,
                    row_number=row_number,
                    field="timestamp",
                    raw_value=bar.timestamp.isoformat(),
                    reason=(
                        "current timestamp "
                        f"{bar.timestamp.isoformat()} is earlier than "
                        "previous.end_time "
                        f"{previous.end_time.isoformat()}"
                    ),
                )
            )
        elif comparable and bar.timestamp > previous.end_time:
            gap_count += 1
            warnings.append(
                DataQualityIssue(
                    code="interval_gap",
                    severity=IssueSeverity.WARNING,
                    row_number=row_number,
                    field="timestamp",
                    raw_value=bar.timestamp.isoformat(),
                    reason=(
                        "interval gap from "
                        f"{previous.end_time.isoformat()} to "
                        f"{bar.timestamp.isoformat()}; it may represent a "
                        "session close, weekend, or holiday"
                    ),
                )
            )

    timestamps = [bar.timestamp for bar in bars]
    accepted_rows = len(bars)
    effective_total = (
        accepted_rows + rejected_rows if total_rows is None else total_rows
    )
    if effective_total != accepted_rows + rejected_rows:
        raise ValueError(
            "total_rows must equal len(bars) + rejected_rows"
        )

    return DataQualityReport(
        total_rows=effective_total,
        accepted_rows=accepted_rows,
        rejected_rows=rejected_rows,
        duplicate_count=duplicate_count,
        conflicting_duplicate_count=conflicting_duplicate_count,
        out_of_order_count=out_of_order_count,
        overlap_count=overlap_count,
        gap_count=gap_count,
        invalid_ohlc_count=invalid_ohlc_count,
        invalid_timestamp_count=invalid_timestamp_count,
        invalid_volume_count=invalid_volume_count,
        symbol_mismatch_count=symbol_mismatch_count,
        timeframe=timeframe,
        source=source,
        earliest_timestamp=min(timestamps) if timestamps else None,
        latest_timestamp=max(timestamps) if timestamps else None,
        warnings=tuple(warnings),
        errors=tuple(errors),
        assumptions=tuple(assumptions),
    )
