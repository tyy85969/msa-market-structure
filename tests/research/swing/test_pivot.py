from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest

from msa.data import Timeframe
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LifecycleState,
    MarketRole,
    PriceRange,
    ScaleDescriptor,
    StructureSourceType,
)
from msa.research.swing import (
    PivotDetectorConfig,
    SwingConfigurationError,
    SwingDetectionEvent,
    SwingDetectionResult,
    SwingDetector,
    SwingInputError,
    canonical_bar_key,
)
from msa.research.swing.pivot import STRUCTURE_FAMILY
from tests.research.swing.fixtures import (
    SCALE,
    START,
    bar,
    bars_from_extrema,
    detector,
    dual_pivot_bars,
    high_pivot_bars,
    load_result,
    low_pivot_bars,
    pivot_config,
)


def only_candidate(bars: tuple[object, ...], **config: object):
    result = detector(**config).detect_batch(load_result(bars))  # type: ignore[arg-type]
    assert len(result.candidates) == 1
    return result.candidates[0]


def test_detects_clear_strict_high_pivot() -> None:
    candidate = only_candidate(high_pivot_bars())
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.price_range == PriceRange(
        Decimal("30.1250"), Decimal("30.1250")
    )


def test_detects_clear_strict_low_pivot() -> None:
    candidate = only_candidate(low_pivot_bars())
    assert candidate.boundary_side is BoundarySide.LOWER
    assert candidate.price_range == PriceRange(
        Decimal("5.2500"), Decimal("5.2500")
    )


def test_same_center_may_emit_distinct_high_and_low_candidates() -> None:
    result = detector().detect_batch(load_result(dual_pivot_bars()))
    assert len(result.candidates) == 2
    assert {item.boundary_side for item in result.candidates} == {
        BoundarySide.UPPER,
        BoundarySide.LOWER,
    }
    assert len({item.candidate_id for item in result.candidates}) == 2


def test_equal_high_is_not_selected_under_strict_policy() -> None:
    bars = bars_from_extrema(("20", "30", "30"), ("10", "11", "12"))
    assert detector().detect_batch(load_result(bars)).candidates == ()


def test_equal_low_is_not_selected_under_strict_policy() -> None:
    bars = bars_from_extrema(("20", "21", "22"), ("10", "5", "5"))
    assert detector().detect_batch(load_result(bars)).candidates == ()


def test_leading_window_never_emits_without_left_context() -> None:
    bars = bars_from_extrema(("40", "20"), ("1", "10"))
    result = detector().detect_batch(load_result(bars))
    assert result.candidates == ()
    assert result.report.leading_incomplete_count == 1


def test_trailing_window_never_emits_without_right_context() -> None:
    bars = bars_from_extrema(("20", "40"), ("10", "1"))
    result = detector().detect_batch(load_result(bars))
    assert result.candidates == ()
    assert result.report.trailing_incomplete_count == 1


def test_price_range_preserves_exact_decimal() -> None:
    candidate = only_candidate(high_pivot_bars())
    assert str(candidate.price_range.low) == "30.1250"
    assert candidate.price_range.low is candidate.price_range.high


def test_origin_time_is_center_timestamp() -> None:
    bars = high_pivot_bars()
    assert only_candidate(bars).origin_time == bars[2].timestamp


def test_confirm_time_is_maximum_complete_window_availability() -> None:
    delays = (
        timedelta(0),
        timedelta(hours=5),
        timedelta(0),
        timedelta(minutes=9),
        timedelta(0),
    )
    bars = bars_from_extrema(
        ("15", "17", "30", "18", "16"),
        ("10", "11", "12", "11", "10"),
        delays=delays,
    )
    candidate = only_candidate(bars)
    expected = max(bar.available_time for bar in bars[1:4])
    assert candidate.confirm_time == expected


def test_confirm_time_is_not_center_end_time() -> None:
    bars = list(high_pivot_bars())
    bars[3] = replace(
        bars[3], available_time=bars[3].end_time + timedelta(minutes=17)
    )
    candidate = only_candidate(tuple(bars))
    assert candidate.confirm_time == bars[3].available_time
    assert candidate.confirm_time != bars[2].end_time


def test_confirm_time_is_not_file_end_time() -> None:
    bars = high_pivot_bars()
    candidate = only_candidate(bars)
    assert candidate.confirm_time == bars[3].available_time
    assert candidate.confirm_time < bars[-1].end_time


