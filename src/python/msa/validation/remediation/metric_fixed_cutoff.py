"""C-008C-H3 reviewed Protected Source transition authority."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Mapping

from msa.validation.experiments.contracts import (
    ProtectedSourceFile,
    ProtectedSourceManifest,
)
from msa.validation.experiments.identity import (
    canonical_json_bytes,
    digest,
    semantic_id,
)

from .decimal_context import (
    REVIEWED_REMEDIATION_ID,
    check_existing_decimal_remediation_evidence,
)


H3_TRANSITION_EVIDENCE_PATH = Path(
    "docs/validation/evidence/c008c_h3_metric_fixed_cutoff_transition.json"
)
H3_TRANSITION_BASE_COMMIT = (
    "cdb6b9dd11ce8a39560d20fe4ea0fa428a293888"
)
H3_REVIEWED_SOURCE_COMMIT = (
    "db498d5d454c0fa923cf8fab73cafa0e7ee66a8b"
)
H3_TRANSITION_SCHEMA_VERSION = 1
H3_REVIEWED_TRANSITION_ID = (
    "c008c-h3-protected-source-transition-v1-"
    "77f8fa90e463fade77041de6f5bbbbdc500f6f613661af3cffb1763cef66f3a4"
)

_HISTORICAL_MANIFEST_PATH = Path(
    "docs/validation/evidence/c008c_protected_source_manifest.json"
)
_HISTORICAL_MANIFEST_ID = (
    "c008c-protected-source-manifest-v1-"
    "f93cda3d0966ee1340addebe36e8c008591d94d19d966828471721a18fdf2356"
)
_HISTORICAL_MANIFEST_SHA256 = (
    "a4651a946ddc3731d35953e01d2018874672504a48eba74e87819ffb47d649a7"
)
_H2_EVIDENCE_SHA256 = (
    "97bb6868eb343572851aef07d32da805a71433549bf2d471d7dae9b11b467431"
)
_EVENTS_PATH = "src/python/msa/validation/metrics/events.py"
_EVENTS_BEFORE_BLOB_SHA = "127cd8d557122fe970e3e467bb0d73a49d3f7d44"
_EVENTS_BEFORE_SHA256 = (
    "fc11b023054b446ba7d0f565a46437aa6a6330a64e51b6b00737494fdf96138a"
)
_EVENTS_AFTER_BLOB_SHA = "855973d1d9222ddd6ac5e47c0e8b4f7ac619b5a3"
_EVENTS_AFTER_SHA256 = (
    "5b738822a1446ad592e4328f9d553b0eab8eaef7f7fb47212fae761343130ca9"
)


class ProtectedSourceTransitionError(ValueError):
    """Raised when the H3 transition differs from reviewed authority."""


def _root(root: Path | None) -> Path:
    result = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    if not (result / "pyproject.toml").is_file():
        raise ProtectedSourceTransitionError(
            "transition root is not an MSA checkout"
        )
    return result


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()  # noqa: S324


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, object]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise ProtectedSourceTransitionError(f"invalid {label}") from exc
    if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
        raise ProtectedSourceTransitionError(f"non-canonical {label}")
    return raw, payload


def _historical_manifest(
    base: Path,
    supplied: object | None = None,
) -> tuple[ProtectedSourceManifest, bytes]:
    raw, payload = _read_json(
        base / _HISTORICAL_MANIFEST_PATH,
        "historical Protected Source Manifest",
    )
    try:
        manifest = ProtectedSourceManifest.from_dict(payload)
        supplied_payload = (
            None if supplied is None else supplied.to_dict()
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ProtectedSourceTransitionError(
            "invalid historical Protected Source authority"
        ) from exc
    if (
        _sha256(raw) != _HISTORICAL_MANIFEST_SHA256
        or manifest.protected_source_manifest_id != _HISTORICAL_MANIFEST_ID
        or len(manifest.files) != 77
        or (supplied_payload is not None and supplied_payload != payload)
    ):
        raise ProtectedSourceTransitionError(
            "historical Protected Source authority changed"
        )
    return manifest, raw


def _h2_evidence(base: Path) -> tuple[dict[str, object], bytes]:
    path = check_existing_decimal_remediation_evidence(base)
    raw, payload = _read_json(path, "H2 Decimal remediation Evidence")
    if (
        _sha256(raw) != _H2_EVIDENCE_SHA256
        or payload.get("remediation_id") != REVIEWED_REMEDIATION_ID
    ):
        raise ProtectedSourceTransitionError(
            "H2 Decimal remediation Evidence changed"
        )
    return payload, raw


def _source_digest(files: tuple[ProtectedSourceFile, ...]) -> str:
    return digest(
        [
            {
                "relative_path": item.relative_path,
                "sha256": item.sha256,
            }
            for item in files
        ]
    )


def _manifest_from_files(
    template: ProtectedSourceManifest,
    files: tuple[ProtectedSourceFile, ...],
) -> ProtectedSourceManifest:
    payload = {
        "execution_base_commit": template.execution_base_commit,
        "core_reference_commit": template.core_reference_commit,
        "byte_policy": template.byte_policy,
        "files": [item.to_dict() for item in files],
        "schema_version": template.schema_version,
    }
    return ProtectedSourceManifest(
        protected_source_manifest_id=semantic_id(
            "c008c-protected-source-manifest-v1-", payload
        ),
        execution_base_commit=template.execution_base_commit,
        core_reference_commit=template.core_reference_commit,
        byte_policy=template.byte_policy,
        files=files,
        schema_version=template.schema_version,
    )


def _post_h2_manifest(
    base: Path,
    historical: ProtectedSourceManifest,
    h2_evidence: Mapping[str, object],
) -> tuple[ProtectedSourceManifest, ProtectedSourceManifest]:
    from msa.validation.experiments.protected_source import (
        build_protected_source_manifest,
    )

    current = build_protected_source_manifest(base)
    historical_by_path = {
        item.relative_path: item for item in historical.files
    }
    current_by_path = {item.relative_path: item for item in current.files}
    changes = h2_evidence.get("protected_source_changes")
    added = h2_evidence.get("added_arithmetic_authority")
    if not isinstance(changes, list) or not isinstance(added, dict):
        raise ProtectedSourceTransitionError(
            "H2 protected source transition is malformed"
        )
    expected_sha256 = {
        path: item.sha256 for path, item in historical_by_path.items()
    }
    for item in changes:
        if not isinstance(item, dict):
            raise ProtectedSourceTransitionError(
                "H2 protected source change is malformed"
            )
        expected_sha256[item["relative_path"]] = item["new_sha256"]
    added_path = added.get("relative_path")
    if not isinstance(added_path, str) or added_path not in current_by_path:
        raise ProtectedSourceTransitionError(
            "H2 added protected source is unavailable"
        )
    expected_sha256[added_path] = current_by_path[added_path].sha256
    if set(current_by_path) != set(expected_sha256):
        raise ProtectedSourceTransitionError(
            "protected source path set differs from post-H2 authority"
        )
    if expected_sha256.get(_EVENTS_PATH) != _EVENTS_BEFORE_SHA256:
        raise ProtectedSourceTransitionError(
            "events.py before digest is not post-H2 authority"
        )
    for path, expected in expected_sha256.items():
        if path == _EVENTS_PATH:
            if current_by_path[path].sha256 not in {
                _EVENTS_BEFORE_SHA256,
                _EVENTS_AFTER_SHA256,
            }:
                raise ProtectedSourceTransitionError(
                    "unreviewed protected source difference: events.py"
                )
        elif current_by_path[path].sha256 != expected:
            raise ProtectedSourceTransitionError(
                f"unreviewed protected source difference: {path}"
            )
    post_h2_files = tuple(
        historical_by_path[_EVENTS_PATH]
        if item.relative_path == _EVENTS_PATH
        else item
        for item in current.files
    )
    post_h2 = _manifest_from_files(current, post_h2_files)
    return post_h2, current


def validate_post_h2_protected_source_authority(
    historical_manifest: object,
    root: Path | None = None,
) -> ProtectedSourceManifest:
    """Rebuild the reviewed post-H2 authority without accepting H3."""

    base = _root(root)
    historical, _ = _historical_manifest(base, historical_manifest)
    h2_evidence, _ = _h2_evidence(base)
    post_h2, _ = _post_h2_manifest(base, historical, h2_evidence)
    return post_h2


def build_metric_fixed_cutoff_transition_evidence(
    root: Path | None = None,
) -> dict[str, object]:
    base = _root(root)
    historical, historical_raw = _historical_manifest(base)
    h2_evidence, h2_raw = _h2_evidence(base)
    post_h2, current = _post_h2_manifest(
        base, historical, h2_evidence
    )
    current_by_path = {item.relative_path: item for item in current.files}
    events = current_by_path[_EVENTS_PATH]
    events_raw = (base / _EVENTS_PATH).read_bytes()
    if (
        events.sha256 != _EVENTS_AFTER_SHA256
        or _git_blob_sha(events_raw) != _EVENTS_AFTER_BLOB_SHA
    ):
        raise ProtectedSourceTransitionError(
            "events.py differs from reviewed H3 remediation"
        )
    payload: dict[str, object] = {
        "transition_version": (
            "C008C_H3_METRIC_FIXED_CUTOFF_PROTECTED_SOURCE_TRANSITION_V1"
        ),
        "transition_base_commit": H3_TRANSITION_BASE_COMMIT,
        "reviewed_source_commit": H3_REVIEWED_SOURCE_COMMIT,
        "historical_authority": {
            "relative_path": _HISTORICAL_MANIFEST_PATH.as_posix(),
            "manifest_id": _HISTORICAL_MANIFEST_ID,
            "sha256": _sha256(historical_raw),
            "protected_path_count": len(historical.files),
        },
        "post_h2_authority": {
            "remediation_id": REVIEWED_REMEDIATION_ID,
            "evidence_sha256": _sha256(h2_raw),
            "protected_source_manifest_id": (
                post_h2.protected_source_manifest_id
            ),
            "protected_source_digest": _source_digest(post_h2.files),
            "protected_path_count": len(post_h2.files),
        },
        "reviewed_change": {
            "relative_path": _EVENTS_PATH,
            "before_blob_sha": _EVENTS_BEFORE_BLOB_SHA,
            "before_sha256": _EVENTS_BEFORE_SHA256,
            "after_blob_sha": _EVENTS_AFTER_BLOB_SHA,
            "after_sha256": _EVENTS_AFTER_SHA256,
        },
        "post_h3_authority": {
            "protected_source_manifest_id": (
                current.protected_source_manifest_id
            ),
            "protected_source_digest": _source_digest(current.files),
            "protected_path_count": len(current.files),
        },
        "protected_path_set_unchanged_from_post_h2": True,
        "historical_evidence_unchanged": True,
        "h2_remediation_evidence_unchanged": True,
        "b_v2_executed": False,
        "oos_executed": False,
        "schema_version": H3_TRANSITION_SCHEMA_VERSION,
    }
    return {
        "transition_id": semantic_id(
            "c008c-h3-protected-source-transition-v1-", payload
        ),
        "payload_sha256": digest(payload),
        **payload,
    }


def validate_metric_fixed_cutoff_transition_evidence(
    evidence: Mapping[str, object],
    root: Path | None = None,
) -> dict[str, object]:
    expected = build_metric_fixed_cutoff_transition_evidence(root)
    if dict(evidence) != expected:
        raise ProtectedSourceTransitionError(
            "H3 transition differs from current reviewed authority"
        )
    if evidence.get("transition_id") != H3_REVIEWED_TRANSITION_ID:
        raise ProtectedSourceTransitionError(
            "H3 transition differs from reviewed transition ID"
        )
    return dict(evidence)


def check_existing_metric_fixed_cutoff_transition_evidence(
    root: Path | None = None,
) -> Path:
    base = _root(root)
    path = base / H3_TRANSITION_EVIDENCE_PATH
    raw, payload = _read_json(path, "H3 Protected Source transition Evidence")
    validated = validate_metric_fixed_cutoff_transition_evidence(
        payload, base
    )
    if raw != canonical_json_bytes(validated):
        raise ProtectedSourceTransitionError(
            "H3 transition Evidence is non-canonical"
        )
    return path


def validate_historical_protected_source_transition(
    historical_manifest: object,
    root: Path | None = None,
) -> None:
    """Bridge immutable v1 through H2 to the reviewed post-H3 source."""

    base = _root(root)
    _historical_manifest(base, historical_manifest)
    check_existing_metric_fixed_cutoff_transition_evidence(base)


__all__ = [
    "H3_REVIEWED_TRANSITION_ID",
    "H3_TRANSITION_EVIDENCE_PATH",
    "ProtectedSourceTransitionError",
    "build_metric_fixed_cutoff_transition_evidence",
    "check_existing_metric_fixed_cutoff_transition_evidence",
    "validate_historical_protected_source_transition",
    "validate_metric_fixed_cutoff_transition_evidence",
    "validate_post_h2_protected_source_authority",
]
