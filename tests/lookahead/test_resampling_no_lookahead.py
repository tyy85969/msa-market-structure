from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.data import (
    CanonicalBar,
    CompletedBarPolicy,
    CoveragePolicy,
    ExplicitFixedAnchorPolicy,
    LoadResult,
    ResampleConfig,
    SessionIdPolicy,
    SourceDataConfig,
    Timeframe,
    TimestampSemantics,
    VolumeType,
    iter_resample_events,
    resample_as_of,
    resample_load_result,
    validate_bar_sequence,
)


UTC = timezone.utc
START = datetime(2026, 1, 2, 8, 0, tzinfo=UTC)


def m15_bar(
    index: int,
    *,
    available_time: datetime | None = None,
    price_offset: Decimal = Decimal(0),
) -> CanonicalBar:
    timestamp = START + index * timedelta(minutes=15)
    end_time = timestamp + timedelta(minutes=15)
    opening = Decimal(2000 + index) + price_offset
    return CanonicalBar(
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=timestamp,
        end_time=end_time,
        open=opening,
        high=opening + Decimal(3),
        low=opening - Decimal(2),
        close=opening + Decimal(1),
        volume=Decimal(index + 1),
        volume_type=VolumeType.TICK,
        source="replay-feed",
        source_timezone="UTC",
        session_id="replay-session",
        boundary_policy=None,
        is_complete=True,
        available_time=available_time or end_time,
    )


def replay_load_result(bars: tuple[CanonicalBar, ...]) -> LoadResult:
    report = validate_bar_sequence(
        bars,
        source="replay-feed",
        timeframe=Timeframe.M15,
    )
    config = SourceDataConfig(
        source="replay-feed",
        source_timezone="UTC",
        source_symbol="GOLD",
        canonical_symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp_column="time",
        timestamp_semantics=TimestampSemantics.OPEN_TIME,
        timestamp_format="%Y-%m-%dT%H:%M:%S%z",
        open_column="open",
        high_column="high",
        low_column="low",
        close_column="close",
        volume_column="volume",
        volume_type=VolumeType.TICK,
        completed_bar_policy=CompletedBarPolicy.ALL_ROWS_ARE_CLOSED,
        availability_lag=timedelta(0),
        session_id="replay-session",
        boundary_policy=None,
        end_time_column=None,
    )
    return LoadResult(
        bars=bars,
        quality_report=report,
        source_config=config,
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )


def h1_config(*, publication_lag: timedelta = timedelta(0)) -> ResampleConfig:
    policy = ExplicitFixedAnchorPolicy(
        policy_id="replay-h1-anchor-v1",
        anchor=START,
        target_timeframe=Timeframe.H1,
    )
    return ResampleConfig(
        source_timeframe=Timeframe.M15,
        target_timeframe=Timeframe.H1,
        alignment_policy=policy,
        coverage_policy=CoveragePolicy.CONTIGUOUS_FIXED,
        publication_lag=publication_lag,
        policy_id=policy.policy_id,
        session_id_policy=SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE,
    )


def delayed_first_bucket() -> tuple[CanonicalBar, ...]:
    bars = [m15_bar(index) for index in range(8)]
    bars[3] = m15_bar(
        3, available_time=START + timedelta(hours=1, minutes=5)
    )
    return tuple(bars)


@pytest.mark.parametrize(
    "processing_time",
    [
        START + timedelta(minutes=15),
        START + timedelta(minutes=30),
        START + timedelta(minutes=45),
    ],
)
def test_forming_h1_final_ohlc_is_not_visible_inside_bucket(
    processing_time: datetime,
) -> None:
    result = resample_as_of(
        replay_load_result(delayed_first_bucket()),
        h1_config(),
        processing_time,
    )

    assert result.bars == ()


def test_h1_end_time_does_not_confirm_when_last_member_is_unavailable() -> None:
    result = resample_as_of(
        replay_load_result(delayed_first_bucket()),
        h1_config(),
        START + timedelta(hours=1),
    )

    assert result.bars == ()


