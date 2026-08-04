"""Deterministic dependency-aware C-007B resonance scoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from typing import Any, Mapping

from msa.domain import BoundarySide, LifecycleState, PriceRange, ProvenanceRef

from .contracts import ResonanceEvidence, ResonanceEvidenceTier, ResonanceFrame, ResonanceFrameHistory
from .decimal_arithmetic import canonical_decimal_boundary
from .errors import (
    ResonanceScoringConfigurationError,
    ResonanceScoringEngineError,
    ResonanceScoringInputError,
    ResonanceScoringSerializationError,
)
from .scoring_contracts import (
    SCHEMA_VERSION,
    _ASSUMPTIONS,
    _SCORING_MODULE,
    _component_id,
    _context_key,
    _contribution_id,
    _dependency_edges,
    _dependency_partition,
    _direction_factor,
    _direction_relation,
    _elapsed_seconds,
    _exact_payload,
    _lifecycle_weight,
    _price_relation_and_distance,
    _range_gap,
    _rank_sort_key,
    _report_for,
    _score_frame_id,
    _shared_component_families,
    _zone_key_id,
    _zone_snapshot_id,
    ResonanceClass,
    ResonanceClassRationale,
    ResonanceDependencyComponent,
    ResonanceEvidenceContribution,
    ResonanceRankKey,
    ResonanceRangeGap,
    ResonanceScoreFrame,
    ResonanceScoreHistory,
    ResonanceScoringConfig,
    ResonanceZone,
    ResonanceZoneExplanation,
)


def _evidence_key(item: ResonanceEvidence) -> tuple[object, ...]:
    return (
        item.boundary.boundary_side.value,
        item.boundary.price_range.low,
        item.boundary.price_range.high,
        item.subject_id,
        item.evidence_id,
    )


def _price_components(
    evidence: tuple[ResonanceEvidence, ...], tolerance: Decimal
) -> tuple[tuple[ResonanceEvidence, ...], ...]:
    ordered = tuple(sorted(evidence, key=_evidence_key))
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        parent[max(left_root, right_root)] = min(left_root, right_root)

    for left, right in combinations(range(len(ordered)), 2):
        if ordered[left].boundary.boundary_side is not ordered[right].boundary.boundary_side:
            continue
        if _range_gap(ordered[left].boundary.price_range, ordered[right].boundary.price_range) <= tolerance:
            union(left, right)
    grouped: dict[int, list[ResonanceEvidence]] = {}
    for index, item in enumerate(ordered):
        grouped.setdefault(find(index), []).append(item)
    return tuple(
        sorted(
            (tuple(sorted(items, key=lambda item: item.evidence_id)) for items in grouped.values()),
            key=lambda items: (
                0 if items[0].boundary.boundary_side is BoundarySide.UPPER else 1,
                tuple(item.evidence_id for item in items),
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class _ZoneDraft:
    values: tuple[tuple[str, object], ...]

    def get(self, name: str) -> object:
        return dict(self.values)[name]


@dataclass(frozen=True, slots=True)
class ResonanceScorer:
    config: ResonanceScoringConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.config, ResonanceScoringConfig):
            raise ResonanceScoringConfigurationError(
                "ResonanceScorer.config must be a ResonanceScoringConfig"
            )
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise ResonanceScoringConfigurationError(
                f"ResonanceScorer.schema_version must be {SCHEMA_VERSION}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceScorer:
        data = _exact_payload(payload, cls.__name__, {"config"})
        try:
            return cls(
                config=ResonanceScoringConfig.from_dict(data["config"]),
                schema_version=data["schema_version"],
            )
        except ResonanceScoringSerializationError:
            raise
        except (TypeError, ValueError, RuntimeError) as exc:
            raise ResonanceScoringSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc

    @canonical_decimal_boundary
    def score_frame(self, frame: ResonanceFrame) -> ResonanceScoreFrame:
        self._validate_frame(frame)
        tolerance = self.config.effective_tolerance(frame.reference_price.price)
        drafts = tuple(
            self._draft(frame, members, tolerance)
            for members in _price_components(frame.evidence, tolerance)
        )
        upper_drafts = tuple(
            sorted(
                (item for item in drafts if item.get("side") is BoundarySide.UPPER),
                key=self._draft_rank_key,
            )
        )
        lower_drafts = tuple(
            sorted(
                (item for item in drafts if item.get("side") is BoundarySide.LOWER),
                key=self._draft_rank_key,
            )
        )
        zones = tuple(
            self._zone(item, rank)
            for values in (upper_drafts, lower_drafts)
            for rank, item in enumerate(values, 1)
        )
        report = _report_for(frame, zones, self.config)
        score_frame_id = _score_frame_id(
            source_frame_id=frame.frame_id,
            as_of_time=frame.as_of_time.isoformat(),
            config=self.config.to_dict(),
            zone_snapshot_ids=tuple(item.zone_snapshot_id for item in zones),
            report=report.to_dict(),
            schema_version=SCHEMA_VERSION,
        )
        provenance = ProvenanceRef(
            source_module=_SCORING_MODULE,
            source_version=self.config.engine_version,
            source_object_id=score_frame_id,
            policy_id=self.config.policy_id,
            parent_object_ids=tuple(sorted({
                frame.frame_id,
                *(item.zone_snapshot_id for item in zones),
            })),
            notes=(f"engine_id={self.config.engine_id}",),
        )
        return ResonanceScoreFrame(
            score_frame_id=score_frame_id,
            as_of_time=frame.as_of_time,
            source_frame_id=frame.frame_id,
            source_frame=frame,
            zones=zones,
            report=report,
            config_snapshot=self.config,
            provenance=provenance,
        )

    def build_batch(self, history: ResonanceFrameHistory) -> ResonanceScoreHistory:
        if not isinstance(history, ResonanceFrameHistory):
            raise ResonanceScoringInputError(
                "build_batch requires a ResonanceFrameHistory"
            )
        frames = tuple(self.score_frame(item) for item in history.frames)
        return ResonanceScoreHistory(
            frames=frames,
            final_frame=frames[-1],
            source_history=history,
            config_snapshot=self.config,
        )

    def _validate_frame(self, frame: ResonanceFrame) -> None:
        if not isinstance(frame, ResonanceFrame):
            raise ResonanceScoringInputError(
                "C-007B consumes only an authoritative ResonanceFrame"
            )
        config_contexts = tuple(item.context for item in self.config.context_weights)
        if config_contexts != frame.config_snapshot.contexts:
            raise ResonanceScoringInputError(
                "context_weights must exactly cover source Frame contexts"
            )
        if any(item.state_confirm_time > frame.as_of_time for item in frame.evidence):
            raise ResonanceScoringInputError(
                "source Frame contains future Evidence"
            )
        tolerance = self.config.effective_tolerance(frame.reference_price.price)
        horizon = self.config.distance_horizon(frame.reference_price.price)
        if tolerance <= 0 or horizon <= 0:
            raise ResonanceScoringInputError(
                "effective tolerance and distance horizon must be > 0"
            )

    def _draft(
        self,
        frame: ResonanceFrame,
        members: tuple[ResonanceEvidence, ...],
        tolerance: Decimal,
    ) -> _ZoneDraft:
        side = members[0].boundary.boundary_side
        price_range = PriceRange(
            min(item.boundary.price_range.low for item in members),
            max(item.boundary.price_range.high for item in members),
        )
        member_ids = tuple(item.evidence_id for item in members)
        subject_ids = tuple(sorted(item.subject_id for item in members))
        contexts = tuple(sorted({item.context for item in members}, key=_context_key))
        source_types = tuple(sorted({source for item in members for source in item.source_types}, key=lambda item: item.value))
        families = tuple(sorted({family for item in members for family in item.structure_families}))
        contribution_values: dict[str, dict[str, object]] = {}
        dependency_components = _dependency_partition(members)
        component_ids: dict[str, str] = {}
        component_shared: dict[str, tuple[str, ...]] = {}
        for component_members in dependency_components:
            ids = tuple(item.evidence_id for item in component_members)
            shared = _shared_component_families(component_members)
            component_id = _component_id(
                engine_id=self.config.engine_id,
                engine_version=self.config.engine_version,
                policy_id=self.config.policy_id,
                member_evidence_ids=ids,
                shared_family_ids=shared,
                schema_version=SCHEMA_VERSION,
            )
            for item in component_members:
                component_ids[item.evidence_id] = component_id
            component_shared[component_id] = shared
        for evidence in members:
            relation = _direction_relation(side, evidence.direction)
            age = _elapsed_seconds(frame.as_of_time - evidence.state_confirm_time)
            if age < 0:
                raise ResonanceScoringInputError("Evidence state_confirm_time follows Frame as_of_time")
            freshness = max(
                self.config.freshness_floor,
                Decimal("1") - age / self.config.freshness_horizon_seconds,
            )
            extra_touches = max(0, evidence.touch_count - 1)
            touch = max(
                self.config.touch_floor,
                Decimal("1") - Decimal(extra_touches) * self.config.touch_penalty_per_extra,
            )
            tier_weight = (
                self.config.candidate_tier_weight
                if evidence.tier is ResonanceEvidenceTier.CANDIDATE
                else self.config.confirmed_tier_weight
            )
            lifecycle_weight = _lifecycle_weight(evidence.lifecycle_state, self.config)
            direction_factor = _direction_factor(relation, self.config)
            context_weight = self.config.context_weight(evidence.context)
            raw = context_weight * tier_weight * lifecycle_weight * freshness * touch * direction_factor
            values: dict[str, object] = {
                "evidence_id": evidence.evidence_id,
                "subject_id": evidence.subject_id,
                "lifecycle_state_id": evidence.lifecycle_state_id,
                "context": evidence.context,
                "side": side,
                "tier": evidence.tier,
                "lifecycle_state": evidence.lifecycle_state,
                "direction": evidence.direction,
                "direction_relation": relation,
                "context_weight": context_weight,
                "tier_weight": tier_weight,
                "lifecycle_weight": lifecycle_weight,
                "age_seconds": age,
                "freshness_factor": freshness,
                "touch_count": evidence.touch_count,
                "extra_touches": extra_touches,
                "touch_factor": touch,
                "direction_factor": direction_factor,
                "raw_contribution": raw,
                "dependency_component_id": component_ids[evidence.evidence_id],
            }
            contribution_id = _contribution_id(
                config=self.config.to_dict(),
                evidence_id=evidence.evidence_id,
                subject_id=evidence.subject_id,
                lifecycle_state_id=evidence.lifecycle_state_id,
                context=evidence.context.to_dict(),
                side=side.value,
                tier=evidence.tier.value,
                lifecycle_state=evidence.lifecycle_state.value,
                direction=evidence.direction.value,
                direction_relation=relation.value,
                context_weight=str(context_weight),
                tier_weight=str(tier_weight),
                lifecycle_weight=str(lifecycle_weight),
                age_seconds=str(age),
                freshness_factor=str(freshness),
                touch_count=evidence.touch_count,
                extra_touches=extra_touches,
                touch_factor=str(touch),
                direction_factor=str(direction_factor),
                raw_contribution=str(raw),
                dependency_component_id=component_ids[evidence.evidence_id],
                schema_version=SCHEMA_VERSION,
            )
            values["contribution_id"] = contribution_id
            contribution_values[evidence.evidence_id] = values
        contributions = tuple(
            ResonanceEvidenceContribution(**contribution_values[item_id])  # type: ignore[arg-type]
            for item_id in member_ids
        )
        contributions_by_id = {item.evidence_id: item for item in contributions}
        components: list[ResonanceDependencyComponent] = []
        for component_members in dependency_components:
            ids = tuple(item.evidence_id for item in component_members)
            ordered = tuple(sorted((contributions_by_id[item] for item in ids), key=lambda item: (-item.raw_contribution, item.evidence_id)))
            primary = ordered[0]
            repeated = sum((item.raw_contribution for item in ordered[1:]), Decimal("0"))
            component_id = component_ids[ids[0]]
            components.append(
                ResonanceDependencyComponent(
                    component_id=component_id,
                    member_evidence_ids=ids,
                    shared_family_ids=component_shared[component_id],
                    primary_evidence_id=primary.evidence_id,
                    primary_raw_contribution=primary.raw_contribution,
                    repeated_raw_contribution=repeated,
                    repeat_credit=self.config.dependency_repeat_credit,
                    adjusted_component_score=primary.raw_contribution + self.config.dependency_repeat_credit * repeated,
                )
            )
        ordered_components = tuple(sorted(components, key=lambda item: item.component_id))
        dependency_base = sum((item.adjusted_component_score for item in ordered_components), Decimal("0"))
        source_bonus = min(
            self.config.source_diversity_bonus_cap,
            Decimal(max(0, len(source_types) - 1)) * self.config.source_diversity_bonus_per_extra,
        )
        context_bonus = min(
            self.config.context_diversity_bonus_cap,
            Decimal(max(0, len(contexts) - 1)) * self.config.context_diversity_bonus_per_extra,
        )
        quality = dependency_base + source_bonus + context_bonus
        price = frame.reference_price.price
        price_relation, distance = _price_relation_and_distance(side, price_range, price)
        distance_horizon = self.config.distance_horizon(price)
        distance_factor = max(Decimal("0"), Decimal("1") - distance / distance_horizon)
        placement = {
            "EXPECTED_SIDE": self.config.expected_side_factor,
            "CONTAINS_PRICE": self.config.contains_price_factor,
            "OPPOSITE_SIDE": self.config.opposite_side_factor,
        }[price_relation.value]
        selection = quality * distance_factor * placement
        resonance_class = (
            ResonanceClass.SINGLE
            if len(members) == 1
            else ResonanceClass.MULTI_CONTEXT_RESONANCE
            if len(members) >= self.config.minimum_resonant_evidence_count
            and len(contexts) >= self.config.minimum_resonant_context_count
            else ResonanceClass.LOCAL_CLUSTER
        )
        member_boundary_ranges = tuple(
            {"subject_id": item.subject_id, "price_range": item.boundary.price_range.to_dict()}
            for item in sorted(members, key=lambda item: item.subject_id)
        )
        zone_key_id = _zone_key_id(
            engine_id=self.config.engine_id,
            engine_version=self.config.engine_version,
            policy_id=self.config.policy_id,
            side=side.value,
            price_range=price_range.to_dict(),
            member_subject_ids=subject_ids,
            member_boundary_ranges=member_boundary_ranges,
            schema_version=SCHEMA_VERSION,
        )
        score_payload = {
            "dependency_adjusted_base_score": str(dependency_base),
            "source_diversity_bonus": str(source_bonus),
            "context_diversity_bonus": str(context_bonus),
            "quality_score": str(quality),
            "reference_price": str(price),
            "distance_factor": str(distance_factor),
            "placement_factor": str(placement),
            "selection_score": str(selection),
        }
        zone_snapshot_id = _zone_snapshot_id(
            source_frame_id=frame.frame_id,
            config=self.config.to_dict(),
            zone_key_id=zone_key_id,
            member_evidence_ids=member_ids,
            contribution_ids=tuple(item.contribution_id for item in contributions),
            dependency_component_ids=tuple(item.component_id for item in ordered_components),
            scores=score_payload,
            price_relation=price_relation.value,
            distance=str(distance),
            resonance_class=resonance_class.value,
            schema_version=SCHEMA_VERSION,
        )
        direct_gaps = tuple(
            ResonanceRangeGap(
                left_evidence_id=left.evidence_id,
                right_evidence_id=right.evidence_id,
                gap=_range_gap(left.boundary.price_range, right.boundary.price_range),
                directly_connected=_range_gap(left.boundary.price_range, right.boundary.price_range) <= tolerance,
            )
            for left, right in combinations(sorted(members, key=lambda item: item.evidence_id), 2)
        )
        rationale = ResonanceClassRationale(
            evidence_count=len(members),
            distinct_context_count=len(contexts),
            minimum_resonant_evidence_count=self.config.minimum_resonant_evidence_count,
            minimum_resonant_context_count=self.config.minimum_resonant_context_count,
            assigned_class=resonance_class,
        )
        provenance = ProvenanceRef(
            source_module=_SCORING_MODULE,
            source_version=self.config.engine_version,
            source_object_id=zone_snapshot_id,
            policy_id=self.config.policy_id,
            parent_object_ids=tuple(sorted({
                frame.frame_id,
                *member_ids,
                *(item.contribution_id for item in contributions),
                *(item.component_id for item in ordered_components),
            })),
            notes=(f"engine_id={self.config.engine_id}",),
        )
        values: dict[str, object] = {
            "zone_key_id": zone_key_id,
            "zone_snapshot_id": zone_snapshot_id,
            "source_frame_id": frame.frame_id,
            "side": side,
            "price_range": price_range,
            "resonance_class": resonance_class,
            "member_evidence_ids": member_ids,
            "member_subject_ids": subject_ids,
            "contexts": contexts,
            "source_types": source_types,
            "structure_families": families,
            "candidate_count": sum(item.tier is ResonanceEvidenceTier.CANDIDATE for item in members),
            "confirmed_count": sum(item.tier is ResonanceEvidenceTier.CONFIRMED for item in members),
            "fresh_count": sum(item.lifecycle_state is LifecycleState.FRESH for item in members),
            "tested_count": sum(item.lifecycle_state is LifecycleState.TESTED for item in members),
            "weakened_count": sum(item.lifecycle_state is LifecycleState.WEAKENED for item in members),
            "flipped_count": sum(item.lifecycle_state is LifecycleState.FLIPPED for item in members),
            "distinct_context_count": len(contexts),
            "distinct_source_type_count": len(source_types),
            "distinct_structure_family_count": len(families),
            "earliest_evidence_confirm_time": min(item.state_confirm_time for item in members),
            "latest_evidence_confirm_time": max(item.state_confirm_time for item in members),
            "dependency_components": ordered_components,
            "contributions": contributions,
            "dependency_adjusted_base_score": dependency_base,
            "source_diversity_bonus": source_bonus,
            "context_diversity_bonus": context_bonus,
            "quality_score": quality,
            "reference_price": price,
            "price_relation": price_relation,
            "distance": distance,
            "distance_horizon": distance_horizon,
            "distance_factor": distance_factor,
            "placement_factor": placement,
            "selection_score": selection,
            "effective_tolerance": tolerance,
            "direct_gaps": direct_gaps,
            "chain_bridged": len(members) > 2 and any(not item.directly_connected for item in direct_gaps),
            "dependency_edges": _dependency_edges(members),
            "rationale": rationale,
            "provenance": provenance,
        }
        return _ZoneDraft(tuple(values.items()))

    @staticmethod
    def _draft_rank_key(item: _ZoneDraft) -> tuple[object, ...]:
        latest = item.get("latest_evidence_confirm_time")
        if not isinstance(latest, datetime):
            raise ResonanceScoringEngineError(
                "zone draft latest_evidence_confirm_time must be a datetime"
            )
        epoch = datetime(1970, 1, 1, tzinfo=latest.tzinfo)
        delta = latest - epoch
        micros = delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
        return (
            -item.get("selection_score"),  # type: ignore[operator]
            -item.get("quality_score"),  # type: ignore[operator]
            -item.get("distinct_context_count"),  # type: ignore[operator]
            -item.get("distinct_source_type_count"),  # type: ignore[operator]
            item.get("distance"),
            -micros,
            item.get("zone_key_id"),
            item.get("zone_snapshot_id"),
        )

    def _zone(self, draft: _ZoneDraft, side_rank: int) -> ResonanceZone:
        rank_key = ResonanceRankKey(
            selection_score=draft.get("selection_score"),  # type: ignore[arg-type]
            quality_score=draft.get("quality_score"),  # type: ignore[arg-type]
            distinct_context_count=draft.get("distinct_context_count"),  # type: ignore[arg-type]
            distinct_source_type_count=draft.get("distinct_source_type_count"),  # type: ignore[arg-type]
            distance=draft.get("distance"),  # type: ignore[arg-type]
            latest_evidence_confirm_time=draft.get("latest_evidence_confirm_time"),  # type: ignore[arg-type]
            zone_key_id=draft.get("zone_key_id"),  # type: ignore[arg-type]
            zone_snapshot_id=draft.get("zone_snapshot_id"),  # type: ignore[arg-type]
        )
        explanation = ResonanceZoneExplanation(
            effective_clustering_tolerance=draft.get("effective_tolerance"),  # type: ignore[arg-type]
            direct_member_gaps=draft.get("direct_gaps"),  # type: ignore[arg-type]
            single_link_member_evidence_ids=draft.get("member_evidence_ids"),  # type: ignore[arg-type]
            chain_bridged=draft.get("chain_bridged"),  # type: ignore[arg-type]
            member_evidence_ids=draft.get("member_evidence_ids"),  # type: ignore[arg-type]
            member_subject_ids=draft.get("member_subject_ids"),  # type: ignore[arg-type]
            member_contexts=draft.get("contexts"),  # type: ignore[arg-type]
            context_weights=tuple(
                item for item in self.config.context_weights
                if item.context in draft.get("contexts")  # type: ignore[operator]
            ),
            contributions=draft.get("contributions"),  # type: ignore[arg-type]
            dependency_family_edges=draft.get("dependency_edges"),  # type: ignore[arg-type]
            dependency_components=draft.get("dependency_components"),  # type: ignore[arg-type]
            dependency_repeat_credit=self.config.dependency_repeat_credit,
            dependency_adjusted_base_score=draft.get("dependency_adjusted_base_score"),  # type: ignore[arg-type]
            source_diversity_bonus=draft.get("source_diversity_bonus"),  # type: ignore[arg-type]
            context_diversity_bonus=draft.get("context_diversity_bonus"),  # type: ignore[arg-type]
            quality_score=draft.get("quality_score"),  # type: ignore[arg-type]
            reference_price=draft.get("reference_price"),  # type: ignore[arg-type]
            price_relation=draft.get("price_relation"),  # type: ignore[arg-type]
            distance=draft.get("distance"),  # type: ignore[arg-type]
            distance_horizon=draft.get("distance_horizon"),  # type: ignore[arg-type]
            distance_factor=draft.get("distance_factor"),  # type: ignore[arg-type]
            placement_factor=draft.get("placement_factor"),  # type: ignore[arg-type]
            selection_score=draft.get("selection_score"),  # type: ignore[arg-type]
            resonance_class_rationale=draft.get("rationale"),  # type: ignore[arg-type]
            side_rank_key=rank_key,
            assumptions=_ASSUMPTIONS,
        )
        zone_fields = {
            "zone_key_id", "zone_snapshot_id", "source_frame_id", "side",
            "price_range", "resonance_class", "member_evidence_ids",
            "member_subject_ids", "contexts", "source_types", "structure_families",
            "candidate_count", "confirmed_count", "fresh_count", "tested_count",
            "weakened_count", "flipped_count", "distinct_context_count",
            "distinct_source_type_count", "distinct_structure_family_count",
            "earliest_evidence_confirm_time", "latest_evidence_confirm_time",
            "dependency_components", "contributions", "dependency_adjusted_base_score",
            "source_diversity_bonus", "context_diversity_bonus", "quality_score",
            "reference_price", "price_relation", "distance", "distance_factor",
            "placement_factor", "selection_score", "provenance",
        }
        values = dict(draft.values)
        return ResonanceZone(
            **{name: values[name] for name in zone_fields},  # type: ignore[arg-type]
            side_rank=side_rank,
            explanation=explanation,
        )
