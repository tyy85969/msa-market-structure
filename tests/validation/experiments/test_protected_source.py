from dataclasses import replace

import pytest

from msa.validation.experiments import (
    ExperimentProtectedSourceError,
    build_protected_source_manifest,
    validate_protected_source_manifest,
)


def test_protected_manifest_is_sorted_relative_and_source_bound() -> None:
    manifest = build_protected_source_manifest()
    paths = tuple(item.relative_path for item in manifest.files)
    assert len(manifest.files) == 77
    assert paths == tuple(sorted(paths))
    assert len(set(paths)) == len(paths)
    assert all("\\" not in item and not item.startswith("/") for item in paths)
    assert not any("/validation/experiments/" in item for item in paths)
    assert validate_protected_source_manifest(manifest) == manifest


def test_protected_source_change_fails_closed() -> None:
    manifest = build_protected_source_manifest()
    first = replace(manifest.files[0], sha256="0" * 64)
    with pytest.raises(ExperimentProtectedSourceError):
        replace(manifest, files=(first, *manifest.files[1:]))
