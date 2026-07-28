import random

from msa.research.msa_core.contracts import validate_source_input
from msa.validation import SyntheticScenarioKind
from msa.validation.experiments import (
    build_c008c_synthetic_dataset,
    build_synthetic_source_input,
)
from msa.reference import core_alpha_v1_config


def test_synthetic_generation_is_repeatable_and_formal() -> None:
    for kind in SyntheticScenarioKind:
        for seed in (0, 1, 2, 3):
            first = build_synthetic_source_input(kind, seed)
            random.seed(999999)
            second = build_synthetic_source_input(kind, seed)
            assert first.to_dict() == second.to_dict()
            assert validate_source_input(
                first, core_alpha_v1_config()
            ) == first
            assert all(
                bar.is_complete
                for bar in first.reference_price_data.bars
            )


def test_source_input_is_never_reused_across_partitions() -> None:
    cases = build_c008c_synthetic_dataset().cases
    by_digest = {
        item.source_input_payload_digest: item.partition for item in cases
    }
    assert len(by_digest) == len(cases)
