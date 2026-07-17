from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import random

import pytest

from msa.data import (
    CanonicalBar,
    DataLoadError,
    ResampleError,
    Timeframe,
    iter_resample_events,
    load_records,
    resample_as_of,
    resample_load_result,
)
from tests.audit.fixtures import (
    START,
    fixed_config,
    load_indices,
    records_for_indices,
    source_config,
)


RANDOM_SEED = 20260717


def delayed_h1_source() -> tuple[timedelta, ...]:
    delays = [timedelta(0) for _ in range(8)]
    delays[3] = timedelta(minutes=5)
    return tuple(delays)


def target_signature(bar: CanonicalBar) -> tuple[object, ...]:
    return (
        bar.timestamp,
        bar.end_time,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.volume_type,
        bar.available_time,
        bar.boundary_policy,
    )


def first_replay_events(load_result: object, config: object) -> tuple[CanonicalBar, ...]:
    batch_events = tuple(iter_resample_events(load_result, config))  # type: ignore[arg-type]
    processing_times = sorted({bar.available_time for bar in batch_events})
    seen: set[datetime] = set()
    replay_events: list[CanonicalBar] = []
    for processing_time in processing_times:
        snapshot = resample_as_of(
            load_result, config, processing_time  # type: ignore[arg-type]
        )
        for bar in snapshot.bars:
            if bar.timestamp not in seen:
                replay_events.append(bar)
                seen.add(bar.timestamp)
    return tuple(replay_events)


@pytest.mark.parametrize("elapsed_minutes", [15, 30, 45, 60])
def test_forming_h1_never_exposes_final_ohlc_or_close(
    elapsed_minutes: int,
) -> None:
    loaded = load_indices(range(8), delays=delayed_h1_source())

    snapshot = resample_as_of(
        loaded,
        fixed_config(Timeframe.H1),
        START + timedelta(minutes=elapsed_minutes),
    )

    assert snapshot.bars == ()
    assert snapshot.report.complete_bucket_count == 0


def test_target_first_appears_at_full_causal_formula() -> None:
    delays = [timedelta(0) for _ in range(4)]
    delays[0] = timedelta(minutes=90)
    lag = timedelta(seconds=17)
    loaded = load_indices(range(4), delays=tuple(delays))
    config = fixed_config(Timeframe.H1, publication_lag=lag)
    expected = max(
        START + timedelta(hours=1),
        max(bar.available_time for bar in loaded.bars),
    ) + lag

    before = resample_as_of(loaded, config, expected - timedelta(microseconds=1))
    at_time = resample_as_of(loaded, config, expected)

    assert before.bars == ()
    assert at_time.bars[0].available_time == expected


@pytest.mark.parametrize("delayed_index", range(4))
def test_delaying_any_member_moves_target_availability(
    delayed_index: int,
) -> None:
    delays = [timedelta(0) for _ in range(4)]
    delays[delayed_index] = timedelta(minutes=80)
    loaded = load_indices(range(4), delays=tuple(delays))

    target = resample_load_result(
        loaded, fixed_config(Timeframe.H1)
    ).bars[0]

    assert target.available_time == max(
        target.end_time,
        max(bar.available_time for bar in loaded.bars),
    )


def test_earliest_member_arriving_last_controls_target() -> None:
    delays = [timedelta(0) for _ in range(4)]
    delays[0] = timedelta(hours=3)
    loaded = load_indices(range(4), delays=tuple(delays))
    target = resample_load_result(
        loaded, fixed_config(Timeframe.H1)
    ).bars[0]

    assert loaded.bars[0].available_time > loaded.bars[-1].available_time
    assert target.available_time == loaded.bars[0].available_time


def test_event_order_is_available_time_not_timestamp() -> None:
    delays = [timedelta(0) for _ in range(8)]
    delays[0] = timedelta(hours=4)
    loaded = load_indices(range(8), delays=tuple(delays))

    events = tuple(iter_resample_events(loaded, fixed_config(Timeframe.H1)))

    assert events[0].timestamp == START + timedelta(hours=1)
    assert events[1].timestamp == START
    assert [bar.available_time for bar in events] == sorted(
        bar.available_time for bar in events
    )