def test_high_mapping_is_upper_resistance_swing() -> None:
    candidate = only_candidate(high_pivot_bars())
    assert candidate.source_type is StructureSourceType.SWING
    assert candidate.boundary_side is BoundarySide.UPPER
    assert candidate.market_role is MarketRole.RESISTANCE


def test_low_mapping_is_lower_support_swing() -> None:
    candidate = only_candidate(low_pivot_bars())
    assert candidate.source_type is StructureSourceType.SWING
    assert candidate.boundary_side is BoundarySide.LOWER
    assert candidate.market_role is MarketRole.SUPPORT


def test_candidate_uses_confirmed_status_only() -> None:
    candidate = only_candidate(high_pivot_bars())
    assert candidate.confirmation_status is ConfirmationStatus.CONFIRMED
    assert candidate.lifecycle_state is LifecycleState.CONFIRMED


def test_touch_and_break_fields_start_empty() -> None:
    candidate = only_candidate(high_pivot_bars())
    assert candidate.touch_count == 0
    assert candidate.last_touch_time is None
    assert candidate.last_touch_confirm_time is None
    assert candidate.break_time is None
    assert candidate.break_confirm_time is None


def test_structure_family_is_stable_and_explainable() -> None:
    first = only_candidate(high_pivot_bars())
    second = only_candidate(high_pivot_bars())
    assert first.structure_family == STRUCTURE_FAMILY
    assert second.structure_family == first.structure_family


def test_provenance_retains_detector_policy_timeframe_and_window() -> None:
    candidate = only_candidate(high_pivot_bars())
    provenance = candidate.provenance
    assert provenance.source_module == "msa.research.swing.pivot"
    assert provenance.source_version == "1.0.0"
    assert provenance.policy_id == "pivot-strict-v1"
    assert len(provenance.parent_object_ids) == 3
    assert any(note == "source_timeframe=H1" for note in provenance.notes)
    assert any(note == "tie_policy=STRICT" for note in provenance.notes)


def test_canonical_bar_key_is_stable_and_documents_identity_fields() -> None:
    source_bar = high_pivot_bars()[2]
    first = canonical_bar_key(source_bar)
    assert first == canonical_bar_key(source_bar)
    assert first.startswith("bar:v1:")
    assert '"source":"synthetic-feed"' in first
    assert '"symbol":"XAUUSD"' in first
    assert '"timeframe":"H1"' in first


def test_same_input_and_config_produce_same_candidate_id() -> None:
    assert only_candidate(high_pivot_bars()).candidate_id == only_candidate(
        high_pivot_bars()
    ).candidate_id


def test_changing_side_changes_candidate_id() -> None:
    candidates = detector().detect_batch(load_result(dual_pivot_bars())).candidates
    assert candidates[0].candidate_id != candidates[1].candidate_id


def test_changing_origin_changes_candidate_id() -> None:
    original = only_candidate(high_pivot_bars())
    shifted = only_candidate(
        bars_from_extrema(
            ("15", "17", "30.1250", "18", "16"),
            ("10", "11", "12", "11", "10"),
            start=START + timedelta(days=1),
        )
    )
    assert shifted.origin_time != original.origin_time
    assert shifted.candidate_id != original.candidate_id


def test_changing_exact_price_changes_candidate_id() -> None:
    original = only_candidate(high_pivot_bars())
    changed = only_candidate(
        bars_from_extrema(
            ("15", "17", "30.1251", "18", "16"),
            ("10", "11", "12", "11", "10"),
        )
    )
    assert changed.candidate_id != original.candidate_id


def test_changing_window_availability_changes_candidate_id_and_confirm_time() -> None:
    ordinary_bars = high_pivot_bars()
    delayed_bars = list(ordinary_bars)
    delayed_bars[3] = replace(
        delayed_bars[3],
        available_time=delayed_bars[3].end_time + timedelta(minutes=1),
    )
    ordinary = only_candidate(ordinary_bars)
    delayed = only_candidate(tuple(delayed_bars))
    assert delayed.confirm_time != ordinary.confirm_time
    assert delayed.candidate_id != ordinary.candidate_id


@pytest.mark.parametrize(
    "config_change",
    [
        {"left_bars": 2},
        {"right_bars": 2},
        {"policy_id": "pivot-strict-v2"},
        {"detector_version": "1.0.1"},
    ],
)
def test_changing_configuration_changes_candidate_id(
    config_change: dict[str, object],
) -> None:
    original = only_candidate(high_pivot_bars())
    changed = only_candidate(high_pivot_bars(), **config_change)
    assert changed.candidate_id != original.candidate_id


