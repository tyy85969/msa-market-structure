import pytest

from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.remediation import (
    RemediationEvidenceError,
    compare_decimal_context_case,
)


@pytest.mark.parametrize("scenario", tuple(SyntheticScenarioKind))
def test_five_validation_seed_2_cases_have_complete_cross_context_equality(
    scenario: SyntheticScenarioKind,
) -> None:
    result = compare_decimal_context_case(scenario, 2)
    assert result["core_audit_metric_replay_full_equal"] is True
    assert result["caller_context_restored"] is True
    assert {item["context"] for item in result["contexts"]} == {
        "DEFAULT",
        "PRECISION_7_ROUND_FLOOR",
        "PRECISION_50_ROUND_CEILING",
    }
    assert {item["run_id"] for item in result["contexts"]} == {
        result["expected_default_run_id"]
    }


def test_oos_seed_3_is_rejected_before_execution() -> None:
    with pytest.raises(
        RemediationEvidenceError,
        match="VALIDATION seed 2 only",
    ):
        compare_decimal_context_case(SyntheticScenarioKind.SINGLE_TREND, 3)
