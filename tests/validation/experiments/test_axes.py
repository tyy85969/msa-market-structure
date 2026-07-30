from decimal import Decimal

from msa.validation.experiments import (
    ParameterAxisKind,
    VariantLevel,
    default_c008c_experiment_plan,
)


def test_exact_eight_axes_and_values_are_frozen() -> None:
    axes = default_c008c_experiment_plan().axes
    assert [item.code for item in axes] == [
        "DEPENDENCY_REPEAT_CREDIT",
        "SOURCE_DIVERSITY_BONUS_PER_EXTRA",
        "CONTEXT_DIVERSITY_BONUS_PER_EXTRA",
        "MINIMUM_REPLACEMENT_SCORE_IMPROVEMENT",
        "ATR_PERIOD",
        "TURN_RESOLUTION_BARS",
        "BREAK_OBSERVATION_BARS",
        "REACTION_OBSERVATION_BARS",
    ]
    assert [tuple(value.level for value in item.values) for item in axes] == [
        (VariantLevel.LOW, VariantLevel.BASELINE, VariantLevel.HIGH)
    ] * 8
    assert [tuple(value.value for value in item.values) for item in axes] == [
        (Decimal("0"), Decimal("0.25"), Decimal("0.5")),
        (Decimal("0"), Decimal("0.2"), Decimal("0.4")),
        (Decimal("0"), Decimal("0.3"), Decimal("0.6")),
        (Decimal("0"), Decimal("0.1"), Decimal("0.2")),
        (10, 14, 20),
        (4, 8, 12),
        (4, 8, 12),
        (4, 8, 12),
    ]
    assert [item.kind for item in axes].count(ParameterAxisKind.MODEL) == 4
    assert [item.kind for item in axes].count(ParameterAxisKind.METRIC) == 4
