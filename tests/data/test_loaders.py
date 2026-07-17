from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import msa.data
from msa.data import (
    CanonicalBar,
    CompletedBarPolicy,
    DataLoadError,
    SourceConfigurationError,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    load_csv,
    load_records,
)


UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures"


def open_time_config(**overrides: object) -> SourceDataConfig:
    values: dict[str, object] = {
        "source": "synthetic-feed",
        "source_timezone": "America/New_York",
        "source_symbol": "GOLD",
        "canonical_symbol": "XAUUSD",
        "timeframe": Timeframe.M15,
        "timestamp_column": "time",
        "timestamp_semantics": TimestampSemantics.OPEN_TIME,
        "timestamp_format": "%Y-%m-%d %H:%M:%S",
        "open_column": "open",
        "high_column": "high",
        "low_column": "low",
        "close_column": "close",
        "volume_column": "tick_volume",
        "volume_type": VolumeType.TICK,
        "completed_bar_policy": CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        "availability_lag": timedelta(seconds=2),
        "session_id": "synthetic-session",
        "boundary_policy": None,
        "end_time_column": None,
        "symbol_column": "symbol",
    }
    values.update(overrides)
    return SourceDataConfig(**values)


def close_time_config(**overrides: object) -> SourceDataConfig:
    values: dict[str, object] = {
        "source_timezone": "+02:00",
        "timestamp_column": "close_time",
        "timestamp_semantics": TimestampSemantics.CLOSE_TIME,
        "timestamp_format": "%Y-%m-%dT%H:%M:%S%z",
        "volume_column": "real_volume",
        "volume_type": VolumeType.REAL,
        "availability_lag": timedelta(0),
    }
    values.update(overrides)
    return replace(open_time_config(), **values)


def valid_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "time": "2026-01-02 03:00:00",
        "symbol": "GOLD",
        "open": "2000.0",
        "high": "2002.0",
        "low": "1998.0",
        "close": "2001.0",
        "tick_volume": "125",
    }
    record.update(overrides)
    return record


def test_valid_open_time_csv_loads_as_canonical_bars() -> None:
    result = load_csv(FIXTURES / "valid_open_time.csv", open_time_config())

    assert result.loaded_row_count == 2
    assert result.accepted_row_count == 2
    assert result.rejected_row_count == 0
    assert all(isinstance(bar, CanonicalBar) for bar in result.bars)
    assert result.bars[0].timestamp == datetime(2026, 1, 2, 8, 0, tzinfo=UTC)
    assert result.bars[0].end_time == datetime(2026, 1, 2, 8, 15, tzinfo=UTC)


def test_valid_close_time_csv_calculates_open_time() -> None:
    result = load_csv(FIXTURES / "valid_close_time.csv", close_time_config())

    assert result.bars[0].timestamp == datetime(2026, 1, 2, 8, 0, tzinfo=UTC)
    assert result.bars[0].end_time == datetime(2026, 1, 2, 8, 15, tzinfo=UTC)


def test_source_local_timezone_is_converted_to_utc() -> None:
    bar = load_records([valid_record()], open_time_config()).bars[0]

    assert bar.timestamp == datetime(2026, 1, 2, 8, 0, tzinfo=UTC)
    assert bar.source_timezone == "America/New_York"


def test_non_utc_offset_timestamp_is_converted_to_utc() -> None:
    bar = load_csv(
        FIXTURES / "valid_close_time.csv", close_time_config()
    ).bars[0]

    assert bar.end_time == datetime(2026, 1, 2, 8, 15, tzinfo=UTC)


def test_explicit_symbol_mapping_is_applied() -> None:
    bar = load_records([valid_record()], open_time_config()).bars[0]

    assert bar.symbol == "XAUUSD"
    assert bar.symbol != "GOLD"


def test_source_symbol_mismatch_is_rejected_with_context() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records([valid_record(symbol="XAUUSD")], open_time_config())

    issue = exc_info.value.report.errors[0]
    assert issue.row_number == 1
    assert issue.field == "symbol"
    assert "XAUUSD" in issue.raw_value
    assert exc_info.value.report.symbol_mismatch_count == 1


