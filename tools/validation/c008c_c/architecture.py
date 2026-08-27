"""First-and-only C-008C-C locked synthetic OOS execution architecture.

This module is additive.  It consumes the frozen C-008C-A authority and the
committed C-008C-B-v2 outcome without changing either source set or Evidence.
The formal outcome command has no retry mode and writes its attempt marker
before the first seed-3 Core executor is entered.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter
from typing import Any, Mapping

from msa.research.msa_core import MSACorePipeline, MSACoreRun, replay_msa_core_run
from msa.research.msa_core.errors import MSACoreError
from msa.validation.causal_audit import CausalAuditor
from msa.validation.contracts import CausalAuditReport
from msa.validation.errors import MSAValidationError
from msa.validation.experiments.contracts import DatasetPartition
from msa.validation.experiments.execution.contracts import (
    ExperimentCaseStatus,
    ExperimentFailureStage,
    ExperimentFixedCutoffComparison,
    ExperimentMetricDeltaSummary,
    ExperimentReplayComparison,
    FixedCutoffStatus,
    ReplayComparisonStatus,
)
from msa.validation.experiments.execution.contracts_v2 import (
    C008CBV2ExecutionContract,
    C008CBV2RunReport,
    DeterminismEvidenceKind,
    ExperimentDeterminismComparisonV2,
)
from msa.validation.experiments.execution.cutoff import (
    _checkpoint as _cutoff_checkpoint,
)
from msa.validation.experiments.execution.cutoff import (
    _comparison as _cutoff_comparison,
)
from msa.validation.experiments.execution.cutoff import (
    _metric_cutoff_projection,
    _truncate_source,
)
from msa.validation.experiments.execution.deltas import (
    _delta as _metric_delta,
)
from msa.validation.experiments.execution.deltas import (
    _summary as _metric_delta_summary,
)
from msa.validation.experiments.execution.evidence_v2 import (
    check_existing_c008c_b_v2_evidence,
)
from msa.validation.experiments.execution.manifest import (
    build_c008c_b_execution_manifest,
    load_c008c_b_authority,
)
from msa.validation.experiments.execution.replay import (
    _comparison as _replay_comparison,
)
from msa.validation.experiments.execution.runner import (
    _determinism_v2,
    _snapshot,
)
from msa.validation.experiments.identity import (
    canonical_json_bytes,
    digest,
    semantic_id,
)
from msa.validation.metrics import (
    MetricEvaluationReport,
    StructuralMetricAggregate,
    StructuralMetricError,
    StructuralMetricEvaluator,
    default_metric_formula_registry,
    validate_metric_evaluation_report,
)

from .contracts import (
    C008CCCaseResult,
    C008CCPartition,
)


SCHEMA_VERSION = 1
EXECUTION_SEMANTICS = "C-008C-C-POST-FIX-LOCKED-SYNTHETIC-OOS-V1"
BASE_MAIN_SHA = "6e031bd4f73364df1ff60743e3f011f78c45df63"
LEGACY_CONTRACT_PATH = Path(
    "docs/validation/evidence/c008c_c_locked_oos_execution_contract.json"
)
LEGACY_ATTEMPT_PATH = Path(
    "docs/validation/evidence/c008c_c_locked_oos_attempt.json"
)
CONTRACT_PATH = Path(
    "docs/validation/evidence/"
    "c008c_c_post_fix_locked_oos_execution_contract.json"
)
ATTEMPT_PATH = Path(
    "docs/validation/evidence/c008c_c_post_fix_locked_oos_attempt.json"
)
REPORT_PATH = Path(
    "docs/validation/evidence/c008c_c_locked_oos_report.json"
)
B_V2_CONTRACT_PATH = Path(
    "docs/validation/evidence/c008c_b_v2_execution_contract.json"
)
B_V2_REPORT_PATH = Path(
    "docs/validation/evidence/c008c_b_v2_dev_validation_report.json"
)
B_V2_SOURCE_PATH = Path(
    "docs/validation/evidence/c008c_b_v2_execution_source_manifest.json"
)
FORMAL_COMMAND = "python -B tools/validation/generate_c008c_c_results.py"
_C_SOURCE_PATHS = (
    Path("tools/validation/c008c_c/__init__.py"),
    Path("tools/validation/c008c_c/architecture.py"),
    Path("tools/validation/c008c_c/contracts.py"),
    Path("tools/validation/generate_c008c_c_results.py"),
)
_C_EVIDENCE_PATHS = frozenset((CONTRACT_PATH, ATTEMPT_PATH, REPORT_PATH))
_FORMAL_MAX_WORKERS = 12
_GIT_TIMEOUT_SECONDS = 10


class C008CCError(RuntimeError):
    """Fail-closed C-008C-C architecture or Evidence error."""


@dataclass(frozen=True, slots=True)
class _CExecutionArtifacts:
    result: C008CCCaseResult
    run: MSACoreRun | None
    audit: CausalAuditReport | None
    metric_report: MetricEvaluationReport | None


def _root(root: Path | None) -> Path:
    base = Path.cwd() if root is None else Path(root)
    try:
        resolved = base.resolve(strict=True)
    except OSError as exc:
        raise C008CCError("repository root cannot be resolved") from exc
    if not (resolved / "pyproject.toml").is_file():
        raise C008CCError("repository root is not an MSA checkout")
    return resolved


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise C008CCError(f"cannot hash authority path: {path}") from exc


def _canonical_payload(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C008CCError(f"{label} is missing or invalid") from exc
    if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
        raise C008CCError(f"{label} is not canonical JSON")
    return raw, payload


def _git_stdout(base: Path, arguments: tuple[str, ...], label: str) -> bytes:
    environment = os.environ.copy()
    for name in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        environment.pop(name, None)
    try:
        completed = subprocess.run(
            ("git", "-C", str(base), *arguments),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise C008CCError(f"Git {label} failed") from exc
    if completed.returncode != 0:
        raise C008CCError(f"Git {label} failed")
    return completed.stdout


def _head_blob(base: Path, relative_path: Path) -> bytes:
    return _git_stdout(
        base,
        ("cat-file", "blob", f"HEAD:{relative_path.as_posix()}"),
        f"HEAD blob read for {relative_path.as_posix()}",
    )


def _require_clean_worktree(base: Path) -> None:
    if _git_stdout(base, ("status", "--porcelain=v1"), "status").strip():
        raise C008CCError("formal C-008C-C execution requires a clean worktree")


def _history_locks(base: Path) -> list[dict[str, object]]:
    evidence_root = base / "docs/validation/evidence"
    try:
        paths = tuple(
            sorted(
                (
                    path
                    for path in evidence_root.glob("*.json")
                    if path.relative_to(base) not in _C_EVIDENCE_PATHS
                ),
                key=lambda path: path.relative_to(base).as_posix(),
            )
        )
    except OSError as exc:
        raise C008CCError("historical Evidence scope cannot be enumerated") from exc
    if not paths:
        raise C008CCError("historical Evidence scope is empty")
    return [
        {
            "relative_path": path.relative_to(base).as_posix(),
            "sha256": _sha256(path),
        }
        for path in paths
    ]


def _c_source_locks(base: Path) -> list[dict[str, object]]:
    locks: list[dict[str, object]] = []
    for relative in _C_SOURCE_PATHS:
        path = base / relative
        if not path.is_file() or path.is_symlink():
            raise C008CCError(
                f"formal C source is missing or irregular: {relative.as_posix()}"
            )
        locks.append(
            {"relative_path": relative.as_posix(), "sha256": _sha256(path)}
        )
    return locks


def _load_b_v2_prerequisite(
    base: Path,
) -> tuple[C008CBV2ExecutionContract, C008CBV2RunReport]:
    check_existing_c008c_b_v2_evidence(base)
    _, contract_payload = _canonical_payload(
        base / B_V2_CONTRACT_PATH, "B-v2 execution contract"
    )
    _, report_payload = _canonical_payload(
        base / B_V2_REPORT_PATH, "B-v2 execution report"
    )
    try:
        contract = C008CBV2ExecutionContract.from_dict(contract_payload)
        report = C008CBV2RunReport.from_dict(report_payload)
    except (TypeError, ValueError) as exc:
        raise C008CCError("B-v2 prerequisite contract is invalid") from exc
    if (
        report.stage_status.value != "READY_FOR_LOCKED_OOS"
        or report.execution_contract_id != contract.execution_contract_id
        or report.executed_pair_count != 390
        or report.deferred_oos_pair_count != 130
        or report.oos_executed
    ):
        raise C008CCError("B-v2 prerequisite is not READY_FOR_LOCKED_OOS")
    return contract, report


def _contract_without_id(base: Path) -> dict[str, object]:
    b_contract, b_report = _load_b_v2_prerequisite(base)
    manifest = build_c008c_b_execution_manifest(base)
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    case_index = {item.dataset_case_id: item for item in dataset.cases}
    oos_pairs = manifest.deferred_oos_pairs
    oos_case_ids = manifest.deferred_oos_case_ids
    scenarios = [case_index[item].scenario_kind.value for item in oos_case_ids]
    if (
        len(oos_pairs) != 130
        or len(oos_case_ids) != 5
        or len(manifest.variant_ids) != 26
        or any(
            pair.seed != 3
            or pair.partition is not DatasetPartition.OOS
            or not pair.deferred_to_c008c_c
            for pair in oos_pairs
        )
        or any(
            case_index[item].seed != 3
            or case_index[item].partition is not DatasetPartition.OOS
            for item in oos_case_ids
        )
    ):
        raise C008CCError("frozen OOS schedule is not 5 x 26 seed-3 pairs")
    return {
        "execution_semantics": EXECUTION_SEMANTICS,
        "base_main_sha": BASE_MAIN_SHA,
        "formal_command": FORMAL_COMMAND,
        "report_relative_path": REPORT_PATH.as_posix(),
        "attempt_relative_path": ATTEMPT_PATH.as_posix(),
        "b_v2_execution_contract_id": b_contract.execution_contract_id,
        "b_v2_run_report_id": b_report.run_report_id,
        "b_v2_execution_source_manifest_id": (
            b_report.execution_source_manifest_id
        ),
        "b_v2_stage_status": b_report.stage_status.value,
        "historical_execution_manifest_id": manifest.execution_manifest_id,
        "dataset_manifest_id": manifest.dataset_manifest_id,
        "experiment_plan_id": manifest.experiment_plan_id,
        "reviewed_protected_source_manifest_id": (
            b_report.reviewed_protected_source_manifest_id
        ),
        "partition": DatasetPartition.OOS.value,
        "seed": 3,
        "scenario_count": 5,
        "scenarios": scenarios,
        "oos_case_ids": list(oos_case_ids),
        "variant_count": 26,
        "variant_ids": list(manifest.variant_ids),
        "oos_pair_count": 130,
        "oos_pair_ids": [item.execution_pair_id for item in oos_pairs],
        "baseline_variant_id": plan.variants[0].variant_id,
        "baseline_replay_count": 5,
        "baseline_replay_sample_ids": list(
            manifest.deferred_baseline_replay_sample_ids
        ),
        "fixed_cutoff_count": 5,
        "fixed_cutoff_case_ids": list(
            manifest.deferred_fixed_cutoff_case_ids
        ),
        "metric_coverage_subject": "BASELINE_OOS_UNIQUE_SAMPLES",
        "comparison_semantics": "C-008C-B-v2 comparators reused unchanged",
        "formal_execution_limit": 1,
        "retry_allowed": False,
        "outcome_driven_selection_allowed": False,
        "real_market_oos_status": "NOT_RUN_NOT_EVIDENCED",
        "c_source_locks": _c_source_locks(base),
        "historical_evidence_locks": _history_locks(base),
        "schema_version": SCHEMA_VERSION,
    }


def build_c008c_c_execution_contract(
    root: Path | None = None,
) -> dict[str, object]:
    base = _root(root)
    payload = _contract_without_id(base)
    return {
        "execution_contract_id": semantic_id(
            "c008c-c-post-fix-locked-oos-execution-contract-v1-", payload
        ),
        **payload,
    }


def _write_or_refuse_different(path: Path, raw: bytes) -> None:
    try:
        if path.exists():
            if path.read_bytes() != raw:
                raise C008CCError(
                    f"refusing to overwrite different Evidence: {path}"
                )
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except C008CCError:
        raise
    except OSError as exc:
        raise C008CCError(f"cannot create append-only Evidence: {path}") from exc


def prepare_c008c_c_execution_contract(
    root: Path | None = None,
) -> Path:
    base = _root(root)
    if (base / ATTEMPT_PATH).exists() or (base / REPORT_PATH).exists():
        raise C008CCError("outcome Evidence already exists")
    contract = build_c008c_c_execution_contract(base)
    path = base / CONTRACT_PATH
    _write_or_refuse_different(path, canonical_json_bytes(contract))
    return path


def load_committed_c008c_c_execution_contract(
    root: Path | None = None,
) -> dict[str, object]:
    base = _root(root)
    path = base / CONTRACT_PATH
    raw, payload = _canonical_payload(path, "C execution contract")
    if raw != _head_blob(base, CONTRACT_PATH):
        raise C008CCError("C execution contract differs from Git HEAD")
    expected = build_c008c_c_execution_contract(base)
    if payload != expected:
        raise C008CCError("C execution contract or locked source bytes differ")
    return payload


def validate_c008c_c_preflight(
    root: Path | None = None,
    *,
    require_clean: bool = True,
) -> dict[str, object]:
    base = _root(root)
    if require_clean:
        _require_clean_worktree(base)
    contract = load_committed_c008c_c_execution_contract(base)
    if (base / ATTEMPT_PATH).exists() or (base / REPORT_PATH).exists():
        raise C008CCError(
            "formal OOS attempt or report already exists; retry is forbidden"
        )
    return contract


def _c_case_result(
    pair: object,
    variant: object,
    *,
    status: ExperimentCaseStatus,
    run: MSACoreRun | None,
    audit: CausalAuditReport | None,
    metric_report: MetricEvaluationReport | None,
    failure_stage: ExperimentFailureStage | None,
    failure_error_type: str | None,
) -> C008CCCaseResult:
    """Build one C-owned locked-OOS outcome without entering a B CaseResult."""

    if pair.seed != 3 or pair.partition is not DatasetPartition.OOS:
        raise C008CCError("C CaseResult source must be frozen seed-3 OOS")
    aggregate_snapshots = (
        ()
        if metric_report is None
        or status is ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED
        else tuple(_snapshot(item) for item in metric_report.aggregates)
    )
    run_payload = None if run is None else run.to_dict()
    audit_payload = None if audit is None else audit.to_dict()
    metric_payload = None if metric_report is None else metric_report.to_dict()
    return C008CCCaseResult.create(
        execution_pair_id=pair.execution_pair_id,
        dataset_case_id=pair.dataset_case_id,
        variant_id=pair.variant_id,
        experiment_kind=variant.experiment_kind,
        level=variant.level,
        partition=C008CCPartition.LOCKED_OOS,
        scenario=pair.scenario,
        seed=3,
        execution_status=status,
        source_input_payload_digest=pair.source_input_payload_digest,
        core_config_payload_digest=pair.core_config_payload_digest,
        metric_config_payload_digest=pair.metric_config_payload_digest,
        run_id=None if run is None else run.run_id,
        run_payload_digest=None if run_payload is None else digest(run_payload),
        audit_report_id=None if audit is None else audit.audit_report_id,
        audit_payload_digest=(
            None if audit_payload is None else digest(audit_payload)
        ),
        audit_passed=None if audit is None else audit.passed,
        metric_report_id=(
            None if metric_report is None else metric_report.metric_report_id
        ),
        metric_report_payload_digest=(
            None if metric_payload is None else digest(metric_payload)
        ),
        aggregates=aggregate_snapshots,
        event_count=0 if metric_report is None else metric_report.event_count,
        box_episode_count=(
            0 if run is None else run.report.created_event_count
        ),
        matured_count=(
            0
            if metric_report is None
            else metric_report.matured_observation_count
        ),
        censored_count=(
            0
            if metric_report is None
            else metric_report.censored_observation_count
        ),
        unavailable_count=(
            0
            if metric_report is None
            else metric_report.unavailable_observation_count
        ),
        failure_stage=failure_stage,
        failure_error_type=failure_error_type,
        schema_version=1,
    )


def _execute_oos_pair(
    pair: object,
    case: object,
    variant: object,
) -> _CExecutionArtifacts:
    if (
        pair.dataset_case_id != case.dataset_case_id
        or pair.variant_id != variant.variant_id
        or pair.seed != 3
        or pair.partition is not DatasetPartition.OOS
        or not pair.deferred_to_c008c_c
        or case.seed != 3
        or case.partition is not DatasetPartition.OOS
    ):
        raise C008CCError("C primary pair is not frozen seed-3 OOS authority")
    try:
        run = MSACorePipeline(variant.core_config_snapshot).run(case.source_input)
    except MSACoreError as exc:
        return _CExecutionArtifacts(
            _c_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.PIPELINE_FAILED,
                run=None,
                audit=None,
                metric_report=None,
                failure_stage=ExperimentFailureStage.PIPELINE,
                failure_error_type=type(exc).__name__,
            ),
            None,
            None,
            None,
        )
    try:
        audit = CausalAuditor().audit_run(run)
    except MSAValidationError as exc:
        return _CExecutionArtifacts(
            _c_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.CAUSAL_AUDIT_FAILED,
                run=run,
                audit=None,
                metric_report=None,
                failure_stage=ExperimentFailureStage.CAUSAL_AUDIT,
                failure_error_type=type(exc).__name__,
            ),
            run,
            None,
            None,
        )
    if not audit.passed:
        return _CExecutionArtifacts(
            _c_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.CAUSAL_AUDIT_FAILED,
                run=run,
                audit=audit,
                metric_report=None,
                failure_stage=ExperimentFailureStage.CAUSAL_AUDIT,
                failure_error_type="C008CBCausalAuditFailure",
            ),
            run,
            audit,
            None,
        )
    try:
        metric = StructuralMetricEvaluator(
            variant.metric_config_snapshot
        ).evaluate(run)
    except StructuralMetricError as exc:
        return _CExecutionArtifacts(
            _c_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.METRIC_EVALUATION_FAILED,
                run=run,
                audit=audit,
                metric_report=None,
                failure_stage=ExperimentFailureStage.METRIC_EVALUATION,
                failure_error_type=type(exc).__name__,
            ),
            run,
            audit,
            None,
        )
    try:
        validate_metric_evaluation_report(run, metric)
    except StructuralMetricError as exc:
        return _CExecutionArtifacts(
            _c_case_result(
                pair,
                variant,
                status=ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED,
                run=run,
                audit=audit,
                metric_report=metric,
                failure_stage=ExperimentFailureStage.METRIC_SOURCE_BIND,
                failure_error_type=type(exc).__name__,
            ),
            run,
            audit,
            metric,
        )
    return _CExecutionArtifacts(
        _c_case_result(
            pair,
            variant,
            status=ExperimentCaseStatus.PASSED,
            run=run,
            audit=audit,
            metric_report=metric,
            failure_stage=None,
            failure_error_type=None,
        ),
        run,
        audit,
        metric,
    )


def _execute_oos_triplet(item: tuple[object, object, object]) -> tuple[object, ...]:
    pair, case, variant = item
    with localcontext() as normal_a_context:
        normal_a_context.prec = 28
        normal_a_context.rounding = ROUND_HALF_EVEN
        normal_a = _execute_oos_pair(pair, case, variant)
    with localcontext() as normal_b_context:
        normal_b_context.prec = 28
        normal_b_context.rounding = ROUND_HALF_EVEN
        normal_b = _execute_oos_pair(pair, case, variant)
    with localcontext() as altered_context:
        altered_context.prec = 7
        altered_context.rounding = ROUND_FLOOR
        altered = _execute_oos_pair(pair, case, variant)
    same = _determinism_v2(
        pair,
        normal_a,
        normal_b,
        DeterminismEvidenceKind.SAME_CONTEXT_REPEAT,
    )
    decimal = _determinism_v2(
        pair,
        normal_a,
        altered,
        DeterminismEvidenceKind.DECIMAL_CONTEXT_PERTURBATION,
    )
    coverage_source = None
    if variant.level.value == "BASELINE" and normal_a.metric_report is not None:
        coverage_source = {
            "case_result_id": normal_a.result.case_result_id,
            "dataset_case_id": normal_a.result.dataset_case_id,
            "metric_report_id": normal_a.metric_report.metric_report_id,
            "aggregates": [
                aggregate.to_dict()
                for aggregate in normal_a.metric_report.aggregates
            ],
        }
    return normal_a.result, same, decimal, coverage_source


def _execute_oos_replay(item: tuple[str, object, object]) -> object:
    sample_id, case, baseline = item
    if case.seed != 3 or case.partition is not DatasetPartition.OOS:
        raise C008CCError("C replay schedule is not seed-3 OOS")
    batch_run = None
    replay_run = None
    audit = None
    batch_metric = None
    replay_metric = None
    try:
        pipeline = MSACorePipeline(baseline.core_config_snapshot)
        batch_run = pipeline.run(case.source_input)
        replay_run = replay_msa_core_run(pipeline, case.source_input)
        audit = CausalAuditor().compare_batch_replay(batch_run, replay_run)
        evaluator = StructuralMetricEvaluator(
            baseline.metric_config_snapshot
        )
        batch_metric = evaluator.evaluate(batch_run)
        validate_metric_evaluation_report(batch_run, batch_metric)
        replay_metric = evaluator.evaluate(replay_run)
        validate_metric_evaluation_report(replay_run, replay_metric)
    except (MSACoreError, MSAValidationError, StructuralMetricError) as exc:
        return _replay_comparison(
            replay_sample_id=sample_id,
            scope="BASELINE",
            case=case,
            variant=baseline,
            status=ReplayComparisonStatus.EXECUTION_FAILED,
            batch_run=batch_run,
            replay_run=replay_run,
            comparison_audit=audit,
            batch_metric=batch_metric,
            replay_metric=replay_metric,
            run_equal=False,
            metric_equal=False,
            failure_error_type=type(exc).__name__,
        )
    run_equal = batch_run.to_dict() == replay_run.to_dict()
    metric_equal = batch_metric.to_dict() == replay_metric.to_dict()
    return _replay_comparison(
        replay_sample_id=sample_id,
        scope="BASELINE",
        case=case,
        variant=baseline,
        status=(
            ReplayComparisonStatus.MATCH
            if audit.passed and run_equal and metric_equal
            else ReplayComparisonStatus.MISMATCH
        ),
        batch_run=batch_run,
        replay_run=replay_run,
        comparison_audit=audit,
        batch_metric=batch_metric,
        replay_metric=replay_metric,
        run_equal=run_equal,
        metric_equal=metric_equal,
        failure_error_type=None,
    )


def _execute_oos_cutoff(item: tuple[object, object]) -> object:
    case, baseline = item
    if case.seed != 3 or case.partition is not DatasetPartition.OOS:
        raise C008CCError("C fixed-cutoff schedule is not seed-3 OOS")
    checkpoints = []
    try:
        pipeline = MSACorePipeline(baseline.core_config_snapshot)
        extended_run = pipeline.run(case.source_input)
        auditor = CausalAuditor()
        evaluator = StructuralMetricEvaluator(
            baseline.metric_config_snapshot
        )
        for index, cutoff in enumerate(extended_run.processing_times):
            prefix_run = pipeline.run(_truncate_source(case.source_input, cutoff))
            shared = auditor.compare_shared_asof(
                prefix_run,
                extended_run,
                cutoff + timedelta(microseconds=1),
            )
            prefix_stable = (
                True
                if index + 1 == len(extended_run.processing_times)
                else auditor.compare_prefix(prefix_run, extended_run).passed
            )
            prefix_metric = evaluator.evaluate(prefix_run)
            validate_metric_evaluation_report(prefix_run, prefix_metric)
            extended_metric = evaluator.evaluate(extended_run, cutoff)
            validate_metric_evaluation_report(extended_run, extended_metric)
            metric_stable = (
                _metric_cutoff_projection(prefix_metric)
                == _metric_cutoff_projection(extended_metric)
            )
            checkpoints.append(
                _cutoff_checkpoint(
                    cutoff=cutoff,
                    prefix_run=prefix_run,
                    extended_run=extended_run,
                    comparison_audit=shared,
                    prefix_metric=prefix_metric,
                    extended_metric=extended_metric,
                    stable=shared.passed and prefix_stable and metric_stable,
                )
            )
    except (MSACoreError, MSAValidationError, StructuralMetricError, ValueError) as exc:
        return _cutoff_comparison(
            case=case,
            baseline_variant_id=baseline.variant_id,
            status=FixedCutoffStatus.EXECUTION_FAILED,
            checkpoints=tuple(checkpoints),
            failure_error_type=type(exc).__name__,
        )
    frozen = tuple(checkpoints)
    return _cutoff_comparison(
        case=case,
        baseline_variant_id=baseline.variant_id,
        status=(
            FixedCutoffStatus.STABLE
            if all(item.stable for item in frozen)
            else FixedCutoffStatus.REWRITE_DETECTED
        ),
        checkpoints=frozen,
        failure_error_type=None,
    )


def _run_primary(
    base: Path,
    manifest: object,
) -> tuple[
    tuple[C008CCCaseResult, ...],
    tuple[ExperimentDeterminismComparisonV2, ...],
    tuple[ExperimentDeterminismComparisonV2, ...],
    list[dict[str, object]],
]:
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    variants = {item.variant_id: item for item in plan.variants}
    scheduled = tuple(
        (pair, cases[pair.dataset_case_id], variants[pair.variant_id])
        for pair in manifest.deferred_oos_pairs
    )
    if len(scheduled) != 130:
        raise C008CCError("C primary schedule must contain exactly 130 pairs")
    results: list[C008CCCaseResult] = []
    same: list[ExperimentDeterminismComparisonV2] = []
    decimal: list[ExperimentDeterminismComparisonV2] = []
    coverage_sources: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, values in enumerate(
            executor.map(_execute_oos_triplet, scheduled), start=1
        ):
            result, same_item, decimal_item, coverage = values
            results.append(result)
            same.append(same_item)
            decimal.append(decimal_item)
            if coverage is not None:
                coverage_sources.append(coverage)
            if index % 10 == 0 or index == len(scheduled):
                print(
                    f"C-008C-C primary progress {index}/{len(scheduled)}",
                    flush=True,
                )
    expected_ids = tuple(
        item.execution_pair_id for item in manifest.deferred_oos_pairs
    )
    if (
        tuple(item.execution_pair_id for item in results) != expected_ids
        or tuple(item.execution_pair_id for item in same) != expected_ids
        or tuple(item.execution_pair_id for item in decimal) != expected_ids
        or len(coverage_sources) != 5
    ):
        raise C008CCError("C primary execution omitted or reordered authority")
    return tuple(results), tuple(same), tuple(decimal), coverage_sources


def _run_replay(base: Path, manifest: object) -> tuple[object, ...]:
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    baseline = plan.variants[0]
    scheduled = tuple(
        (sample_id, cases[case_id], baseline)
        for sample_id, case_id in zip(
            manifest.deferred_baseline_replay_sample_ids,
            manifest.deferred_oos_case_ids,
            strict=True,
        )
    )
    results: list[object] = []
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, result in enumerate(
            executor.map(_execute_oos_replay, scheduled), start=1
        ):
            results.append(result)
            print(f"C-008C-C replay progress {index}/5", flush=True)
    if len(results) != 5:
        raise C008CCError("C replay execution must produce five results")
    return tuple(results)


def _run_cutoff(base: Path, manifest: object) -> tuple[object, ...]:
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    cases = {item.dataset_case_id: item for item in dataset.cases}
    baseline = plan.variants[0]
    scheduled = tuple(
        (cases[case_id], baseline)
        for case_id in manifest.deferred_fixed_cutoff_case_ids
    )
    results: list[object] = []
    with ProcessPoolExecutor(max_workers=_FORMAL_MAX_WORKERS) as executor:
        for index, result in enumerate(
            executor.map(_execute_oos_cutoff, scheduled), start=1
        ):
            results.append(result)
            print(f"C-008C-C fixed-cutoff progress {index}/5", flush=True)
    if len(results) != 5:
        raise C008CCError("C fixed-cutoff must produce five results")
    return tuple(results)


def _oos_metric_deltas(
    base: Path,
    case_results: tuple[C008CCCaseResult, ...],
) -> tuple[ExperimentMetricDeltaSummary, ...]:
    _, dataset, _, plan, _ = load_c008c_b_authority(base)
    oos_case_ids = tuple(
        item.dataset_case_id
        for item in dataset.cases
        if item.partition is DatasetPartition.OOS
    )
    baseline_id = plan.variants[0].variant_id
    index = {
        (item.dataset_case_id, item.variant_id): item
        for item in case_results
    }
    if len(index) != 130:
        raise C008CCError("OOS metric deltas require 130 unique CaseResults")
    formulas = default_metric_formula_registry()
    summaries: list[ExperimentMetricDeltaSummary] = []
    for variant in plan.variants[1:]:
        deltas = tuple(
            _metric_delta(
                index[(case_id, baseline_id)],
                index[(case_id, variant.variant_id)],
                formula.metric_name,
                formula.metric_formula_id,
            )
            for case_id in oos_case_ids
            for formula in formulas
        )
        summaries.append(
            _metric_delta_summary(
                DatasetPartition.OOS,
                variant.variant_id,
                baseline_id,
                deltas,
            )
        )
    result = tuple(summaries)
    if len(result) != 25 or sum(len(item.metric_deltas) for item in result) != 1250:
        raise C008CCError("OOS metric delta schedule must be exactly 1,250")
    return result


def _coverage_summaries(
    base: Path,
    case_results: tuple[C008CCCaseResult, ...],
    sources: list[dict[str, object]],
) -> list[dict[str, object]]:
    _, _, gates, plan, _ = load_c008c_b_authority(base)
    policy = next(
        item.policy for item in gates if item.code == "OOS_SAMPLE_COVERAGE"
    )
    baseline_id = plan.variants[0].variant_id
    baseline_results = tuple(
        item for item in case_results if item.variant_id == baseline_id
    )
    if len(baseline_results) != 5 or len(sources) != 5:
        raise C008CCError("coverage requires five Baseline OOS reports")
    result_index = {item.case_result_id: item for item in baseline_results}
    aggregate_index: dict[str, list[StructuralMetricAggregate]] = {}
    source_case_ids: list[str] = []
    for source in sources:
        if set(source) != {
            "case_result_id",
            "dataset_case_id",
            "metric_report_id",
            "aggregates",
        }:
            raise C008CCError("coverage source report fields are invalid")
        case_result = result_index.get(str(source["case_result_id"]))
        if (
            case_result is None
            or case_result.dataset_case_id != source["dataset_case_id"]
            or case_result.metric_report_id != source["metric_report_id"]
        ):
            raise C008CCError("coverage source does not bind its CaseResult")
        aggregates = [
            StructuralMetricAggregate.from_dict(item)
            for item in source["aggregates"]  # type: ignore[index]
        ]
        if len(aggregates) != 10:
            raise C008CCError("coverage source must retain ten aggregates")
        source_case_ids.append(case_result.case_result_id)
        for aggregate in aggregates:
            aggregate_index.setdefault(aggregate.metric_name.value, []).append(
                aggregate
            )
    summaries: list[dict[str, object]] = []
    for rule in policy.sample_coverage_rules:
        aggregates = aggregate_index.get(rule.metric_code, [])
        observation_ids = tuple(
            observation_id
            for aggregate in aggregates
            for observation_id in aggregate.source_observation_ids
        )
        duplicate_count = len(observation_ids) - len(set(observation_ids))
        if rule.denominator_kind == "BOX_EPISODES":
            observed = sum(item.box_episode_count for item in baseline_results)
            evidence_ids = tuple(item.case_result_id for item in baseline_results)
            stored_observation_ids: tuple[str, ...] = ()
            censored = 0
            unavailable = 0
        else:
            observed = sum(item.matured_count for item in aggregates)
            evidence_ids = tuple(
                item.metric_aggregate_id for item in aggregates
            )
            stored_observation_ids = observation_ids
            censored = sum(item.censored_count for item in aggregates)
            unavailable = sum(item.unavailable_count for item in aggregates)
        kwargs = {
            "metric_code": rule.metric_code,
            "denominator_kind": rule.denominator_kind,
            "minimum_count": rule.minimum_count,
            "observed_count": observed,
            "passed": observed >= rule.minimum_count and duplicate_count == 0,
            "duplicate_observation_count": duplicate_count,
            "censored_count": censored,
            "unavailable_count": unavailable,
            "evidence_ids": list(evidence_ids),
            "source_observation_ids": list(stored_observation_ids),
            "schema_version": SCHEMA_VERSION,
        }
        summaries.append(
            {
                "coverage_result_id": semantic_id(
                    "c008c-c-oos-metric-coverage-v1-", kwargs
                ),
                **kwargs,
            }
        )
    if len(summaries) != 10:
        raise C008CCError("all ten OOS coverage rules are required")
    return summaries


def _finding(
    *,
    variant_id: str,
    rule_code: str,
    evidence_scope: str,
    evidence_ids: tuple[str, ...],
    triggered: bool,
    insufficient: bool,
    facts: tuple[str, ...],
) -> dict[str, object]:
    status = (
        "DEGENERATED"
        if triggered
        else "INSUFFICIENT_EVIDENCE"
        if insufficient
        else "NOT_DEGENERATED"
    )
    kwargs = {
        "variant_id": variant_id,
        "rule_code": rule_code,
        "evidence_scope": evidence_scope,
        "evidence_ids": list(evidence_ids),
        "triggered": triggered,
        "insufficient": insufficient,
        "status": status,
        "facts": list(facts),
        "schema_version": SCHEMA_VERSION,
    }
    return {
        "degeneration_finding_id": semantic_id(
            "c008c-c-degeneration-finding-v1-", kwargs
        ),
        **kwargs,
    }


def _degeneration_summaries(
    base: Path,
    b_report: C008CBV2RunReport,
    case_results: tuple[C008CCCaseResult, ...],
    metric_deltas: tuple[ExperimentMetricDeltaSummary, ...],
    c_cutoff: tuple[ExperimentFixedCutoffComparison, ...],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    _, _, gates, plan, _ = load_c008c_b_authority(base)
    rule_codes = tuple(
        item.rule_code
        for item in next(
            gate for gate in gates if gate.code == "NO_NEIGHBORHOOD_DEGENERATION"
        ).policy.degeneration_rules
    )
    b_summaries = {item.variant_id: item for item in b_report.degeneration_summaries}
    deltas = {item.variant_id: item for item in metric_deltas}
    results = {
        variant.variant_id: tuple(
            item for item in case_results if item.variant_id == variant.variant_id
        )
        for variant in plan.variants[1:]
    }
    all_cutoff = (*b_report.fixed_cutoff_comparisons, *c_cutoff)
    cutoff_ids = tuple(item.fixed_cutoff_comparison_id for item in all_cutoff)
    cutoff_triggered = any(
        item.status is not FixedCutoffStatus.STABLE for item in all_cutoff
    )
    summaries: list[dict[str, object]] = []
    for variant in plan.variants[1:]:
        variant_results = results[variant.variant_id]
        if len(variant_results) != 5:
            raise C008CCError("each Variant requires five OOS CaseResults")
        b_summary = b_summaries[variant.variant_id]
        b_findings = {item.rule_code: item for item in b_summary.findings}
        result_ids = tuple(item.case_result_id for item in variant_results)
        pipeline_failures = sum(
            item.status is ExperimentCaseStatus.PIPELINE_FAILED
            for item in variant_results
        )
        audit_failures = sum(
            item.status is ExperimentCaseStatus.CAUSAL_AUDIT_FAILED
            for item in variant_results
        )
        metric_failures = sum(
            item.status
            in (
                ExperimentCaseStatus.METRIC_EVALUATION_FAILED,
                ExperimentCaseStatus.METRIC_SOURCE_BIND_FAILED,
            )
            for item in variant_results
        )
        findings: list[dict[str, object]] = []
        for code in rule_codes:
            if code == "PIPELINE_EXECUTION_FAILURE":
                finding = _finding(
                    variant_id=variant.variant_id,
                    rule_code=code,
                    evidence_scope="C_LOCKED_OOS",
                    evidence_ids=result_ids,
                    triggered=pipeline_failures > 0,
                    insufficient=False,
                    facts=(f"pipeline_failures={pipeline_failures}",),
                )
            elif code == "CAUSAL_AUDIT_FAILURE":
                finding = _finding(
                    variant_id=variant.variant_id,
                    rule_code=code,
                    evidence_scope="C_LOCKED_OOS",
                    evidence_ids=result_ids,
                    triggered=audit_failures > 0,
                    insufficient=False,
                    facts=(f"causal_audit_failures={audit_failures}",),
                )
            elif code == "METRIC_SOURCE_BIND_FAILURE":
                finding = _finding(
                    variant_id=variant.variant_id,
                    rule_code=code,
                    evidence_scope="C_LOCKED_OOS",
                    evidence_ids=result_ids,
                    triggered=metric_failures > 0,
                    insufficient=False,
                    facts=(f"metric_failures={metric_failures}",),
                )
            elif code == "FUTURE_PREFIX_REWRITE":
                finding = _finding(
                    variant_id=variant.variant_id,
                    rule_code=code,
                    evidence_scope="BASELINE_GLOBAL",
                    evidence_ids=cutoff_ids,
                    triggered=False,
                    insufficient=False,
                    facts=(
                        f"baseline_fixed_cutoff_cases={len(all_cutoff)}",
                        f"baseline_cutoff_non_stable={sum(item.status is not FixedCutoffStatus.STABLE for item in all_cutoff)}",
                        "variant_propagation=false",
                    ),
                )
            else:
                source = b_findings[code]
                finding = _finding(
                    variant_id=variant.variant_id,
                    rule_code=code,
                    evidence_scope="B_V2_VALIDATION_FROZEN",
                    evidence_ids=source.evidence_source_ids,
                    triggered=source.triggered,
                    insufficient=source.status.value == "INSUFFICIENT_EVIDENCE",
                    facts=source.facts,
                )
            findings.append(finding)
        triggered_codes = tuple(
            item["rule_code"] for item in findings if item["triggered"]
        )
        insufficient = any(item["insufficient"] for item in findings)
        sensitive = (
            b_summary.status.value == "SENSITIVE"
            or deltas[variant.variant_id].non_zero_count > 0
        )
        status = (
            "DEGENERATED"
            if triggered_codes
            else "INSUFFICIENT_EVIDENCE"
            if insufficient
            else "SENSITIVE"
            if sensitive
            else "NOT_DEGENERATED"
        )
        kwargs = {
            "variant_id": variant.variant_id,
            "status": status,
            "findings": findings,
            "triggered_rule_codes": list(triggered_codes),
            "oos_non_zero_metric_delta_count": deltas[
                variant.variant_id
            ].non_zero_count,
            "schema_version": SCHEMA_VERSION,
        }
        summaries.append(
            {
                "degeneration_summary_id": semantic_id(
                    "c008c-c-degeneration-summary-v1-", kwargs
                ),
                **kwargs,
            }
        )
    global_kwargs = {
        "rule_code": "FUTURE_PREFIX_REWRITE",
        "baseline_variant_id": plan.variants[0].variant_id,
        "evidence_ids": list(cutoff_ids),
        "triggered": cutoff_triggered,
        "status": "DEGENERATED" if cutoff_triggered else "NOT_DEGENERATED",
        "facts": [
            f"baseline_fixed_cutoff_cases={len(all_cutoff)}",
            f"baseline_cutoff_non_stable={sum(item.status is not FixedCutoffStatus.STABLE for item in all_cutoff)}",
            "variant_propagation=false",
        ],
        "schema_version": SCHEMA_VERSION,
    }
    global_evidence = {
        "global_evidence_id": semantic_id(
            "c008c-c-global-degeneration-evidence-v1-", global_kwargs
        ),
        **global_kwargs,
    }
    return summaries, global_evidence


_STATIC_PASS = frozenset(
    {
        "BASE_COMMIT_MATCH",
        "CORE_PROFILE_AUTHORIZED",
        "PROTECTED_SOURCE_UNCHANGED",
        "DATASET_MANIFEST_VALID",
        "DATASET_PARTITIONS_DISJOINT",
        "ALL_SCENARIOS_PRESENT",
        "PLAN_PREDECLARED",
        "PLAN_OUTCOME_INDEPENDENT",
        "MODEL_VARIANTS_OAT",
        "METRIC_VARIANTS_OAT",
        "ABLATION_PUBLIC_CONFIG_ONLY",
        "INCREMENT_ENDS_AT_BASELINE",
        "NO_PARAMETER_OPTIMIZATION",
        "NO_TRADING_FIELDS",
        "EVIDENCE_REPRODUCIBLE",
    }
)


def _gate_result(
    definition: object,
    *,
    passed: bool,
    evidence_kind: str,
    evidence_ids: tuple[str, ...],
    evidence_payload: object,
    rationale: str,
) -> dict[str, object]:
    kwargs = {
        "gate_definition_id": definition.gate_definition_id,
        "gate_code": definition.code,
        "status": "PASS" if passed else "FAIL",
        "evidence_kind": evidence_kind,
        "evidence_ids": list(evidence_ids),
        "evidence_payload_digest": digest(evidence_payload),
        "rationale": rationale,
        "schema_version": SCHEMA_VERSION,
    }
    return {
        "gate_result_id": semantic_id("c008c-c-gate-result-v1-", kwargs),
        **kwargs,
    }


def _gate_results(
    base: Path,
    contract: Mapping[str, object],
    b_report: C008CBV2RunReport,
    case_results: tuple[C008CCCaseResult, ...],
    same: tuple[ExperimentDeterminismComparisonV2, ...],
    decimal: tuple[ExperimentDeterminismComparisonV2, ...],
    coverage: list[dict[str, object]],
    replay: tuple[ExperimentReplayComparison, ...],
    cutoff: tuple[ExperimentFixedCutoffComparison, ...],
    degeneration: list[dict[str, object]],
    global_degeneration: dict[str, object],
) -> list[dict[str, object]]:
    _, _, gates, _, _ = load_c008c_b_authority(base)
    all_cases = (*b_report.case_results, *case_results)
    all_same = (*b_report.same_context_comparisons, *same)
    all_decimal = (*b_report.decimal_context_comparisons, *decimal)
    all_baseline_replay = tuple(
        item for item in b_report.replay_comparisons if item.scope == "BASELINE"
    ) + replay
    b_variant_replay = tuple(
        item for item in b_report.replay_comparisons if item.scope == "VARIANT"
    )
    all_cutoff = (*b_report.fixed_cutoff_comparisons, *cutoff)
    results: list[dict[str, object]] = []
    for gate in gates:
        code = gate.code
        if code in _STATIC_PASS:
            passed = True
            kind = "FROZEN_AUTHORITY"
            ids = (str(contract["execution_contract_id"]),)
            payload: object = contract
            rationale = "Frozen authority and outcome-independent policy validate"
        elif code == "ALL_CASES_MUST_EXECUTE":
            passed = len(all_cases) == 520
            kind = "CASE_RESULTS"
            ids = tuple(item.case_result_id for item in all_cases)
            payload = [item.to_dict() for item in all_cases]
            rationale = f"{len(all_cases)}/520 frozen pairs produced CaseResults"
        elif code == "ALL_CORE_RUNS_MUST_AUDIT":
            passed = len(all_cases) == 520 and all(
                item.audit_passed is True for item in all_cases
            )
            kind = "CAUSAL_AUDIT"
            ids = tuple(item.case_result_id for item in all_cases)
            payload = [item.to_dict() for item in all_cases]
            rationale = f"{sum(item.audit_passed is True for item in all_cases)}/520 Runs passed causal audit"
        elif code == "ALL_METRIC_REPORTS_MUST_SOURCE_BIND":
            passed = len(all_cases) == 520 and all(
                item.status is ExperimentCaseStatus.PASSED for item in all_cases
            )
            kind = "METRIC_SOURCE_BINDING"
            ids = tuple(item.case_result_id for item in all_cases)
            payload = [item.to_dict() for item in all_cases]
            rationale = f"{sum(item.status is ExperimentCaseStatus.PASSED for item in all_cases)}/520 Metric Reports source-bind"
        elif code == "BASELINE_BATCH_REPLAY_PARITY":
            passed = len(all_baseline_replay) == 20 and all(
                item.status is ReplayComparisonStatus.MATCH
                for item in all_baseline_replay
            )
            kind = "BASELINE_REPLAY"
            ids = tuple(item.replay_comparison_id for item in all_baseline_replay)
            payload = [item.to_dict() for item in all_baseline_replay]
            rationale = f"{sum(item.status is ReplayComparisonStatus.MATCH for item in all_baseline_replay)}/20 Baseline replays match"
        elif code == "VARIANT_REPLAY_SAMPLE_PARITY":
            passed = len(b_variant_replay) == 125 and all(
                item.status is ReplayComparisonStatus.MATCH
                for item in b_variant_replay
            )
            kind = "FROZEN_B_V2_VARIANT_REPLAY"
            ids = tuple(item.replay_comparison_id for item in b_variant_replay)
            payload = [item.to_dict() for item in b_variant_replay]
            rationale = "All 125 predeclared seed-2 Variant replays match"
        elif code == "FIXED_CUTOFF_STABILITY":
            passed = len(all_cutoff) == 20 and all(
                item.status is FixedCutoffStatus.STABLE for item in all_cutoff
            )
            kind = "FIXED_CUTOFF"
            ids = tuple(item.fixed_cutoff_comparison_id for item in all_cutoff)
            payload = [item.to_dict() for item in all_cutoff]
            rationale = f"{sum(item.status is FixedCutoffStatus.STABLE for item in all_cutoff)}/20 Baseline cases are stable"
        elif code == "DETERMINISTIC_REPEAT":
            passed = len(all_same) == 520 and all(
                item.status is ReplayComparisonStatus.MATCH for item in all_same
            )
            kind = "SAME_CONTEXT_REPEAT"
            ids = tuple(item.determinism_comparison_id for item in all_same)
            payload = [item.to_dict() for item in all_same]
            rationale = f"{sum(item.status is ReplayComparisonStatus.MATCH for item in all_same)}/520 same-context repeats match"
        elif code == "DECIMAL_CONTEXT_INDEPENDENCE":
            passed = len(all_decimal) == 520 and all(
                item.status is ReplayComparisonStatus.MATCH for item in all_decimal
            )
            kind = "DECIMAL_CONTEXT_PERTURBATION"
            ids = tuple(item.determinism_comparison_id for item in all_decimal)
            payload = [item.to_dict() for item in all_decimal]
            rationale = f"{sum(item.status is ReplayComparisonStatus.MATCH for item in all_decimal)}/520 Decimal-context comparisons match"
        elif code == "TEN_AGGREGATES_ALWAYS_PRESENT":
            passed = len(all_cases) == 520 and all(
                len(item.aggregates) == 10 for item in all_cases
            )
            kind = "METRIC_AGGREGATES"
            ids = tuple(item.case_result_id for item in all_cases)
            payload = [item.to_dict() for item in all_cases]
            rationale = f"{sum(len(item.aggregates) == 10 for item in all_cases)}/520 CaseResults retain ten aggregates"
        elif code == "OOS_SAMPLE_COVERAGE":
            passed = len(coverage) == 10 and all(item["passed"] for item in coverage)
            kind = "OOS_METRIC_COVERAGE"
            ids = tuple(str(item["coverage_result_id"]) for item in coverage)
            payload = coverage
            rationale = f"{sum(bool(item['passed']) for item in coverage)}/10 frozen OOS coverage minima pass"
        elif code == "NO_NEIGHBORHOOD_DEGENERATION":
            passed = (
                len(degeneration) == 25
                and all(
                    item["status"] not in ("DEGENERATED", "INSUFFICIENT_EVIDENCE")
                    for item in degeneration
                )
                and global_degeneration["status"] == "NOT_DEGENERATED"
            )
            kind = "SUBJECT_BOUND_DEGENERATION"
            ids = tuple(str(item["degeneration_summary_id"]) for item in degeneration) + (
                str(global_degeneration["global_evidence_id"]),
            )
            payload = {
                "variant_summaries": degeneration,
                "global_evidence": global_degeneration,
            }
            rationale = "Variant subject evidence and Baseline-global rewrite evidence evaluated separately"
        elif code == "FREEZE_SOURCE_BOUND":
            passed = True
            kind = "C_EXECUTION_SOURCE_BINDING"
            ids = (str(contract["execution_contract_id"]),) + tuple(
                item.case_result_id for item in case_results
            )
            payload = {
                "execution_contract_id": contract["execution_contract_id"],
                "c_source_locks": contract["c_source_locks"],
                "historical_evidence_locks": contract[
                    "historical_evidence_locks"
                ],
                "oos_case_result_ids": [
                    item.case_result_id for item in case_results
                ],
            }
            rationale = "C report inputs bind the committed source and historical Evidence locks"
        else:
            raise C008CCError(f"unsupported frozen Gate code: {code}")
        results.append(
            _gate_result(
                gate,
                passed=passed,
                evidence_kind=kind,
                evidence_ids=ids,
                evidence_payload=payload,
                rationale=rationale,
            )
        )
    if len(results) != 27 or len({item["gate_code"] for item in results}) != 27:
        raise C008CCError("exactly 27 unique final C GateResults are required")
    return results


def _attempt_payload(contract: Mapping[str, object]) -> dict[str, object]:
    payload = {
        "execution_semantics": EXECUTION_SEMANTICS,
        "execution_contract_id": contract["execution_contract_id"],
        "formal_execution_count": 1,
        "execution_started": True,
        "retry_allowed": False,
        "partition": DatasetPartition.OOS.value,
        "seed": 3,
        "oos_pair_count": 130,
        "schema_version": SCHEMA_VERSION,
    }
    return {
        "attempt_id": semantic_id(
            "c008c-c-post-fix-locked-oos-attempt-v1-", payload
        ),
        **payload,
    }


def _build_report(
    base: Path,
    contract: Mapping[str, object],
    attempt: Mapping[str, object],
    b_report: C008CBV2RunReport,
    case_results: tuple[C008CCCaseResult, ...],
    same: tuple[ExperimentDeterminismComparisonV2, ...],
    decimal: tuple[ExperimentDeterminismComparisonV2, ...],
    metric_deltas: tuple[ExperimentMetricDeltaSummary, ...],
    coverage_sources: list[dict[str, object]],
    coverage: list[dict[str, object]],
    replay: tuple[ExperimentReplayComparison, ...],
    cutoff: tuple[ExperimentFixedCutoffComparison, ...],
    degeneration: list[dict[str, object]],
    global_degeneration: dict[str, object],
) -> dict[str, object]:
    gates = _gate_results(
        base,
        contract,
        b_report,
        case_results,
        same,
        decimal,
        coverage,
        replay,
        cutoff,
        degeneration,
        global_degeneration,
    )
    freeze_eligible = all(item["status"] == "PASS" for item in gates)
    payload = {
        "execution_semantics": EXECUTION_SEMANTICS,
        "execution_contract_id": contract["execution_contract_id"],
        "attempt_id": attempt["attempt_id"],
        "b_v2_execution_contract_id": contract["b_v2_execution_contract_id"],
        "b_v2_run_report_id": b_report.run_report_id,
        "b_v2_execution_source_manifest_id": (
            b_report.execution_source_manifest_id
        ),
        "historical_execution_manifest_id": (
            contract["historical_execution_manifest_id"]
        ),
        "dataset_manifest_id": contract["dataset_manifest_id"],
        "experiment_plan_id": contract["experiment_plan_id"],
        "reviewed_protected_source_manifest_id": (
            contract["reviewed_protected_source_manifest_id"]
        ),
        "partition": DatasetPartition.OOS.value,
        "seed": 3,
        "scenarios": contract["scenarios"],
        "oos_case_ids": contract["oos_case_ids"],
        "variant_ids": contract["variant_ids"],
        "case_results": [item.to_dict() for item in case_results],
        "same_context_comparisons": [item.to_dict() for item in same],
        "decimal_context_comparisons": [item.to_dict() for item in decimal],
        "metric_delta_summaries": [
            item.to_dict() for item in metric_deltas
        ],
        "coverage_source_reports": coverage_sources,
        "metric_coverage_results": coverage,
        "replay_comparisons": [item.to_dict() for item in replay],
        "fixed_cutoff_comparisons": [item.to_dict() for item in cutoff],
        "degeneration_summaries": degeneration,
        "global_degeneration_evidence": global_degeneration,
        "gate_results": gates,
        "oos_scenario_count": 5,
        "oos_variant_count": 26,
        "oos_pair_count": 130,
        "passed_case_count": sum(
            item.status is ExperimentCaseStatus.PASSED for item in case_results
        ),
        "failed_case_count": sum(
            item.status is not ExperimentCaseStatus.PASSED for item in case_results
        ),
        "same_context_match_count": sum(
            item.status is ReplayComparisonStatus.MATCH for item in same
        ),
        "decimal_context_match_count": sum(
            item.status is ReplayComparisonStatus.MATCH for item in decimal
        ),
        "baseline_replay_match_count": sum(
            item.status is ReplayComparisonStatus.MATCH for item in replay
        ),
        "replay_mismatch_count": sum(
            item.status is not ReplayComparisonStatus.MATCH for item in replay
        ),
        "fixed_cutoff_stable_count": sum(
            item.status is FixedCutoffStatus.STABLE for item in cutoff
        ),
        "fixed_cutoff_rewrite_count": sum(
            item.rewrite_count for item in cutoff
        ),
        "coverage_pass_count": sum(bool(item["passed"]) for item in coverage),
        "degeneration_status_counts": {
            status: sum(item["status"] == status for item in degeneration)
            for status in (
                "NOT_DEGENERATED",
                "SENSITIVE",
                "DEGENERATED",
                "INSUFFICIENT_EVIDENCE",
            )
        },
        "gate_pass_count": sum(item["status"] == "PASS" for item in gates),
        "gate_fail_count": sum(item["status"] == "FAIL" for item in gates),
        "final_decision": "FREEZE_ELIGIBLE" if freeze_eligible else "BLOCKED",
        "freeze_eligible": freeze_eligible,
        "synthetic_oos_status": "COMPLETED",
        "formal_execution_count": 1,
        "retry_count": 0,
        "b_v2_rerun_performed": False,
        "non_oos_seed_consumed": False,
        "outcome_driven_selection_performed": False,
        "source_authority_status": "MATCHED_BEFORE_AND_AFTER",
        "limitations": [
            "This is synthetic engineering OOS only.",
            "Real-market XAUUSD OOS remains NOT RUN / NOT EVIDENCED.",
            "No profitability or trading edge is claimed.",
            "C-009 is not started by this outcome.",
        ],
        "schema_version": SCHEMA_VERSION,
    }
    return {
        "run_report_id": semantic_id(
            "c008c-c-post-fix-locked-oos-run-report-v1-", payload
        ),
        **payload,
    }


def _objects_from_report(
    payload: Mapping[str, object],
) -> tuple[
    tuple[C008CCCaseResult, ...],
    tuple[ExperimentDeterminismComparisonV2, ...],
    tuple[ExperimentDeterminismComparisonV2, ...],
    tuple[ExperimentMetricDeltaSummary, ...],
    tuple[ExperimentReplayComparison, ...],
    tuple[ExperimentFixedCutoffComparison, ...],
]:
    try:
        return (
            tuple(
                C008CCCaseResult.from_dict(item)
                for item in payload["case_results"]  # type: ignore[index]
            ),
            tuple(
                ExperimentDeterminismComparisonV2.from_dict(item)
                for item in payload["same_context_comparisons"]  # type: ignore[index]
            ),
            tuple(
                ExperimentDeterminismComparisonV2.from_dict(item)
                for item in payload["decimal_context_comparisons"]  # type: ignore[index]
            ),
            tuple(
                ExperimentMetricDeltaSummary.from_dict(item)
                for item in payload["metric_delta_summaries"]  # type: ignore[index]
            ),
            tuple(
                ExperimentReplayComparison.from_dict(item)
                for item in payload["replay_comparisons"]  # type: ignore[index]
            ),
            tuple(
                ExperimentFixedCutoffComparison.from_dict(item)
                for item in payload["fixed_cutoff_comparisons"]  # type: ignore[index]
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise C008CCError("serialized C outcome members are invalid") from exc


def _validate_attempt(
    attempt: Mapping[str, object], contract: Mapping[str, object]
) -> None:
    if dict(attempt) != _attempt_payload(contract):
        raise C008CCError("C attempt marker is invalid")


def validate_c008c_c_report(
    payload: Mapping[str, object],
    root: Path | None = None,
) -> dict[str, object]:
    base = _root(root)
    contract = load_committed_c008c_c_execution_contract(base)
    _, attempt = _canonical_payload(base / ATTEMPT_PATH, "C attempt marker")
    _validate_attempt(attempt, contract)
    _, b_report = _load_b_v2_prerequisite(base)
    (
        case_results,
        same,
        decimal,
        metric_deltas,
        replay,
        cutoff,
    ) = _objects_from_report(payload)
    manifest = build_c008c_b_execution_manifest(base)
    expected_pair_ids = tuple(
        item.execution_pair_id for item in manifest.deferred_oos_pairs
    )
    if (
        len(case_results) != 130
        or tuple(item.execution_pair_id for item in case_results)
        != expected_pair_ids
        or tuple(item.execution_pair_id for item in same) != expected_pair_ids
        or tuple(item.execution_pair_id for item in decimal) != expected_pair_ids
        or any(
            item.seed != 3
            or item.partition is not C008CCPartition.LOCKED_OOS
            for item in case_results
        )
        or len(metric_deltas) != 25
        or len(replay) != 5
        or len(cutoff) != 5
    ):
        raise C008CCError("C report does not bind the complete frozen OOS schedule")
    expected_deltas = _oos_metric_deltas(base, case_results)
    if tuple(item.to_dict() for item in metric_deltas) != tuple(
        item.to_dict() for item in expected_deltas
    ):
        raise C008CCError("C metric deltas contradict CaseResults")
    try:
        coverage_sources = list(payload["coverage_source_reports"])  # type: ignore[arg-type]
        stored_coverage = list(payload["metric_coverage_results"])  # type: ignore[arg-type]
        stored_degeneration = list(payload["degeneration_summaries"])  # type: ignore[arg-type]
        stored_global = dict(payload["global_degeneration_evidence"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        raise C008CCError("C derived Evidence members are invalid") from exc
    expected_coverage = _coverage_summaries(
        base, case_results, coverage_sources
    )
    if stored_coverage != expected_coverage:
        raise C008CCError("C metric coverage contradicts source aggregates")
    expected_degeneration, expected_global = _degeneration_summaries(
        base,
        b_report,
        case_results,
        metric_deltas,
        cutoff,
    )
    if (
        stored_degeneration != expected_degeneration
        or stored_global != expected_global
    ):
        raise C008CCError("C degeneration Evidence is not derivable")
    expected = _build_report(
        base,
        contract,
        attempt,
        b_report,
        case_results,
        same,
        decimal,
        metric_deltas,
        coverage_sources,
        stored_coverage,
        replay,
        cutoff,
        stored_degeneration,
        stored_global,
    )
    if dict(payload) != expected:
        raise C008CCError("C report is not the canonical derived outcome")
    return expected


def run_c008c_c_locked_oos(
    root: Path | None = None,
) -> tuple[Path, Path, dict[str, object], float]:
    """Run exactly one formal seed-3 OOS attempt and write canonical Evidence."""

    base = _root(root)
    contract = validate_c008c_c_preflight(base, require_clean=True)
    attempt = _attempt_payload(contract)
    attempt_path = base / ATTEMPT_PATH
    report_path = base / REPORT_PATH
    _write_or_refuse_different(attempt_path, canonical_json_bytes(attempt))
    started = perf_counter()
    manifest = build_c008c_b_execution_manifest(base)
    _, b_report = _load_b_v2_prerequisite(base)
    case_results, same, decimal, coverage_sources = _run_primary(
        base, manifest
    )
    replay = _run_replay(base, manifest)
    cutoff = _run_cutoff(base, manifest)
    metric_deltas = _oos_metric_deltas(base, case_results)
    coverage = _coverage_summaries(base, case_results, coverage_sources)
    degeneration, global_degeneration = _degeneration_summaries(
        base,
        b_report,
        case_results,
        metric_deltas,
        cutoff,
    )
    if build_c008c_c_execution_contract(base) != contract:
        raise C008CCError("formal source or historical Evidence changed during OOS")
    report = _build_report(
        base,
        contract,
        attempt,
        b_report,
        case_results,
        same,
        decimal,
        metric_deltas,
        coverage_sources,
        coverage,
        replay,
        cutoff,
        degeneration,
        global_degeneration,
    )
    _write_or_refuse_different(report_path, canonical_json_bytes(report))
    validate_c008c_c_report(report, base)
    return attempt_path, report_path, report, perf_counter() - started


def check_existing_c008c_c_evidence(
    root: Path | None = None,
) -> tuple[tuple[Path, Path, Path], dict[str, object]]:
    """Validate committed architecture and existing outcome without execution."""

    base = _root(root)
    load_committed_c008c_c_execution_contract(base)
    _, attempt = _canonical_payload(base / ATTEMPT_PATH, "C attempt marker")
    _, report = _canonical_payload(base / REPORT_PATH, "C outcome report")
    contract = load_committed_c008c_c_execution_contract(base)
    _validate_attempt(attempt, contract)
    validated = validate_c008c_c_report(report, base)
    return (
        (base / CONTRACT_PATH, base / ATTEMPT_PATH, base / REPORT_PATH),
        validated,
    )


def evidence_sha256(path: Path) -> str:
    return _sha256(path)


__all__ = [
    "ATTEMPT_PATH",
    "BASE_MAIN_SHA",
    "C008CCError",
    "CONTRACT_PATH",
    "EXECUTION_SEMANTICS",
    "FORMAL_COMMAND",
    "LEGACY_ATTEMPT_PATH",
    "LEGACY_CONTRACT_PATH",
    "REPORT_PATH",
    "build_c008c_c_execution_contract",
    "check_existing_c008c_c_evidence",
    "evidence_sha256",
    "load_committed_c008c_c_execution_contract",
    "prepare_c008c_c_execution_contract",
    "run_c008c_c_locked_oos",
    "validate_c008c_c_preflight",
    "validate_c008c_c_report",
]
