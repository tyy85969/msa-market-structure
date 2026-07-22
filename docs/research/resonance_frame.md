# Causal Multi-Context Resonance Frame

## 1. Purpose

C-007A assembles an immutable, causally aligned observation frame across explicit
`timeframe + scale` contexts. It exposes the complete current structural evidence
universe, the stored direction for every context, and the latest completed and
available reference close. It produces no trading claim.

## 2. C-007 staging

C-007A owns evidence assembly, exact context alignment, reference-price causality,
deterministic identity, Batch, As-Of, Replay, and no-lookahead validation. C-007B
may later create resonance zones and scores. C-007C may later select and manage an
`ActiveBox`. C-007D may later integrate and audit those approved stages.

## 3. Why C-007A is not scoring

Assembly must first preserve every eligible fact without embedding an unvalidated
ranking policy. This stage defines no score, weight, tolerance, threshold,
freshness decay, diversity bonus, dependency penalty, distance score, or optimized
parameter.

## 4. LifecycleHistory is the evidence universe

For the selected `LifecycleSnapshot`, every configured-context subject in `FRESH`,
`TESTED`, `WEAKENED`, or `FLIPPED` produces exactly one `ResonanceEvidence`.
`LifecycleSubjectState` supplies the authoritative subject ID, lifecycle state ID,
latest event ID, test count, lifecycle times, and effective boundary snapshot.

## 5. C-006B boundaries are not the universe

C-006B uses the local `LATEST_CAUSAL` baseline to fill four boundary slots. An
older effective subject may be absent from all four slots while remaining important
for later distance, quality, or cross-context analysis. C-007A therefore never uses
those four slots to reduce the evidence universe. Tests preserve two effective Upper
subjects even when only the newer one is selected by C-006B.

## 6. TimeframeState is causal context

Each configured context embeds the authoritative immutable `TimeframeState`, plus
its timeframe snapshot ID and lifecycle source ID. Direction, state ID, OriginTime,
and ConfirmTime are read-only views of that object rather than duplicated facts. A
deterministic `context_state_id` hashes the complete TimeframeState and alignment
payload. C-007A does not infer Direction or rerun selection, lifecycle, pool, level,
or Swing logic.

## 7. Exact multi-context alignment

At processing time `t`, the assembler selects the latest `LifecycleSnapshot` whose
`as_of_time <= t`. Every configured `TimeframeStateHistory` must contain exactly one
snapshot with both the same AsOfTime and the same `source_lifecycle_snapshot_id`.
Missing alignment fails closed; an older context state is never substituted. The
frame is therefore one atomic view of one lifecycle snapshot.

## 8. Reference price

`ReferencePriceSnapshot` embeds the complete authoritative `CanonicalBar`; reference
price is its read-only `close` property. The snapshot recomputes `reference_id` from
the complete canonical bar payload. The bar must be complete, match the configured
symbol and reference timeframe, and come from an error-free `LoadResult`. No float
conversion, rounding, ATR, or derived price is used.

## 9. Available-time semantics

The selected reference bar is the latest deterministic bar satisfying
`available_time <= processing_time`. `end_time` alone grants no visibility. A later
bar, even when historically ended, cannot change an earlier frame before its
explicit availability.

Reference age is computed from integer days, seconds, and microseconds before exact
Decimal division by one million. It never passes through floating-point
`timedelta.total_seconds()`.

## 10. Effective lifecycle eligibility

The only policy is `ALL_EFFECTIVE_LIFECYCLE_STATES`. `FRESH`, `TESTED`, `WEAKENED`,
and `FLIPPED` are effective. `BROKEN` and `RETIRED` remain explicit exclusion facts.
Pre-activation `CONFIRMED` is not resonance evidence.

## 11. One state, one evidence

One current `LifecycleSubjectState` produces at most one Evidence. Subject IDs,
lifecycle state IDs, and evidence IDs are unique. A state is never duplicated into
Candidate and Confirmed views.

## 12. Candidate and Confirmed tier

`FRESH` maps to `CANDIDATE`. `TESTED`, `WEAKENED`, and `FLIPPED` map to `CONFIRMED`.
Tier is a factual view of the authoritative lifecycle state, not a score.

## 13. FLIPPED mapping

