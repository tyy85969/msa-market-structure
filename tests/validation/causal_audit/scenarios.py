from __future__ import annotations

from msa.validation import (
    SyntheticScenarioDescriptor,
    SyntheticScenarioKind,
)
from msa.validation.identity import semantic_id

from .fixtures import with_reference_prices


_ASSUMPTIONS = (
    "Synthetic bars are deterministic engineering fixtures",
    "Synthetic bars do not represent the distribution of a real market",
    "Parameters are not optimized for XAUUSD",
)
_EXPECTED = (
    "Every consumed fact is available by the Bundle AsOf",
    "Batch and replay preserve complete public payloads",
    "No later bar rewrites an earlier Bundle",
)
_PRICES = {
    SyntheticScenarioKind.SINGLE_TREND: ("98", "101", "104", "107"),
    SyntheticScenarioKind.RANGE: ("100", "102", "99", "101"),
    SyntheticScenarioKind.V_REVERSAL: ("105", "99", "102", "106"),
    SyntheticScenarioKind.FALSE_BREAK: ("100", "109", "101", "100"),
    SyntheticScenarioKind.GAP_SHOCK: ("99", "100", "114", "112"),
}


def descriptor(kind: SyntheticScenarioKind) -> SyntheticScenarioDescriptor:
    seed = 8000 + list(SyntheticScenarioKind).index(kind)
    scenario_id = f"c008a-{kind.value.lower().replace('_', '-')}"
    payload = {
        "scenario_id": scenario_id,
        "kind": kind.value,
        "seed": seed,
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "bar_count": len(_PRICES[kind]),
        "assumptions": list(_ASSUMPTIONS),
        "expected_causal_properties": list(_EXPECTED),
        "schema_version": 1,
    }
    return SyntheticScenarioDescriptor(
        scenario_descriptor_id=semantic_id(
            "synthetic-scenario-v1-", payload
        ),
        scenario_id=scenario_id,
        kind=kind,
        seed=seed,
        symbol="XAUUSD",
        timeframe="H1",
        bar_count=len(_PRICES[kind]),
        assumptions=_ASSUMPTIONS,
        expected_causal_properties=_EXPECTED,
    )


def scenario_run(kind: SyntheticScenarioKind):
    return with_reference_prices(_PRICES[kind])


def all_descriptors() -> tuple[SyntheticScenarioDescriptor, ...]:
    return tuple(descriptor(kind) for kind in SyntheticScenarioKind)