@pytest.mark.parametrize("field_name", ["source_symbol", "canonical_symbol"])
def test_symbol_mapping_cannot_be_omitted(field_name: str) -> None:
    with pytest.raises(SourceConfigurationError, match=field_name):
        open_time_config(**{field_name: "  "})


@pytest.mark.parametrize(
    ("volume_type", "volume_column", "raw_volume", "expected"),
    [
        (VolumeType.REAL, "volume", "10", Decimal("10")),
        (VolumeType.TICK, "volume", "11", Decimal("11")),
        (VolumeType.UNAVAILABLE, None, None, None),
    ],
)
def test_volume_types_remain_explicit(
    volume_type: VolumeType,
    volume_column: str | None,
    raw_volume: str | None,
    expected: Decimal | None,
) -> None:
    config = open_time_config(
        volume_type=volume_type, volume_column=volume_column
    )
    record = valid_record()
    if volume_column is not None:
        record[volume_column] = raw_volume

    bar = load_records([record], config).bars[0]

    assert bar.volume_type is volume_type
    assert bar.volume == expected


def test_volume_none_and_observed_zero_are_distinct() -> None:
    unavailable = load_records(
        [valid_record()],
        open_time_config(
            volume_type=VolumeType.UNAVAILABLE, volume_column=None
        ),
    ).bars[0]
    observed_zero = load_csv(
        FIXTURES / "valid_close_time.csv", close_time_config()
    ).bars[0]

    assert unavailable.volume is None
    assert observed_zero.volume == Decimal("0")


def test_availability_lag_is_applied_after_end_time() -> None:
    bar = load_records([valid_record()], open_time_config()).bars[0]

    assert bar.available_time == bar.end_time + timedelta(seconds=2)
    assert bar.available_time >= bar.end_time


def test_explicit_completion_column_is_strictly_mapped() -> None:
    config = open_time_config(
        volume_type=VolumeType.UNAVAILABLE,
        volume_column=None,
        completed_bar_policy=CompletedBarPolicy.EXPLICIT_COLUMN,
        complete_column="complete",
        complete_true_values=("closed",),
        complete_false_values=("forming",),
        availability_lag=timedelta(0),
    )

    result = load_csv(FIXTURES / "explicit_completion.csv", config)

    assert result.bars[0].is_complete
    assert not result.bars[1].is_complete
    assert not result.bars[1].is_confirmed_at(result.bars[1].available_time)


def test_unknown_completion_value_is_not_coerced_to_true() -> None:
    config = open_time_config(
        completed_bar_policy=CompletedBarPolicy.EXPLICIT_COLUMN,
        complete_column="complete",
        complete_true_values=("closed",),
        complete_false_values=("forming",),
    )
    record = valid_record(complete="yes")

    with pytest.raises(DataLoadError, match="unknown completion state"):
        load_records([record], config)


def test_invalid_ohlc_is_rejected_with_row_and_field() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records([valid_record(high="1999")], open_time_config())

    issue = exc_info.value.report.errors[0]
    assert issue.row_number == 1
    assert issue.field == "ohlc"
    assert exc_info.value.report.invalid_ohlc_count == 1


def test_invalid_volume_is_rejected_with_row_and_field() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records([valid_record(tick_volume="-1")], open_time_config())

    issue = exc_info.value.report.errors[0]
    assert issue.row_number == 1
    assert issue.field == "tick_volume"
    assert exc_info.value.report.invalid_volume_count == 1


def test_invalid_timestamp_is_rejected_with_row_and_raw_value() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records([valid_record(time="not-a-time")], open_time_config())

    issue = exc_info.value.report.errors[0]
    assert issue.row_number == 1
    assert issue.field == "time"
    assert "not-a-time" in issue.raw_value
    assert exc_info.value.report.invalid_timestamp_count == 1


def test_sensitive_configured_field_value_is_redacted_from_error() -> None:
    config = open_time_config(symbol_column="api_key")
    record = valid_record(api_key="PRIVATE-VALUE-123")

    with pytest.raises(DataLoadError) as exc_info:
        load_records([record], config)

    assert "PRIVATE-VALUE-123" not in str(exc_info.value)
    assert "redacted-sensitive-field" in str(exc_info.value)


