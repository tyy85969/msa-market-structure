from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, getcontext
import random

import pytest

from msa.research.lifecycle import LifecycleEventType
from msa.research.msa_core.contracts import validate_source_input
from msa.validation import StructuralMetricEvaluator, SyntheticScenarioKind
from msa.validation.experiments import (
    build_c008c_synthetic_dataset,
    build_synthetic_source_input,
    c008c_synthetic_dataset_capacity_policy,
)
from msa.reference import core_alpha_v1_config


def test_synthetic_generation_is_repeatable_and_formal() -> None:
    for kind in SyntheticScenarioKind:
        for seed in (0, 1, 2, 3):
            first = build_synthetic_source_input(kind, seed)
            random.seed(999999)
            second = build_synthetic_source_input(kind, seed)
            assert first.to_dict() == second.to_dict()
            assert validate_source_input(
                first, core_alpha_v1_config()
            ) == first
            assert all(
                bar.is_complete
                for bar in first.reference_price_data.bars
            )


def test_source_input_is_never_reused_across_partitions() -> None:
    cases = build_c008c_synthetic_dataset().cases
    by_digest = {
        item.source_input_payload_digest: item.partition for item in cases
    }
    assert len(by_digest) == len(cases)


def test_every_case_satisfies_frozen_time_capacity() -> None:
    manifest = build_c008c_synthetic_dataset()
    assert (
        manifest.capacity_policy
        == c008c_synthetic_dataset_capacity_policy()
    )
    for case in manifest.cases:
        bars = case.source_input.reference_price_data.bars
        confirm_time = min(
            item.event_confirm_time
            for item in case.source_input.lifecycle_history.events
            if item.event_type is LifecycleEventType.ACTIVATED
        )
        assert len(bars) == 96
        assert sum(item.available_time <= confirm_time for item in bars) == 32
        assert sum(item.available_time > confirm_time for item in bars) == 64
        assert all(item.is_complete for item in bars)
        assert all(
            current.timestamp > previous.timestamp
            and current.available_time >= current.end_time
            for previous, current in zip(bars, bars[1:])
        )


def test_decimal_context_does_not_change_dataset_payload() -> None:
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        expected = build_c008c_synthetic_dataset().to_dict()
        getcontext().prec = 6
        getcontext().rounding = ROUND_DOWN
        assert build_c008c_synthetic_dataset().to_dict() == expected
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding


def test_future_append_does_not_rewrite_existing_bar_prefix() -> None:
    source = build_synthetic_source_input(
        SyntheticScenarioKind.SINGLE_TREND, 0
    )
    bars = source.reference_price_data.bars
    prefix = tuple(item.to_dict() for item in bars)
    last = bars[-1]
    future = replace(
        last,
        timestamp=last.timestamp + timedelta(hours=1),
        end_time=last.end_time + timedelta(hours=1),
        available_time=last.available_time + timedelta(hours=1),
        open=last.close,
        high=last.close + Decimal("0.75"),
        low=last.close - Decimal("0.75"),
    )
    extended = (*bars, future)
    assert tuple(item.to_dict() for item in extended[:-1]) == prefix


def test_false_break_crosses_public_threshold_then_returns() -> None:
    source = build_synthetic_source_input(
        SyntheticScenarioKind.FALSE_BREAK, 0
    )
    upper = next(
        item.subject_ref
        for item in source.lifecycle_history.final_snapshot.states
        if item.subject_ref.object_id.endswith("upper-primary")
    )
    threshold = upper.price_range.high + Decimal("1")
    return_threshold = upper.price_range.low - Decimal("1")
    bars = source.reference_price_data.bars
    break_index = next(
        index for index, item in enumerate(bars) if item.close >= threshold
    )
    assert any(
        item.close <= return_threshold for item in bars[break_index + 1 :]
    )
    assert any(
        item.event_type is LifecycleEventType.BROKEN
        and item.subject_id == upper.object_id
        for item in source.lifecycle_history.events
    )


def test_gap_shock_contains_explicit_nonzero_jump() -> None:
    bars = build_synthetic_source_input(
        SyntheticScenarioKind.GAP_SHOCK, 0
    ).reference_price_data.bars
    assert any(
        abs(current.open - previous.close) >= Decimal("10")
        for previous, current in zip(bars, bars[1:])
    )


def test_trend_range_and_v_reversal_retain_declared_semantics() -> None:
    trend = build_synthetic_source_input(
        SyntheticScenarioKind.SINGLE_TREND, 0
    ).reference_price_data.bars
    assert all(
        current.close > previous.close
        for previous, current in zip(trend, trend[1:])
    )

    ranged = build_synthetic_source_input(
        SyntheticScenarioKind.RANGE, 0
    ).reference_price_data.bars
    range_closes = tuple(item.close for item in ranged)
    assert max(range_closes) - min(range_closes) == Decimal("4")
    directions = tuple(
        current.close.compare(previous.close)
        for previous, current in zip(ranged, ranged[1:])
    )
    assert Decimal("-1") in directions and Decimal("1") in directions

    reversal = build_synthetic_source_input(
        SyntheticScenarioKind.V_REVERSAL, 0
    ).reference_price_data.bars
    closes = tuple(item.close for item in reversal)
    turning_index = closes.index(min(closes))
    assert 0 < turning_index < len(closes) - 1
    assert all(
        current < previous
        for previous, current in zip(
            closes[: turning_index + 1], closes[1 : turning_index + 1]
        )
    )
    assert all(
        current > previous
        for previous, current in zip(
            closes[turning_index:], closes[turning_index + 1 :]
        )
    )


def test_dataset_capacity_build_never_calls_metric_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("metric outcome evaluator was called")

    monkeypatch.setattr(StructuralMetricEvaluator, "evaluate", forbidden)
    build_c008c_synthetic_dataset()
