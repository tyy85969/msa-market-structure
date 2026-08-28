from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from c008c_c import architecture
from msa.validation.experiments.contracts import DatasetPartition
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)


ROOT = Path(__file__).resolve().parents[5]
LEGACY_ATTEMPT_SHA256 = (
    "9b085a2b05de853471d1fe12f1eb44e56a2de00529e3f1ef4c1233ea27cf7104"
)
FAILED_POST_FIX_ATTEMPT_SHA256 = (
    "279db9e6f4be33ea78156020ed1703b707ac42d56418ac94eb0a12dd5968ae81"
)


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
    assert contract["validation_exposure_status"] == "POST_EXPOSURE"
    assert contract["prior_primary_execution_count"] == 1
    assert contract["prior_primary_completed_pair_count"] == 130
    assert contract["pristine_locked_holdout"] is False
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


def test_final_binding_preserves_both_failed_attempts(
    contract: dict[str, object],
) -> None:
    legacy_attempt = ROOT / architecture.LEGACY_ATTEMPT_PATH
    legacy_contract = ROOT / architecture.LEGACY_CONTRACT_PATH
    failed_post_fix_attempt = ROOT / architecture.FAILED_POST_FIX_ATTEMPT_PATH
    failed_post_fix_contract = ROOT / architecture.FAILED_POST_FIX_CONTRACT_PATH
    historical = {
        item["relative_path"]: item["sha256"]
        for item in contract["historical_evidence_locks"]
    }
    assert architecture.CONTRACT_PATH != architecture.LEGACY_CONTRACT_PATH
    assert architecture.ATTEMPT_PATH != architecture.LEGACY_ATTEMPT_PATH
    assert architecture.CONTRACT_PATH != architecture.FAILED_POST_FIX_CONTRACT_PATH
    assert architecture.ATTEMPT_PATH != architecture.FAILED_POST_FIX_ATTEMPT_PATH
    assert hashlib.sha256(legacy_attempt.read_bytes()).hexdigest() == (
        LEGACY_ATTEMPT_SHA256
    )
    assert historical[architecture.LEGACY_ATTEMPT_PATH.as_posix()] == (
        LEGACY_ATTEMPT_SHA256
    )
    assert historical[architecture.LEGACY_CONTRACT_PATH.as_posix()] == (
        hashlib.sha256(legacy_contract.read_bytes()).hexdigest()
    )
    assert hashlib.sha256(failed_post_fix_attempt.read_bytes()).hexdigest() == (
        FAILED_POST_FIX_ATTEMPT_SHA256
    )
    assert historical[architecture.FAILED_POST_FIX_ATTEMPT_PATH.as_posix()] == (
        FAILED_POST_FIX_ATTEMPT_SHA256
    )
    assert historical[architecture.FAILED_POST_FIX_CONTRACT_PATH.as_posix()] == (
        hashlib.sha256(failed_post_fix_contract.read_bytes()).hexdigest()
    )


def test_final_contract_binds_current_c_sources(
    contract: dict[str, object],
) -> None:
    locks = {
        item["relative_path"]: item["sha256"]
        for item in contract["c_source_locks"]
    }
    assert set(locks) == {
        item.as_posix() for item in architecture._C_SOURCE_PATHS
    }
    assert locks == {
        item.as_posix(): hashlib.sha256((ROOT / item).read_bytes()).hexdigest()
        for item in architecture._C_SOURCE_PATHS
    }


def test_preflight_rejects_one_byte_locked_source_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_path = ROOT / architecture.CONTRACT_PATH
    committed_raw = contract_path.read_bytes()
    locked_path = (ROOT / architecture._C_SOURCE_PATHS[0]).resolve()
    actual_sha256 = architecture._sha256

    def _mutated_sha256(path: Path) -> str:
        if path.resolve() == locked_path:
            return hashlib.sha256(path.read_bytes() + b"\x00").hexdigest()
        return actual_sha256(path)

    monkeypatch.setattr(
        architecture,
        "_head_blob",
        lambda base, relative: committed_raw,
    )
    monkeypatch.setattr(architecture, "_sha256", _mutated_sha256)
    with pytest.raises(
        architecture.C008CCError,
        match="contract or locked source bytes differ",
    ):
        architecture.validate_c008c_c_preflight(ROOT, require_clean=False)


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
