from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from msa.data import (
    CanonicalBar,
    CompletedBarPolicy,
    DataLoadError,
    IssueSeverity,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    load_csv,
    load_records,
    validate_bar_sequence,
)


UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures"


def config() -> SourceDataConfig:
    return SourceDataConfig(
        source="quality-test",
        source_timezone="UTC",
        source_symbol="GOLD",
        canonical_symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp_column="time",
        timestamp_semantics=TimestampSemantics.OPEN_TIME,
        timestamp_format="%Y-%m-%d %H:%M:%S",
        open_column="open",
        high_column="high",
        low_column="low",
        close_column="close",
        volume_column=None,
        volume_type=VolumeType.UNAVAILABLE,
        completed_bar_policy=CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        availability_lag=timedelta(0),
        session_id=None,
        boundary_policy=None,
        end_time_column=None,
        symbol_column="symbol",
    )


def record(timestamp: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "time": timestamp,
        "symbol": "GOLD",
        "open": "2000",
        "high": "2002",
        "low": "1998",
        "close": "2001",
    }
    values.update(overrides)
    return values


def bar_at(minute: int, **overrides: object) -> CanonicalBar:
    timestamp = datetime(2026, 1, 2, 8, minute, tzinfo=UTC)
    values: dict[str, object] = {
        "symbol": "XAUUSD",
        "timeframe": Timeframe.M15,
        "timestamp": timestamp,
        "end_time": timestamp + timedelta(minutes=15),
        "open": Decimal("2000"),
        "high": Decimal("2002"),
        "low": Decimal("1998"),
        "close": Decimal("2001"),
        "volume": None,
        "volume_type": VolumeType.UNAVAILABLE,
        "source": "quality-test",
        "source_timezone": "UTC",
        "is_complete": True,
        "available_time": timestamp + timedelta(minutes=15),
    }
    values.update(overrides)
    return CanonicalBar(**values)


def test_continuous_fixed_duration_data_has_no_gap() -> None:
    report = validate_bar_sequence(
        [bar_at(0), bar_at(15)],
        source="quality-test",
        timeframe=Timeframe.M15,
    )

    assert report.gap_count == 0
    assert report.overlap_count == 0
    assert report.warnings == ()
    assert not report.has_errors


def test_interval_gap_is_reported_but_not_filled() -> None:
    source_config = config()
    result = load_records(
        [record("2026-01-02 08:00:00"), record("2026-01-02 08:30:00")],
        source_config,
    )

    assert result.quality_report.gap_count == 1
    assert result.quality_report.overlap_count == 0
    assert len(result.bars) == 2
    warning = result.quality_report.warnings[0]
    assert warning.code == "interval_gap"
    assert warning.severity is IssueSeverity.WARNING
    assert "session close, weekend, or holiday" in warning.reason


def test_csv_gap_fixture_is_accepted_without_repair() -> None:
    source_config = replace(
        config(),
        source_timezone="America/New_York",
        volume_column="tick_volume",
        volume_type=VolumeType.TICK,
    )

    result = load_csv(FIXTURES / "interval_gap.csv", source_config)

    assert result.quality_report.gap_count == 1
    assert result.accepted_row_count == 2


def test_identical_duplicate_is_rejected_in_strict_mode() -> None:
    first = record("2026-01-02 08:00:00")

    with pytest.raises(DataLoadError) as exc_info:
        load_records([first, dict(first)], config())

    report = exc_info.value.report
    assert report.duplicate_count == 1
    assert report.conflicting_duplicate_count == 0
    assert report.overlap_count == 0
    assert report.errors[0].code == "duplicate"
    assert report.errors[0].row_number == 2


def test_conflicting_duplicate_is_rejected_in_strict_mode() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records(
            [
                record("2026-01-02 08:00:00"),
                record(
                    "2026-01-02 08:00:00",
                    high="2003",
                    close="2002",
                ),
            ],
            config(),
        )

    report = exc_info.value.report
    assert report.duplicate_count == 1
    assert report.conflicting_duplicate_count == 1
    assert report.errors[0].code == "conflicting_duplicate"


def test_out_of_order_input_is_rejected_without_sorting() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records(
            [
                record("2026-01-02 08:15:00", close="2002"),
                record("2026-01-02 08:00:00", close="2001"),
            ],
            config(),
        )

    report = exc_info.value.report
    assert report.out_of_order_count == 1
    assert report.overlap_count == 0
    assert report.errors[0].row_number == 2
    assert report.earliest_timestamp == datetime(2026, 1, 2, 8, 0, tzinfo=UTC)
    assert report.latest_timestamp == datetime(2026, 1, 2, 8, 15, tzinfo=UTC)


def test_overlapping_fixed_intervals_are_reported_as_errors() -> None:
    report = validate_bar_sequence(
        [bar_at(0), bar_at(5)],
        source="quality-test",
        timeframe=Timeframe.M15,
    )

    assert report.overlap_count == 1
    assert report.gap_count == 0
    assert report.warnings == ()
    issue = report.errors[0]
    assert issue.code == "interval_overlap"
    assert issue.row_number == 2
    assert issue.raw_value == "2026-01-02T08:05:00+00:00"
    assert "previous.end_time 2026-01-02T08:15:00+00:00" in issue.reason


def test_strict_load_rejects_overlapping_fixed_intervals() -> None:
    with pytest.raises(DataLoadError) as exc_info:
        load_records(
            [
                record("2026-01-02 08:00:00"),
                record("2026-01-02 08:05:00", close="2002"),
            ],
            config(),
        )

    assert exc_info.value.report.overlap_count == 1
    assert exc_info.value.report.errors[0].code == "interval_overlap"


def test_quality_report_is_immutable() -> None:
    report = validate_bar_sequence(
        [bar_at(0)], source="quality-test", timeframe=Timeframe.M15
    )

    with pytest.raises(FrozenInstanceError):
        report.gap_count = 10  # type: ignore[misc]


def test_report_records_required_identity_and_counts() -> None:
    report = validate_bar_sequence(
        [bar_at(0), bar_at(15)],
        source="quality-test",
        timeframe=Timeframe.M15,
        assumptions=("explicit test assumption",),
    )

    assert report.total_rows == 2
    assert report.accepted_rows == 2
    assert report.rejected_rows == 0
    assert report.timeframe is Timeframe.M15
    assert report.source == "quality-test"
    assert report.earliest_timestamp == bar_at(0).timestamp
    assert report.latest_timestamp == bar_at(15).timestamp
    assert report.assumptions == ("explicit test assumption",)


def test_quality_validation_preserves_available_time() -> None:
    bars = (bar_at(0), bar_at(15))

    validate_bar_sequence(
        bars, source="quality-test", timeframe=Timeframe.M15
    )

    assert bars[0].available_time == datetime(2026, 1, 2, 8, 15, tzinfo=UTC)
    assert bars[1].available_time == datetime(2026, 1, 2, 8, 30, tzinfo=UTC)
