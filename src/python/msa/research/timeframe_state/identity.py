"""Private canonical identity helpers shared by generation and validation."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Mapping, Sequence


def _digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _engine_id_from_notes(notes: Sequence[str]) -> str:
    values = tuple(
        item.removeprefix("engine_id=")
        for item in notes
        if item.startswith("engine_id=")
    )
    if len(values) != 1 or not values[0]:
        raise ValueError("provenance notes must contain exactly one engine_id")
    return values[0]


def _state_id(
    *,
    engine_id: str,
    engine_version: str,
    policy_id: str,
    symbol: str,
    target_timeframe: str,
    target_scale: Mapping[str, object],
    selection_policy: str,
    direction: str,
    candidate_upper_boundary: object,
    candidate_lower_boundary: object,
    confirmed_upper_boundary: object,
    confirmed_lower_boundary: object,
    forming_candidate_ids: Sequence[str],
    origin_time: datetime,
    confirm_time: datetime,
    domain_schema_version: int,
    engine_schema_version: int,
) -> str:
    identity = {
        "engine_id": engine_id,
        "engine_version": engine_version,
        "policy_id": policy_id,
        "symbol": symbol,
        "target_timeframe": target_timeframe,
        "target_scale": dict(target_scale),
        "selection_policy": selection_policy,
        "direction": direction,
        "candidate_upper_boundary": candidate_upper_boundary,
        "candidate_lower_boundary": candidate_lower_boundary,
        "confirmed_upper_boundary": confirmed_upper_boundary,
        "confirmed_lower_boundary": confirmed_lower_boundary,
        "forming_candidate_ids": list(forming_candidate_ids),
        "origin_time": origin_time.isoformat(),
        "confirm_time": confirm_time.isoformat(),
        "domain_schema_version": domain_schema_version,
        "engine_schema_version": engine_schema_version,
    }
    return f"timeframe-state-v1-{_digest(identity)}"


def _event_id(
    *,
    engine_id: str,
    engine_version: str,
    policy_id: str,
    previous_state_id: str | None,
    current_state_id: str,
    event_type: str,
    event_confirm_time: datetime,
    previous_direction: str | None,
    current_direction: str,
    changed_fields: Sequence[str],
    source_lifecycle_snapshot_id: str,
    source_lifecycle_event_ids: Sequence[str],
    prior_event_id: str | None,
    schema_version: int,
) -> str:
    identity = {
        "engine_id": engine_id,
        "engine_version": engine_version,
        "policy_id": policy_id,
        "previous_state_id": previous_state_id,
        "current_state_id": current_state_id,
        "event_type": event_type,
        "event_confirm_time": event_confirm_time.isoformat(),
        "previous_direction": previous_direction,
        "current_direction": current_direction,
        "changed_fields": list(changed_fields),
        "source_lifecycle_snapshot_id": source_lifecycle_snapshot_id,
        "source_lifecycle_event_ids": list(source_lifecycle_event_ids),
        "prior_event_id": prior_event_id,
        "schema_version": schema_version,
    }
    time_key = event_confirm_time.strftime("%Y%m%dT%H%M%S.%fZ")
    return f"timeframe-state-event-v1-{time_key}-{_digest(identity)}"


def _snapshot_id(
    *,
    config: Mapping[str, object],
    source_lifecycle_snapshot_id: str,
    as_of_time: datetime,
    state: Mapping[str, object],
    explanation: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    report: Mapping[str, object],
    schema_version: int,
) -> str:
    identity = {
        "config": dict(config),
        "source_lifecycle_snapshot_id": source_lifecycle_snapshot_id,
        "as_of_time": as_of_time.isoformat(),
        "state": dict(state),
        "explanation": dict(explanation),
        "events": [dict(item) for item in events],
        "report": dict(report),
        "schema_version": schema_version,
    }
    return f"timeframe-state-snapshot-v1-{_digest(identity)}"