@pytest.mark.parametrize(
    ("raw_time", "reason"),
    [
        ("2026-11-01 01:30:00", "ambiguous"),
        ("2026-03-08 02:30:00", "does not exist"),
    ],
)
def test_ambiguous_or_nonexistent_dst_time_is_rejected(
    raw_time: str, reason: str
) -> None:
    with pytest.raises(DataLoadError, match=reason):
        load_records([valid_record(time=raw_time)], open_time_config())


def test_embedded_offset_must_match_configured_timezone() -> None:
    config = open_time_config(timestamp_format="%Y-%m-%d %H:%M:%S%z")

    with pytest.raises(DataLoadError, match="conflicts"):
        load_records(
            [valid_record(time="2026-01-02 03:00:00+0200")], config
        )


def test_missing_required_csv_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing-high.csv"
    path.write_text(
        "time,symbol,open,low,close,tick_volume\n"
        "2026-01-02 03:00:00,GOLD,2000,1998,2001,10\n",
        encoding="utf-8",
    )

    with pytest.raises(DataLoadError, match="missing required columns: high"):
        load_csv(path, open_time_config())


def test_empty_source_symbol_is_rejected() -> None:
    with pytest.raises(DataLoadError, match="field 'symbol'.*empty"):
        load_records([valid_record(symbol="")], open_time_config())


@pytest.mark.parametrize("timeframe", [Timeframe.D, Timeframe.W])
def test_daily_and_weekly_config_require_explicit_boundaries(
    timeframe: Timeframe,
) -> None:
    with pytest.raises(SourceConfigurationError, match="boundary_policy"):
        open_time_config(timeframe=timeframe)


def test_daily_open_time_accepts_explicit_end_and_boundary_policy() -> None:
    config = open_time_config(
        timeframe=Timeframe.D,
        end_time_column="end",
        boundary_policy="broker-session-v1",
    )
    record = valid_record(end="2026-01-03 03:00:00")

    bar = load_records([record], config).bars[0]

    assert bar.boundary_policy == "broker-session-v1"
    assert bar.end_time == datetime(2026, 1, 3, 8, 0, tzinfo=UTC)


def test_explicit_delimiter_is_used(tmp_path: Path) -> None:
    path = tmp_path / "semicolon.csv"
    path.write_text(
        "time;symbol;open;high;low;close;tick_volume\n"
        "2026-01-02 03:00:00;GOLD;2000;2002;1998;2001;10\n",
        encoding="utf-8",
    )

    result = load_csv(path, open_time_config(delimiter=";"))

    assert result.accepted_row_count == 1


def test_csv_input_is_not_modified() -> None:
    path = FIXTURES / "valid_open_time.csv"
    before = path.read_bytes()

    load_csv(path, open_time_config())

    assert path.read_bytes() == before


def test_load_result_order_matches_legal_input_order() -> None:
    result = load_csv(FIXTURES / "valid_open_time.csv", open_time_config())

    assert [bar.close for bar in result.bars] == [
        Decimal("2001.0"),
        Decimal("2002.0"),
    ]


def test_load_result_retains_quality_report_and_config_snapshot() -> None:
    config = open_time_config()
    result = load_records([valid_record()], config)

    assert result.source_config is config
    assert result.config_snapshot is config
    assert result.quality_report.source == config.source
    with pytest.raises(FrozenInstanceError):
        result.source_config.source = "changed"  # type: ignore[misc]


def test_canonical_serialization_retains_loader_available_time() -> None:
    bar = load_records([valid_record()], open_time_config()).bars[0]

    restored = CanonicalBar.from_dict(bar.to_dict())

    assert restored.available_time == bar.available_time
    assert restored == bar


def test_report_only_mode_must_be_explicit() -> None:
    result = load_records(
        [valid_record(tick_volume="bad")],
        open_time_config(strict=False),
    )

    assert result.rejected_row_count == 1
    assert result.bars == ()
    assert result.quality_report.has_errors


def test_loader_surface_does_not_expose_resampling() -> None:
    assert not hasattr(msa.data, "resample")
