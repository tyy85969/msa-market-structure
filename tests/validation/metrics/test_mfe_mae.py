from decimal import Decimal

from msa.validation import ValidationMetricName

from .scenarios import touch_observations


def test_known_support_and_resistance_mfe_mae() -> None:
    observations = touch_observations()
    assert tuple(
        item.value for item in observations[ValidationMetricName.MFE]
    ) == (Decimal("24"), Decimal("25"))
    assert tuple(
        item.value for item in observations[ValidationMetricName.MAE]
    ) == (Decimal("6"), Decimal("5"))


def test_touch_bar_is_excluded_from_excursion_window() -> None:
    observations = touch_observations()
    all_values = (
        *observations[ValidationMetricName.MFE],
        *observations[ValidationMetricName.MAE],
    )
    assert all(len(item.observed_bar_ids) == 1 for item in all_values)
    assert len({item.observed_bar_ids[0] for item in all_values}) == 1


def test_known_positive_reactions_are_atr_normalized() -> None:
    reactions = touch_observations()[
        ValidationMetricName.FIRST_TOUCH_REACTION
    ]
    assert reactions[0].numerator == Decimal("18")
    assert reactions[1].numerator == Decimal("20")
    assert all(item.value > 0 for item in reactions)
