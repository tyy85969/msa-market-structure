"""Project a compact C-009 Pine-parity fixture from an existing Core run.

This adapter only serializes already-computed reference facts.  It does not
change, rerun, or authorize any C-008 validation semantics.
"""

from __future__ import annotations

from typing import Any

from msa.research.msa_core import MSACoreRun


def _structure(evidence: Any) -> dict[str, object]:
    boundary = evidence.boundary
    return {
        "subject_id": evidence.subject_id,
        "origin_time": boundary.origin_time.isoformat(),
        "confirm_time": boundary.confirm_time.isoformat(),
        "state_confirm_time": evidence.state_confirm_time.isoformat(),
        "side": boundary.boundary_side.value,
        "price_range": {
            "low": str(boundary.price_range.low),
            "high": str(boundary.price_range.high),
        },
        "lifecycle_state": evidence.lifecycle_state.value,
        "tier": evidence.tier.value,
        "context": {
            "timeframe": evidence.context.timeframe.value,
            "scale": evidence.context.scale.scale_id,
        },
        "touch_count": evidence.touch_count,
    }


def _zone(zone: Any) -> dict[str, object]:
    return {
        "side": zone.side.value,
        "lower": str(zone.price_range.low),
        "upper": str(zone.price_range.high),
        "resonance_class": zone.resonance_class.value,
        "quality_score": str(zone.quality_score),
        "selection_score": str(zone.selection_score),
        "member_count": len(zone.member_evidence_ids),
        "context_count": zone.distinct_context_count,
    }


def _active_box(selection: Any) -> dict[str, object] | None:
    snapshot = selection.active_box_snapshot
    if snapshot is None:
        return None
    value = snapshot.active_box
    return {
        "status": value.status.value,
        "lower": str(value.lower_boundary.price_range.low),
        "upper": str(value.upper_boundary.price_range.high),
        "origin_time": value.origin_time.isoformat(),
        "confirm_time": value.confirm_time.isoformat(),
        "as_of_time": value.as_of_time.isoformat(),
    }


def build_c009_pine_reference(
    run: MSACoreRun,
    *,
    sample_id: str = "core-alpha-v1-deterministic-fixture",
) -> dict[str, object]:
    """Return key causal events from a supplied deterministic Core run."""

    if not isinstance(run, MSACoreRun):
        raise TypeError("run must be an MSACoreRun")
    frames: list[dict[str, object]] = []
    # Keep the checked-in fixture lightweight: first causal frame and final
    # state demonstrate candidate-to-confirmed progression without exporting a
    # research report or full C-008 artefacts.
    selected_bundles = (run.frame_bundles[0], run.final_bundle)
    for bundle in selected_bundles:
        frames.append(
            {
                "as_of_time": bundle.as_of_time.isoformat(),
                "structures": [
                    _structure(item) for item in bundle.resonance_frame.evidence
                ],
                "resonance_zones": [
                    _zone(item) for item in bundle.score_frame.zones
                ],
                "active_box": _active_box(bundle.selection_frame),
            }
        )
    transitions = [
        {
            "subject_id": event.subject_id,
            "event_type": event.event_type.value,
            "from_state": event.from_state.value,
            "to_state": event.to_state.value,
            "origin_time": event.event_origin_time.isoformat(),
            "confirm_time": event.event_confirm_time.isoformat(),
        }
        for event in run.source_input.lifecycle_history.events
    ]
    return {
        "schema_version": 1,
        "purpose": "C-009 Pine migration parity fixture; not C-008 evidence",
        "sample": {
            "sample_id": sample_id,
            "run_id": run.run_id,
            "frame_count": len(frames),
        },
        "lifecycle_transitions": transitions,
        "frames": frames,
    }
