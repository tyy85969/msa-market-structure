"""Canonical JSON and SHA-256 identities for C-007C contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Mapping

from msa.data import Timeframe
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    LifecycleState,
    MarketRole,
    PriceRange,
    ScaleDescriptor,
)

if TYPE_CHECKING:
    from .contracts import ActiveBoxSelectionConfig


def canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def semantic_id(prefix: str, payload: Mapping[str, object]) -> str:
    return f"{prefix}{digest(payload)}"


def cluster_identity_payload(
    *,
    config: "ActiveBoxSelectionConfig",
    source_score_frame_id: str,
    source_zone_key_id: str,
    source_zone_snapshot_id: str,
    selection_confirm_time: datetime,
    symbol: str,
    timeframe: Timeframe,
    scale: ScaleDescriptor,
    price_range: PriceRange,
    boundary_side: BoundarySide,
    market_role: MarketRole,
    lifecycle_state: LifecycleState,
    origin_time: datetime,
    member_refs: tuple[BoundaryRef, ...],
    cluster_family: str,
    schema_version: int,
) -> dict[str, object]:
    """Return the one authoritative C-007C aggregate Cluster identity payload."""
    return {
        "config": config.to_dict(),
        "source_score_frame_id": source_score_frame_id,
        "source_zone_key_id": source_zone_key_id,
        "source_zone_snapshot_id": source_zone_snapshot_id,
        "selection_confirm_time": selection_confirm_time.isoformat(),
        "symbol": symbol,
        "timeframe": timeframe.value,
        "scale": scale.to_dict(),
        "price_range": price_range.to_dict(),
        "boundary_side": boundary_side.value,
        "market_role": market_role.value,
        "lifecycle_state": lifecycle_state.value,
        "origin_time": origin_time.isoformat(),
        "member_refs": [item.to_dict() for item in member_refs],
        "cluster_family": cluster_family,
        "schema_version": schema_version,
    }


def require_semantic_id(
    value: object,
    prefix: str,
    payload: Mapping[str, object],
    field_name: str,
    error_type: type[Exception],
) -> str:
    if not isinstance(value, str):
        raise error_type(f"{field_name} must be a string")
    expected = semantic_id(prefix, payload)
    if value != expected:
        raise error_type(f"{field_name} does not match exact semantic payload")
    return value
