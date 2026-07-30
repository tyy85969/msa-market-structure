from collections import Counter
from dataclasses import replace

import pytest

from msa.validation import SyntheticScenarioKind
from msa.validation.experiments import (
    DatasetPartition,
    ExperimentDatasetError,
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
    assert manifest.capacity_policy.minimum_pre_confirm_completed_bars == 20
    assert manifest.capacity_policy.minimum_post_confirm_completed_bars == 24
    assert manifest.capacity_policy.generated_warmup_bars == 32
    assert manifest.capacity_policy.generated_post_confirm_bars == 64
    assert manifest.capacity_policy.maximum_atr_period == 20
    assert manifest.capacity_policy.maximum_outcome_horizon_bars == 24
    assert manifest.capacity_policy.all_bars_must_be_complete is True
    assert manifest.capacity_policy.no_external_data is True
    assert type(manifest).from_dict(manifest.to_dict()) == manifest


def test_capacity_policy_cannot_be_relaxed_by_direct_construction() -> None:
    policy = build_c008c_synthetic_dataset().capacity_policy
    with pytest.raises(ExperimentDatasetError):
        replace(policy, minimum_pre_confirm_completed_bars=19)
    with pytest.raises(ExperimentDatasetError):
        replace(policy, maximum_outcome_horizon_bars=12)
