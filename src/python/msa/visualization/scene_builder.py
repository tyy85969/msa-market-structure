"""Project authoritative MSA Core output into a causal visual scene.

This module deliberately imports no engines.  It never detects structure,
clusters evidence, scores Zones, or selects an Active Box.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime

from msa.research.msa_core import MSACoreRun
from msa.research.resonance import ResonanceEvidenceTier
from msa.validation.contracts import SyntheticScenarioKind

from .contracts import (
    ADVICE_LABEL,
    CORE_STATUS,
    OOS_LABEL,
    PREVIEW_LABEL,
    BoundaryTier,
    DisplayState,
    VisualActiveBox,
    VisualBoundary,
    VisualCandle,
    VisualLevel,
    VisualScene,
    VisualZone,
)
from .errors import VisualPreviewScopeError, VisualSceneBuildError


def _semantic_id(prefix: str, payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return prefix + hashlib.sha256(raw).hexdigest()


def _unique(*values: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _candle(bar: object) -> VisualCandle:
    try:
        payload = bar.to_dict()
        source_id = _semantic_id("visual-candle-v1-", payload)
        return VisualCandle(
            source_id=source_id,
            timestamp=bar.timestamp,
            end_time=bar.end_time,
            available_time=bar.available_time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise VisualSceneBuildError("invalid public CanonicalBar payload") from exc


def _boundary(
    evidence: object,
    *,
    display_state: DisplayState,
    confirm_time: datetime,
    display_end_time: datetime,
    show_origin_extension: bool,
    source_bundle_id: str,
    maximum_context_rank: int,
) -> VisualBoundary:
    boundary = evidence.boundary
    tier = (
        BoundaryTier.CONFIRMED
        if evidence.tier is ResonanceEvidenceTier.CONFIRMED
        else BoundaryTier.CANDIDATE
    )
    level = (
        VisualLevel.HIGH_TIMEFRAME
        if evidence.context.scale.rank == maximum_context_rank
        else VisualLevel.MAJOR
    )
    identity = {
        "boundary_id": boundary.object_id,
        "subject_id": evidence.subject_id,
        "lifecycle_state_id": evidence.lifecycle_state_id,
        "display_state": display_state.value,
        "confirm_time": confirm_time.isoformat(),
        "display_end_time": display_end_time.isoformat(),
    }
    return VisualBoundary(
        visual_boundary_id=_semantic_id("visual-boundary-v1-", identity),
        boundary_id=boundary.object_id,
        subject_id=evidence.subject_id,
        side=boundary.boundary_side.value,
        tier=tier,
        visual_level=level,
        lifecycle_state=evidence.lifecycle_state.value,
        display_state=display_state,
        timeframe=evidence.context.timeframe.value,
        scale_id=evidence.context.scale.scale_id,
        price_low=boundary.price_range.low,
        price_high=boundary.price_range.high,
        origin_time=boundary.origin_time,
        confirm_time=confirm_time,
        display_end_time=display_end_time,
        show_origin_extension=show_origin_extension,
        source_ids=_unique(
            evidence.evidence_id,
            evidence.lifecycle_state_id,
            boundary.object_id,
            source_bundle_id,
        ),
    )


def _boundaries(run: MSACoreRun, as_of_time: datetime) -> tuple[VisualBoundary, ...]:
    records: dict[tuple[str, str], tuple[object, str]] = {}
    exclusions: dict[str, tuple[DisplayState, datetime, str]] = {}
    for bundle in run.frame_bundles:
        if bundle.as_of_time > as_of_time:
            continue
        frame = bundle.resonance_frame
        for evidence in frame.evidence:
            records.setdefault(
                (evidence.subject_id, evidence.lifecycle_state_id),
                (evidence, bundle.bundle_id),
            )
        for subject_id in frame.excluded_broken_subject_ids:
            exclusions.setdefault(
                subject_id, (DisplayState.BROKEN, bundle.as_of_time, bundle.bundle_id)
            )
        for subject_id in frame.excluded_retired_subject_ids:
            exclusions.setdefault(
                subject_id, (DisplayState.RETIRED, bundle.as_of_time, bundle.bundle_id)
            )

    by_subject: dict[str, list[tuple[object, str]]] = defaultdict(list)
    for evidence, bundle_id in records.values():
        by_subject[evidence.subject_id].append((evidence, bundle_id))

    maximum_rank = max(
        item.scale.rank for item in run.config_snapshot.frame_config.contexts
    )
    projected: list[VisualBoundary] = []
    for subject_id in sorted(by_subject):
        states = sorted(
            by_subject[subject_id],
            key=lambda item: (
                item[0].state_confirm_time,
                item[0].lifecycle_state_id,
            ),
        )
        exclusion = exclusions.get(subject_id)
        for index, (evidence, bundle_id) in enumerate(states):
            next_time = (
                states[index + 1][0].state_confirm_time
                if index + 1 < len(states)
                else (exclusion[1] if exclusion is not None else as_of_time)
            )
            projected.append(
                _boundary(
                    evidence,
                    display_state=DisplayState.ACTIVE,
                    confirm_time=evidence.state_confirm_time,
                    display_end_time=next_time,
                    show_origin_extension=index == 0,
                    source_bundle_id=bundle_id,
                    maximum_context_rank=maximum_rank,
                )
            )
        if exclusion is not None:
            state, exclusion_time, exclusion_bundle_id = exclusion
            last_evidence = states[-1][0]
            projected.append(
                _boundary(
                    last_evidence,
                    display_state=state,
                    confirm_time=exclusion_time,
                    display_end_time=as_of_time,
                    show_origin_extension=False,
                    source_bundle_id=exclusion_bundle_id,
                    maximum_context_rank=maximum_rank,
                )
            )
    return tuple(
        sorted(
            projected,
            key=lambda item: (
                item.confirm_time,
                item.subject_id,
                item.visual_boundary_id,
            ),
        )
    )


def _zones(run: MSACoreRun) -> tuple[VisualZone, ...]:
    bundle = run.final_bundle
    evidence = {
        item.evidence_id: item for item in bundle.resonance_frame.evidence
    }
    zones: list[VisualZone] = []
    for zone in bundle.score_frame.zones:
        try:
            members = tuple(evidence[item] for item in zone.member_evidence_ids)
        except KeyError as exc:
            raise VisualSceneBuildError(
                "Zone members are not present in the authoritative Frame Bundle"
            ) from exc
        zones.append(
            VisualZone(
                zone_key_id=zone.zone_key_id,
                zone_snapshot_id=zone.zone_snapshot_id,
                side=zone.side.value,
                resonance_class=zone.resonance_class.value,
                price_low=zone.price_range.low,
                price_high=zone.price_range.high,
                origin_time=min(item.boundary.origin_time for item in members),
                confirm_time=zone.latest_evidence_confirm_time,
                candidate_count=zone.candidate_count,
                confirmed_count=zone.confirmed_count,
                source_ids=_unique(
                    zone.zone_snapshot_id,
                    zone.zone_key_id,
                    zone.source_frame_id,
                    *zone.member_evidence_ids,
                ),
            )
        )
    return tuple(zones)


def _active_box(run: MSACoreRun) -> VisualActiveBox | None:
    frame = run.final_bundle.selection_frame
    snapshot = frame.active_box_snapshot
    if snapshot is None:
        return None
    box = snapshot.active_box
    return VisualActiveBox(
        box_id=box.box_id,
        status=box.status.value,
        lower_low=box.lower_boundary.price_range.low,
        lower_high=box.lower_boundary.price_range.high,
        upper_low=box.upper_boundary.price_range.low,
        upper_high=box.upper_boundary.price_range.high,
        origin_time=box.origin_time,
        confirm_time=box.confirm_time,
        source_ids=_unique(
            snapshot.box_snapshot_id,
            snapshot.box_key_id,
            frame.selection_frame_id,
            frame.source_score_frame_id,
            snapshot.observed_lower_zone_snapshot_id,
            snapshot.observed_upper_zone_snapshot_id,
        ),
    )


def build_visual_scene(
    scenario: SyntheticScenarioKind,
    seed: int,
    run: MSACoreRun,
) -> VisualScene:
    """Build one final-AsOf scene from an already executed public Core run."""

    if seed != 2:
        raise VisualPreviewScopeError(
            "bounded visual preview permits only VALIDATION seed 2"
        )
    if not isinstance(scenario, SyntheticScenarioKind):
        raise VisualPreviewScopeError("scenario must be SyntheticScenarioKind")
    if not isinstance(run, MSACoreRun):
        raise VisualSceneBuildError("run must be an MSACoreRun")

    bundle = run.final_bundle
    as_of_time = bundle.as_of_time
    candles = tuple(
        _candle(bar)
        for bar in run.source_input.reference_price_data.bars
        if bar.is_complete and bar.available_time <= as_of_time
    )
    boundaries = _boundaries(run, as_of_time)
    confirmed = tuple(
        item for item in boundaries if item.tier is BoundaryTier.CONFIRMED
    )
    candidates = tuple(
        item for item in boundaries if item.tier is BoundaryTier.CANDIDATE
    )
    return VisualScene(
        scenario=scenario.value,
        seed=seed,
        partition="VALIDATION",
        as_of_time=as_of_time,
        symbol=run.config_snapshot.frame_config.symbol,
        reference_timeframe=(
            run.config_snapshot.frame_config.reference_price_timeframe.value
        ),
        preview_label=PREVIEW_LABEL,
        oos_label=OOS_LABEL,
        advice_label=ADVICE_LABEL,
        core_status=CORE_STATUS,
        candles=candles,
        confirmed_boundaries=confirmed,
        candidate_boundaries=candidates,
        resonance_zones=_zones(run),
        active_box=_active_box(run),
        source_ids=_unique(
            run.run_id,
            bundle.bundle_id,
            bundle.resonance_frame.frame_id,
            bundle.score_frame.score_frame_id,
            bundle.selection_frame.selection_frame_id,
        ),
    )
