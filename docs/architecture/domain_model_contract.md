# MSA Domain Model Contract

## 1. Purpose

C-002 defines the immutable value objects, domain snapshots, validation rules,
serialization format, and causal event-time semantics that later MSA structure
algorithms must use. The contract makes invalid or prematurely available state
unrepresentable without implementing any structure-detection behavior.

## 2. Dependency on C-001

C-002 reuses `Timeframe` from `msa.data.contracts`; it does not create a second
timeframe enum or a second `CanonicalBar`. It also carries forward the C-001
rules that datetimes are timezone-aware and normalized to UTC, prices retain
`Decimal` precision, inputs are immutable, and availability is explicit rather
than inferred from a historical timestamp.

Domain models consume caller-supplied structural facts. They do not load,
repair, resample, or otherwise change C-001 market data.

## 3. Domain Boundary

C-002 defines objects and invariants only:

- `PriceRange`, `ScaleDescriptor`, and `ProvenanceRef`;
- `BoundaryRef` causal snapshots;
- `LevelCandidate` and `StructureCluster`;
- `TimeframeState` and `ActiveBox` snapshots;
- stable enums and domain-specific errors;
- strict, deterministic serialization;
- causal availability guards.

C-003 and C-004 may later produce `LevelCandidate` instances. C-005 may later
implement clustering. C-006 may later implement lifecycle transitions. C-007
may later select Active Boxes. Those tasks must supply every ID, time, source,
state, and result explicitly and must continue to obey this contract.

## 4. OriginTime

`origin_time` records when the represented source event or structural context
originated. It is not an availability time. A historical display may draw a
confirmed structure from `origin_time`, but the earlier drawing location does
not make that structure available to events, tests, alerts, state selection, or
other downstream consumers.

Every supplied OriginTime is required to be timezone-aware and is normalized
to UTC. The model never substitutes the system clock.

## 5. ConfirmTime

`confirm_time` is the earliest instant at which the entire represented immutable
snapshot may be consumed downstream. An object is unavailable when
`processing_time < confirm_time` and first becomes available when
`processing_time == confirm_time`.

Confirmed objects require `confirm_time >= origin_time`. A forming
`LevelCandidate` has `confirm_time=None`, never reports itself as confirmed,
and cannot be converted to `BoundaryRef`. Cluster, state, and box constructors
reject members or boundaries that would require information later than their
own ConfirmTime.

Every touch, break, freeze, or retire fact already expressed by a snapshot must
have occurred and become knowable no later than that snapshot's ConfirmTime.
A later event therefore requires the caller to create a new immutable snapshot
with a new causal ConfirmTime that is no earlier than the event's confirmation.
Changing historical drawing back to OriginTime does not move ConfirmTime or
make the snapshot available earlier.

## 6. AsOfTime

`as_of_time` is the explicit processing time at which a `TimeframeState` or
`ActiveBox` snapshot was constructed. It is separate from ConfirmTime and
cannot replace it. Snapshot construction requires
`as_of_time >= confirm_time`; downstream availability remains governed by
ConfirmTime.

## 7. PriceRange

`PriceRange(low, high)` is an inclusive, immutable interval. Both values must
already be finite `Decimal` instances, and `low <= high`. Float values are not
silently converted. `low == high` represents a single price level.

The value exposes Decimal-preserving `width`, `midpoint`, `contains(price)`,
and `overlaps(other)` operations. Touching inclusive endpoints overlap.

## 8. ScaleDescriptor

`ScaleDescriptor` contains an explicit non-empty `scale_id` and either a
non-negative integer `rank` or `None`. The caller supplies both values. The
model does not infer scale from `Timeframe` and does not hard-code unapproved
meanings such as MICRO, PRIMARY, or HTF.

## 9. ProvenanceRef

`ProvenanceRef` preserves a non-empty source module, source version, source
object ID, optional policy ID, deterministic parent IDs, and a finite tuple of
text notes. Parent IDs must be unique and are stored in sorted order. Notes
retain their explicit tuple order.

The object contains no mutable mapping and no recursively nested provenance
objects. It therefore preserves source identity without allowing unbounded
metadata graphs inside frozen domain values.

