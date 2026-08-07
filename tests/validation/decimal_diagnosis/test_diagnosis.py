from __future__ import annotations

from decimal import Decimal, getcontext
from pathlib import Path

import pytest

from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.experiments.synthetic_suite import (
    build_synthetic_source_input,
)
from tools.validation.diagnose_core_decimal_context import (
    DIAGNOSIS_VERSION,
    MAXIMUM_CASES,
    SELECTED_SCENARIOS,
    VALIDATION_SEED,
    DecimalDiagnosisError,
    _ALTERED_CONTEXT,
    _DEFAULT_CONTEXT,
    _first_numeric_divergence,
    _first_metric_semantic_difference,
    _run_once,
    build_diagnosis,
    diagnose_cases,
    render_diagnosis,
    reproduce_freshness_expression,
)


ROOT = Path(__file__).resolve().parents[3]


def _context_snapshot() -> tuple[object, ...]:
    context = getcontext()
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        tuple(
            sorted(
                (signal.__name__, enabled)
                for signal, enabled in context.traps.items()
            )
        ),
        tuple(
            sorted(
                (signal.__name__, enabled)
                for signal, enabled in context.flags.items()
            )
        ),
    )


def test_selection_is_three_bounded_validation_seed_two_cases() -> None:
    assert VALIDATION_SEED == 2
    assert MAXIMUM_CASES == 3
    assert SELECTED_SCENARIOS == (
        SyntheticScenarioKind.SINGLE_TREND,
        SyntheticScenarioKind.V_REVERSAL,
        SyntheticScenarioKind.FALSE_BREAK,
    )


def test_seed_three_and_more_than_three_cases_are_rejected() -> None:
    with pytest.raises(DecimalDiagnosisError, match="seed 2"):
        diagnose_cases(((SyntheticScenarioKind.SINGLE_TREND, 3),))
    with pytest.raises(DecimalDiagnosisError, match="one to three"):
        diagnose_cases(
            (
                (SyntheticScenarioKind.SINGLE_TREND, 2),
                (SyntheticScenarioKind.V_REVERSAL, 2),
                (SyntheticScenarioKind.FALSE_BREAK, 2),
                (SyntheticScenarioKind.RANGE, 2),
            )
        )


def test_formula_id_remains_metric_semantics() -> None:
    default = {
        "formula_registry": [{"formula_id": "formula-default"}],
    }
    altered = {
        "formula_registry": [{"formula_id": "formula-altered"}],
    }
    assert _first_metric_semantic_difference(default, altered) == (
        "/formula_registry/0/formula_id",
        "formula-default",
        "formula-altered",
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "event_id",
        "observation_id",
        "match_id",
        "aggregate_id",
        "future_domain_id",
    ),
)
def test_domain_ids_remain_metric_semantics(field_name: str) -> None:
    default = {"items": [{field_name: "domain-default"}]}
    altered = {"items": [{field_name: "domain-altered"}]}
    assert _first_metric_semantic_difference(default, altered) == (
        f"/items/0/{field_name}",
        "domain-default",
        "domain-altered",
    )


@pytest.mark.parametrize(
    "field_name",
    ("metric_report_id", "source_run_id", "provenance"),
)
def test_only_explicit_top_level_metric_wrappers_are_ignored(
    field_name: str,
) -> None:
    default = {field_name: "wrapper-default", "event_count": 1}
    altered = {field_name: "wrapper-altered", "event_count": 1}
    assert _first_metric_semantic_difference(default, altered) is None


def test_wrapper_change_does_not_hide_first_semantic_difference() -> None:
    default = {
        "metric_report_id": "wrapper-default",
        "source_run_id": "run-default",
        "provenance": ["default"],
        "formula_registry": [{"formula_id": "formula-default"}],
    }
    altered = {
        "metric_report_id": "wrapper-altered",
        "source_run_id": "run-altered",
        "provenance": ["altered"],
        "formula_registry": [{"formula_id": "formula-altered"}],
    }
    assert _first_metric_semantic_difference(default, altered) == (
        "/formula_registry/0/formula_id",
        "formula-default",
        "formula-altered",
    )


def test_wrapper_names_are_semantic_below_metric_report_top_level() -> None:
    default = {"events": [{"source_run_id": "nested-default"}]}
    altered = {"events": [{"source_run_id": "nested-altered"}]}
    assert _first_metric_semantic_difference(default, altered) == (
        "/events/0/source_run_id",
        "nested-default",
        "nested-altered",
    )


