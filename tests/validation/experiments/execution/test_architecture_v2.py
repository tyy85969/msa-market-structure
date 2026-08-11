from __future__ import annotations

from dataclasses import fields
import importlib.util
from pathlib import Path
import shutil

import pytest

from msa.validation.experiments.execution import (
    B_V2_EXECUTION_CONTRACT_PATH,
    B_V2_EXECUTION_SOURCE_MANIFEST_PATH,
    B_V2_REPORT_PATH,
    C008CBStageStatus,
    C008CBV2ExecutionContract,
    C008CBV2ExecutionSourceManifest,
    C008CBV2RunReport,
    DeterminismEvidenceKind,
    GateEvaluationStatus,
    build_c008c_b_v2_execution_contract,
    build_c008c_b_v2_execution_source_manifest,
    build_c008c_b_v2_report,
    check_existing_c008c_b_v2_evidence,
    derive_c008c_b_v2_stage,
    validate_c008c_b_v2_execution_contract,
    validate_c008c_b_v2_execution_schedule,
    validate_c008c_b_v2_execution_source_authority,
    validate_c008c_b_v2_report,
    write_c008c_b_v2_evidence,
)
from msa.validation.experiments.execution.contracts import (
    C008CBExecutionManifest,
)
from msa.validation.experiments.execution.degeneration import (
    evaluate_validation_degeneration_v2,
)
from msa.validation.experiments.execution.errors import (
    C008CBEvidenceError,
    C008CBManifestError,
    C008CBPreflightError,
    C008CBReportError,
)
from msa.validation.experiments.execution.gate_evaluator import (
    evaluate_c008c_b_v2_gates,
)
from msa.validation.experiments.execution.report import _partition_summaries
from msa.validation.experiments.execution.runner import (
    C008CBV2PrimaryExecution,
    _ExecutionArtifacts,
    _determinism_v2,
)
from msa.validation.experiments.identity import semantic_id


ROOT = Path(__file__).resolve().parents[4]

_HISTORICAL_NAMES = (
    "c008c_b_dev_validation_report.json",
    "c008c_b_execution_manifest.json",
    "c008c_b_root_cause_lock.json",
    "c008c_b_root_cause_manifest.json",
    "c008c_b_root_cause_report.json",
    "c008c_baseline_snapshot.json",
    "c008c_dataset_manifest.json",
    "c008c_experiment_plan.json",
    "c008c_protected_source_manifest.json",
    "c008c_h2_decimal_remediation.json",
    "c008c_h3_metric_fixed_cutoff_transition.json",
)


def _resign(cls, id_field: str, payload: dict):
    signed = dict(payload)
    signed[id_field] = semantic_id(
        cls._PREFIX,
        {key: value for key, value in signed.items() if key != id_field},
    )
    return cls.from_dict(signed)


def _replace_gate(gate, status: GateEvaluationStatus):
    payload = gate.to_dict()
    payload["status"] = status.value
    return _resign(type(gate), "gate_result_id", payload)


def _ready_gates(gates):
    deferred = {
        "ALL_CASES_MUST_EXECUTE",
        "OOS_SAMPLE_COVERAGE",
        "FREEZE_SOURCE_BOUND",
    }
    partial = {
        "ALL_CORE_RUNS_MUST_AUDIT",
        "ALL_METRIC_REPORTS_MUST_SOURCE_BIND",
        "BASELINE_BATCH_REPLAY_PARITY",
        "FIXED_CUTOFF_STABILITY",
        "DETERMINISTIC_REPEAT",
        "DECIMAL_CONTEXT_INDEPENDENCE",
        "TEN_AGGREGATES_ALWAYS_PRESENT",
    }
    return tuple(
        _replace_gate(
            item,
            GateEvaluationStatus.DEFERRED_TO_C008C_C
            if item.gate_code in deferred
            else GateEvaluationStatus.PARTIAL_PASS_DEFERRED_OOS
            if item.gate_code in partial
            else GateEvaluationStatus.PASS,
        )
        for item in gates
    )