## 10. BoundarySide vs MarketRole

`BoundarySide` (`UPPER` or `LOWER`) describes geometric placement in a
structural context. `MarketRole` (`SUPPORT`, `RESISTANCE`, or `NEUTRAL`)
describes the stored market role. They are separate fields and neither implies
a bullish, bearish, buy, or sell direction.

C-002 defines no trading direction. MSA V1 produces no buy or sell arrows.

## 11. LevelCandidate

`LevelCandidate` stores an explicit candidate ID, symbol, `Timeframe`, scale,
price range, source type, boundary side, market role, confirmation status,
lifecycle state, OriginTime, optional ConfirmTime, touch facts, break facts,
structure family, and provenance.

For `FORMING`, ConfirmTime must be `None` and lifecycle must be `CANDIDATE`.
For `CONFIRMED`, ConfirmTime is required, cannot precede OriginTime, and
lifecycle cannot remain `CANDIDATE`.

`touch_count` is non-negative. Zero touches require both last-touch fields to
be absent; a positive count requires both. A stored touch must satisfy
`origin_time <= last_touch_time <= last_touch_confirm_time <= confirm_time`.
Break time fields are likewise both absent or both present, and a stored break
must satisfy
`origin_time <= break_time <= break_confirm_time <= confirm_time`. Because a
forming candidate has no ConfirmTime, it cannot contain these confirmed event
facts. Supplying touch or break facts does not trigger a lifecycle transition.

`is_confirmed_at`, `require_confirmed_at`, and `to_boundary_ref` enforce causal
consumption without detecting or changing the candidate.

## 12. StructureCluster

`StructureCluster` stores an explicit cluster ID, symbol, owning/output
`Timeframe`, scale, caller-supplied price range, side, role, lifecycle,
OriginTime, ConfirmTime, non-empty member snapshot tuple, cluster family, and
provenance. The explicit output Timeframe is not inferred from member
timeframes; members may legitimately span multiple or identical timeframes.

Member object IDs must be unique. Every member must be a confirmed
`BoundaryRef` with the same symbol and side, and cluster ConfirmTime cannot
precede any member ConfirmTime. The constructor does not remove duplicates,
compute a range, choose a representative price, or calculate resonance.

Deterministic properties expose the union of member source types, timeframes,
and structure families. Member snapshots remain present even when several
members share a structure family; a shared family is not automatically treated
as independent evidence.

## 13. BoundaryRef

`BoundaryRef` is a complete immutable causal snapshot, not a database-style ID
pointer. It records object kind and ID, symbol, Timeframe, scale, price range,
side, role, lifecycle, OriginTime, ConfirmTime, source types, structure
families, and provenance as they existed when the snapshot was created.

ConfirmTime is mandatory and cannot precede OriginTime. A reference cannot use
the `CANDIDATE` lifecycle, source types and structure families must be non-empty,
and `is_confirmed_at(processing_time)` returns true only at or after
ConfirmTime. This lets historical snapshots remain auditable if a future
object version changes.

## 14. TimeframeState

`TimeframeState` is an immutable snapshot identified by explicit `state_id`
and non-empty string `state_version`. It contains symbol, Timeframe, scale,
OriginTime, ConfirmTime, AsOfTime, optional upper and lower `BoundaryRef`
snapshots, forming candidate IDs, and provenance.

An empty state, a state with only one boundary, or a state with both boundaries
is valid. Referenced boundary symbols must match the state. Upper and lower
slots require their corresponding sides. Boundary ConfirmTimes cannot exceed
the state's ConfirmTime. When both exist, the lower range high cannot exceed
the upper range low. Forming IDs must be unique and are stored in sorted order.

The model implements no boundary selection or state-update engine.

## 15. ActiveBox

`ActiveBox` stores explicit lower and upper boundary snapshots, selection
price, status, OriginTime, ConfirmTime, AsOfTime, optional frozen and retired
times, and provenance. Both boundary symbols must match the box; lower and
upper sides are enforced; both must already be confirmed by box ConfirmTime.