Every Evidence boundary is created only through
`LifecycleSubjectState.to_boundary_ref()`. A FLIPPED state therefore carries its
effective reversed side and role, current lifecycle state, state ConfirmTime, and
lifecycle provenance. The original `subject_ref` is retained as an upstream fact,
not substituted as the current boundary. Validation also requires the formal
`lifecycle-boundary-v1-{state_id}` identity, lifecycle engine source, exact state
source object, exact subject/event parents, lifecycle state, and state ConfirmTime.

## 14. BROKEN and RETIRED

Configured-context BROKEN and RETIRED subject IDs are recorded in separate canonical
frame and report fields. They generate no current Evidence and are not deleted from
the upstream lifecycle history. Evidence, BROKEN, and RETIRED subject partitions are
pairwise disjoint.

## 15. Context Direction

Evidence Direction is copied from the exactly aligned `ResonanceContextState` for
the boundary's timeframe and scale. Direction is structural context, not buy/sell
bias.

## 16. Touch-count provenance

`touch_count` is copied from the formal `LifecycleSubjectState.test_count`. C-007A
does not inspect bars to reconstruct touches.

## 17. Source and family facts

`source_types` and `structure_families` must exactly equal the effective
`BoundaryRef` facts and are stored canonically. This stage neither assumes family
independence nor converts diversity into a bonus.

## 18. Batch schedule

The default schedule is the strictly sorted unique union of lifecycle snapshot
AsOfTimes and reference-bar AvailableTimes, starting at the first common causal
availability. Each point creates a frame, including price-only observations.

## 19. As-Of

`build_as_of(data, processing_time)` requires an aware time. Between lifecycle
snapshots, structural Evidence and context state remain unchanged. Between reference
AvailableTimes, the previous completed bar remains selected. Frame AsOfTime always
equals the requested processing time.

## 20. Replay

Default Replay uses the exact Batch schedule and must be byte-equivalent to Batch.
An explicit schedule must be aware, strictly increasing, unique, include every
default frame time, and may add extra AsOf observations without admitting future
facts.

## 21. Input-order invariance

Configured contexts, histories, context states, Evidence, exclusions, provenance
parents, and identity inputs are canonically normalized. Reversing the timeframe
history tuple cannot change any public payload.

## 22. No-lookahead

Lifecycle visibility follows snapshot AsOfTime; state visibility follows exact
lifecycle alignment; price visibility follows AvailableTime. OriginTime never grants
availability. Appending immutable future history, future tests, breaks, flips,
retirements, directions, or price bars cannot rewrite an earlier frame. Tests compare
full frame payloads, not only counts.

## 23. Deterministic IDs

Reference, ContextState, Evidence, and Frame identities use compact canonical JSON
and SHA-256. Frame identity includes config, processing time, lifecycle source,
reference source, ordered complete-payload ContextState identities, ordered evidence
IDs, exclusions, and schema identity. No clock, UUID, Python `hash()`, filename, or
input position participates.

## 24. Provenance

Frame provenance is bounded to the selected lifecycle snapshot, selected timeframe
snapshots, reference snapshot, and selected lifecycle state IDs. Evidence provenance
is bounded to the subject, lifecycle state, latest lifecycle event, and effective
boundary. Module, version, policy, the single engine-ID note, and exact parent sets
are validated against the frame config. Complete histories are never copied into
provenance.

## 25. Non-configured contexts

A non-configured lifecycle context cannot enter Evidence, configured TimeframeState
selection facts, effective/excluded sets, report structure counts, or any later
C-007B scoring input. It can change the raw lifecycle snapshot ID, timeframe snapshot
lineage (including lineage-bearing upstream provenance), Frame provenance, and Frame
ID. The Frame is intentionally bound to the exact observed upstream snapshot; this
contract does not claim that adding a non-configured context preserves Frame ID.

## 26. Known limitations

This is an offline immutable-history baseline without live watermarks, corrections,
or a revision protocol. Upstream histories must preserve old immutable snapshots when
future facts are appended. C-007A records facts but does not establish empirical edge.

## 27. C-007B and C-007C boundaries

C-007B may operate on the complete Evidence tuple to evaluate zones, dependence,
distance, and configured scores after separate approval. C-007C may select, freeze,
replace, or retire an Active Box only after C-007B. Neither behavior exists here.

## 28. C-008 boundary and exclusions

C-008 integration, TradingView/Pine behavior, Fibonacci, Imbalance, RSI, volume or
momentum filters, signals, EA behavior, and parameter optimization are outside this
stage. C-007A does not produce buy/sell signals or trading recommendations.
