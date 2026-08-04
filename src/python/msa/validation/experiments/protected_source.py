"""Deterministic protected-source manifest for C-008C execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .contracts import (
    CORE_REFERENCE_COMMIT,
    EXECUTION_BASE_COMMIT,
    PROTECTED_SOURCE_BYTE_POLICY,
    ProtectedSourceFile,
    ProtectedSourceManifest,
)
from .errors import ExperimentProtectedSourceError
from .errors import ExperimentEvidenceError
from .identity import canonical_json_bytes, semantic_id


def repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _resolve_root(
    root: Path | None, error_type: type[ValueError]
) -> Path:
    if root is None:
        return repository_root()
    if not isinstance(root, Path):
        raise error_type("root must be pathlib.Path or None")
    try:
        return root.resolve()
    except (OSError, RuntimeError) as exc:
        raise error_type("unable to resolve repository root") from exc


def _category(relative_path: str) -> str:
    if relative_path.startswith("src/python/msa/reference/"):
        return "REFERENCE"
    if relative_path.startswith("src/python/msa/research/"):
        return "RESEARCH"
    if relative_path.startswith("src/python/msa/validation/metrics/"):
        return "STRUCTURAL_METRICS"
    return "CAUSAL_VALIDATION"


def _protected_paths(root: Path) -> tuple[Path, ...]:
    values = {
        *(
            item
            for item in (root / "src/python/msa/reference").rglob("*.py")
            if item.is_file()
        ),
        *(
            item
            for item in (root / "src/python/msa/research").rglob("*.py")
            if item.is_file()
        ),
        *(
            item
            for item in (root / "src/python/msa/validation/metrics").rglob(
                "*.py"
            )
            if item.is_file()
        ),
    }
    validation = root / "src/python/msa/validation"
    values.update(
        validation / name
        for name in (
            "causal_audit.py",
            "comparison.py",
            "contracts.py",
            "metric_registry.py",
        )
    )
    if any(not item.is_file() for item in values):
        raise ExperimentProtectedSourceError(
            "a required protected source file is missing"
        )
    return tuple(
        sorted(values, key=lambda item: item.relative_to(root).as_posix())
    )


def _entry(root: Path, path: Path) -> ProtectedSourceFile:
    data = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    if b"\r" in data:
        raise ExperimentProtectedSourceError(
            f"protected source must use canonical LF worktree bytes: {relative}"
        )
    return ProtectedSourceFile(
        relative_path=relative,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        category=_category(relative),
    )


def build_protected_source_manifest(
    root: Path | None = None,
) -> ProtectedSourceManifest:
    base = _resolve_root(root, ExperimentProtectedSourceError)
    try:
        files = tuple(_entry(base, item) for item in _protected_paths(base))
    except (
        AssertionError,
        AttributeError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentProtectedSourceError(
            "unable to read protected source authority"
        ) from exc
    payload = {
        "execution_base_commit": EXECUTION_BASE_COMMIT,
        "core_reference_commit": CORE_REFERENCE_COMMIT,
        "byte_policy": PROTECTED_SOURCE_BYTE_POLICY,
        "files": [item.to_dict() for item in files],
        "schema_version": 1,
    }
    return ProtectedSourceManifest(
        protected_source_manifest_id=semantic_id(
            "c008c-protected-source-manifest-v1-", payload
        ),
        execution_base_commit=EXECUTION_BASE_COMMIT,
        core_reference_commit=CORE_REFERENCE_COMMIT,
        byte_policy=PROTECTED_SOURCE_BYTE_POLICY,
        files=files,
    )


def validate_protected_source_manifest(
    manifest: ProtectedSourceManifest,
    root: Path | None = None,
) -> ProtectedSourceManifest:
    if not isinstance(manifest, ProtectedSourceManifest):
        raise ExperimentProtectedSourceError(
            "manifest must be ProtectedSourceManifest"
        )
    try:
        original_payload = manifest.to_dict()
        restored = ProtectedSourceManifest.from_dict(original_payload)
        restored_payload = restored.to_dict()
        current = build_protected_source_manifest(root)
        current_payload = current.to_dict()
    except (
        AssertionError,
        AttributeError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentProtectedSourceError(
            "manifest is not formally valid"
        ) from exc
    if (
        restored != manifest
        or restored_payload != original_payload
        or original_payload != current_payload
    ):
        try:
            from msa.validation.remediation import (
                validate_historical_protected_source_transition,
            )

            validate_historical_protected_source_transition(manifest, root)
        except (ImportError, OSError, TypeError, ValueError) as exc:
            raise ExperimentProtectedSourceError(
                "protected source differs from the frozen manifest"
            ) from exc
    return manifest


def write_c008c_authority_evidence(
    root: Path | None = None,
    *,
    check: bool = False,
) -> tuple[Path, ...]:
    """Write or byte-check the four canonical C-008C authority files."""

    from .baseline import core_experiment_baseline
    from .dataset import build_c008c_synthetic_dataset
    from .gates import default_c008c_gate_registry
    from .plan import default_c008c_experiment_plan
    from .authority import (
        validate_c008c_experiment_plan,
        validate_c008c_gate_registry,
        validate_c008c_synthetic_dataset,
        validate_core_experiment_baseline,
    )

    base = _resolve_root(root, ExperimentEvidenceError)
    evidence_dir = base / "docs/validation/evidence"
    if not check and (
        evidence_dir / "c008c_h2_decimal_remediation.json"
    ).is_file():
        raise ExperimentEvidenceError(
            "historical C-008C v1 Evidence cannot be regenerated after "
            "a versioned remediation"
        )
    try:
        baseline = core_experiment_baseline()
        dataset = build_c008c_synthetic_dataset()
        gates = default_c008c_gate_registry()
        plan = default_c008c_experiment_plan()
        if check:
            protected = ProtectedSourceManifest.from_dict(
                json.loads(
                    (evidence_dir / "c008c_protected_source_manifest.json")
                    .read_text(encoding="utf-8")
                )
            )
        else:
            protected = build_protected_source_manifest(base)
        validate_core_experiment_baseline(baseline)
        validate_c008c_synthetic_dataset(dataset)
        validate_c008c_gate_registry(gates)
        validate_c008c_experiment_plan(plan)
        validate_protected_source_manifest(protected, base)
    except (
        AssertionError,
        AttributeError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentEvidenceError(
            "C-008C source authority validation failed"
        ) from exc
    values = (
        ("c008c_baseline_snapshot.json", baseline.to_dict()),
        (
            "c008c_dataset_manifest.json",
            dataset.to_dict(),
        ),
        (
            "c008c_experiment_plan.json",
            plan.to_dict(),
        ),
        (
            "c008c_protected_source_manifest.json",
            protected.to_dict(),
        ),
    )
    paths = tuple(evidence_dir / name for name, _ in values)
    if check:
        for path, (_, payload) in zip(paths, values, strict=True):
            expected = canonical_json_bytes(payload)
            try:
                actual = path.read_bytes()
            except OSError as exc:
                raise ExperimentEvidenceError(
                    f"evidence file is missing: {path.name}"
                ) from exc
            if actual != expected:
                raise ExperimentEvidenceError(
                    f"evidence bytes differ: {path.name}"
                )
        return paths
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        for path, (_, payload) in zip(paths, values, strict=True):
            path.write_bytes(canonical_json_bytes(payload))
    except OSError as exc:
        raise ExperimentEvidenceError(
            "unable to write canonical C-008C evidence"
        ) from exc
    return paths
