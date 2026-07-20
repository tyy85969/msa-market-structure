from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from msa.data import Timeframe
from msa.research.swing import (
    AtrReversalDetectorConfig,
    AtrStructureBreakDetectorConfig,
    StructureBreakDetectorConfig,
    SwingConfigurationError,
    SwingDetectionEvent,
    SwingDetectionResult,
    SwingInputError,
)
from tests.research.swing.c003b_fixtures import (
    atr_combination_bars,
    atr_config,
    atr_detector,
    atr_turn_bars,
    combined_config,
    combined_detector,
    ohlc_bar,
    pivot_upper_break_bars,
    structure_config,
    structure_detector,
)
from tests.research.swing.fixtures import START, load_result


@pytest.mark.parametrize(
    ("config", "config_type"),
    [
        (atr_config(), AtrReversalDetectorConfig),
        (structure_config(), StructureBreakDetectorConfig),
        (combined_config(), AtrStructureBreakDetectorConfig),
    ],
)
def test_config_round_trip_is_exact(config, config_type) -> None:
    assert config_type.from_dict(config.to_dict()) == config
    assert config_type.from_dict(config.to_dict()).to_dict() == config.to_dict()


@pytest.mark.parametrize(
    ("config", "config_type"),
    [
        (atr_config(), AtrReversalDetectorConfig),
        (structure_config(), StructureBreakDetectorConfig),
        (combined_config(), AtrStructureBreakDetectorConfig),
    ],
)
def test_unknown_config_field_fails(config, config_type) -> None:
    payload = config.to_dict()
    payload["automatic_parameter"] = True
    with pytest.raises(SwingConfigurationError, match="unknown fields"):
        config_type.from_dict(payload)


@pytest.mark.parametrize(
    ("config", "config_type"),
    [
        (atr_config(), AtrReversalDetectorConfig),
        (structure_config(), StructureBreakDetectorConfig),
        (combined_config(), AtrStructureBreakDetectorConfig),
    ],
)
def test_unknown_schema_fails(config, config_type) -> None:
    payload = config.to_dict()
    payload["schema_version"] = 2
    with pytest.raises(SwingConfigurationError, match="schema_version"):
        config_type.from_dict(payload)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: atr_config(strict=False),
        lambda: structure_config(strict=False),
        lambda: combined_config(strict=False),
    ],
)
def test_strict_false_fails(factory) -> None:
    with pytest.raises(SwingConfigurationError, match="strict must be True"):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: atr_config(reversal_multiplier=1.0),
        lambda: structure_config(break_buffer=0.0),
        lambda: combined_config(break_buffer=0.0),
    ],
)
def test_float_configuration_fails(factory) -> None:
    with pytest.raises(SwingConfigurationError, match="Decimal"):
        factory()


def test_non_finite_and_invalid_decimal_configuration_fails() -> None:
    for value in (Decimal("NaN"), Decimal("Infinity"), Decimal("0")):
        with pytest.raises(SwingConfigurationError):
            atr_config(reversal_multiplier=value)
    with pytest.raises(SwingConfigurationError):
        structure_config(break_buffer=Decimal("NaN"))
    with pytest.raises(SwingConfigurationError):
        combined_config(break_buffer=Decimal("-1"))


@pytest.mark.parametrize(
    ("detector", "bars"),
    [
        (atr_detector(), atr_turn_bars()),
        (structure_detector(), pivot_upper_break_bars()),
        (combined_detector(), atr_combination_bars()),
    ],
)
def test_result_report_and_event_round_trip(detector, bars) -> None:
    result = detector.detect_batch(load_result(bars))
    restored = SwingDetectionResult.from_dict(result.to_dict())
    assert restored == result
    for event in detector.iter_events(load_result(bars)):
        assert SwingDetectionEvent.from_dict(event.to_dict()) == event


@pytest.mark.parametrize(
    "detector",
    [atr_detector(), structure_detector(), combined_detector()],
)
def test_mixed_symbol_is_rejected(detector) -> None:
    bars = list(atr_combination_bars())
    bars[2] = replace(bars[2], symbol="EURUSD")
    with pytest.raises(SwingInputError, match="mixed symbol"):
        detector.detect_batch(load_result(tuple(bars)))


@pytest.mark.parametrize(
    "detector",
    [atr_detector(), structure_detector(), combined_detector()],
)
def test_mixed_timeframe_is_rejected(detector) -> None:
    bars = list(atr_combination_bars())
    bars[2] = ohlc_bar(
        2,
        open="11",
        high="12",
        low="9",
        close="11",
        timeframe=Timeframe.H2,
    )
    with pytest.raises(SwingInputError, match="mixed timeframe"):
        detector.detect_batch(load_result(tuple(bars)))


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate", "quality_report"),
        ("overlap", "quality_report"),
        ("out_of_order", "quality_report"),
    ],
)
def test_invalid_sequence_quality_is_rejected(case: str, message: str) -> None:
    first = ohlc_bar(0, open="10", high="11", low="9", close="10")
    if case == "duplicate":
        bars = (first, first)
    elif case == "overlap":
        bars = (
            first,
            ohlc_bar(
                1,
                open="10",
                high="11",
                low="9",
                close="10",
                timestamp=START + timedelta(minutes=30),
            ),
        )
    else:
        bars = (
            first,
            ohlc_bar(
                1,
                open="10",
                high="11",
                low="9",
                close="10",
                timestamp=START - timedelta(hours=1),
            ),
        )
    with pytest.raises(SwingInputError, match=message):
        atr_detector().detect_batch(load_result(bars))


def test_invalid_ohlc_is_rejected_if_object_was_unsafely_corrupted() -> None:
    bars = list(atr_turn_bars())
    object.__setattr__(bars[2], "high", Decimal("1"))
    with pytest.raises(SwingInputError, match="invalid OHLC"):
        atr_detector().detect_batch(load_result(tuple(bars)))


@pytest.mark.parametrize(
    "detector",
    [atr_detector(), structure_detector(), combined_detector()],
)
def test_naive_processing_time_is_rejected(detector) -> None:
    with pytest.raises(SwingInputError, match="timezone-aware"):
        detector.detect_as_of(
            load_result(atr_combination_bars()),
            datetime(2026, 7, 1, 5, 0),
        )


def test_input_order_and_objects_are_not_modified_or_sorted() -> None:
    bars = atr_turn_bars()
    before = tuple(bar.to_dict() for bar in bars)
    atr_detector().detect_batch(load_result(bars))
    assert tuple(bar.to_dict() for bar in bars) == before

    reversed_bars = tuple(reversed(bars))
    with pytest.raises(SwingInputError):
        atr_detector().detect_batch(load_result(reversed_bars))
    assert reversed_bars[0].timestamp > reversed_bars[-1].timestamp