def test_id_implementation_does_not_use_random_uuid_or_builtin_hash() -> None:
    source = Path("src/python/msa/research/swing/pivot.py").read_text(
        encoding="utf-8"
    )
    assert "uuid4" not in source
    assert "datetime.now" not in source
    assert "hash(" not in source
    assert "sha256" in source


def test_input_objects_are_not_modified() -> None:
    bars = high_pivot_bars()
    before = tuple(item.to_dict() for item in bars)
    detector().detect_batch(load_result(bars))
    assert tuple(item.to_dict() for item in bars) == before


def test_gap_counts_actual_bar_sequence_without_filling() -> None:
    bars = (
        bar(0, high="20", low="10"),
        bar(1, high="40", low="11"),
        bar(
            3,
            high="21",
            low="12",
            timestamp=START + timedelta(hours=3),
        ),
    )
    result = detector().detect_batch(load_result(bars))
    assert len(result.candidates) == 1
    assert result.report.gap_count == 1
    assert result.report.input_bar_count == 3
    assert any("actual bars only" in warning for warning in result.report.warnings)


def test_report_records_counts_and_time_bounds() -> None:
    result = detector().detect_batch(load_result(dual_pivot_bars()))
    report = result.report
    assert report.input_bar_count == 3
    assert report.evaluated_center_count == 1
    assert report.confirmed_high_count == 1
    assert report.confirmed_low_count == 1
    assert report.rejected_window_count == 0
    assert report.earliest_origin_time == report.latest_origin_time
    assert report.earliest_confirm_time == report.latest_confirm_time
    assert report.errors == ()


def test_non_pivot_window_is_counted_as_rejected() -> None:
    bars = bars_from_extrema(("20", "21", "22"), ("10", "11", "12"))
    result = detector().detect_batch(load_result(bars))
    assert result.report.evaluated_center_count == 1
    assert result.report.rejected_window_count == 1


def test_mixed_symbol_is_rejected() -> None:
    bars = list(high_pivot_bars())
    bars[3] = replace(bars[3], symbol="EURUSD")
    with pytest.raises(SwingInputError, match="mixed symbol"):
        detector().detect_batch(load_result(tuple(bars)))


def test_mixed_timeframe_is_rejected() -> None:
    bars = list(high_pivot_bars())
    bars[3] = replace(
        bars[3],
        timeframe=Timeframe.H2,
        end_time=bars[3].timestamp + timedelta(hours=2),
        available_time=bars[3].timestamp + timedelta(hours=2),
    )
    with pytest.raises(SwingInputError, match="mixed timeframe"):
        detector().detect_batch(load_result(tuple(bars)))


def test_mixed_source_is_rejected() -> None:
    bars = list(high_pivot_bars())
    bars[3] = replace(bars[3], source="other-feed")
    with pytest.raises(SwingInputError, match="mixed source"):
        detector().detect_batch(load_result(tuple(bars)))


def test_incomplete_bar_is_rejected() -> None:
    bars = list(high_pivot_bars())
    bars[3] = replace(bars[3], is_complete=False)
    with pytest.raises(SwingInputError, match="incomplete source bar"):
        detector().detect_batch(load_result(tuple(bars)))


@pytest.mark.parametrize("case", ["duplicate", "overlap", "out_of_order"])
def test_c001_quality_errors_are_rejected(case: str) -> None:
    first = bar(0)
    if case == "duplicate":
        bars = (first, first)
    elif case == "overlap":
        bars = (
            first,
            bar(1, timestamp=START + timedelta(minutes=30)),
        )
    else:
        bars = (
            first,
            bar(1, timestamp=START - timedelta(hours=2)),
        )
    with pytest.raises(SwingInputError, match="quality_report"):
        detector().detect_batch(load_result(bars))


def test_invalid_ohlc_is_rejected_even_if_object_was_unsafely_corrupted() -> None:
    bars = list(high_pivot_bars())
    object.__setattr__(bars[2], "high", Decimal("1"))
    with pytest.raises(SwingInputError, match="invalid OHLC"):
        detector().detect_batch(load_result(tuple(bars)))


