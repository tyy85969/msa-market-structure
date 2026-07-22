# C-007C Causal Active Box Contract

## 1. Purpose

C-007C freezes immutable contracts for eligibility, nearest-qualified ordering,
hysteresis, formal Zone projection, Active Box episodes, events, SelectionFrames,
and history validation. It does not execute a selector.

## 2. C-007C staging

This is the contract stage only. C-007C-ENGINE may later execute these pure
rules across Frames after separate approval.

## 3. C-007B input boundary

`ResonanceScoreFrame` is authoritative. C-007C neither recalculates C-007B
scores nor reads facts outside the current ScoreFrame.

## 4. Why a Zone is not one member

A Zone can cover several contexts and its range is the complete member
envelope. Choosing one member would discard aggregate identity and provenance.

## 5. Why StructureCluster projection is used

The formal path is `ResonanceZone -> StructureCluster -> BoundaryRef ->
ActiveBox`. It reuses the authoritative Domain model without adding a Zone
object kind or manufacturing a BoundaryRef.

## 6. Explicit output context

The output `Timeframe` and `ScaleDescriptor` come only from
`ActiveBoxSelectionConfig`. Member contexts never implicitly choose them.

## 7. Aggregate CONFIRMED meaning

Projection lifecycle `CONFIRMED` means C-007C confirmed this aggregate as a Box
boundary projection at the selection time. It does not overwrite member
FRESH, TESTED, WEAKENED, or FLIPPED facts.

## 8. Zone Eligibility

A Zone is eligible exactly when its price relation is `EXPECTED_SIDE`, its
class is allowed, quality and selection scores meet inclusive minima, and its
distance factor is strictly positive. Every Zone receives one evaluation and
failure reasons use fixed enum order.

## 9. Nearest-qualified ordering

Each side orders eligible Zones by distance ascending, selection score
descending, quality score descending, context count descending, source-type
count descending, latest evidence ConfirmTime descending, stable Zone ID
ascending, then Zone snapshot ID ascending. C-007B `side_rank` is audit data,
not the final selection order.

## 10. Hysteresis

Without current state, the first eligible Zone is selected. A missing or
ineligible current Zone is replaced by the first eligible Zone or cleared.
An eligible current Zone is retained unless a non-current challenger is
strictly better by the configured distance margin, or is no farther and
strictly exceeds the configured selection-score improvement. Equality never
triggers replacement, and a farther challenger cannot replace current.

## 11. Stable zone_key

Episode continuity uses `zone_key_id`, never `zone_snapshot_id`. Price,
freshness, direction, and score updates may create a new snapshot of the same
stable Zone.

## 12. Zone snapshot updates

The current observed Zone snapshot IDs are audit facts in each decision and Box
snapshot. They may change without changing the Box episode.

## 13. SideDecision

`ActiveBoxSideDecision` records all evaluations, exact eligible order, current,
challenger, margins, gains, action, and selected Zone. Its deterministic ID is
recomputed from the complete decision payload.

## 14. Zone projection

Projection extracts exactly the Zone's evidence from the current source Frame,
uses every corresponding complete `BoundaryRef`, verifies the Zone envelope,
and constructs a deterministic `StructureCluster`. The contract independently
recomputes canonical members, member IDs, envelope, earliest OriginTime,
selection ConfirmTime, side/role, lifecycle, family, output context,
provenance, and Cluster ID. A projection is authoritative only when it exactly
equals a fresh projection of the uniquely matching key and snapshot in that
same ScoreFrame.

## 15. Projection provenance

Bounded provenance names the source ScoreFrame, Zone snapshot, member Evidence
IDs, and member Boundary IDs. It does not copy a history or nest provenance.

## 16. box_key_id

`box_key_id` is stable for one episode and binds engine/policy identity,
creation time, explicit output context, stable lower/upper Zone keys,
projection IDs, original selection price, and schema.

## 17. box_snapshot_id

`box_snapshot_id` binds the episode key, current ScoreFrame, complete Domain
`ActiveBox`, observed Zone snapshots, status, and schema. AsOf, observed
snapshots, or freeze status therefore changes the snapshot identity.

## 18. Domain ActiveBox mapping

The Domain object uses the episode key as `box_id`, explicit configured output
context, formal projected boundaries, earliest boundary OriginTime, and bounded
provenance. C-007C never emits INVALIDATED or RETIRED.

