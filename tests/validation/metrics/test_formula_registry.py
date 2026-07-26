from msa.validation import (
    FORMULA_STATUS_FROZEN,
    default_metric_formula_registry,
    default_metric_registry,
)


def test_formula_registry_exactly_extends_c008a_authority() -> None:
    definitions = default_metric_registry()
    formulas = default_metric_formula_registry()
    assert len(formulas) == 10
    assert tuple(item.metric_definition_id for item in formulas) == tuple(
        item.metric_definition_id for item in definitions
    )
    assert tuple(item.metric_name for item in formulas) == tuple(
        item.name for item in definitions
    )
    assert all(
        item.formula_status == FORMULA_STATUS_FROZEN
        for item in formulas
    )


def test_formula_registry_round_trips_and_is_deterministic() -> None:
    first = default_metric_formula_registry()
    second = default_metric_formula_registry()
    assert first == second
    assert [item.to_dict() for item in first] == [
        item.to_dict() for item in second
    ]
    assert all(type(item).from_dict(item.to_dict()) == item for item in first)
