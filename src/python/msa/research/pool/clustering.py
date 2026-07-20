"""Deterministic side-separated SINGLE_LINK Level Pool clustering."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from itertools import combinations
import json
from typing import Any, Iterator, Mapping

from msa.domain import (
    BoundarySide,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    StructureCluster,
)

from .contracts import (
    SCHEMA_VERSION,
    ClusterExplanation,
    ClusterFormationEvent,
    DependencyGroup,
    LevelPoolConfig,
    LevelPoolHistory,
    LevelPoolInput,
    LevelPoolReport,
    LevelPoolSnapshot,
    _exact_payload,
    _normalize_time,
)
from .distance import range_gap
from .errors import (
    LevelPoolClusteringError,
    LevelPoolInputError,
    LevelPoolSerializationError,
)
from .families import (
    assignment_map,
    build_dependency_groups,
    dependency_family_id,
)


SOURCE_MODULE = "msa.research.pool.clustering"
CLUSTER_FAMILY = "price-cluster-range-gap-single-link-v1"


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LevelPoolClusteringError(
            "unable to build canonical JSON identity or provenance"
        ) from exc


def _candidate_fact(candidate: LevelCandidate) -> dict[str, object]:
    if candidate.confirm_time is None:
        raise LevelPoolClusteringError("validated candidate has no confirm_time")
    return {
        "candidate_id": candidate.candidate_id,
        "source_type": candidate.source_type.value,
        "timeframe": candidate.timeframe.value,
        "scale": candidate.scale.to_dict(),
        "price_range": candidate.price_range.to_dict(),
        "origin_time": candidate.origin_time.isoformat(),
        "confirm_time": candidate.confirm_time.isoformat(),
        "structure_family": candidate.structure_family,
        "provenance": candidate.provenance.to_dict(),
    }


def _candidate_key(candidate: LevelCandidate) -> str:
    return _canonical_json(_candidate_fact(candidate))


def _components(
    candidates: tuple[LevelCandidate, ...], tolerance: object
) -> tuple[tuple[tuple[LevelCandidate, ...], ...], int]:
    ordered = tuple(sorted(candidates, key=_candidate_key))
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    edge_count = 0
    for left, right in combinations(range(len(ordered)), 2):
        if ordered[left].boundary_side is not ordered[right].boundary_side:
            continue
        if range_gap(ordered[left].price_range, ordered[right].price_range) <= tolerance:
            edge_count += 1
            union(left, right)
    grouped: dict[int, list[LevelCandidate]] = {}
    for index, candidate in enumerate(ordered):
        grouped.setdefault(find(index), []).append(candidate)
    components = tuple(
        sorted(
            (
                tuple(sorted(values, key=_candidate_key))
                for values in grouped.values()
            ),
            key=lambda values: tuple(item.candidate_id for item in values),
        )
    )
    return components, edge_count


def _cluster_identity(
    config: LevelPoolConfig,
    symbol: str,
    side: BoundarySide,
    price_range: PriceRange,
    origin_time: datetime,
    confirm_time: datetime,
    members: tuple[LevelCandidate, ...],
    groups: tuple[DependencyGroup, ...],
) -> dict[str, object]:
    role = MarketRole.RESISTANCE if side is BoundarySide.UPPER else MarketRole.SUPPORT
    return {
        "pool_id": config.pool_id,
        "pool_version": config.pool_version,
        "policy_id": config.policy_id,
        "symbol": symbol,
        "cluster_timeframe": config.cluster_timeframe.value,
        "cluster_scale": config.cluster_scale.to_dict(),
        "boundary_side": side.value,
        "market_role": role.value,
        "price_range": price_range.to_dict(),
        "origin_time": origin_time.isoformat(),
        "confirm_time": confirm_time.isoformat(),
        "tolerance_mode": config.tolerance_mode.value,
        "absolute_tolerance": (
            None if config.absolute_tolerance is None else str(config.absolute_tolerance)
        ),
        "normalization_unit": (
            None if config.normalization_unit is None else str(config.normalization_unit)
        ),
        "normalized_tolerance": (
            None
            if config.normalized_tolerance is None
            else str(config.normalized_tolerance)
        ),
        "effective_tolerance": str(config.effective_tolerance),
        "linkage_mode": config.linkage_mode.value,
        "member_candidate_ids": [item.candidate_id for item in members],
        "member_facts": [_candidate_fact(item) for item in members],
        "dependency_groups": [item.to_dict() for item in groups],
        "schema_version": SCHEMA_VERSION,
    }


@dataclass(frozen=True, slots=True)
class LevelPoolClusterer:
    """Research-only deterministic Level Pool organizer."""

    config: LevelPoolConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.config, LevelPoolConfig):
            raise LevelPoolClusteringError("config must be a LevelPoolConfig")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LevelPoolClusteringError(
                f"LevelPoolClusterer.schema_version must be {SCHEMA_VERSION}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LevelPoolClusterer:
        data = _exact_payload(payload, cls.__name__, {"config"})
        try:
            return cls(
                LevelPoolConfig.from_dict(data["config"]),
                data["schema_version"],
            )
        except LevelPoolSerializationError:
            raise
        except (TypeError, ValueError, LevelPoolClusteringError) as exc:
            raise LevelPoolSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc

    def build_as_of(
        self, data: LevelPoolInput, processing_time: datetime
    ) -> LevelPoolSnapshot:
        if not isinstance(data, LevelPoolInput):
            raise LevelPoolInputError("build_as_of requires a LevelPoolInput")
        as_of = _normalize_time(
            "processing_time", processing_time, LevelPoolInputError
        )
        visible = tuple(
            sorted(
                (
                    item
                    for item in data.candidates
                    if item.confirm_time is not None and item.confirm_time <= as_of
                ),
                key=_candidate_key,
            )
        )
        assignments = assignment_map(data.family_assignments)
        components, edge_count = _components(
            visible, self.config.effective_tolerance
        )
        clusters: list[StructureCluster] = []
        explanations: list[ClusterExplanation] = []
        for component in components:
            cluster, explanation = self._build_cluster(component, assignments)
            clusters.append(cluster)
            explanations.append(explanation)
        ordered_clusters = tuple(sorted(clusters, key=lambda item: item.cluster_id))
        ordered_explanations = tuple(
            sorted(explanations, key=lambda item: item.cluster_id)
        )
        report = self._build_report(
            data,
            visible,
            ordered_clusters,
            ordered_explanations,
            assignments,
            edge_count,
        )
        snapshot_identity = {
            "config": self.config.to_dict(),
            "as_of_time": as_of.isoformat(),
            "visible_candidate_ids": sorted(item.candidate_id for item in visible),
            "clusters": [item.to_dict() for item in ordered_clusters],
            "explanations": [item.to_dict() for item in ordered_explanations],
            "schema_version": SCHEMA_VERSION,
        }
        digest = sha256(_canonical_json(snapshot_identity).encode("utf-8")).hexdigest()
        return LevelPoolSnapshot(
            snapshot_id=f"level-pool-snapshot-v1-{digest}",
            as_of_time=as_of,
            visible_candidate_ids=tuple(item.candidate_id for item in visible),
            clusters=ordered_clusters,
            explanations=ordered_explanations,
            report=report,
        )

    def build_batch(self, data: LevelPoolInput) -> LevelPoolHistory:
        """Build atomic history at every unique candidate ConfirmTime."""

        if not isinstance(data, LevelPoolInput):
            raise LevelPoolInputError("build_batch requires a LevelPoolInput")
        schedule = tuple(
            sorted(
                {
                    item.confirm_time
                    for item in data.candidates
                    if item.confirm_time is not None
                }
            )
        )
        return self._history_for_schedule(data, schedule)

    def iter_events(
        self, data: LevelPoolInput
    ) -> Iterator[ClusterFormationEvent]:
        yield from self.build_batch(data).formation_events

    def _build_cluster(
        self,
        members: tuple[LevelCandidate, ...],
        assignments: dict[str, Any],
    ) -> tuple[StructureCluster, ClusterExplanation]:
        if not members:
            raise LevelPoolClusteringError("component must not be empty")
        side = members[0].boundary_side
        if any(item.boundary_side is not side for item in members):
            raise LevelPoolClusteringError("component cannot span boundary sides")
        if any(item.confirm_time is None for item in members):
            raise LevelPoolClusteringError("component contains unconfirmed candidate")
        price_range = PriceRange(
            min(item.price_range.low for item in members),
            max(item.price_range.high for item in members),
        )
        origin_time = min(item.origin_time for item in members)
        confirm_time = max(
            item.confirm_time for item in members if item.confirm_time is not None
        )
        groups = build_dependency_groups(members, assignments)
        identity = _cluster_identity(
            self.config,
            members[0].symbol,
            side,
            price_range,
            origin_time,
            confirm_time,
            members,
            groups,
        )
        digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
        cluster_id = f"structure-cluster-v1-{digest}"
        member_ids = tuple(item.candidate_id for item in members)
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE,
            source_version=self.config.pool_version,
            source_object_id=f"level-pool-cluster-evidence-v1-{digest}",
            policy_id=self.config.policy_id,
            parent_object_ids=member_ids,
            notes=(
                f"pool_id={self.config.pool_id}",
                f"pool_version={self.config.pool_version}",
                f"policy_id={self.config.policy_id}",
                f"tolerance_mode={self.config.tolerance_mode.value}",
                f"effective_tolerance={self.config.effective_tolerance}",
                f"linkage_mode={self.config.linkage_mode.value}",
                f"cluster_timeframe={self.config.cluster_timeframe.value}",
                f"cluster_scale={_canonical_json(self.config.cluster_scale.to_dict())}",
                f"ordered_member_candidate_ids={_canonical_json(list(member_ids))}",
                f"dependency_groups={_canonical_json([item.to_dict() for item in groups])}",
            ),
        )
        role = MarketRole.RESISTANCE if side is BoundarySide.UPPER else MarketRole.SUPPORT
        cluster = StructureCluster(
            cluster_id=cluster_id,
            symbol=members[0].symbol,
            timeframe=self.config.cluster_timeframe,
            scale=self.config.cluster_scale,
            price_range=price_range,
            boundary_side=side,
            market_role=role,
            lifecycle_state=LifecycleState.CONFIRMED,
            origin_time=origin_time,
            confirm_time=confirm_time,
            member_refs=tuple(item.to_boundary_ref() for item in members),
            cluster_family=CLUSTER_FAMILY,
            provenance=provenance,
        )
        explanation = ClusterExplanation(
            cluster_id=cluster_id,
            member_candidate_ids=member_ids,
            raw_member_count=len(members),
            dependency_family_count=len(groups),
            dependency_groups=groups,
            source_types=tuple(
                sorted({item.source_type for item in members}, key=lambda x: x.value)
            ),
            timeframes=tuple(
                sorted({item.timeframe for item in members}, key=lambda x: x.value)
            ),
            member_scales=tuple(
                sorted(
                    {item.scale for item in members},
                    key=lambda x: (x.scale_id, -1 if x.rank is None else x.rank),
                )
            ),
            structure_families=tuple(
                sorted({item.structure_family for item in members})
            ),
            boundary_side=side,
            price_range=price_range,
            origin_time=origin_time,
            confirm_time=confirm_time,
            effective_tolerance=self.config.effective_tolerance,
            tolerance_mode=self.config.tolerance_mode,
            linkage_mode=self.config.linkage_mode,
        )
        return cluster, explanation

    def _build_report(
        self,
        data: LevelPoolInput,
        visible: tuple[LevelCandidate, ...],
        clusters: tuple[StructureCluster, ...],
        explanations: tuple[ClusterExplanation, ...],
        assignments: dict[str, Any],
        edge_count: int,
    ) -> LevelPoolReport:
        source_counts = Counter(item.source_type.value for item in visible)
        timeframe_counts = Counter(item.timeframe.value for item in visible)
        visible_ids = {item.candidate_id for item in visible}
        explicit_count = sum(candidate_id in assignments for candidate_id in visible_ids)
        family_ids = {
            dependency_family_id(item, assignments) for item in visible
        }
        family_clusters: dict[str, set[str]] = {}
        for explanation in explanations:
            for group in explanation.dependency_groups:
                family_clusters.setdefault(group.dependency_family_id, set()).add(
                    explanation.cluster_id
                )
        split_count = sum(len(cluster_ids) > 1 for cluster_ids in family_clusters.values())
        origins = tuple(item.origin_time for item in visible)
        confirms = tuple(
            item.confirm_time for item in visible if item.confirm_time is not None
        )
        cluster_confirms = tuple(item.confirm_time for item in clusters)
        warnings = [
            "SINGLE_LINK permits chain bridging across a connected component",
            "dependency families are metadata only and are not converted to scores",
            "C-005 is a research baseline and does not select trading boundaries",
        ]
        if split_count:
            warnings.append(
                f"{split_count} dependency family/families span multiple price clusters"
            )
        return LevelPoolReport(
            input_candidate_count=len(visible),
            visible_candidate_count=len(visible),
            upper_candidate_count=sum(
                item.boundary_side is BoundarySide.UPPER for item in visible
            ),
            lower_candidate_count=sum(
                item.boundary_side is BoundarySide.LOWER for item in visible
            ),
            cluster_count=len(clusters),
            singleton_cluster_count=sum(len(item.member_refs) == 1 for item in clusters),
            merged_cluster_count=sum(len(item.member_refs) > 1 for item in clusters),
            graph_edge_count=edge_count,
            explicit_assignment_count=explicit_count,
            implicit_family_count=len(visible) - explicit_count,
            dependency_family_count=len(family_ids),
            split_dependency_family_count=split_count,
            source_type_counts=tuple(sorted(source_counts.items())),
            timeframe_counts=tuple(sorted(timeframe_counts.items())),
            structure_family_count=len({item.structure_family for item in visible}),
            earliest_candidate_origin_time=min(origins) if origins else None,
            latest_candidate_origin_time=max(origins) if origins else None,
            earliest_candidate_confirm_time=min(confirms) if confirms else None,
            latest_candidate_confirm_time=max(confirms) if confirms else None,
            earliest_cluster_confirm_time=(
                min(cluster_confirms) if cluster_confirms else None
            ),
            latest_cluster_confirm_time=(
                max(cluster_confirms) if cluster_confirms else None
            ),
            tolerance_mode=self.config.tolerance_mode,
            effective_tolerance=self.config.effective_tolerance,
            linkage_mode=self.config.linkage_mode,
            pool_id=self.config.pool_id,
            pool_version=self.config.pool_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "all visible inputs are immutable confirmed LevelCandidate snapshots",
                "UPPER and LOWER graphs are permanently separate",
                "range-gap distance uses exact Decimal arithmetic",
                "cluster context is caller supplied and not inferred from members",
            ),
            warnings=tuple(warnings),
            errors=(),
        )

    def _history_for_schedule(
        self,
        data: LevelPoolInput,
        schedule: tuple[datetime, ...],
    ) -> LevelPoolHistory:
        if not schedule:
            raise LevelPoolClusteringError("history schedule must not be empty")
        previous: tuple[StructureCluster, ...] = ()
        seen: set[str] = set()
        events: list[ClusterFormationEvent] = []
        final_snapshot: LevelPoolSnapshot | None = None
        for processing_time in schedule:
            snapshot = self.build_as_of(data, processing_time)
            for cluster in snapshot.clusters:
                if cluster.cluster_id in seen:
                    continue
                if cluster.confirm_time != processing_time:
                    raise LevelPoolClusteringError(
                        "cluster first appearance did not equal cluster.confirm_time; "
                        "the replay schedule must include every formation time"
                    )
                member_ids = {item.object_id for item in cluster.member_refs}
                supersedes = tuple(
                    sorted(
                        old.cluster_id
                        for old in previous
                        if old.cluster_id != cluster.cluster_id
                        and member_ids.intersection(
                            item.object_id for item in old.member_refs
                        )
                    )
                )
                events.append(
                    ClusterFormationEvent(
                        first_seen_time=processing_time,
                        cluster=cluster,
                        supersedes_cluster_ids=supersedes,
                    )
                )
                seen.add(cluster.cluster_id)
            previous = snapshot.clusters
            final_snapshot = snapshot
        if final_snapshot is None:
            raise LevelPoolClusteringError("history failed to create final snapshot")
        ordered_events = tuple(
            sorted(
                events,
                key=lambda item: (item.first_seen_time, item.cluster.cluster_id),
            )
        )
        return LevelPoolHistory(ordered_events, final_snapshot)
