# Deterministic Level Pool and Explainable Price Clustering

## 1. Purpose

C-005 organizes confirmed structural evidence into deterministic, explainable
price clusters. It is a reproducible organization layer, not a signal or
boundary-selection engine.

## 2. Dependencies

The implementation depends on C-001 market/time contracts, the C-002 domain
model, and confirmed C-003/C-004 `LevelCandidate` outputs. It reuses the
existing `StructureCluster`, `BoundaryRef`, `PriceRange`, `ScaleDescriptor`,
`Timeframe`, `ProvenanceRef`, and domain enums without defining alternatives.

## 3. Research-only status

The tolerance and SINGLE_LINK policy are baselines. No value is approved as
optimal for XAUUSD, and no trading or performance conclusion follows from a
cluster.

## 4. Level Pool input

`LevelPoolInput` accepts a non-empty tuple of unique-ID, single-symbol,
confirmed `LevelCandidate` snapshots plus optional explicit dependency-family
assignments. Input order is set-like: the algorithm normalizes internally but
does not mutate, repair, reprice, merge IDs, or delete equal-price members.

## 5. Supported source types

The allowed sources are `SWING`, `PERIODIC_EXTREME`, and
`HISTORICAL_REACTION`. Every candidate must have confirmed status, non-null
ConfirmTime, lifecycle exactly `CONFIRMED`, and the mapping
`UPPER/RESISTANCE` or `LOWER/SUPPORT`.

## 6. Explicit cluster context

The caller supplies `cluster_timeframe` and `cluster_scale`. They identify the
analysis context of the output snapshot. They are never inferred from the
largest member timeframe, member count, ordering, or a representative member.
Every member retains its original timeframe and scale.

## 7. Absolute tolerance

In `ABSOLUTE` mode, `absolute_tolerance` is a finite non-negative Decimal and
the normalized fields are absent:

```text
effective_tolerance = absolute_tolerance
```

## 8. Normalized tolerance

In `NORMALIZED` mode, the caller supplies a finite positive
`normalization_unit` and finite non-negative `normalized_tolerance`:

```text
effective_tolerance = normalization_unit * normalized_tolerance
```

C-005 does not calculate ATR, choose its timeframe, infer volatility, or
hard-code XAUUSD parameters.

## 9. Range-gap distance

For inclusive ranges A and B, overlap or endpoint contact has distance zero.
If `A.high < B.low`, distance is `B.low - A.high`; if `B.high < A.low`, it is
`A.low - B.high`. Exact Decimal arithmetic is used without midpoint
substitution, float conversion, tick rounding, or range expansion.

## 10. SINGLE_LINK graph

Only `SINGLE_LINK` is supported. Two same-side candidates receive an undirected
edge when `range_gap <= effective_tolerance`; equality connects. Clusters are
the graph's connected components, including singleton components.

## 11. Chain bridging

SINGLE_LINK is transitive through graph paths. If A connects to B and B
connects to C, A/B/C form one component even when A and C are farther apart
than the tolerance. Reports disclose this baseline property.

## 12. Side separation

UPPER and LOWER candidates are always evaluated in separate graphs. Source
type, timeframe, scale, `structure_family`, and dependency family do not split
a same-side price component.

## 13. StructureCluster mapping

Each component becomes the existing `StructureCluster`. Its price range is the
member envelope, its role is `UPPER -> RESISTANCE` or `LOWER -> SUPPORT`, its
lifecycle is `CONFIRMED`, and every candidate becomes a sorted full
`BoundaryRef`. No representative replaces the members.

## 14. Cluster OriginTime

Cluster OriginTime is the minimum member OriginTime. It is historical context,
not causal availability.

## 15. Cluster ConfirmTime

Cluster ConfirmTime is the maximum member ConfirmTime. A cluster is absent
before that time and available at equality.

## 16. Cluster ID

IDs use SHA-256 over compact UTF-8 JSON with sorted keys. Identity includes
pool/version/policy, symbol, explicit context, side/role, envelope, OriginTime,
ConfirmTime, full tolerance configuration, linkage, ordered member IDs and
facts, member provenance, and dependency groups. No position, filename,
clock, UUID, Python `hash()`, or unordered set output is used.

