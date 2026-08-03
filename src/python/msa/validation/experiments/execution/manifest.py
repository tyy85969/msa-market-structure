"""Outcome-free C-008C-B execution manifest construction and validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..authority import (
    validate_c008c_experiment_plan,
    validate_c008c_gate_registry,
    validate_c008c_synthetic_dataset,
    validate_core_experiment_baseline,
)
from ..baseline import core_experiment_baseline
from ..contracts import (
    CoreExperimentBaseline,
    DatasetPartition,
    ExperimentDatasetManifest,
    ExperimentPlan,
    ProtectedSourceManifest,
)
from ..dataset import build_c008c_synthetic_dataset
from ..gates import default_c008c_gate_registry
from ..identity import canonical_json_bytes, digest, semantic_id
from ..plan import default_c008c_experiment_plan
from ..protected_source import validate_protected_source_manifest
from .contracts import (
    CORE_REFERENCE_COMMIT,
    FROZEN_EXECUTION_BASE_COMMIT,
    REPOSITORY_BASE_COMMIT,
    C008CBExecutionManifest,
    C008CBExecutionPair,
)
from .errors import C008CBManifestError, C008CBPreflightError


_EVIDENCE_DIR = Path("docs/validation/evidence")
_BASELINE_FILE = _EVIDENCE_DIR / "c008c_baseline_snapshot.json"
_DATASET_FILE = _EVIDENCE_DIR / "c008c_dataset_manifest.json"
_PLAN_FILE = _EVIDENCE_DIR / "c008c_experiment_plan.json"
_PROTECTED_FILE = _EVIDENCE_DIR / "c008c_protected_source_manifest.json"

_MANIFEST_ASSUMPTIONS = (
    "Manifest exists before and does not consume any Core Run Audit Report Metric Report or outcome",
    "Execution order is frozen as B-stage case order then frozen Variant order with no early stopping",
    "Only DEVELOPMENT seeds 0 and 1 and VALIDATION seed 2 are executable in C-008C-B",
    "All seed 3 OOS execution replay cutoff and metric outcomes are deferred to C-008C-C",
    "Coverage collapse uses Decimal decline_fraction strictly greater than 0.90",
    "Coverage collapse triggers when at least five distinct metrics lose eligible or matured coverage",
    "Metric deltas are descriptive variant minus same-case Baseline values with no better worse meaning",
    "Unsupported ablations remain UNSUPPORTED_BY_PUBLIC_CONFIG and are not executed by monkeypatch",
    "No outcome may alter Variant inclusion order Dataset Gate threshold or parameter value",
)


def _root(root: Path | None) -> Path:
    base = Path.cwd() if root is None else Path(root)
    try:
        resolved = base.resolve(strict=True)
    except OSError as exc:
        raise C008CBPreflightError("repository root cannot be resolved") from exc
    if not (resolved / "pyproject.toml").is_file() or not (
        resolved / _PROTECTED_FILE
    ).is_file():
        raise C008CBPreflightError("repository root is not the C-008C checkout")
    return resolved


def _committed_payload(base: Path, relative: Path) -> dict[str, object]:
    path = base / relative
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C008CBPreflightError(
            f"committed authority evidence cannot be read: {relative.as_posix()}"
        ) from exc
    if not isinstance(payload, dict):
        raise C008CBPreflightError(
            f"authority evidence must be JSON object: {relative.as_posix()}"
        )
    if raw != canonical_json_bytes(payload):
        raise C008CBPreflightError(
            f"authority evidence is not canonical bytes: {relative.as_posix()}"
        )
    return payload


def load_c008c_b_authority(
    root: Path | None = None,
) -> tuple[
    CoreExperimentBaseline,
    ExperimentDatasetManifest,
    tuple,
    ExperimentPlan,
    ProtectedSourceManifest,
]:
    """Load committed A evidence and validate every source authority."""

    base = _root(root)
    try:
        baseline = CoreExperimentBaseline.from_dict(
            _committed_payload(base, _BASELINE_FILE)
        )
        dataset = ExperimentDatasetManifest.from_dict(
            _committed_payload(base, _DATASET_FILE)
        )
        plan = ExperimentPlan.from_dict(
            _committed_payload(base, _PLAN_FILE)
        )
        protected = ProtectedSourceManifest.from_dict(
            _committed_payload(base, _PROTECTED_FILE)
        )
        validated_baseline = validate_core_experiment_baseline(baseline)
        validated_dataset = validate_c008c_synthetic_dataset(dataset)
        gates = validate_c008c_gate_registry(default_c008c_gate_registry())
        validated_plan = validate_c008c_experiment_plan(plan)
        validated_protected = validate_protected_source_manifest(
            protected, base
        )
    except (
        AssertionError,
        AttributeError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise C008CBPreflightError(
            "C-008C-B frozen authority preflight failed"
        ) from exc
    if (
        validated_baseline.to_dict()
        != core_experiment_baseline().to_dict()
        or validated_dataset.to_dict()
        != build_c008c_synthetic_dataset().to_dict()
        or validated_plan.to_dict()
        != default_c008c_experiment_plan().to_dict()
    ):
        raise C008CBPreflightError("committed authority differs from Builder")
    return (
        validated_baseline,
        validated_dataset,
        gates,
        validated_plan,
        validated_protected,
    )


def _pair_payload(
    *,
    dataset_case_id: str,
    variant_id: str,
    partition: DatasetPartition,
    scenario: object,
    seed: int,
    schedule_index: int,
    source_input_payload_digest: str,
    core_config_payload_digest: str,
    metric_config_payload_digest: str,
    deferred_to_c008c_c: bool,
) -> dict[str, object]:
    return {
        "dataset_case_id": dataset_case_id,
        "variant_id": variant_id,
        "partition": partition.value,
        "scenario": scenario.value,
        "seed": seed,
        "schedule_index": schedule_index,
        "source_input_payload_digest": source_input_payload_digest,
        "core_config_payload_digest": core_config_payload_digest,
        "metric_config_payload_digest": metric_config_payload_digest,
        "deferred_to_c008c_c": deferred_to_c008c_c,
        "schema_version": 1,
    }


def _pair(
    case: object,
    variant: object,
    schedule_index: int,
) -> C008CBExecutionPair:
    payload = _pair_payload(
        dataset_case_id=case.dataset_case_id,
        variant_id=variant.variant_id,
        partition=case.partition,
        scenario=case.scenario_kind,
        seed=case.seed,
        schedule_index=schedule_index,
        source_input_payload_digest=case.source_input_payload_digest,
        core_config_payload_digest=digest(
            variant.core_config_snapshot.to_dict()
        ),
        metric_config_payload_digest=digest(
            variant.metric_config_snapshot.to_dict()
        ),
        deferred_to_c008c_c=case.partition is DatasetPartition.OOS,
    )
    return C008CBExecutionPair(
        execution_pair_id=semantic_id(
            C008CBExecutionPair._PREFIX, payload
        ),
        dataset_case_id=case.dataset_case_id,
        variant_id=variant.variant_id,
        partition=case.partition,
        scenario=case.scenario_kind,
        seed=case.seed,
        schedule_index=schedule_index,
        source_input_payload_digest=case.source_input_payload_digest,
        core_config_payload_digest=payload["core_config_payload_digest"],
        metric_config_payload_digest=payload[
            "metric_config_payload_digest"
        ],
        deferred_to_c008c_c=payload["deferred_to_c008c_c"],
    )


def _sample_id(prefix: str, case_id: str, variant_id: str) -> str:
    return semantic_id(
        prefix,
        {
            "dataset_case_id": case_id,
            "variant_id": variant_id,
            "schema_version": 1,
        },
    )


def _build_manifest_from_authority(
    root: Path | None = None,
) -> C008CBExecutionManifest:
    """Build the complete B schedule without reading any outcome."""

    (
        baseline,
        dataset,
        gates,
        plan,
        protected,
    ) = load_c008c_b_authority(root)
    cases_by_id = {item.dataset_case_id: item for item in dataset.cases}
    variants_by_id = {item.variant_id: item for item in plan.variants}
    ordered_cases = tuple(
        cases_by_id[item]
        for item in plan.execution_scope_policy.dataset_case_ids
    )
    ordered_variants = tuple(
        variants_by_id[item]
        for item in plan.execution_scope_policy.variant_ids
    )
    executable_cases = tuple(
        item
        for item in ordered_cases
        if item.partition is not DatasetPartition.OOS
    )
    deferred_cases = tuple(
        item
        for item in ordered_cases
        if item.partition is DatasetPartition.OOS
    )
    execution_pairs = tuple(
        _pair(case, variant, case_index * len(ordered_variants) + variant_index)
        for case_index, case in enumerate(executable_cases)
        for variant_index, variant in enumerate(ordered_variants)
    )
    deferred_oos_pairs = tuple(
        _pair(
            case,
            variant,
            len(execution_pairs)
            + case_index * len(ordered_variants)
            + variant_index,
        )
        for case_index, case in enumerate(deferred_cases)
        for variant_index, variant in enumerate(ordered_variants)
    )
    baseline_variant = ordered_variants[0]
    non_baseline_variants = ordered_variants[1:]
    validation_case_ids = plan.variant_replay_policy.dataset_case_ids
    variant_replay_sample_ids = tuple(
        _sample_id(
            "c008c-b-variant-replay-sample-v1-",
            case_id,
            variant.variant_id,
        )
        for variant in non_baseline_variants
        for case_id in validation_case_ids
    )
    baseline_replay_sample_ids = tuple(
        _sample_id(
            "c008c-b-baseline-replay-sample-v1-",
            case.dataset_case_id,
            baseline_variant.variant_id,
        )
        for case in executable_cases
    )
    deferred_baseline_replay_sample_ids = tuple(
        _sample_id(
            "c008c-b-baseline-replay-sample-v1-",
            case.dataset_case_id,
            baseline_variant.variant_id,
        )
        for case in deferred_cases
    )
    execution_schedule_digest = digest(
        [item.to_dict() for item in execution_pairs]
    )
    variant_replay_schedule_digest = digest(
        list(variant_replay_sample_ids)
    )
    baseline_replay_schedule_digest = digest(
        {
            "executed": list(baseline_replay_sample_ids),
            "deferred": list(deferred_baseline_replay_sample_ids),
        }
    )
    fixed_cutoff_case_ids = tuple(
        item.dataset_case_id for item in executable_cases
    )
    deferred_fixed_cutoff_case_ids = tuple(
        item.dataset_case_id for item in deferred_cases
    )
    fixed_cutoff_schedule_digest = digest(
        {
            "executed": list(fixed_cutoff_case_ids),
            "deferred": list(deferred_fixed_cutoff_case_ids),
        }
    )
    kwargs = {
        "repository_base_commit": REPOSITORY_BASE_COMMIT,
        "frozen_execution_base_commit": FROZEN_EXECUTION_BASE_COMMIT,
        "core_reference_commit": CORE_REFERENCE_COMMIT,
        "baseline_id": baseline.baseline_id,
        "dataset_manifest_id": dataset.dataset_manifest_id,
        "experiment_plan_id": plan.experiment_plan_id,
        "protected_source_manifest_id": (
            protected.protected_source_manifest_id
        ),
        "gate_definition_ids": tuple(
            item.gate_definition_id for item in gates
        ),
        "variant_ids": tuple(item.variant_id for item in ordered_variants),
        "frozen_case_ids": tuple(
            item.dataset_case_id for item in ordered_cases
        ),
        "executable_case_ids": fixed_cutoff_case_ids,
        "deferred_oos_case_ids": deferred_fixed_cutoff_case_ids,
        "execution_pairs": execution_pairs,
        "deferred_oos_pairs": deferred_oos_pairs,
        "variant_replay_sample_ids": variant_replay_sample_ids,
        "baseline_replay_sample_ids": baseline_replay_sample_ids,
        "deferred_baseline_replay_sample_ids": (
            deferred_baseline_replay_sample_ids
        ),
        "fixed_cutoff_case_ids": fixed_cutoff_case_ids,
        "deferred_fixed_cutoff_case_ids": (
            deferred_fixed_cutoff_case_ids
        ),
        "execution_schedule_digest": execution_schedule_digest,
        "variant_replay_schedule_digest": (
            variant_replay_schedule_digest
        ),
        "baseline_replay_schedule_digest": (
            baseline_replay_schedule_digest
        ),
        "fixed_cutoff_schedule_digest": fixed_cutoff_schedule_digest,
        "assumptions": _MANIFEST_ASSUMPTIONS,
        "schema_version": 1,
    }
    identity_payload = {
        key: (
            [item.to_dict() for item in value]
            if key in ("execution_pairs", "deferred_oos_pairs")
            else list(value)
            if isinstance(value, tuple)
            else value
        )
        for key, value in kwargs.items()
    }
    manifest = C008CBExecutionManifest(
        execution_manifest_id=semantic_id(
            C008CBExecutionManifest._PREFIX, identity_payload
        ),
        **kwargs,
    )
    return manifest


def build_c008c_b_execution_manifest(
    root: Path | None = None,
) -> C008CBExecutionManifest:
    """Build and source-validate the outcome-free B execution manifest."""

    manifest = _build_manifest_from_authority(root)
    return validate_c008c_b_execution_manifest(manifest, root)


def validate_c008c_b_execution_manifest(
    manifest: C008CBExecutionManifest,
    root: Path | None = None,
) -> C008CBExecutionManifest:
    """Validate contract, identity, authority binding, and exact schedule."""

    if not isinstance(manifest, C008CBExecutionManifest):
        raise C008CBManifestError(
            "manifest must be C008CBExecutionManifest"
        )
    try:
        payload = manifest.to_dict()
        restored = C008CBExecutionManifest.from_dict(payload)
    except (
        AssertionError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise C008CBManifestError(
            "execution manifest formal validation failed"
        ) from exc
    if restored != manifest or restored.to_dict() != payload:
        raise C008CBManifestError(
            "execution manifest does not round-trip exactly"
        )
    # Rebuild from source authority without accepting caller overrides.
    expected = _build_manifest_from_authority(root)
    if expected.to_dict() != payload:
        raise C008CBManifestError(
            "execution manifest differs from frozen source authority"
        )
    return manifest


__all__ = [
    "build_c008c_b_execution_manifest",
    "load_c008c_b_authority",
    "validate_c008c_b_execution_manifest",
]