## 19. Original selection price

`selection_price` is the reference price at episode creation. It is immutable
across later observations and freezing.

## 20. ACTIVE geometry

For an ACTIVE Frame, current reference price must remain between the lower and
upper inner boundary edges, inclusively. ACTIVE ConfirmTime is creation time;
AsOf advances by exact current ScoreFrame observations and must equal the
current ScoreFrame AsOf. Observation requires both stable keys and their
caller-supplied snapshot IDs to equal the authoritative current Zones.

## 21. FROZEN history

FROZEN is a terminal historical structural snapshot. Freeze, ConfirmTime, and
AsOf are the causal freeze time. Later prices need not remain inside the Box.
Freeze time cannot precede the last ACTIVE AsOf, and freezing preserves the
episode key, projections, creation time, original selection price, and last
observed Zone facts exactly.

## 22. Pair creation

With no current Box, a complete selected lower/upper pair creates one Box and
one `CREATED(INITIAL_PAIR)` event. An incomplete pair creates none. Every
CREATED result must exactly equal the formal creation helper output, including
the current ScoreFrame reference price as the original selection price.

## 23. Pair replacement

If either stable Zone key changes and both selected sides remain present, the
old episode is frozen before the new episode is created at the same AsOf.

## 24. Pair unavailable behavior

If an existing episode loses either selected side, it is frozen with
`PAIR_UNAVAILABLE` and the current Active Box becomes absent.

## 25. Price crossing behavior

Crossing is handled by the causal C-007B price relation in its corresponding
ScoreFrame. C-007C adds no special future-price path.

## 26. Event ledger

Only `CREATED` and `FROZEN` exist. IDs bind exact previous/resulting snapshots.
Replacement order is always FROZEN old then CREATED new. Every Box appearing
in a Frame, event snapshot, or frozen ledger has exactly one prior CREATED and
at most one later FROZEN; a frozen key cannot become ACTIVE again.

## 27. SelectionFrame

A Frame binds one current ScoreFrame, exact LOWER and UPPER decisions, optional
ACTIVE snapshot, zero to two ordered events, exact report, config, and bounded
provenance. Every identity and nested decision is recomputed.

Public construction, observation, freeze, event, Frame, and decision-validation
helpers validate input types before reading attributes or enum values and fail
closed with the C-007C contract error hierarchy.

## 28. History

History is a validator, not a builder engine. Frames are strictly increasing
and map exactly to the immutable ScoreHistory. Each episode has one CREATED and
at most one FROZEN, never reactivates, and frozen snapshots exactly match the
event ledger. Validation carries the previous ACTIVE snapshot across Frames:
Decision current keys must equal that snapshot; an unchanged pair must equal
the formal observation result; an unavailable pair must formally freeze it;
and a changed pair must atomically freeze it before creating a distinct,
current-ScoreFrame-authoritative episode.

## 29. No-Lookahead

Visibility begins at ConfirmTime, never OriginTime. Selection and projection
use only the current ScoreFrame; selection time equals Frame AsOf; member
ConfirmTimes cannot be later. Future appends cannot change old full payloads,
projections, events, or frozen snapshots.

## 30. Deterministic identity

Decision, projection, cluster, Box key, Box snapshot, event, and Frame IDs use
canonical JSON plus SHA-256. No system clock, UUID, Python hash, random
tie-break, float, or tuple position supplies identity.

## 31. Parameter disclaimer

All thresholds and margins are research configuration. They have not been
optimized for XAUUSD. Nearest-qualified does not imply trading advantage.

## 32. Known limitations

The contract does not decide when to call its pure functions, traverse a
history, tune parameters, or validate profitability. Formal C-008 empirical
validation remains future work.

## 33. C-007C-ENGINE boundary

C-007C-ENGINE may later implement the approved cross-Frame state machine. This
stage contains no `ActiveBoxSelector`, replacement loop, Batch, or Replay.

## 34. C-007D boundary

C-007D integration is not started and no downstream signal or Pine behavior is
introduced.

## 35. C-008 validation boundary

C-008 must separately evaluate stability, sensitivity, out-of-sample behavior,
and no-lookahead. Active Box is not a trading signal and this contract produces
no buy/sell, entry/exit, stop-loss, or take-profit recommendation.