@pytest.fixture(scope="session")
def b_v2_architecture_bundle(compact_components):
    same = []
    decimal = []
    for pair, result in zip(
        compact_components["manifest"].execution_pairs,
        compact_components["case_results"],
        strict=True,
    ):
        artifacts = _ExecutionArtifacts(result, None, None, None)
        same.append(
            _determinism_v2(
                pair,
                artifacts,
                artifacts,
                DeterminismEvidenceKind.SAME_CONTEXT_REPEAT,
            )
        )
        decimal.append(
            _determinism_v2(
                pair,
                artifacts,
                artifacts,
                DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION,
            )
        )
    same = tuple(same)
    decimal = tuple(decimal)
    degeneration, global_evidence = evaluate_validation_degeneration_v2(
        compact_components["case_results"],
        compact_components["deltas"],
        compact_components["replay"],
        compact_components["cutoff"],
    )
    gates = evaluate_c008c_b_v2_gates(
        compact_components["manifest"],
        compact_components["case_results"],
        same,
        decimal,
        compact_components["replay"],
        compact_components["cutoff"],
        degeneration,
        global_evidence,
    )
    partitions = _partition_summaries(
        compact_components["case_results"],
        compact_components["deltas"],
        compact_components["replay"],
        degeneration,
        None,
    )
    contract = build_c008c_b_v2_execution_contract(
        compact_components["manifest"]
    )
    report = build_c008c_b_v2_report(
        compact_components["manifest"],
        contract,
        compact_components["case_results"],
        same,
        decimal,
        compact_components["deltas"],
        partitions,
        compact_components["replay"],
        compact_components["cutoff"],
        degeneration,
        global_evidence,
        gates,
    )
    return {
        **compact_components,
        "same": same,
        "decimal": decimal,
        "v2_degeneration": degeneration,
        "global": global_evidence,
        "v2_gates": gates,
        "v2_partitions": partitions,
        "contract": contract,
        "v2_report": report,
    }


def _copy_authority_root(target: Path) -> None:
    (target / "docs/validation/evidence").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "pyproject.toml", target / "pyproject.toml")
    for name in _HISTORICAL_NAMES:
        shutil.copyfile(
            ROOT / "docs/validation/evidence" / name,
            target / "docs/validation/evidence" / name,
        )
    shutil.copyfile(
        ROOT / B_V2_EXECUTION_SOURCE_MANIFEST_PATH,
        target / B_V2_EXECUTION_SOURCE_MANIFEST_PATH,
    )
    for entry in build_c008c_b_v2_execution_source_manifest(ROOT).files:
        source = ROOT / entry.relative_path
        destination = target / entry.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_v2_report_round_trip_and_source_bound_validation(
    b_v2_architecture_bundle,
) -> None:
    report = b_v2_architecture_bundle["v2_report"]
    restored = C008CBV2RunReport.from_dict(report.to_dict())
    assert restored == report
    assert restored.schema_version == 2
    assert restored.run_report_id.startswith("c008c-b-v2-run-report-v2-")
    source = validate_c008c_b_v2_execution_source_authority(ROOT)
    assert restored.execution_source_manifest_id == source.source_manifest_id
    assert restored.stage_status is C008CBStageStatus.BLOCKED_BEFORE_OOS
    assert validate_c008c_b_v2_report(
        restored,
        b_v2_architecture_bundle["contract"],
        b_v2_architecture_bundle["manifest"],
    ) == restored


def test_stage_decision_accepts_only_frozen_ready_or_blocked_paths(
    b_v2_architecture_bundle,
) -> None:
    ready = _ready_gates(b_v2_architecture_bundle["v2_gates"])
    assert derive_c008c_b_v2_stage(ready) is (
        C008CBStageStatus.READY_FOR_LOCKED_OOS
    )
    blocked = list(ready)
    index = next(
        index
        for index, item in enumerate(blocked)
        if item.gate_code == "DETERMINISTIC_REPEAT"
    )
    blocked[index] = _replace_gate(
        blocked[index], GateEvaluationStatus.FAIL
    )
    assert derive_c008c_b_v2_stage(tuple(blocked)) is (
        C008CBStageStatus.BLOCKED_BEFORE_OOS
    )
    with pytest.raises(C008CBReportError, match="exact ordered"):
        derive_c008c_b_v2_stage(ready[:-1])
    with pytest.raises(C008CBReportError, match="exact ordered"):
        derive_c008c_b_v2_stage(ready + (ready[-1],))


