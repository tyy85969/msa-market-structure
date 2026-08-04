from __future__ import annotations

from decimal import Decimal, getcontext

import pytest

from msa.validation.contracts import SyntheticScenarioKind
from tools.validation.diagnose_core_decimal_context import (
    DecimalDiagnosisError,
    build_diagnosis,
    diagnose_cases,
    render_diagnosis,
    reproduce_freshness_expression,
)


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


@pytest.fixture(scope="module")
def diagnosis() -> dict[str, object]:
    original = _context_snapshot()
    result = build_diagnosis()
    assert _context_snapshot() == original
    return result


def test_selection_is_three_bounded_validation_seed_two_cases(
    diagnosis: dict[str, object],
) -> None:
    policy = diagnosis["execution_policy"]
    cases = diagnosis["cases"]
    assert policy["partition"] == "VALIDATION"
    assert policy["seed"] == 2
    assert policy["case_count"] == policy["maximum_case_count"] == 3
    assert policy["runs_per_case"] == {
        "default_context": 1,
        "altered_context": 1,
    }
    assert [item["scenario"] for item in cases] == [
        "SINGLE_TREND",
        "V_REVERSAL",
        "FALSE_BREAK",
    ]
    assert all(item["seed"] == 2 for item in cases)
    assert all(item["input_unchanged"] for item in cases)
    for forbidden in (
        "oos_executed",
        "b_executed",
        "variants_executed",
        "replay_executed",
        "fixed_cutoff_executed",
        "formal_evidence_written",
    ):
        assert policy[forbidden] is False


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


def test_first_numeric_path_and_propagation_are_reproduced(
    diagnosis: dict[str, object],
) -> None:
    for case in diagnosis["cases"]:
        first = case["first_non_identity_numeric_difference"]
        assert (
            first["function"],
            first["field"],
            first["frame_index"],
        ) == ("ResonanceScorer._draft", "freshness_factor", 1)
        assert first["stored_default_output"] == first["default_output"]
        assert first["stored_altered_output"] == first["altered_output"]
        assert first["classification"]["root_operation"] == "division"
        propagation = case["propagation"]
        assert propagation["dependency_contribution"]["default"] != (
            propagation["dependency_contribution"]["altered"]
        )
        assert propagation["zone_score"]["default"] != (
            propagation["zone_score"]["altered"]
        )
        assert propagation["score_frame_id"]["default"] != (
            propagation["score_frame_id"]["altered"]
        )
        assert propagation["run_id"]["default"] != (
            propagation["run_id"]["altered"]
        )
        assert propagation["metric_report"]["default_status"] == "PRODUCED"
        assert (
            propagation["metric_report"]["altered_status"]
            == "REJECTED_BEFORE_REPORT"
        )
        assert propagation["metric_report"]["altered_metric_report_id"] is None


def test_rendered_output_is_deterministic_and_has_no_host_or_trading_fields(
    diagnosis: dict[str, object],
) -> None:
    first = render_diagnosis(diagnosis)
    second = render_diagnosis(diagnosis)
    assert first == second
    assert "D:\\" not in first
    assert "msa-market-structure-c008c-h2-diag" not in first
    assert "XAUUSD" not in first
    for field_name in ('"open":', '"high":', '"low":', '"close":'):
        assert field_name not in first
    assert "T00:" not in first
    assert "T01:" not in first