def test_production_source_has_no_deferred_detectors_or_signal_code() -> None:
    source_root = Path("src/python/msa/research/swing")
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in source_root.glob("*.py")
    ).lower()
    for forbidden in ("atr reversal", "zigzag", "structure-break", "buy signal"):
        assert forbidden not in production


def test_valid_config_round_trip() -> None:
    config = pivot_config(left_bars=2, right_bars=3)
    assert config.strict is True
    assert config.to_dict()["strict"] is True
    assert PivotDetectorConfig.from_dict(config.to_dict()) == config
    assert config.to_dict()["schema_version"] == 1


def test_strict_false_is_rejected() -> None:
    with pytest.raises(
        SwingConfigurationError,
        match="PivotDetectorConfig.strict must be True",
    ):
        pivot_config(strict=False)


def test_serialized_strict_false_is_rejected() -> None:
    payload = pivot_config().to_dict()
    payload["strict"] = False
    with pytest.raises(
        SwingConfigurationError,
        match="C-003A supports strict mode only",
    ):
        PivotDetectorConfig.from_dict(payload)


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_non_bool_strict_is_rejected(value: object) -> None:
    with pytest.raises(SwingConfigurationError, match="strict must be a bool"):
        pivot_config(strict=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["left_bars", "right_bars"])
def test_zero_window_parameter_is_rejected(field_name: str) -> None:
    with pytest.raises(SwingConfigurationError, match=field_name):
        pivot_config(**{field_name: 0})


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_non_positive_or_non_integer_left_parameter_is_rejected(
    value: object,
) -> None:
    with pytest.raises(SwingConfigurationError, match="left_bars"):
        pivot_config(left_bars=value)  # type: ignore[arg-type]


def test_unknown_tie_policy_is_rejected() -> None:
    payload = pivot_config().to_dict()
    payload["tie_policy"] = "PICK_FIRST"
    with pytest.raises(SwingConfigurationError, match="unknown tie_policy"):
        PivotDetectorConfig.from_dict(payload)


def test_tie_policy_must_be_explicit_enum() -> None:
    with pytest.raises(SwingConfigurationError, match="tie_policy"):
        PivotDetectorConfig(
            "pivot",
            "1",
            1,
            1,
            "STRICT",  # type: ignore[arg-type]
            SCALE,
            "policy",
        )


def test_scale_is_caller_supplied_and_not_inferred_from_timeframe() -> None:
    explicit = ScaleDescriptor("caller-defined-scale", None)
    config = pivot_config(scale=explicit)
    assert config.scale is explicit
    assert Timeframe.H1.value not in config.scale.scale_id


def test_missing_scale_is_rejected_during_deserialization() -> None:
    payload = pivot_config().to_dict()
    del payload["scale"]
    with pytest.raises(SwingConfigurationError, match="missing fields"):
        PivotDetectorConfig.from_dict(payload)


def test_config_repeated_serialization_is_deterministic() -> None:
    config = pivot_config()
    assert config.to_dict() == config.to_dict()
    assert json.dumps(config.to_dict(), sort_keys=True) == json.dumps(
        config.to_dict(), sort_keys=True
    )


def test_config_is_immutable() -> None:
    config = pivot_config()
    with pytest.raises(FrozenInstanceError):
        config.left_bars = 4  # type: ignore[misc]


def test_unknown_schema_version_is_rejected() -> None:
    payload = pivot_config().to_dict()
    payload["schema_version"] = 2
    with pytest.raises(SwingConfigurationError, match="schema_version"):
        PivotDetectorConfig.from_dict(payload)


def test_unknown_config_field_is_rejected() -> None:
    payload = pivot_config().to_dict()
    payload["automatic_scale"] = "forbidden"
    with pytest.raises(SwingConfigurationError, match="unknown fields"):
        PivotDetectorConfig.from_dict(payload)


def test_detector_implements_public_protocol() -> None:
    assert isinstance(detector(), SwingDetector)


def test_result_and_report_round_trip_deterministically() -> None:
    result = detector().detect_batch(load_result(high_pivot_bars()))
    restored = SwingDetectionResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.to_dict() == result.to_dict()


def test_event_round_trip_preserves_first_seen_time() -> None:
    event = tuple(detector().iter_events(load_result(high_pivot_bars())))[0]
    restored = SwingDetectionEvent.from_dict(event.to_dict())
    assert restored == event
    assert restored.first_seen_time == restored.candidate.confirm_time