def test_report_rejects_ready_stage_that_contradicts_gate_payload(
    b_v2_architecture_bundle,
) -> None:
    payload = b_v2_architecture_bundle["v2_report"].to_dict()
    payload["stage_status"] = C008CBStageStatus.READY_FOR_LOCKED_OOS.value
    forged = _resign(C008CBV2RunReport, "run_report_id", payload)
    with pytest.raises(C008CBReportError, match="stage decision"):
        validate_c008c_b_v2_report(
            forged,
            b_v2_architecture_bundle["contract"],
            b_v2_architecture_bundle["manifest"],
        )


def test_report_rejects_missing_reordered_and_duplicate_pair_results(
    b_v2_architecture_bundle,
) -> None:
    payload = b_v2_architecture_bundle["v2_report"].to_dict()
    missing = dict(payload)
    missing["case_results"] = missing["case_results"][:-1]
    with pytest.raises(C008CBReportError):
        _resign(C008CBV2RunReport, "run_report_id", missing)

    reordered = dict(payload)
    reordered["case_results"] = list(reversed(reordered["case_results"]))
    forged = _resign(C008CBV2RunReport, "run_report_id", reordered)
    with pytest.raises(C008CBReportError, match="reordered"):
        validate_c008c_b_v2_report(
            forged,
            b_v2_architecture_bundle["contract"],
            b_v2_architecture_bundle["manifest"],
        )

    duplicate = dict(payload)
    values = list(duplicate["case_results"])
    values[-1] = values[0]
    duplicate["case_results"] = values
    with pytest.raises(C008CBReportError):
        _resign(C008CBV2RunReport, "run_report_id", duplicate)


def test_contract_and_report_reject_authority_mismatches(
    b_v2_architecture_bundle,
) -> None:
    contract_payload = b_v2_architecture_bundle["contract"].to_dict()
    contract_payload["historical_execution_manifest_id"] = "wrong-manifest"
    forged_contract = _resign(
        C008CBV2ExecutionContract,
        "execution_contract_id",
        contract_payload,
    )
    with pytest.raises(C008CBManifestError, match="historical manifest"):
        validate_c008c_b_v2_execution_contract(
            forged_contract, b_v2_architecture_bundle["manifest"]
        )

    report_payload = b_v2_architecture_bundle["v2_report"].to_dict()
    report_payload["reviewed_protected_source_manifest_id"] = "wrong-source"
    forged_report = _resign(
        C008CBV2RunReport, "run_report_id", report_payload
    )
    with pytest.raises(C008CBReportError, match="source authority"):
        validate_c008c_b_v2_report(
            forged_report,
            b_v2_architecture_bundle["contract"],
            b_v2_architecture_bundle["manifest"],
        )

    report_payload = b_v2_architecture_bundle["v2_report"].to_dict()
    report_payload["execution_source_manifest_id"] = "forged-source-manifest"
    forged_report = _resign(
        C008CBV2RunReport, "run_report_id", report_payload
    )
    with pytest.raises(C008CBReportError, match="execution source authority"):
        validate_c008c_b_v2_report(
            forged_report,
            b_v2_architecture_bundle["contract"],
            b_v2_architecture_bundle["manifest"],
        )


def test_execution_source_manifest_is_canonical_complete_and_source_bound() -> None:
    source = validate_c008c_b_v2_execution_source_authority(ROOT)
    assert C008CBV2ExecutionSourceManifest.from_dict(source.to_dict()) == source
    assert source.schema_version == 2
    assert source.file_count == 138
    assert source.source_manifest_id.startswith(
        "c008c-b-v2-execution-source-manifest-v2-"
    )
    paths = tuple(item.relative_path for item in source.files)
    assert paths == tuple(sorted(paths))
    assert paths[-1] == "tools/validation/generate_c008c_b_v2_results.py"
    assert all(
        path.startswith("src/python/msa/") and path.endswith(".py")
        for path in paths[:-1]
    )


