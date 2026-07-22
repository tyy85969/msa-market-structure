# Causal Per-Timeframe Structure State Engine

## 1. Purpose

C-006B converts an immutable C-006A `LifecycleHistory` into one explicit
`symbol + timeframe + scale` context. It emits Candidate and Confirmed upper
and lower boundaries, a stored `Direction`, a verifiable explanation, an event
ledger, and causal Batch, As-Of, and Replay histories. It is a research
baseline, not a trading signal.

## 2. Dependencies

The module reuses `msa.domain.TimeframeState`, `Direction`, `BoundaryRef`,
`Timeframe`, `ScaleDescriptor`, `ProvenanceRef`, `LifecycleState`, and the
C-006A lifecycle contracts. It creates no parallel domain or lifecycle model.

## 3. TimeframeState v2

Every result is the existing immutable `msa.domain.TimeframeState` schema v2.
The engine supplies all four Candidate/Confirmed slots, an explicit Direction,
causal times, empty forming IDs, and bounded provenance. No v1 migration is
performed.

## 4. C-006A LifecycleHistory input

`TimeframeStateInput` accepts one non-empty, already validated
`LifecycleHistory`. Every `LifecycleSnapshot` is consumed as one atomic input
batch. C-006B neither mutates lifecycle objects nor repeats C-006A transition
or price logic.

## 5. Why raw bars are not reprocessed

C-006A owns bar observation, tests, weakening, breaks, flips, retirement, and
their availability. Re-reading bars here would create a second lifecycle
algorithm and could disagree with the authoritative event ledger. C-006B reads
no `CanonicalBar`.

## 6. Explicit symbol, timeframe, and scale

The target context comes only from `TimeframeStateConfig`; it is never inferred
from the history and XAUUSD is not hard-coded. States from other symbols,
timeframes, or scales are legal input and are ignored for local selection.

## 7. Candidate eligibility

`FRESH`, `TESTED`, `WEAKENED`, and `FLIPPED` enter Candidate selection.
Candidate Upper and Candidate Lower are selected independently.

## 8. Confirmed eligibility

`TESTED`, `WEAKENED`, and `FLIPPED` enter Confirmed selection. A qualifying
state may occupy both its Candidate and Confirmed slot.

## 9. BROKEN and RETIRED exclusion

`BROKEN` and `RETIRED` remain visible in explanation and report exclusion
facts but cannot occupy a current boundary slot. History is preserved; no
upstream lifecycle subject is deleted.

## 10. FLIPPED effective mapping

All selected boundaries are created with
`LifecycleSubjectState.to_boundary_ref()`. A FLIPPED subject therefore uses
its effective reversed side/role, its `state_confirm_time`, its current
lifecycle state, and lifecycle-derived provenance. The original `subject_ref`
is never substituted.

## 11. LATEST_CAUSAL key

The only supported policy compares the complete descending key:

```text
(state_confirm_time,
 structural_confirm_time,
 subject_ref.object_id,
 state_id)
```

`BoundarySelectionKey` exposes the same four facts. Input position, set order,
price distance, source type, family, test count, timeframe weight, scores, and
current market price do not participate.

## 12. Raw per-side winners

Candidate Upper, Candidate Lower, Confirmed Upper, and Confirmed Lower each
take the first eligible state after descending key order. These are raw winners
before pair validity is enforced.

## 13. Crossing conflict resolution

Each Candidate and Confirmed pair independently requires
`lower.price_range.high <= upper.price_range.low`. When raw winners cross, the
side with the greater complete LATEST_CAUSAL key is retained and the older side
is cleared with reason `CROSSED_PAIR_OLDER_SIDE`. The engine does not search
older alternatives or fall back to a prettier compatible pair.

## 14. Candidate pair

The final Candidate pair is the independently resolved Candidate Upper and
Lower. Either side may be absent. It is informational and never drives
Direction.

## 15. Confirmed pair

The final Confirmed pair is resolved independently from Candidate. Direction
uses it only when both sides remain present after crossing resolution.

## 16. Empty forming IDs

`forming_candidate_ids` is always `()`. C-006B does not invent a FORMING
protocol; that contract remains deliberately unfrozen.

## 17. Decimal midpoint

The representative price is exact:

```text
(price_range.low + price_range.high) / Decimal("2")
```

No float conversion, tick rounding, ATR normalization, or current-price input
is allowed.

## 18. Underlying subject identity

Complete-pair explanation records, in Upper/Lower order, underlying subject
IDs, selected lifecycle state IDs, resulting BoundaryRef IDs, and midpoints.
Position equality uses both underlying subject IDs and both midpoints. A
TESTED-to-WEAKENED payload change for the same subjects and prices does not
move Direction, although it still creates a selection/state event.

## 19. Initial UNKNOWN and RANGE

Before any complete Confirmed pair, Direction is `UNKNOWN`. The first complete
pair initializes `RANGE`.

## 20. UP

When a changed complete pair has both Upper and Lower midpoints strictly above
the most recent historical complete pair, raw Direction is `UP`.

## 21. DOWN

When both midpoints are strictly below the most recent historical complete
pair, raw Direction is `DOWN`.

## 22. RANGE

All mixed changes produce raw `RANGE`: one side up and one down, one changed
and one equal, expansion, contraction, or replacement subjects at equal
midpoints.

## 23. TURNING

An UP-to-raw-DOWN or DOWN-to-raw-UP reversal yields `TURNING`. A later changed
pair resolves TURNING directly to raw UP, DOWN, or RANGE. TURNING is a local
structure-state transition, not a buy/sell instruction.

## 24. Pair loss and rebuild

