from msa.validation.experiments import (
    ExperimentKind,
    VariantLevel,
    default_c008c_experiment_plan,
)


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            item
            for child in value.values()
            for item in _keys(child)
        }
    if isinstance(value, list):
        return {item for child in value for item in _keys(child)}
    return set()


def test_plan_freezes_complete_variant_universe_without_outcomes() -> None:
    plan = default_c008c_experiment_plan()
    assert len(plan.axes) == 8
    assert len(plan.variants) == 26
    assert len(
        [
            item
            for item in plan.variants
            if item.experiment_kind is ExperimentKind.BASELINE
        ]
    ) == 1
    assert len(
        [item for item in plan.variants if item.level is VariantLevel.LOW]
    ) == 8
    assert len(
        [item for item in plan.variants if item.level is VariantLevel.HIGH]
    ) == 8
    payload_keys = {item.lower() for item in _keys(plan.to_dict())}
    for prohibited in ("winner", "leaderboard", "best_parameters", "outcome"):
        assert prohibited not in payload_keys
    assert type(plan).from_dict(plan.to_dict()) == plan