@pytest.mark.parametrize(
    ("default", "altered", "expected"),
    (
        (
            {"events": [{"event_id": "event-default"}]},
            {"events": [{}]},
            ("/events/0/event_id", "event-default", "<MISSING>"),
        ),
        (
            {"events": [{}]},
            {"events": [{"event_id": "event-altered"}]},
            ("/events/0/event_id", "<MISSING>", "event-altered"),
        ),
        (
            {"event_count": 1},
            {"event_count": "1"},
            ("/event_count", 1, "1"),
        ),
        (
            {"events": [{"event_id": "first"}, {"event_id": "second"}]},
            {"events": [{"event_id": "second"}, {"event_id": "first"}]},
            ("/events/0/event_id", "first", "second"),
        ),
        (
            {"events": [{"event_id": "first"}]},
            {
                "events": [
                    {"event_id": "first"},
                    {"event_id": "extra"},
                ]
            },
            ("/events/1", "<MISSING>", {"event_id": "extra"}),
        ),
    ),
)
def test_metric_semantic_difference_detects_shape_type_value_and_list_order(
    default: dict[str, object],
    altered: dict[str, object],
    expected: tuple[object, object, object],
) -> None:
    assert _first_metric_semantic_difference(default, altered) == expected


def test_minimal_reproduction_is_same_context_stable_and_cross_context_distinct(
) -> None:
    original = _context_snapshot()
    result = reproduce_freshness_expression(
        Decimal("3600"), Decimal("86400")
    )
    assert result == {
        "operands": {
            "age_seconds": "3600",
            "freshness_horizon_seconds": "86400",
        },
        "default_division_output": (
            "0.04166666666666666666666666667"
        ),
        "altered_division_output": "0.04166666",
        "default_output": "0.9583333333333333333333333333",
        "altered_output": "0.9583333",
        "default_repeat_output": "0.9583333333333333333333333333",
        "default_repeat_equal": True,
        "default_altered_different": True,
    }
    assert _context_snapshot() == original


@pytest.mark.parametrize("scenario", SELECTED_SCENARIOS)
def test_current_core_is_equal_across_default_and_altered_decimal_contexts(
    scenario: SyntheticScenarioKind,
) -> None:
    source = build_synthetic_source_input(scenario, VALIDATION_SEED)
    source_before = source.to_dict()
    context_before = _context_snapshot()

    default = _run_once(source, _DEFAULT_CONTEXT)
    altered = _run_once(source, _ALTERED_CONTEXT)

    assert source.to_dict() == source_before
    assert _context_snapshot() == context_before
    assert default.run.to_dict() == altered.run.to_dict()
    assert default.run.run_id == altered.run.run_id
    assert default.metric_error_type is altered.metric_error_type is None
    assert default.metric_report is not None
    assert altered.metric_report is not None
    assert default.metric_report.to_dict() == altered.metric_report.to_dict()
    with pytest.raises(
        DecimalDiagnosisError,
        match="no non-identity Core numeric divergence found",
    ):
        _first_numeric_divergence(default.run, altered.run)


def test_no_diagnosis_divergence_is_post_remediation_success() -> None:
    original = _context_snapshot()
    with pytest.raises(
        DecimalDiagnosisError,
        match="no non-identity Core numeric divergence found",
    ):
        build_diagnosis()
    assert _context_snapshot() == original


def test_historical_diagnosis_document_retains_reviewed_root_cause() -> None:
    text = (
        ROOT / "docs/validation/core_decimal_context_diagnosis.md"
    ).read_text(encoding="utf-8")
    assert "first non-identity numeric divergence" in text
    assert "`freshness_factor`" in text
    assert "`ResonanceScorer._draft`" in text
    assert "`0.9583333333333333333333333333`" in text
    assert "`0.9583333`" in text


def test_rendered_output_is_deterministic_and_has_no_host_or_trading_fields(
) -> None:
    current_status = {
        "diagnosis_version": DIAGNOSIS_VERSION,
        "current_core_status": "NO_NON_IDENTITY_NUMERIC_DIVERGENCE",
        "historical_root_cause_document": (
            "docs/validation/core_decimal_context_diagnosis.md"
        ),
    }
    first = render_diagnosis(current_status)
    second = render_diagnosis(current_status)
    assert first == second
    assert "D:\\" not in first
    assert "msa-market-structure-c008c-h2-diag" not in first
    assert "XAUUSD" not in first
    for field_name in ('"open":', '"high":', '"low":', '"close":'):
        assert field_name not in first
    assert "T00:" not in first
    assert "T01:" not in first
