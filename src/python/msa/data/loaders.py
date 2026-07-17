"""Source-configured CSV and iterable-record market-data loading."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from decimal import Decimal, InvalidOperation
from os import PathLike
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from msa.data.contracts import (
    CanonicalBar,
    ContractValidationError,
    VolumeType,
)
from msa.data.quality import (
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    validate_bar_sequence,
)
from msa.data.source_config import (
    CompletedBarPolicy,
    SourceDataConfig,
    TimestampSemantics,
)


@dataclass(frozen=True, slots=True)
class LoadResult:
    """Immutable result of a successful source-configured load."""

    bars: tuple[CanonicalBar, ...]
    quality_report: DataQualityReport
    source_config: SourceDataConfig
    loaded_row_count: int
    accepted_row_count: int
    rejected_row_count: int

    def __post_init__(self) -> None:
        if self.loaded_row_count != self.quality_report.total_rows:
            raise ValueError("loaded_row_count must match quality report")
        if self.accepted_row_count != self.quality_report.accepted_rows:
            raise ValueError("accepted_row_count must match quality report")
        if self.rejected_row_count != self.quality_report.rejected_rows:
            raise ValueError("rejected_row_count must match quality report")
        if len(self.bars) != self.accepted_row_count:
            raise ValueError("bars length must equal accepted_row_count")

    @property
    def config_snapshot(self) -> SourceDataConfig:
        """Return the immutable configuration used for this load."""

        return self.source_config


class DataLoadError(ValueError):
    """Raised when strict loading finds any row or sequence error."""

    def __init__(self, report: DataQualityReport) -> None:
        self.report = report
        first_error = report.errors[0] if report.errors else None
        detail = str(first_error) if first_error is not None else "unknown error"
        super().__init__(f"market-data loading failed: {detail}")


@dataclass(frozen=True, slots=True)
class _RowValidationError(Exception):
    issue: DataQualityIssue
    category: str | None = None


def load_csv(
    path: str | PathLike[str], config: SourceDataConfig
) -> LoadResult:
    """Load a UTF-8 CSV without sorting, repairing, or modifying it."""

    csv_path = Path(path)
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=config.delimiter)
            fieldnames = tuple(reader.fieldnames or ())
            header_error = _validate_csv_header(fieldnames, config)
            if header_error is not None:
                raise DataLoadError(_empty_report(config, header_error))
            numbered_records = tuple(
                (reader.line_num, dict(record)) for record in reader
            )
    except DataLoadError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        issue = DataQualityIssue(
            code="invalid_csv",
            severity=IssueSeverity.ERROR,
            row_number=1,
            field="csv",
            raw_value=_safe_raw(csv_path.name),
            reason=f"unable to read a UTF-8 CSV ({type(exc).__name__})",
        )
        raise DataLoadError(_empty_report(config, issue)) from exc

    return _load_numbered_records(numbered_records, config)


def load_records(
    records: Iterable[Mapping[str, object]], config: SourceDataConfig
) -> LoadResult:
    """Load source records using exactly the same mapping as the CSV path."""

    numbered_records = tuple(enumerate(records, start=1))
    return _load_numbered_records(numbered_records, config)


def _validate_csv_header(
    fieldnames: Sequence[str], config: SourceDataConfig
) -> DataQualityIssue | None:
    if not fieldnames:
        return DataQualityIssue(
            code="missing_header",
            severity=IssueSeverity.ERROR,
            row_number=1,
            field="header",
            raw_value="()",
            reason="CSV must contain a header row",
        )
    if len(fieldnames) != len(set(fieldnames)):
        return DataQualityIssue(
            code="duplicate_header",
            severity=IssueSeverity.ERROR,
            row_number=1,
            field="header",
            raw_value=_safe_raw(fieldnames),
            reason="CSV header names must be unique",
        )
    missing = [
        column for column in config.required_columns() if column not in fieldnames
    ]
    if missing:
        return DataQualityIssue(
            code="missing_columns",
            severity=IssueSeverity.ERROR,
            row_number=1,
            field="header",
            raw_value=_safe_raw(fieldnames),
            reason=f"missing required columns: {', '.join(missing)}",
        )
    return None


def _load_numbered_records(
    numbered_records: Sequence[tuple[int, object]],
    config: SourceDataConfig,
) -> LoadResult:
    bars: list[CanonicalBar] = []
    accepted_row_numbers: list[int] = []
    issues: list[DataQualityIssue] = []
    counts = {
        "invalid_ohlc": 0,
        "invalid_timestamp": 0,
        "invalid_volume": 0,
        "symbol_mismatch": 0,
    }

    for row_number, record in numbered_records:
        if not isinstance(record, Mapping):
            issues.append(
                DataQualityIssue(
                    code="invalid_record",
                    severity=IssueSeverity.ERROR,
                    row_number=row_number,
                    field="row",
                    raw_value=_safe_raw(record),
                    reason="record must be a mapping",
                )
            )
            continue
        try:
            bar = _parse_row(record, row_number, config)
        except _RowValidationError as exc:
            issues.append(exc.issue)
            if exc.category is not None:
                counts[exc.category] += 1
            continue
        bars.append(bar)
        accepted_row_numbers.append(row_number)

    rejected_rows = len(numbered_records) - len(bars)
    report = validate_bar_sequence(
        bars,
        source=config.source,
        timeframe=config.timeframe,
        row_numbers=accepted_row_numbers,
        total_rows=len(numbered_records),
        rejected_rows=rejected_rows,
        prior_issues=issues,
        invalid_ohlc_count=counts["invalid_ohlc"],
        invalid_timestamp_count=counts["invalid_timestamp"],
        invalid_volume_count=counts["invalid_volume"],
        symbol_mismatch_count=counts["symbol_mismatch"],
        assumptions=config.assumptions(),
    )
    if config.strict and report.has_errors:
        raise DataLoadError(report)

    return LoadResult(
        bars=tuple(bars),
        quality_report=report,
        source_config=config,
        loaded_row_count=report.total_rows,
        accepted_row_count=report.accepted_rows,
        rejected_row_count=report.rejected_rows,
    )


def _parse_row(
    record: Mapping[str, object],
    row_number: int,
    config: SourceDataConfig,
) -> CanonicalBar:
    if config.symbol_column is not None:
        raw_symbol = _required_cell(
            record, config.symbol_column, row_number, "symbol_mismatch"
        )
        if not isinstance(raw_symbol, str) or not raw_symbol:
            _raise_row_error(
                row_number,
                config.symbol_column,
                raw_symbol,
                "source symbol must be a non-empty string",
                "symbol_mismatch",
            )
        if raw_symbol != config.source_symbol:
            _raise_row_error(
                row_number,
                config.symbol_column,
                raw_symbol,
                f"source symbol does not equal {config.source_symbol!r}",
                "symbol_mismatch",
            )

    timestamp, end_time = _parse_interval(record, row_number, config)
    is_complete = _parse_completion(record, row_number, config)

    prices: dict[str, Decimal] = {}
    for canonical_name, source_column in (
        ("open", config.open_column),
        ("high", config.high_column),
        ("low", config.low_column),
        ("close", config.close_column),
    ):
        raw_value = _required_cell(
            record, source_column, row_number, "invalid_ohlc"
        )
        prices[canonical_name] = _parse_decimal(
            raw_value,
            row_number=row_number,
            field=source_column,
            category="invalid_ohlc",
        )

    volume: Decimal | None
    if config.volume_type is VolumeType.UNAVAILABLE:
        volume = None
    else:
        assert config.volume_column is not None
        raw_volume = _required_cell(
            record, config.volume_column, row_number, "invalid_volume"
        )
        volume = _parse_decimal(
            raw_volume,
            row_number=row_number,
            field=config.volume_column,
            category="invalid_volume",
        )

    try:
        return CanonicalBar(
            symbol=config.canonical_symbol,
            timeframe=config.timeframe,
            timestamp=timestamp,
            end_time=end_time,
            open=prices["open"],
            high=prices["high"],
            low=prices["low"],
            close=prices["close"],
            volume=volume,
            volume_type=config.volume_type,
            source=config.source,
            source_timezone=config.source_timezone,
            session_id=config.session_id,
            boundary_policy=config.boundary_policy,
            is_complete=is_complete,
            available_time=end_time + config.availability_lag,
        )
    except ContractValidationError as exc:
        message = str(exc)
        if "volume" in message:
            category = "invalid_volume"
            field = config.volume_column or "volume"
            raw_value = volume
        elif any(
            token in message
            for token in ("time", "end_time", "timestamp", "boundary_policy")
        ):
            category = "invalid_timestamp"
            field = config.timestamp_column
            raw_value = record.get(config.timestamp_column)
        else:
            category = "invalid_ohlc"
            field = "ohlc"
            raw_value = {
                config.open_column: record.get(config.open_column),
                config.high_column: record.get(config.high_column),
                config.low_column: record.get(config.low_column),
                config.close_column: record.get(config.close_column),
            }
        _raise_row_error(
            row_number, field, raw_value, message, category
        )


def _parse_interval(
    record: Mapping[str, object],
    row_number: int,
    config: SourceDataConfig,
) -> tuple[datetime, datetime]:
    source_time = _parse_timestamp_column(
        record, config.timestamp_column, row_number, config
    )
    duration = config.timeframe.fixed_duration

    if config.timestamp_semantics is TimestampSemantics.OPEN_TIME:
        timestamp = source_time
        if config.end_time_column is not None:
            end_time = _parse_timestamp_column(
                record, config.end_time_column, row_number, config
            )
        else:
            assert duration is not None
            end_time = timestamp + duration
    else:
        end_time = source_time
        if config.open_time_column is not None:
            timestamp = _parse_timestamp_column(
                record, config.open_time_column, row_number, config
            )
        else:
            assert duration is not None
            timestamp = end_time - duration
    return timestamp, end_time


def _parse_timestamp_column(
    record: Mapping[str, object],
    column: str,
    row_number: int,
    config: SourceDataConfig,
) -> datetime:
    raw_value = _required_cell(
        record, column, row_number, "invalid_timestamp"
    )
    if not isinstance(raw_value, str):
        _raise_row_error(
            row_number,
            column,
            raw_value,
            "timestamp must be text parsed by timestamp_format",
            "invalid_timestamp",
        )
    try:
        parsed = datetime.strptime(raw_value, config.timestamp_format)
    except ValueError as exc:
        _raise_row_error(
            row_number,
            column,
            raw_value,
            f"timestamp does not match format {config.timestamp_format!r}",
            "invalid_timestamp",
        )
        raise AssertionError("unreachable") from exc

    try:
        return _normalize_source_datetime(parsed, config.timezone())
    except ValueError as exc:
        _raise_row_error(
            row_number,
            column,
            raw_value,
            str(exc),
            "invalid_timestamp",
        )


def _normalize_source_datetime(parsed: datetime, source_tz: tzinfo) -> datetime:
    wall_time = parsed.replace(tzinfo=None)
    candidates = _valid_local_candidates(wall_time, source_tz)
    if not candidates:
        raise ValueError(
            "source local time does not exist in the configured timezone"
        )

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if len(candidates) > 1:
            raise ValueError(
                "source local time is ambiguous in the configured timezone; "
                "an explicit UTC offset is required"
            )
        return candidates[0].astimezone(timezone.utc)

    parsed_offset = parsed.utcoffset()
    matching = [
        candidate
        for candidate in candidates
        if candidate.utcoffset() == parsed_offset
    ]
    if not matching:
        raise ValueError(
            "timestamp UTC offset conflicts with source_timezone"
        )
    return parsed.astimezone(timezone.utc)


def _valid_local_candidates(
    wall_time: datetime, source_tz: tzinfo
) -> tuple[datetime, ...]:
    candidates: list[datetime] = []
    seen_offsets = set()
    for fold in (0, 1):
        candidate = wall_time.replace(tzinfo=source_tz, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(source_tz)
        if round_trip.replace(tzinfo=None) != wall_time:
            continue
        offset = candidate.utcoffset()
        if offset not in seen_offsets:
            candidates.append(candidate)
            seen_offsets.add(offset)
    return tuple(candidates)


def _parse_completion(
    record: Mapping[str, object],
    row_number: int,
    config: SourceDataConfig,
) -> bool:
    if config.completed_bar_policy is CompletedBarPolicy.ALL_ROWS_ARE_CLOSED:
        return True

    assert config.complete_column is not None
    raw_value = _required_cell(
        record, config.complete_column, row_number, None
    )
    if not isinstance(raw_value, str):
        _raise_row_error(
            row_number,
            config.complete_column,
            raw_value,
            "completion state must be text with an explicit value mapping",
            None,
        )
    if raw_value in config.complete_true_values:
        return True
    if raw_value in config.complete_false_values:
        return False
    _raise_row_error(
        row_number,
        config.complete_column,
        raw_value,
        "unknown completion state; no implicit truth-value coercion is allowed",
        None,
    )


def _parse_decimal(
    raw_value: object,
    *,
    row_number: int,
    field: str,
    category: str,
) -> Decimal:
    if isinstance(raw_value, bool):
        _raise_row_error(
            row_number, field, raw_value, "numeric value cannot be bool", category
        )
    try:
        if isinstance(raw_value, Decimal):
            value = raw_value
        elif isinstance(raw_value, int):
            value = Decimal(raw_value)
        elif isinstance(raw_value, float):
            value = Decimal(str(raw_value))
        elif isinstance(raw_value, str) and raw_value:
            value = Decimal(raw_value)
        else:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        _raise_row_error(
            row_number, field, raw_value, "value must be a decimal number", category
        )
    if not value.is_finite():
        _raise_row_error(
            row_number, field, raw_value, "value must be finite", category
        )
    return value


def _required_cell(
    record: Mapping[str, object],
    column: str,
    row_number: int,
    category: str | None,
) -> object:
    if column not in record:
        _raise_row_error(
            row_number,
            column,
            "<missing>",
            "required source field is missing",
            category,
        )
    value = record[column]
    if value is None or value == "":
        _raise_row_error(
            row_number,
            column,
            value,
            "required source field is empty",
            category,
        )
    return value


def _raise_row_error(
    row_number: int,
    field: str,
    raw_value: object,
    reason: str,
    category: str | None,
) -> None:
    raise _RowValidationError(
        DataQualityIssue(
            code=category or "invalid_row",
            severity=IssueSeverity.ERROR,
            row_number=row_number,
            field=field,
            raw_value=_safe_raw(raw_value, field=field),
            reason=reason,
        ),
        category,
    )


def _safe_raw(value: object, *, field: str | None = None) -> str:
    if field is not None and _is_sensitive_field(field):
        return "'<redacted-sensitive-field>'"
    if isinstance(value, Mapping):
        value = {
            key: (
                "<redacted-sensitive-field>"
                if _is_sensitive_field(str(key))
                else item
            )
            for key, item in value.items()
        }
    rendered = repr(value)
    if len(rendered) > 160:
        return rendered[:157] + "..."
    return rendered


def _is_sensitive_field(field: str) -> bool:
    normalized = field.lower().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "password",
            "secret",
            "token",
            "connection",
        )
    )


def _empty_report(
    config: SourceDataConfig, issue: DataQualityIssue
) -> DataQualityReport:
    return validate_bar_sequence(
        (),
        source=config.source,
        timeframe=config.timeframe,
        total_rows=0,
        prior_issues=(issue,),
        assumptions=config.assumptions(),
    )