Direction retains two distinct causal facts: the most recent historical
complete Confirmed Pair and the complete pair actually present at the preceding
LifecycleSnapshot. The first loss after a complete pair yields `TURNING` with
`pair_position_changed=true`. Continued incompleteness preserves the current
Direction with `pair_position_changed=false`; it does not emit repeated
Direction changes. If no pair ever formed, an incomplete pair stays `UNKNOWN`.

A pair appearing after an incomplete preceding snapshot is always a rebuild,
even when it restores the same subjects and Decimal midpoints. It compares with
the most recent historical complete pair: both-midpoint rises yield `UP`, both
falls yield `DOWN`, and same/equal/mixed movement yields raw and final `RANGE`.
A rebuild from `TURNING` resolves directly to that raw result and records
`pair_position_changed=true`.

## 25. Semantic state fields

Only Direction, the four complete BoundaryRef payloads, and forming IDs are
semantic fields. AsOfTime, report counters, and non-target history changes do
not independently create a state event. Boundary lifecycle state, ConfirmTime,
ID, or provenance changes are part of the complete boundary payload and are
semantic.

## 26. Atomic LifecycleSnapshot processing

All state and lifecycle events inside one `LifecycleSnapshot` are selected and
interpreted together. At most one TimeframeState event is created for that
source snapshot, so tuple order cannot expose a mixed intermediate pair.

## 27. TimeframeState event ledger

The ledger supports `INITIALIZED`, `SELECTION_CHANGED`, `DIRECTION_CHANGED`,
and `STATE_CHANGED`. INITIALIZED occurs exactly once. Later events point to the
direct previous semantic state and direct previous event. `changed_fields` is
an exact canonical subset of the six semantic fields.

## 28. State ID

State identity hashes canonical compact sorted-key UTF-8 JSON with SHA-256. It
includes engine/policy/context identity, Direction, all four boundary payloads,
forming IDs, semantic OriginTime/ConfirmTime, and schema identity. It excludes
AsOfTime, report counters, and snapshot position.

## 29. Event ID

Event identity hashes engine/policy identity, previous/current state IDs,
event type and ConfirmTime, previous/current Direction, changed fields, source
lifecycle snapshot/event IDs, and the prior timeframe-state event ID. No clock,
UUID, Python hash, filename, or input position participates.

## 30. Provenance

Event provenance references the source lifecycle snapshot, target-context
source lifecycle events, and direct prior timeframe event. State provenance
references the source snapshot that formed the semantic state, selected
lifecycle states, their latest lifecycle events, and the current timeframe
event. Parent IDs are finite and canonical; complete history is never copied.
Validation requires these parent sets exactly, so both missing and injected
parents fail closed.

## 31. Selection explanation

Every snapshot records relevant and eligible IDs, exclusions, raw winners,
crossing resolution, selected boundaries, all stable keys, previous/current
pair identities and midpoints, raw/final Direction, and a fixed rationale. It
contains no score, weight, trade bias, or recommendation and is contract-checked
against State and Report.
The current complete-pair identity is reconstructed from the confirmed state
boundaries, their lifecycle provenance, and the stable comparison keys.
Candidate and Confirmed crossing explanations are validated independently
against their raw and selected IDs; validation never performs fallback search.

State, Event, and Snapshot IDs are recomputed by the same private canonical
identity functions used during generation. History validation independently
replays adjacent six-field semantic diffs and the Direction transition, permits
zero or one new event per snapshot, and rejects coherent-looking substituted
hashes or ledgers.

## 32. As-Of

`build_as_of(data, processing_time)` requires an aware time no earlier than the
first lifecycle snapshot. It consumes only the latest lifecycle prefix whose
`as_of_time <= processing_time`. Between lifecycle snapshots, semantic state,
ID, OriginTime, ConfirmTime, event ledger, and provenance remain unchanged;
only AsOfTime and observational snapshot/report identity advance.

## 33. Batch

Batch processes every lifecycle snapshot AsOfTime in strict order and stores a
TimeframeStateSnapshot at every point. A no-change point keeps the exact event
prefix and semantic state ID.

## 34. Replay

Default Replay uses the Batch schedule and is byte-equivalent. Explicit
schedules must be aware, strictly increasing, begin no earlier than the first
source snapshot, include every true timeframe event first-seen time, and reach
the final lifecycle snapshot. Extra As-Of points are allowed and create no
event.

## 35. No-Lookahead

OriginTime never grants visibility. Future FRESH, TEST, BROKEN, FLIPPED,
RETIRED, crossing, or non-target facts cannot alter an already supplied source
prefix. Every event first appears at its source `LifecycleSnapshot.as_of_time`,
with `first_seen_time == event_confirm_time`. Batch and Replay compare complete
payloads, not only final Direction.

## 36. Input-order invariance

Subjects, keys, eligible lists, selected IDs, source event IDs, and provenance
parents are canonically ordered. Fixed permutations therefore cannot change
selection or public serialization.

## 37. Known limitations

LATEST_CAUSAL is intentionally recency-only and may prefer a newer weak local
fact over an older durable one. Crossing resolution drops the older raw side
without fallback. The offline immutable-history baseline defines no live
watermark, correction, or revision protocol. Direction is structural state,
not empirical trading edge.

## 38. C-007 boundary

C-007, not C-006B, owns multi-timeframe resonance, dependency penalties,
weights, cluster/final ranking, and Active Box selection. This module does not
start or partially implement C-007.

## 39. Open questions

- Which H/EXP record will compare LATEST_CAUSAL with later approved policies?
- Which live watermark and correction protocol can preserve immutable events?
- Which out-of-sample stability criteria must precede any C-007 ranking rule?
- When and how should a future FORMING candidate protocol be frozen?
