"""Frozen deterministic synthetic dataset manifest for C-008C."""

from __future__ import annotations

from msa.data import Timeframe
from msa.validation.contracts import SyntheticScenarioKind

from .contracts import (
    DatasetPartition,
    ExperimentDatasetCase,
    ExperimentDatasetManifest,
    RealMarketOOSStatus,
)
from .identity import digest, semantic_id
from .synthetic_suite import build_synthetic_source_input


_EXPECTED = (
    "Every consumed fact is available by its causal AsOf",
    "OriginTime does not grant visibility before ConfirmTime",
    "All reference bars are complete before formal availability",
    "Future appends cannot rewrite an earlier public payload",
)
_CASE_ASSUMPTIONS = (
    "Synthetic data is used only for engineering acceptance",
    "Synthetic data does not represent real-market distribution",
    "Synthetic data does not represent XAUUSD historical performance",
)
_MANIFEST_ASSUMPTIONS = (
    "Partitions are frozen before any experiment outcome",
    "Seeds are engineering identifiers not random search inputs",
    "No external or real-market data is downloaded",
    "Synthetic OOS is not real-market OOS",
)
_SEED_RULES = (
    "DEVELOPMENT uses seeds 0 and 1",
    "VALIDATION uses seed 2",
    "OOS uses seed 3",
)


def _partition(seed: int) -> DatasetPartition:
    if seed in (0, 1):
        return DatasetPartition.DEVELOPMENT
    if seed == 2:
        return DatasetPartition.VALIDATION
    return DatasetPartition.OOS


def _case(kind: SyntheticScenarioKind, seed: int) -> ExperimentDatasetCase:
    source_input = build_synthetic_source_input(kind, seed)
    source_digest = digest(source_input.to_dict())
    payload = {
        "scenario_kind": kind.value,
        "seed": seed,
        "partition": _partition(seed).value,
        "symbol": "XAUUSD",
        "reference_timeframe": Timeframe.H1.value,
        "source_input": source_input.to_dict(),
        "source_input_payload_digest": source_digest,
        "expected_causal_properties": list(_EXPECTED),
        "assumptions": list(_CASE_ASSUMPTIONS),
        "schema_version": 1,
    }
    return ExperimentDatasetCase(
        dataset_case_id=semantic_id("c008c-dataset-case-v1-", payload),
        scenario_kind=kind,
        seed=seed,
        partition=_partition(seed),
        symbol="XAUUSD",
        reference_timeframe=Timeframe.H1,
        source_input=source_input,
        source_input_payload_digest=source_digest,
        expected_causal_properties=_EXPECTED,
        assumptions=_CASE_ASSUMPTIONS,
    )


def build_c008c_synthetic_dataset() -> ExperimentDatasetManifest:
    cases = tuple(
        _case(kind, seed)
        for kind in SyntheticScenarioKind
        for seed in (0, 1, 2, 3)
    )
    payload = {
        "cases": [item.to_dict() for item in cases],
        "scenario_order": [item.value for item in SyntheticScenarioKind],
        "partition_order": [
            DatasetPartition.DEVELOPMENT.value,
            DatasetPartition.VALIDATION.value,
            DatasetPartition.OOS.value,
        ],
        "seed_partition_rules": list(_SEED_RULES),
        "real_market_oos_status": (
            RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET.value
        ),
        "assumptions": list(_MANIFEST_ASSUMPTIONS),
        "schema_version": 1,
    }
    return ExperimentDatasetManifest(
        dataset_manifest_id=semantic_id(
            "c008c-dataset-manifest-v1-", payload
        ),
        cases=cases,
        scenario_order=tuple(SyntheticScenarioKind),
        partition_order=(
            DatasetPartition.DEVELOPMENT,
            DatasetPartition.VALIDATION,
            DatasetPartition.OOS,
        ),
        seed_partition_rules=_SEED_RULES,
        real_market_oos_status=(
            RealMarketOOSStatus.NOT_RUN_NO_APPROVED_DATASET
        ),
        assumptions=_MANIFEST_ASSUMPTIONS,
    )
