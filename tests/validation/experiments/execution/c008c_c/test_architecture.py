from __future__ import annotations

from pathlib import Path

import pytest

from c008c_c import architecture
from msa.validation.experiments.contracts import DatasetPartition
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)


ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def contract() -> dict[str, object]:
    return architecture.build_c008c_c_execution_contract(ROOT)


def test_contract_binds_only_the_frozen_locked_oos_schedule(
    contract: dict[str, object],
) -> None:
    manifest = build_c008c_b_execution_manifest(ROOT)
    assert contract["base_main_sha"] == architecture.BASE_MAIN_SHA
    assert contract["b_v2_stage_status"] == "READY_FOR_LOCKED_OOS"
    assert contract["partition"] == DatasetPartition.OOS.value
    assert contract["seed"] == 3
    assert contract["scenario_count"] == 5
    assert contract["variant_count"] == 26
    assert contract["oos_pair_count"] == 130
    assert contract["baseline_replay_count"] == 5
    assert contract["fixed_cutoff_count"] == 5
    assert contract["oos_pair_ids"] == [
        item.execution_pair_id for item in manifest.deferred_oos_pairs
    ]
    assert contract["oos_case_ids"] == list(manifest.deferred_oos_case_ids)
    assert contract["baseline_replay_sample_ids"] == list(
        manifest.deferred_baseline_replay_sample_ids
    )
    assert contract["fixed_cutoff_case_ids"] == list(
        manifest.deferred_fixed_cutoff_case_ids
    )
    assert all(
        item.seed == 3
        and item.partition is DatasetPartition.OOS
        and item.deferred_to_c008c_c
        for item in manifest.deferred_oos_pairs
    )


def test_contract_preserves_b_v2_source_scope(
    contract: dict[str, object],
) -> None:
    new_paths = {
        item["relative_path"] for item in contract["c_source_locks"]
    }
    source_payload = architecture._canonical_payload(
        ROOT / architecture.B_V2_SOURCE_PATH,
        "B-v2 source authority",
    )[1]
    b_paths = {item["relative_path"] for item in source_payload["files"]}
    assert len(b_paths) == 138
    assert not new_paths & b_paths
    assert architecture.B_V2_CONTRACT_PATH.as_posix() in {
        item["relative_path"]
        for item in contract["historical_evidence_locks"]
    }
    assert architecture.B_V2_REPORT_PATH.as_posix() in {
        item["relative_path"]
        for item in contract["historical_evidence_locks"]
    }


def test_attempt_marker_is_deterministic_and_forbids_retry(
    contract: dict[str, object],
) -> None:
    first = architecture._attempt_payload(contract)
    second = architecture._attempt_payload(contract)
    assert first == second
    assert first["formal_execution_count"] == 1
    assert first["retry_allowed"] is False
    assert first["seed"] == 3
    assert not any("time" in key.lower() for key in first)


def test_primary_guard_rejects_b_stage_pair_before_core() -> None:
    manifest = build_c008c_b_execution_manifest(ROOT)
    _, dataset, _, plan, _ = load_c008c_b_authority(ROOT)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    pair = manifest.execution_pairs[0]
    with pytest.raises(
        architecture.C008CCError,
        match="not frozen seed-3 OOS authority",
    ):
        architecture._execute_oos_pair(
            pair,
            cases[pair.dataset_case_id],
            variants[pair.variant_id],
        )


def test_append_only_writer_refuses_different_bytes(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    architecture._write_or_refuse_different(path, b"first")
    architecture._write_or_refuse_different(path, b"first")
    with pytest.raises(architecture.C008CCError, match="refusing to overwrite"):
        architecture._write_or_refuse_different(path, b"second")
