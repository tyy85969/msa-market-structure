"""Private canonical identities for C-007A generation and validation."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping, Sequence


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reference_id(bar: Mapping[str, object], *, schema_version: int) -> str:
    return f"resonance-reference-v1-{_digest({'bar': dict(bar), 'schema_version': schema_version})}"


def _evidence_id(
    *,
    subject_id: str,
    lifecycle_state_id: str,
    lifecycle_event_id: str,
    boundary: Mapping[str, object],
    tier: str,
    context: Mapping[str, object],
    direction: str,
    lifecycle_state: str,
    structural_confirm_time: str,
    state_confirm_time: str,
    touch_count: int,
    source_types: Sequence[str],
    structure_families: Sequence[str],
    schema_version: int,
) -> str:
    identity = {
        "subject_id": subject_id,
        "lifecycle_state_id": lifecycle_state_id,
        "lifecycle_event_id": lifecycle_event_id,
        "boundary": dict(boundary),
        "tier": tier,
        "context": dict(context),
        "direction": direction,
        "lifecycle_state": lifecycle_state,
        "structural_confirm_time": structural_confirm_time,
        "state_confirm_time": state_confirm_time,
        "touch_count": touch_count,
        "source_types": list(source_types),
        "structure_families": list(structure_families),
        "schema_version": schema_version,
    }
    return f"resonance-evidence-v1-{_digest(identity)}"


def _frame_id(
    *,
    config: Mapping[str, object],
    as_of_time: str,
    source_lifecycle_snapshot_id: str,
    source_lifecycle_snapshot_time: str,
    reference_price_id: str,
    context_state_ids: Sequence[str],
    evidence_ids: Sequence[str],
    excluded_broken_subject_ids: Sequence[str],
    excluded_retired_subject_ids: Sequence[str],
    schema_version: int,
) -> str:
    identity = {
        "config": dict(config),
        "as_of_time": as_of_time,
        "source_lifecycle_snapshot_id": source_lifecycle_snapshot_id,
        "source_lifecycle_snapshot_time": source_lifecycle_snapshot_time,
        "reference_price_id": reference_price_id,
        "context_state_ids": list(context_state_ids),
        "evidence_ids": list(evidence_ids),
        "excluded_broken_subject_ids": list(excluded_broken_subject_ids),
        "excluded_retired_subject_ids": list(excluded_retired_subject_ids),
        "schema_version": schema_version,
    }
    return f"resonance-frame-v1-{_digest(identity)}"
