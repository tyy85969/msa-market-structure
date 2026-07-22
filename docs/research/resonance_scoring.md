# Dependency-Aware Resonance Zones and Scoring

## 1. Purpose

C-007B converts each authoritative C-007A `ResonanceFrame` into deterministic,
side-separated `ResonanceZone` snapshots with evidence contributions, explicit
dependency adjustment, quality and selection scores, explanations, ranking,
and immutable history. It is a research organization layer, not a signal.

## 2. C-007A input boundary

The scorer consumes only complete `ResonanceFrame` and `ResonanceFrameHistory`
objects. It does not read bars, lifecycle histories, timeframe-state histories,
Level Pools, Swings, periodic extremes, or historical reactions. It never
rebuilds Evidence. C-007A remains authoritative for reference price, Direction,
lifecycle tier/state, touch count, source type, family, identity, and provenance.

## 3. Complete Evidence partition

Every `frame.evidence` member enters exactly one Zone. Candidate, distant,
low-scoring, opposed-Direction, and single-context Evidence are retained.
Singletons are first-class Zones. Frame validation rejects missing, duplicate,
extra, wrong-side, or cross-Zone directly connected Evidence.

## 4. Side-separated clustering

UPPER and LOWER graphs are permanently separate. No price overlap, family,
score, Direction, tier, lifecycle state, or context can connect opposite sides.

## 5. Range gap

For inclusive ranges, overlap and endpoint contact have gap zero. Otherwise the
gap is the distance between the nearest edges. All arithmetic is exact
`Decimal`; midpoint substitution, float conversion, tick rounding, and range
repair are absent.

## 6. Tolerance modes

`ABSOLUTE` uses the explicitly supplied positive absolute tolerance.
`REFERENCE_FRACTION` uses the C-007A reference price multiplied by an explicitly
supplied positive fraction. The two parameter forms are mutually exclusive.

## 7. Single-link and chain bridging

The only clustering policy is `SIDE_SEPARATED_SINGLE_LINK`. Same-side Evidence
receives an undirected edge when `gap <= effective_tolerance`, and connected
components become Zones. Transitive chain bridging is an explicitly accepted
baseline: A-B and B-C may join A/B/C even when A-C is not directly connected.
The explanation records every pair gap, direct connectivity, and whether a
non-direct pair exists inside the connected component.

## 8. Singleton Zones

Evidence with no price neighbor remains a Zone with one member, one dependency
component, and class `SINGLE`. Classification thresholds never filter Zones.

## 9. Context weights

`ResonanceScoringConfig.context_weights` must contain exactly one positive
weight for every C-007A configured `ResonanceContext`. Contexts are canonical
`timeframe + scale` facts and are not inferred from price, source, or order.

## 10. Tier weights

C-007A `CANDIDATE` and `CONFIRMED` tiers use the explicitly supplied candidate
and confirmed weights. C-007B does not promote or demote Evidence.

## 11. Lifecycle weights

FRESH, TESTED, WEAKENED, and FLIPPED use four explicit configuration weights.
BROKEN and RETIRED are absent only because C-007A excludes them from the current
effective Evidence tuple while preserving their upstream exclusion history.

## 12. Direction relation

For UPPER, DOWN is ALIGNED and UP is OPPOSED. For LOWER, UP is ALIGNED and DOWN
is OPPOSED. RANGE, TURNING, and UNKNOWN map to NEUTRAL, TURNING, and UNKNOWN.
Each Evidence retains its own C-007A Direction; no Zone vote overwrites it.
Direction factors are structural context factors, not buy/sell signals.

## 13. Freshness

Freshness uses only `frame.as_of_time - evidence.state_confirm_time`. The
timedelta is converted through integer days, seconds, and microseconds to exact
Decimal seconds. The factor is
`max(freshness_floor, 1 - age / freshness_horizon_seconds)`. OriginTime, system
time, and bar timestamps do not participate.

## 14. Touch penalty

`extra_touches = max(0, touch_count - 1)` and
`touch_factor = max(touch_floor, 1 - extra_touches * penalty)`. Touch counts zero
and one are unpenalized. C-007B never re-reads bars to infer a touch.

## 15. Evidence raw contribution

Each Evidence produces exactly one contribution:

```text
context_weight * tier_weight * lifecycle_weight
* freshness_factor * touch_factor * direction_factor
```

The contribution stores every operand, causal age, touch facts, dependency
component, exact result, and deterministic identity.

## 16. Explicit Family dependency graph

Within each Zone, two Evidence members connect only when their C-007A
`structure_families` intersect. Connected components permit transitive family
dependence. The graph never crosses a Zone or side. A Structure Family is
caller-provided dependency evidence, not proof of statistical independence.

## 17. Dependency component adjusted score

Contributions inside a component are ordered by raw contribution descending,
then Evidence ID ascending. The strongest is primary:

```text
primary_raw + dependency_repeat_credit * sum(repeated_raw)
```

Credit zero keeps only the primary score; credit one applies no dependency
penalty. A singleton equals its raw contribution.

## 18. Source diversity bonus

Only distinct `StructureSourceType` values count. Each distinct source after
the first earns the configured increment up to the configured cap. Repetition
of one type and family counts earn no source bonus.

## 19. Context diversity bonus