@pytest.mark.parametrize(
    "relative_path",
    (
        "src/python/msa/validation/experiments/execution/report_v2.py",
        "src/python/msa/validation/experiments/execution/gate_evaluator.py",
    ),
)
def test_dirty_execution_source_fails_before_primary_executor(
    tmp_path: Path,
    b_v2_architecture_bundle,
    monkeypatch,
    relative_path: str,
) -> None:
    import msa.validation.experiments.execution.report_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    dirty = root / relative_path
    dirty.write_bytes(dirty.read_bytes() + b"\n# dirty source test\n")
    calls = 0

    def primary(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return b_v2_architecture_bundle["case_results"]

    monkeypatch.setattr(module, "run_primary_execution_v2", primary)
    with pytest.raises(C008CBPreflightError, match="differs from committed"):
        module.run_c008c_b_v2_dev_validation(root)
    assert calls == 0


def test_source_authority_missing_or_noncanonical_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    authority = root / B_V2_EXECUTION_SOURCE_MANIFEST_PATH
    authority.unlink()
    with pytest.raises(C008CBPreflightError, match="missing or invalid"):
        validate_c008c_b_v2_execution_source_authority(root)

    _copy_authority_root(root)
    authority.write_bytes(authority.read_bytes() + b" ")
    with pytest.raises(C008CBPreflightError, match="not canonical"):
        validate_c008c_b_v2_execution_source_authority(root)


def test_report_rejects_swapped_or_shared_determinism_evidence(
    b_v2_architecture_bundle,
) -> None:
    payload = b_v2_architecture_bundle["v2_report"].to_dict()
    payload["same_context_comparisons"], payload[
        "decimal_context_comparisons"
    ] = (
        payload["decimal_context_comparisons"],
        payload["same_context_comparisons"],
    )
    with pytest.raises(C008CBReportError):
        _resign(C008CBV2RunReport, "run_report_id", payload)

    payload = b_v2_architecture_bundle["v2_report"].to_dict()
    payload["decimal_context_comparisons"] = payload[
        "same_context_comparisons"
    ]
    with pytest.raises(C008CBReportError):
        _resign(C008CBV2RunReport, "run_report_id", payload)


def test_report_requires_global_degeneration_evidence(
    b_v2_architecture_bundle,
) -> None:
    payload = b_v2_architecture_bundle["v2_report"].to_dict()
    del payload["global_degeneration_evidence"]
    with pytest.raises(C008CBReportError, match="fields mismatch"):
        C008CBV2RunReport.from_dict(payload)


def test_schedule_barrier_rejects_seed3_before_validation_or_execution(
    b_v2_architecture_bundle,
) -> None:
    manifest = b_v2_architecture_bundle["manifest"]
    forged = object.__new__(C008CBExecutionManifest)
    for field in fields(C008CBExecutionManifest):
        object.__setattr__(forged, field.name, getattr(manifest, field.name))
    object.__setattr__(
        forged,
        "execution_pairs",
        (manifest.deferred_oos_pairs[0],) + manifest.execution_pairs[1:],
    )
    with pytest.raises(C008CBManifestError, match="seed 3"):
        validate_c008c_b_v2_execution_schedule(
            forged, b_v2_architecture_bundle["contract"]
        )


def test_orchestration_routes_existing_components_without_real_execution(
    b_v2_architecture_bundle,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.report_v2 as module

    events = []
    primary = C008CBV2PrimaryExecution(
        b_v2_architecture_bundle["case_results"],
        b_v2_architecture_bundle["same"],
        b_v2_architecture_bundle["decimal"],
    )

    def routed(name, value):
        def call(*_args, **_kwargs):
            events.append(name)
            return value

        return call

    monkeypatch.setattr(
        module,
        "run_primary_execution_v2",
        routed("primary", primary),
    )
    monkeypatch.setattr(
        module,
        "run_replay_comparisons",
        routed("replay", b_v2_architecture_bundle["replay"]),
    )
    monkeypatch.setattr(
        module,
        "run_fixed_cutoff_comparisons",
        routed("cutoff", b_v2_architecture_bundle["cutoff"]),
    )
    monkeypatch.setattr(
        module,
        "calculate_metric_deltas",
        routed("deltas", b_v2_architecture_bundle["deltas"]),
    )
    monkeypatch.setattr(
        module,
        "evaluate_validation_degeneration_v2",
        routed(
            "degeneration",
            (
                b_v2_architecture_bundle["v2_degeneration"],
                b_v2_architecture_bundle["global"],
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "evaluate_c008c_b_v2_gates",
        routed("gates", b_v2_architecture_bundle["v2_gates"]),
    )
    monkeypatch.setattr(
        module,
        "_partition_summaries",
        routed("partitions", b_v2_architecture_bundle["v2_partitions"]),
    )
    monkeypatch.setattr(
        module,
        "build_c008c_b_v2_report",
        routed("report", b_v2_architecture_bundle["v2_report"]),
    )
    monkeypatch.setattr(
        module,
        "validate_c008c_b_v2_report",
        routed("validate", b_v2_architecture_bundle["v2_report"]),
    )
    assert module.run_c008c_b_v2_dev_validation() == (
        b_v2_architecture_bundle["v2_report"]
    )
    assert events == [
        "primary",
        "replay",
        "cutoff",
        "deltas",
        "degeneration",
        "gates",
        "partitions",
        "report",
        "validate",
    ]


def test_source_change_during_mocked_orchestration_fails_before_outcome_write(
    tmp_path: Path,
    b_v2_architecture_bundle,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.report_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    primary = C008CBV2PrimaryExecution(
        b_v2_architecture_bundle["case_results"],
        b_v2_architecture_bundle["same"],
        b_v2_architecture_bundle["decimal"],
    )
    validate_calls = 0

    def mutating_primary(*_args, **_kwargs):
        path = (
            root
            / "src/python/msa/validation/experiments/execution/"
            "gate_evaluator.py"
        )
        path.write_bytes(path.read_bytes() + b"\n# during-run mutation\n")
        return primary

    def routed(value):
        return lambda *_args, **_kwargs: value

    def validate(*_args, **_kwargs):
        nonlocal validate_calls
        validate_calls += 1
        return b_v2_architecture_bundle["v2_report"]

    monkeypatch.setattr(module, "run_primary_execution_v2", mutating_primary)
    monkeypatch.setattr(
        module,
        "run_replay_comparisons",
        routed(b_v2_architecture_bundle["replay"]),
    )
    monkeypatch.setattr(
        module,
        "run_fixed_cutoff_comparisons",
        routed(b_v2_architecture_bundle["cutoff"]),
    )
    monkeypatch.setattr(
        module,
        "calculate_metric_deltas",
        routed(b_v2_architecture_bundle["deltas"]),
    )
    monkeypatch.setattr(
        module,
        "evaluate_validation_degeneration_v2",
        routed(
            (
                b_v2_architecture_bundle["v2_degeneration"],
                b_v2_architecture_bundle["global"],
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "evaluate_c008c_b_v2_gates",
        routed(b_v2_architecture_bundle["v2_gates"]),
    )
    monkeypatch.setattr(
        module,
        "_partition_summaries",
        routed(b_v2_architecture_bundle["v2_partitions"]),
    )
    monkeypatch.setattr(
        module,
        "build_c008c_b_v2_report",
        routed(b_v2_architecture_bundle["v2_report"]),
    )
    monkeypatch.setattr(module, "validate_c008c_b_v2_report", validate)

    with pytest.raises(C008CBPreflightError, match="changed during execution"):
        module.run_c008c_b_v2_dev_validation(root)
    assert validate_calls == 0
    assert not (root / B_V2_EXECUTION_CONTRACT_PATH).exists()
    assert not (root / B_V2_REPORT_PATH).exists()


def test_v2_writer_is_append_only_and_preserves_all_historical_bytes(
    tmp_path: Path,
    b_v2_architecture_bundle,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.evidence as v1_evidence
    import msa.validation.experiments.execution.evidence_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    before = {
        name: (root / "docs/validation/evidence" / name).read_bytes()
        for name in _HISTORICAL_NAMES
    }

    def forbidden_v1(*_args, **_kwargs):
        raise AssertionError("historical v1 writer must never be called")

    monkeypatch.setattr(v1_evidence, "write_c008c_b_evidence", forbidden_v1)
    monkeypatch.setattr(
        module,
        "run_c008c_b_v2_dev_validation",
        lambda _root: b_v2_architecture_bundle["v2_report"],
    )
    monkeypatch.setattr(
        module,
        "validate_c008c_b_v2_report",
        lambda report, *_args: report,
    )
    paths = write_c008c_b_v2_evidence(root)
    assert paths == (
        root / B_V2_EXECUTION_CONTRACT_PATH,
        root / B_V2_REPORT_PATH,
    )
    assert all(path.is_file() for path in paths)
    assert check_existing_c008c_b_v2_evidence(root) == paths
    paths[1].write_bytes(b"different-existing-v2-evidence")
    with pytest.raises(C008CBEvidenceError, match="refusing to overwrite"):
        write_c008c_b_v2_evidence(root)
    after = {
        name: (root / "docs/validation/evidence" / name).read_bytes()
        for name in _HISTORICAL_NAMES
    }
    assert after == before


def test_check_existing_fails_closed_on_current_execution_source_mismatch(
    tmp_path: Path,
    b_v2_architecture_bundle,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.evidence_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    monkeypatch.setattr(
        module,
        "run_c008c_b_v2_dev_validation",
        lambda _root: b_v2_architecture_bundle["v2_report"],
    )
    monkeypatch.setattr(
        module,
        "validate_c008c_b_v2_report",
        lambda report, *_args: report,
    )
    write_c008c_b_v2_evidence(root)
    dirty = (
        root
        / "src/python/msa/validation/experiments/execution/report_v2.py"
    )
    dirty.write_bytes(dirty.read_bytes() + b"\n# check-existing mismatch\n")
    with pytest.raises(C008CBPreflightError, match="differs from committed"):
        check_existing_c008c_b_v2_evidence(root)


def test_writer_source_mismatch_fails_before_formal_runner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.evidence_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    dirty = (
        root
        / "src/python/msa/validation/experiments/execution/report_v2.py"
    )
    dirty.write_bytes(dirty.read_bytes() + b"\n# writer preflight mismatch\n")
    calls = 0

    def formal_runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("formal runner must not be called")

    monkeypatch.setattr(
        module, "run_c008c_b_v2_dev_validation", formal_runner
    )
    with pytest.raises(C008CBPreflightError, match="differs from committed"):
        write_c008c_b_v2_evidence(root)
    assert calls == 0
    assert not (root / B_V2_EXECUTION_CONTRACT_PATH).exists()
    assert not (root / B_V2_REPORT_PATH).exists()


def test_writer_rejects_historical_path_and_missing_v2_never_falls_back(
    tmp_path: Path,
    b_v2_architecture_bundle,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.evidence_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    with pytest.raises(C008CBEvidenceError, match="missing or invalid"):
        check_existing_c008c_b_v2_evidence(root)

    monkeypatch.setattr(
        module,
        "B_V2_EXECUTION_CONTRACT_PATH",
        Path("docs/validation/evidence/c008c_b_execution_manifest.json"),
    )
    monkeypatch.setattr(
        module,
        "run_c008c_b_v2_dev_validation",
        lambda _root: b_v2_architecture_bundle["v2_report"],
    )
    monkeypatch.setattr(
        module,
        "validate_c008c_b_v2_report",
        lambda report, *_args: report,
    )
    with pytest.raises(C008CBEvidenceError, match="append-only"):
        write_c008c_b_v2_evidence(root)


def test_check_existing_fails_closed_when_execution_contract_is_missing(
    tmp_path: Path,
    b_v2_architecture_bundle,
    monkeypatch,
) -> None:
    import msa.validation.experiments.execution.evidence_v2 as module

    root = tmp_path / "authority-root"
    _copy_authority_root(root)
    monkeypatch.setattr(
        module,
        "run_c008c_b_v2_dev_validation",
        lambda _root: b_v2_architecture_bundle["v2_report"],
    )
    monkeypatch.setattr(
        module,
        "validate_c008c_b_v2_report",
        lambda report, *_args: report,
    )
    write_c008c_b_v2_evidence(root)
    (root / B_V2_EXECUTION_CONTRACT_PATH).unlink()
    with pytest.raises(C008CBEvidenceError, match="execution contract"):
        check_existing_c008c_b_v2_evidence(root)


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (["--check-existing"], ("check-existing", False)),
        (["--check"], ("write", True)),
        ([], ("write", False)),
    ),
)
def test_cli_routes_modes_without_formal_execution(
    tmp_path: Path,
    monkeypatch,
    argv,
    expected,
) -> None:
    path = ROOT / "tools/validation/generate_c008c_b_v2_results.py"
    spec = importlib.util.spec_from_file_location("c008c_b_v2_cli_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence_paths = (tmp_path / "contract.json", tmp_path / "report.json")
    calls = []

    def check_existing(_root):
        calls.append(("check-existing", False))
        return evidence_paths

    def write(_root, *, check=False):
        calls.append(("write", check))
        return evidence_paths

    monkeypatch.setattr(module, "check_existing_c008c_b_v2_evidence", check_existing)
    monkeypatch.setattr(module, "write_c008c_b_v2_evidence", write)
    monkeypatch.setattr(module, "b_v2_evidence_sha256", lambda _path: "sha")
    assert module.main(argv) == 0
    assert calls == [expected]