The finite Decimal `selection_price` must lie inclusively between the inner
edges `lower.price_range.high` and `upper.price_range.low`. Any supplied
`frozen_time` or `retired_time` must be no later than box ConfirmTime. `FROZEN`
requires an explicit frozen time. `RETIRED` requires an explicit retired time,
while other statuses reject a retired time. When both event times are present,
`frozen_time <= retired_time`.

C-002 does not create versions, replace, freeze, invalidate, or retire a box,
and it implements no lifecycle transition algorithm. It only validates a
caller-supplied immutable snapshot. A later lifecycle fact requires the caller
to construct a new snapshot with an appropriately later causal ConfirmTime.

## 16. Lifecycle Enum

The stable lifecycle values are `CANDIDATE`, `CONFIRMED`, `FRESH`, `TESTED`,
`WEAKENED`, `BROKEN`, `FLIPPED`, and `RETIRED`. C-002 defines their storage and
the minimum confirmation consistency rules. It does not define transitions,
touch detection, break detection, weakening, flipping, or retirement policy.

Other stable enums are:

- `StructureSourceType`: `SWING`, `PERIODIC_EXTREME`, `HISTORICAL_REACTION`;
- `BoundarySide`: `UPPER`, `LOWER`;
- `MarketRole`: `SUPPORT`, `RESISTANCE`, `NEUTRAL`;
- `ConfirmationStatus`: `FORMING`, `CONFIRMED`;
- `StructureObjectKind`: `LEVEL_CANDIDATE`, `STRUCTURE_CLUSTER`;
- `ActiveBoxStatus`: `ACTIVE`, `FROZEN`, `INVALIDATED`, `RETIRED`.

## 17. Serialization Contract

Every public C-002 value and domain object supports `to_dict()` and
`from_dict()`. The public format is JSON-compatible and deterministic:

- every object payload includes `schema_version=1`;
- Decimal values are exact strings;
- datetimes are aware UTC ISO-8601 strings with `+00:00`;
- enums use their stable string values;
- tuples become ordered lists;
- nested value objects retain their own schema version;
- round trips reproduce equal immutable objects.

Deserialization fails closed on an unknown schema version, a missing field, an
unknown field, an unknown enum, a non-string Decimal, a naive or invalid time,
or any reconstructed invariant violation. Pickle is not a public format.

## 18. No-Lookahead Guarantees

- OriginTime never grants availability.
- ConfirmTime is the first consumable instant, including equality.
- AsOfTime records computation but cannot move ConfirmTime earlier.
- A forming Candidate cannot become a confirmed reference.
- Stored touch, break, freeze, and retire facts cannot follow their containing
  snapshot's ConfirmTime.
- A Cluster cannot precede its latest member.
- A State or Active Box cannot reference a future boundary.
- Boundary snapshots are immutable and are not rewritten by future object
  versions.
- Batch filtering by ConfirmTime is testable against chronological event
  consumption.
- Constructors do not mutate their inputs.

Historical graphics may backplot to OriginTime. Events and tests only become
effective from ConfirmTime.

## 19. Immutability

All C-002 value and domain objects are frozen, slotted dataclasses. Collection
fields are tuples, provenance has no mutable dict field, and nested references
are themselves immutable snapshots. IDs and times have no random or clock-based
defaults; callers must supply them explicitly for deterministic replay.

## 20. Out of Scope

C-002 implements no Swing, Pivot, Fractal, ZigZag, ATR reversal, periodic
extreme detection, historical reaction support/resistance detection, Level
Pool, clustering algorithm, deduplication algorithm, resonance score,
lifecycle transition, automatic touch or break judgment, TimeframeState update
engine, Active Box selection/replacement algorithm, Fibonacci, Imbalance, RSI,
volume filter, momentum, buy/sell signal, EA, Pine Script, data download,
database, or parameter optimization.

C-002 does not start C-003 or C-004.

## 21. Open Questions

- Which explicit scale IDs and ranks will the approved C-003/C-004 research
  configurations define?
- Which versioning policy will govern future `state_version` values and schema
  migrations beyond `schema_version=1`?
- Will later correction handling create new versioned snapshots, event records,
  or both? Existing immutable snapshots must never be silently rewritten.
- Which provenance policy IDs will C-003 through C-007 approve for their first
  reproducible algorithms?