Only distinct `ResonanceContext` values count. Each context after the first
earns the configured increment up to the configured cap.

## 20. Quality Score

`quality_score` is dependency-adjusted base plus source and context diversity
bonuses. It deliberately excludes current-price distance and placement.

## 21. Price relation

A Zone containing the reference price is `CONTAINS_PRICE`. UPPER above price
and LOWER below price are `EXPECTED_SIDE`; the reverse placements are
`OPPOSITE_SIDE`. These are geometry labels, not trade instructions.

## 22. Distance

Distance is zero inside a Zone, otherwise the exact nearest-edge distance.
The horizon is either an explicit absolute Decimal or reference-price fraction.
`distance_factor = max(0, 1 - distance / horizon)`.

## 23. Placement Factor

EXPECTED_SIDE, CONTAINS_PRICE, and OPPOSITE_SIDE each have an explicit bounded
factor. The factor is stored independently from distance.

## 24. Selection Score

`selection_score = quality_score * distance_factor * placement_factor`. It is a
deterministic input for C-007C, not expected return, win rate, Sharpe, or trading
edge.

## 25. Resonance Class

One member is `SINGLE`. Multiple members meeting both configured Evidence and
context minima are `MULTI_CONTEXT_RESONANCE`; all other multi-member Zones are
`LOCAL_CLUSTER`. Below-threshold Zones remain present.

## 26. zone_key_id

The stable Zone key hashes engine/policy identity, side, envelope, canonical
member subject IDs, canonical member boundary ranges, and schema identity. It
excludes Frame time, reference price, lifecycle state ID, freshness, distance,
and scores. A price-only observation or TESTED-to-WEAKENED update with unchanged
subjects/ranges therefore preserves the key.

## 27. zone_snapshot_id

The snapshot identity binds the source Frame, complete scoring config, Zone key,
current Evidence IDs, contribution IDs, component IDs, all score fields, price
relation/distance, class, and schema. Price, lifecycle, Direction, dependency,
or score changes therefore produce a new snapshot.

## 28. Side ranking

UPPER and LOWER rank independently from one. The complete key is selection
score descending, quality descending, context count descending, source count
descending, distance ascending, latest Evidence ConfirmTime descending, Zone
key ascending, then Zone snapshot ascending. Ranking does not select an
ActiveBox.

## 29. Explanation

`ResonanceZoneExplanation` is strict versioned data, not prose generated at
runtime. It records tolerance, gaps, component membership, chain bridging,
member/context facts and weights, all contribution operands, dependency edges
and components, bonuses, scores, reference/placement/distance facts, class
rationale, the complete rank key, and fixed assumptions. Contracts recompute
and reject contradictory explanations. Validation binds the complete
Explanation to the authoritative member Evidence and scoring configuration,
including exact Context weights, dependency repeat credit, and every resonance
class rationale field; internally self-consistent but source-inconsistent facts
fail closed.

Every Zone, its snapshot identity and provenance, and the containing ScoreFrame
must reference the same authoritative C-007A source Frame. Recomputing nested or
outer identities cannot legitimize a conflicting Zone source lineage.

## 30. Batch

Batch produces exactly one immutable `ResonanceScoreFrame` for every source
history Frame, preserving time, order, and source Frame identity.

## 31. Replay

Default replay is byte-equivalent to Batch. Explicit replay requires aware
strictly increasing unique authoritative C-007A Frames, cannot omit or alter an
original history Frame, and may include legal extra As-Of Frames with the same
C-007A configuration. C-007B never fabricates a source Frame.

## 32. No-Lookahead

C-007B reads only the supplied Frame snapshot. Future Evidence, TEST,
WEAKENED, FLIPPED, BROKEN, RETIRED, Direction, or reference prices cannot alter
an earlier full score payload. Freshness uses State ConfirmTime; price uses the
C-007A completed/available reference snapshot. Future history append preserves
old immutable frames.

## 33. Input-order invariance

Contexts, Evidence, price graph operations, family graph operations, component
members, contributions, IDs, Zones, and ranks use canonical ordering. Input
position and Python set iteration never supply identity or tie-breaking.

## 34. Parameter status

Every numeric value is an explicit research configuration. Example test values
are engineering fixtures only. They have not been optimized in-sample for
XAUUSD, validated out-of-sample, or approved as recommended trading parameters.

## 35. Known limitations

SINGLE_LINK intentionally permits long chain bridges. Structure families rely
on caller evidence and do not prove statistical independence. Linear freshness,
touch penalties, diversity bonuses, Direction factors, placement factors, and
thresholds are unvalidated baselines. The immutable offline history defines no
live watermark or correction protocol.

## 36. C-007C boundary

C-007C, not C-007B, may decide eligibility, choose final Upper/Lower boundaries,
replace a prior selection, create an `ActiveBox`, or freeze selection history.

## 37. C-007D boundary

C-007D may integrate and audit approved C-007 stages. C-007B performs no later
integration, migration, or production promotion.

## 38. C-008 validation boundary

C-008 may perform later empirical validation, parameter sensitivity, ablation,
and out-of-sample work. No score in this baseline establishes performance.
TradingView/Pine, Fibonacci, Imbalance, RSI, volume/momentum filters, signals,
EA behavior, parameter optimization, and live-trading conclusions are out of
scope.