@pytest.mark.parametrize(
    ("target", "seed_offset"),
    [
        (Timeframe.M30, 0),
        (Timeframe.H1, 1),
        (Timeframe.H2, 2),
    ],
)
def test_seeded_random_batch_replay_and_first_event_equivalence(
    target: Timeframe, seed_offset: int
) -> None:
    rng = random.Random(RANDOM_SEED + seed_offset)
    delays = tuple(
        timedelta(minutes=rng.randint(0, 180)) for _ in range(32)
    )
    loaded = load_indices(range(32), delays=delays)
    config = fixed_config(target)
    batch = resample_load_result(loaded, config)
    batch_events = tuple(iter_resample_events(loaded, config))
    replay_events = first_replay_events(loaded, config)
    final_time = max(bar.available_time for bar in batch_events)
    final_replay = resample_as_of(loaded, config, final_time)

    assert final_replay.bars == batch.bars
    assert [target_signature(bar) for bar in replay_events] == [
        target_signature(bar) for bar in batch_events
    ]
    assert all(isinstance(bar.open, Decimal) for bar in batch.bars)


def test_nonmonotonic_source_availability_replays_deterministically() -> None:
    rng = random.Random(RANDOM_SEED)
    delays = [timedelta(minutes=rng.randint(0, 90)) for _ in range(16)]
    delays[0] = timedelta(hours=5)
    loaded = load_indices(range(16), delays=tuple(delays))
    config = fixed_config(Timeframe.H1)
    processing_time = START + timedelta(hours=6)

    first = resample_as_of(loaded, config, processing_time)
    second = resample_as_of(loaded, config, processing_time)

    assert first == second
    assert any(
        earlier.available_time > later.available_time
        for earlier, later in zip(loaded.bars, loaded.bars[1:])
    )


def test_append_future_bars_does_not_change_existing_targets() -> None:
    delays = tuple(timedelta(minutes=(index * 17) % 53) for index in range(16))
    prefix = load_indices(range(8), delays=delays)
    extended = load_indices(range(16), delays=delays)
    config = fixed_config(Timeframe.H1)

    prefix_targets = resample_load_result(prefix, config).bars
    extended_targets = resample_load_result(extended, config).bars

    assert prefix_targets == extended_targets[: len(prefix_targets)]


def test_future_bucket_price_mutation_cannot_rewrite_history() -> None:
    original = load_indices(range(8))
    changed = load_indices(
        range(8),
        price_offsets={index: Decimal("500") for index in range(4, 8)},
    )
    config = fixed_config(Timeframe.H1)
    original_targets = resample_load_result(original, config).bars
    changed_targets = resample_load_result(changed, config).bars

    assert original_targets[0] == changed_targets[0]
    assert original_targets[1] != changed_targets[1]


def test_emitted_history_is_frozen_when_later_bucket_arrives() -> None:
    first_bucket = load_indices(range(4))
    full_history = load_indices(range(8))
    config = fixed_config(Timeframe.H1)
    emitted = resample_as_of(
        first_bucket, config, START + timedelta(hours=1)
    ).bars[0]
    later = resample_as_of(
        full_history, config, START + timedelta(hours=2)
    ).bars[0]

    assert emitted == later


def test_target_availability_never_uses_next_bucket_or_file_tail() -> None:
    loaded = load_indices(range(12))
    targets = resample_load_result(
        loaded, fixed_config(Timeframe.H1)
    ).bars

    assert targets[0].available_time == START + timedelta(hours=1)
    assert targets[0].available_time != targets[-1].end_time
    assert targets[0].available_time < targets[1].timestamp + timedelta(hours=1)


