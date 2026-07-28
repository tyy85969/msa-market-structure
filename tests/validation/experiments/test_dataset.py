from collections import Counter

from msa.validation import SyntheticScenarioKind
from msa.validation.experiments import (
    DatasetPartition,
    RealMarketOOSStatus,
    build_c008c_synthetic_dataset,
)


def test_dataset_has_frozen_scenario_seed_partition_matrix() -> None:
    manifest = build_c008c_synthetic_dataset()
    assert len(manifest.cases) == 20
    assert tuple(
        (item.scenario_kind, item.seed) for item in manifest.cases
    ) == tuple(
        (kind, seed)
        for kind in SyntheticScenarioKind
        for seed in (0, 1, 2, 3)
    )
    assert Counter(item.partition for item in manifest.cases) == {
        DatasetPartition.DEVELOPMENT: 10,
        DatasetPartition.VALIDATION: 5,
        DatasetPartition.OOS: 5,
    }
    assert len({item.dataset_case_id for item in manifest.cases}) == 20
    assert len(
        {item.source_input_payload_digest for item in manifest.cases}
    ) == 20
    assert (
        manifest.real_market_oos_status
        is RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET
    )
    assert type(manifest).from_dict(manifest.to_dict()) == manifest
