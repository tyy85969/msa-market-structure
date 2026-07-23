from msa.validation import (
    SyntheticScenarioDescriptor,
    SyntheticScenarioKind,
)

from .fixtures import auditor
from .scenarios import all_descriptors, scenario_run


def test_five_scenario_descriptors_are_deterministic_and_strict() -> None:
    first = all_descriptors()
    second = all_descriptors()
    assert len(first) == 5
    assert first == second
    assert {item.kind for item in first} == set(SyntheticScenarioKind)
    assert tuple(
        SyntheticScenarioDescriptor.from_dict(item.to_dict())
        for item in first
    ) == first


def test_every_synthetic_scenario_builds_formal_passing_run() -> None:
    for kind in SyntheticScenarioKind:
        run = scenario_run(kind)
        assert run.to_dict()
        assert auditor().audit_run(run).passed