def test_publication_lag_only_shifts_availability_not_ohlcv() -> None:
    delays = [timedelta(0) for _ in range(8)]
    delays[1] = timedelta(minutes=23)
    loaded = load_indices(range(8), delays=tuple(delays))
    ordinary = resample_load_result(
        loaded, fixed_config(Timeframe.H1)
    ).bars
    lag = timedelta(minutes=7)
    shifted = resample_load_result(
        loaded,
        fixed_config(Timeframe.H1, publication_lag=lag),
    ).bars

    for before, after in zip(ordinary, shifted):
        assert (
            before.timestamp,
            before.end_time,
            before.open,
            before.high,
            before.low,
            before.close,
            before.volume,
        ) == (
            after.timestamp,
            after.end_time,
            after.open,
            after.high,
            after.low,
            after.close,
            after.volume,
        )
        assert after.available_time == before.available_time + lag


def test_explicit_anchor_shift_changes_only_declared_buckets() -> None:
    loaded = load_indices(range(12))
    ordinary = resample_load_result(
        loaded, fixed_config(Timeframe.H1)
    )
    shifted = resample_load_result(
        loaded,
        fixed_config(
            Timeframe.H1,
            anchor=START + timedelta(minutes=30),
            strict=False,
        ),
    )

    assert [bar.timestamp for bar in ordinary.bars] == [
        START,
        START + timedelta(hours=1),
        START + timedelta(hours=2),
    ]
    assert [bar.timestamp for bar in shifted.bars] == [
        START + timedelta(minutes=30),
        START + timedelta(hours=1, minutes=30),
    ]
    assert all(
        bar.boundary_policy == shifted.config.policy_id for bar in shifted.bars
    )


def test_replay_does_not_mutate_records_or_canonical_input() -> None:
    records = records_for_indices(range(8))
    records_before = deepcopy(records)
    loaded = load_records(records, source_config())
    bars_before = tuple(bar.to_dict() for bar in loaded.bars)

    resample_as_of(
        loaded,
        fixed_config(Timeframe.H1),
        START + timedelta(hours=2),
    )

    assert records == records_before
    assert tuple(bar.to_dict() for bar in loaded.bars) == bars_before


def test_as_of_prevalidates_future_identity_and_fails_closed() -> None:
    prefix = load_indices(range(4))
    extended = load_indices(range(8))
    future_bars = list(extended.bars)
    future_bars[-1] = replace(future_bars[-1], source="future-other-feed")
    invalid_future = replace(extended, bars=tuple(future_bars))
    processing_time = START + timedelta(hours=1)

    assert len(
        resample_as_of(
            prefix, fixed_config(Timeframe.H1), processing_time
        ).bars
    ) == 1
    with pytest.raises(ResampleError, match="source identity field source differs"):
        resample_as_of(
            invalid_future, fixed_config(Timeframe.H1), processing_time
        )


def test_as_of_prevalidates_future_quality_and_fails_closed() -> None:
    prefix_records = records_for_indices(range(4))
    future_records = records_for_indices(range(4, 8))
    future_records.append(dict(future_records[-1]))
    report_only = load_records(
        prefix_records + future_records,
        source_config(strict=False),
    )
    processing_time = START + timedelta(hours=1)

    assert report_only.quality_report.has_errors
    with pytest.raises(ResampleError, match="quality_report"):
        resample_as_of(
            report_only, fixed_config(Timeframe.H1), processing_time
        )


def test_permanent_gap_never_synthesizes_target_during_replay() -> None:
    loaded = load_indices((0, 1, 3, 4, 5, 6, 7))
    config = fixed_config(Timeframe.H1)

    with pytest.raises(ResampleError):
        resample_load_result(loaded, config)
    replay = resample_as_of(
        loaded, config, START + timedelta(days=1)
    )

    assert [bar.timestamp for bar in replay.bars] == [START + timedelta(hours=1)]
    assert replay.report.warnings
    assert all(bar.timestamp != START for bar in replay.bars)
