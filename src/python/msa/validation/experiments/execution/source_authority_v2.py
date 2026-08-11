"""Exact, outcome-free source authority for formal C-008C-B-v2 execution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

from ..identity import canonical_json_bytes
from .contracts_v2 import (
    B_V2_SCHEMA_VERSION,
    C008CBV2ExecutionSourceFile,
    C008CBV2ExecutionSourceManifest,
    v2_payload_id,
)
from .errors import C008CBManifestError, C008CBPreflightError


B_V2_EXECUTION_SOURCE_MANIFEST_PATH = Path(
    "docs/validation/evidence/c008c_b_v2_execution_source_manifest.json"
)
_PACKAGE_ROOT = Path("src/python/msa")
_FORMAL_CLI = Path("tools/validation/generate_c008c_b_v2_results.py")
_GIT_TIMEOUT_SECONDS = 10
_HEAD_AUTHORITY_SPEC = (
    f"HEAD:{B_V2_EXECUTION_SOURCE_MANIFEST_PATH.as_posix()}"
)


def _root(root: Path | None) -> Path:
    base = Path.cwd() if root is None else Path(root)
    try:
        resolved = base.resolve(strict=True)
    except OSError as exc:
        raise C008CBPreflightError("repository root cannot be resolved") from exc
    if not (resolved / "pyproject.toml").is_file():
        raise C008CBPreflightError("repository root is not an MSA checkout")
    return resolved


def _source_paths(base: Path) -> tuple[Path, ...]:
    package_root = base / _PACKAGE_ROOT
    cli = base / _FORMAL_CLI
    if not package_root.is_dir() or not cli.is_file():
        raise C008CBPreflightError("formal B-v2 execution source scope is missing")
    candidates = tuple(package_root.rglob("*.py")) + (cli,)
    try:
        resolved = tuple(path.resolve(strict=True) for path in candidates)
    except OSError as exc:
        raise C008CBPreflightError("execution source cannot be resolved") from exc
    if any(
        original.is_symlink() or base not in resolved_path.parents
        for original, resolved_path in zip(candidates, resolved, strict=True)
    ):
        raise C008CBPreflightError(
            "execution source must be regular in-repository files"
        )
    return tuple(
        sorted(resolved, key=lambda path: path.relative_to(base).as_posix())
    )


def build_c008c_b_v2_execution_source_manifest(
    root: Path | None = None,
) -> C008CBV2ExecutionSourceManifest:
    """Recompute the exact formal source lock from current worktree bytes."""

    base = _root(root)
    try:
        files = tuple(
            C008CBV2ExecutionSourceFile(
                relative_path=path.relative_to(base).as_posix(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in _source_paths(base)
        )
    except OSError as exc:
        raise C008CBPreflightError(
            "formal B-v2 execution source cannot be read"
        ) from exc
    payload = {
        "files": [item.to_dict() for item in files],
        "file_count": len(files),
        "schema_version": B_V2_SCHEMA_VERSION,
    }
    return C008CBV2ExecutionSourceManifest(
        source_manifest_id=v2_payload_id(
            C008CBV2ExecutionSourceManifest._PREFIX, payload
        ),
        files=files,
        file_count=len(files),
    )


def _git_stdout(
    base: Path,
    arguments: tuple[str, ...],
    label: str,
) -> bytes:
    command = ("git", "-C", str(base), *arguments)
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
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise C008CBPreflightError(
            f"Git HEAD authority {label} failed"
        ) from exc
    if completed.returncode != 0:
        raise C008CBPreflightError(
            f"Git HEAD authority {label} failed"
        )
    return completed.stdout


def _head_authority_bytes(base: Path) -> bytes:
    inside = _git_stdout(
        base,
        ("rev-parse", "--is-inside-work-tree"),
        "worktree check",
    )
    prefix = _git_stdout(
        base,
        ("rev-parse", "--show-prefix"),
        "repository-root check",
    )
    if inside.strip() != b"true" or prefix.strip():
        raise C008CBPreflightError(
            "formal B-v2 root must be the Git worktree root"
        )
    return _git_stdout(
        base,
        ("cat-file", "blob", _HEAD_AUTHORITY_SPEC),
        "authority blob read",
    )


def load_committed_c008c_b_v2_execution_source_manifest(
    root: Path | None = None,
) -> C008CBV2ExecutionSourceManifest:
    """Load only the owner-reviewed canonical authority; never regenerate it."""

    base = _root(root)
    path = base / B_V2_EXECUTION_SOURCE_MANIFEST_PATH
    try:
        head_raw = _head_authority_bytes(base)
        worktree_raw = path.read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C008CBPreflightError(
            "committed B-v2 execution source manifest is missing or invalid"
        ) from exc
    if worktree_raw != head_raw:
        raise C008CBPreflightError(
            "worktree B-v2 execution source authority differs from Git HEAD"
        )
    try:
        payload = json.loads(head_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C008CBPreflightError(
            "Git HEAD B-v2 execution source authority is invalid"
        ) from exc
    if (
        not isinstance(payload, dict)
        or head_raw != canonical_json_bytes(payload)
    ):
        raise C008CBPreflightError(
            "Git HEAD B-v2 execution source manifest is not canonical"
        )
    try:
        manifest = C008CBV2ExecutionSourceManifest.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise C008CBPreflightError(
            "committed B-v2 execution source manifest contract is invalid"
        ) from exc
    if head_raw != canonical_json_bytes(manifest.to_dict()):
        raise C008CBPreflightError(
            "Git HEAD B-v2 execution source manifest byte mismatch"
        )
    return manifest


def validate_c008c_b_v2_execution_source_authority(
    root: Path | None = None,
) -> C008CBV2ExecutionSourceManifest:
    """Require current exact source bytes to match committed authority."""

    committed = load_committed_c008c_b_v2_execution_source_manifest(root)
    current = build_c008c_b_v2_execution_source_manifest(root)
    if current.to_dict() != committed.to_dict():
        raise C008CBPreflightError(
            "current formal B-v2 execution source differs from committed authority"
        )
    return committed


def validate_c008c_b_v2_execution_source_stability(
    source_before: C008CBV2ExecutionSourceManifest,
    source_after: C008CBV2ExecutionSourceManifest,
) -> None:
    """Fail the whole run if any formal source byte changes during execution."""

    if not isinstance(source_before, C008CBV2ExecutionSourceManifest) or not (
        isinstance(source_after, C008CBV2ExecutionSourceManifest)
    ):
        raise C008CBManifestError("B-v2 source stability requires source manifests")
    if source_before.to_dict() != source_after.to_dict():
        raise C008CBPreflightError(
            "formal B-v2 execution source changed during execution"
        )


__all__ = [
    "B_V2_EXECUTION_SOURCE_MANIFEST_PATH",
    "build_c008c_b_v2_execution_source_manifest",
    "load_committed_c008c_b_v2_execution_source_manifest",
    "validate_c008c_b_v2_execution_source_authority",
    "validate_c008c_b_v2_execution_source_stability",
]
