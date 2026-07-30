from dataclasses import replace
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

from msa.validation.experiments import (
    ExperimentProtectedSourceError,
    PROTECTED_SOURCE_BYTE_POLICY,
    build_protected_source_manifest,
    validate_protected_source_manifest,
)


ROOT = Path(__file__).resolve().parents[3]


def test_protected_manifest_is_sorted_relative_and_source_bound() -> None:
    manifest = build_protected_source_manifest()
    paths = tuple(item.relative_path for item in manifest.files)
    assert len(manifest.files) == 77
    assert paths == tuple(sorted(paths))
    assert len(set(paths)) == len(paths)
    assert all("\\" not in item and not item.startswith("/") for item in paths)
    assert not any("/validation/experiments/" in item for item in paths)
    assert manifest.byte_policy == PROTECTED_SOURCE_BYTE_POLICY
    assert validate_protected_source_manifest(manifest) == manifest


def test_protected_source_change_fails_closed() -> None:
    manifest = build_protected_source_manifest()
    first = replace(manifest.files[0], sha256="0" * 64)
    with pytest.raises(ExperimentProtectedSourceError):
        replace(manifest, files=(first, *manifest.files[1:]))


def test_all_protected_worktree_bytes_are_lf_and_match_manifest() -> None:
    manifest = build_protected_source_manifest()
    for entry in manifest.files:
        data = (ROOT / entry.relative_path).read_bytes()
        assert b"\r" not in data
        assert len(data) == entry.byte_size
        assert hashlib.sha256(data).hexdigest() == entry.sha256


def test_all_protected_paths_are_declared_eol_lf() -> None:
    manifest = build_protected_source_manifest()
    paths = [item.relative_path for item in manifest.files]
    result = subprocess.run(
        ["git", "check-attr", "eol", "--", *paths],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = tuple(item for item in result.stdout.splitlines() if item)
    assert len(lines) == 77
    assert all(item.endswith(": eol: lf") for item in lines)


def test_validator_rejects_crlf_without_repairing_bytes() -> None:
    manifest = build_protected_source_manifest()
    with tempfile.TemporaryDirectory(
        prefix=".c008c-protected-", dir=ROOT
    ) as directory:
        temporary_root = Path(directory)
        for entry in manifest.files:
            source = ROOT / entry.relative_path
            target = temporary_root / entry.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        target_entry = next(
            item
            for item in manifest.files
            if b"\n"
            in (temporary_root / item.relative_path).read_bytes()
        )
        target = temporary_root / target_entry.relative_path
        original = target.read_bytes()
        crlf = original.replace(b"\n", b"\r\n")
        target.write_bytes(crlf)

        with pytest.raises(ExperimentProtectedSourceError):
            validate_protected_source_manifest(manifest, temporary_root)
        assert target.read_bytes() == crlf
