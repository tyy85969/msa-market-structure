"""Deterministic protected-source manifest for C-008C execution."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .contracts import (
    CORE_REFERENCE_COMMIT,
    EXECUTION_BASE_COMMIT,
    ProtectedSourceFile,
    ProtectedSourceManifest,
)
from .errors import ExperimentProtectedSourceError
from .errors import ExperimentEvidenceError
from .identity import canonical_json_bytes, semantic_id


def repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


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
    return ProtectedSourceFile(
        relative_path=relative,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        category=_category(relative),
    )


def build_protected_source_manifest(
    root: Path | None = None,
) -> ProtectedSourceManifest:
    base = repository_root() if root is None else root.resolve()
    files = tuple(_entry(base, item) for item in _protected_paths(base))
    payload = {
        "execution_base_commit": EXECUTION_BASE_COMMIT,
        "core_reference_commit": CORE_REFERENCE_COMMIT,
        "files": [item.to_dict() for item in files],
        "schema_version": 1,
    }
    return ProtectedSourceManifest(
        protected_source_manifest_id=semantic_id(
            "c008c-protected-source-manifest-v1-", payload
        ),
        execution_base_commit=EXECUTION_BASE_COMMIT,
        core_reference_commit=CORE_REFERENCE_COMMIT,
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
        restored = ProtectedSourceManifest.from_dict(manifest.to_dict())
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ExperimentProtectedSourceError(
            "manifest is not formally valid"
        ) from exc
    current = build_protected_source_manifest(root)
    if restored != manifest or manifest.to_dict() != current.to_dict():
        raise ExperimentProtectedSourceError(
            "protected source differs from the frozen manifest"
        )
    return manifest


def write_c008c_authority_evidence(
    root: Path | None = None,
    *,
    check: bool = False,
) -> tuple[Path, ...]:
    """Write or byte-check the four canonical C-008C authority files."""

    from .baseline import core_experiment_baseline
    from .dataset import build_c008c_synthetic_dataset
    from .plan import default_c008c_experiment_plan

    base = repository_root() if root is None else root.resolve()
    evidence_dir = base / "docs/validation/evidence"
    values = (
        ("c008c_baseline_snapshot.json", core_experiment_baseline().to_dict()),
        (
            "c008c_dataset_manifest.json",
            build_c008c_synthetic_dataset().to_dict(),
        ),
        (
            "c008c_experiment_plan.json",
            default_c008c_experiment_plan().to_dict(),
        ),
        (
            "c008c_protected_source_manifest.json",
            build_protected_source_manifest(base).to_dict(),
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