def test_h1_first_appears_at_maximum_member_available_time() -> None:
    first_available = START + timedelta(hours=1, minutes=5)
    load_result = replay_load_result(delayed_first_bucket())

    before = resample_as_of(
        load_result, h1_config(), first_available - timedelta(microseconds=1)
    )
    at_time = resample_as_of(load_result, h1_config(), first_available)

    assert before.bars == ()
    assert len(at_time.bars) == 1
    assert at_time.bars[0].available_time == first_available


def test_batch_and_replay_final_h1_ohlc_are_equal() -> None:
    load_result = replay_load_result(delayed_first_bucket())
    config = h1_config()

    batch = resample_load_result(load_result, config)
    replay = resample_as_of(
        load_result, config, START + timedelta(hours=2)
    )

    assert replay.bars == batch.bars


def test_batch_and_replay_first_availability_events_are_equal() -> None:
    bars = list(delayed_first_bucket())
    bars[0] = replace(
        bars[0], available_time=START + timedelta(hours=2, minutes=10)
    )
    load_result = replay_load_result(tuple(bars))
    config = h1_config()
    batch_events = tuple(iter_resample_events(load_result, config))
    processing_times = sorted({bar.available_time for bar in batch_events})
    replay_events: list[CanonicalBar] = []
    seen: set[datetime] = set()

    for processing_time in processing_times:
        snapshot = resample_as_of(load_result, config, processing_time)
        for bar in snapshot.bars:
            if bar.timestamp not in seen:
                replay_events.append(bar)
                seen.add(bar.timestamp)

    assert [
        (bar.timestamp, bar.available_time) for bar in replay_events
    ] == [
        (bar.timestamp, bar.available_time) for bar in batch_events
    ]
    assert batch_events[0].timestamp == START + timedelta(hours=1)
    assert batch_events[1].timestamp == START


def test_future_bucket_changes_do_not_rewrite_emitted_historical_h1() -> None:
    original = delayed_first_bucket()
    changed = list(original)
    for index in range(4, 8):
        changed[index] = m15_bar(index, price_offset=Decimal(100))

    original_batch = resample_load_result(
        replay_load_result(original), h1_config()
    )
    changed_batch = resample_load_result(
        replay_load_result(tuple(changed)), h1_config()
    )

    assert original_batch.bars[0] == changed_batch.bars[0]
    assert original_batch.bars[1] != changed_batch.bars[1]


def test_delaying_last_m15_delays_h1_by_same_causal_rule() -> None:
    ordinary = tuple(m15_bar(index) for index in range(4))
    delayed = list(ordinary)
    delayed[3] = m15_bar(
        3, available_time=START + timedelta(hours=1, minutes=12)
    )

    ordinary_h1 = resample_load_result(
        replay_load_result(ordinary), h1_config()
    ).bars[0]
    delayed_h1 = resample_load_result(
        replay_load_result(tuple(delayed)), h1_config()
    ).bars[0]

    assert ordinary_h1.available_time == START + timedelta(hours=1)
    assert delayed_h1.available_time == START + timedelta(hours=1, minutes=12)


def test_repeated_as_of_at_same_time_is_deterministic() -> None:
    load_result = replay_load_result(delayed_first_bucket())
    config = h1_config()
    processing_time = START + timedelta(hours=1, minutes=5)

    first = resample_as_of(load_result, config, processing_time)
    second = resample_as_of(load_result, config, processing_time)

    assert first == second


def test_publication_lag_delays_target_after_all_members_are_available() -> None:
    load_result = replay_load_result(tuple(m15_bar(index) for index in range(4)))
    config = h1_config(publication_lag=timedelta(minutes=3))

    at_end = resample_as_of(
        load_result, config, START + timedelta(hours=1)
    )
    at_publication = resample_as_of(
        load_result, config, START + timedelta(hours=1, minutes=3)
    )

    assert at_end.bars == ()
    assert at_publication.bars[0].available_time == START + timedelta(
        hours=1, minutes=3
    )