## 17. Provenance preservation

Cluster provenance records the pool policy, exact tolerance/linkage/context,
all ordered member IDs, and dependency-group summary. Member `BoundaryRef`
snapshots retain their original source type, timeframe, scale, range, times,
structure family, lifecycle, and provenance.

## 18. Existing structure_family semantics

`LevelCandidate.structure_family` identifies a generating algorithm or
structural category. Equal `structure_family` strings are not evidence that
candidates came from the same real market extreme.

## 19. DependencyFamilyAssignment

Callers may explicitly map a candidate ID to a non-empty dependency-family ID
with a non-empty rationale. A family may span timeframes but never symbols or
boundary sides. Price proximity, source type, and structure family never create
an explicit assignment.

## 20. Explicit versus implicit families

An unassigned candidate receives `candidate:<candidate_id>`. This means only
that no evidence currently establishes dependency with another candidate.
Explicit dependency evidence is required to group candidates.

## 21. ClusterExplanation

Every cluster has one explanation containing member IDs, raw member count,
dependency-family count and groups, source types, timeframes, member scales,
structure families, side, range, times, tolerance, and linkage. Family grouping
does not remove members. Counts are not converted into a score, correlation
penalty, rank, or final resonance value.

## 22. Batch Snapshot

Batch history advances through the UTC-sorted unique candidate ConfirmTimes.
All candidates sharing a ConfirmTime enter atomically, so tuple order cannot
create intermediate clusters at that time. The last time produces the final
snapshot.

## 23. As-Of Snapshot

`build_as_of(data, processing_time)` requires an aware time and admits only
candidates with `confirm_time <= processing_time`. OriginTime, file position,
and system time grant no visibility. Snapshot cluster and explanation order is
deterministic.

## 24. Cluster formation history

A newly observed component creates a `ClusterFormationEvent`. Its
`first_seen_time` equals the new cluster's ConfirmTime. A later member creates
a new immutable cluster identity; an earlier cluster object is never edited.

## 25. Supersedes lineage

A new cluster lists prior-snapshot cluster IDs that share at least one member
and have a different ID. A bridge may supersede two prior clusters. This is
snapshot lineage only, not lifecycle retirement, break, or invalidation.

## 26. Replay

Default replay uses every unique candidate ConfirmTime. Explicit schedules must
be aware, strictly increasing, unique, and contain every true first-formation
time; sparse schedules cannot report a late first discovery as causal.

## 27. No-Lookahead guarantees

Future candidates cannot alter earlier visibility, ranges, components,
dependency groups, IDs, explanations, or events. A future bridge merges only
at its own ConfirmTime. Batch and replay compare full cluster facts,
provenance, first-seen times, supersedes IDs, and the final snapshot.

## 28. Input-order invariance

Candidates are sorted by canonical member facts before graph construction,
union operations are deterministic, component/member/group outputs are sorted,
and all identity JSON is canonical. Reversals and fixed permutations therefore
produce byte-equivalent public payloads.

## 29. Known limitations

SINGLE_LINK can create long chains; no alternative linkage is approved.
Dependency families rely on caller evidence and do not prove statistical
independence. Tolerance values are configuration, not approved XAUUSD
parameters. The offline immutable-input model defines no live correction or
watermark protocol.

## 30. C-006 boundary

C-006, not C-005, owns lifecycle transitions such as `FRESH`, `TESTED`,
`WEAKENED`, `BROKEN`, `FLIPPED`, or `RETIRED`. C-005 never applies them.

## 31. C-007 boundary

C-007, not C-005, may combine multi-timeframe state, resonance, boundary
selection, or Active Box behavior. C-005 performs no final resonance scoring,
independence penalty, ranking, TimeframeState construction, or Active Box.

## 32. Open questions

- Which H/EXP record will compare tolerance modes and SINGLE_LINK alternatives?
- What caller evidence protocol should create dependency-family assignments?
- Which live revision/watermark contract can preserve prior immutable events?
- Which out-of-sample stability criteria are required before later selection?
