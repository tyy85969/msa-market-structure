# Causal Structure Lifecycle Event Engine

## 1. Purpose

C-006A defines a research-only immutable lifecycle layer for confirmed structural boundaries. It records activation, tests, weakening, close-only breaks, flips, and retirement as deterministic events. It does not make a trading claim.

## 2. Dependencies

The engine consumes the existing C-001 `LoadResult` and `CanonicalBar` contracts and the C-002 `BoundaryRef` domain snapshot. Subjects originate from C-003/C-004 `LevelCandidate` or C-005 `StructureCluster` facts. No second market-data, price-range, timeframe, provenance, or boundary model is introduced.

## 3. Why lifecycle does not rewrite C-005 clusters

A C-005 cluster ID freezes its formation members and ConfirmTime. Later tests, breaks, and flips are new facts. Rewriting a cluster would erase the distinction between formation knowledge and later lifecycle knowledge, so C-006A retains the original `subject_ref` and creates a separate event ledger plus immutable state snapshots.

## 4. Lifecycle event ledger

The supported event types are `ACTIVATED`, `TEST`, `WEAKENED`, `BROKEN`, `FLIP_TOUCH`, `FLIPPED`, and `RETIRED`. Every state change has an event; state-preserving TEST and FLIP_TOUCH events also remain explicit. Events are globally ordered by `(event_confirm_time, subject_id, event_id)`.

Within that global order, each subject owns one continuous event chain. The chain begins with exactly one `ACTIVATED` event at the subject ConfirmTime. Every later event names the immediate predecessor in `prior_event_ids`, starts from the predecessor's `to_state`, and cannot move ConfirmTime backward. Test counts advance by exactly one only for TEST or WEAKENED events. No event may follow FLIPPED or RETIRED. Event provenance identifies the event itself and contains the subject plus the immediate predecessor when one exists.

## 5. LifecycleSubjectState

Each state preserves the original subject, structural OriginTime and ConfirmTime, current state ConfirmTime, AsOfTime, effective side and role, test count, break/flip/retirement facts, ordered event IDs, deterministic state ID, and bounded provenance. `RETIRED` keeps history; it does not delete the subject.

The state is a verifiable derived view of its complete event prefix, not an independent mutable claim. Its lifecycle state, state ConfirmTime, test count, effective side/role, latest-test fields, and break/flip/retirement facts must match the corresponding ledger events exactly. State provenance identifies the state and contains both the original subject ID and the latest event ID.

## 6. CONFIRMED to FRESH

At the subject's own ConfirmTime, `ACTIVATED` atomically transitions `CONFIRMED -> FRESH`. It requires no price bar, does not increase test count, and cannot appear at OriginTime merely because historical drawing may begin there.

## 7. Test zone

For subject range `[low, high]`, the inclusive test zone is `[low - test_tolerance, high + test_tolerance]`. A completed bar touches when its high reaches the lower edge and its low reaches the upper edge. Invalid or negative zone bounds fail; they are never clipped.

## 8. Separation

Counted tests must be at least `minimum_test_separation_bars` apart by actual `CanonicalBar` sequence index. A source gap creates no synthetic bars. Existing bars advance separation even when wall-clock spacing is irregular.

## 9. WEAKENED

The first valid test moves `FRESH -> TESTED`. Reaching `weakening_test_count` moves `TESTED -> WEAKENED`. Later valid tests remain explicit `WEAKENED -> WEAKENED` TEST events and continue increasing the count.

## 10. Close-only Break

UPPER/RESISTANCE breaks when close is at or above `range.high + break_buffer`. LOWER/SUPPORT breaks symmetrically at or below `range.low - break_buffer`. Equality breaks; wick-only penetration does not.

## 11. Break-before-Test ordering

Every active bar checks Break first. Only a bar that did not break may count as a new Test. One bar therefore cannot be both a Break and Test, and a Break never increments test count.

## 12. Flip zone

The inclusive flip zone is `[low - flip_tolerance, high + flip_tolerance]`. It is observed only after Break. The Break bar itself cannot be a flip touch.

## 13. Flip confirmation

A later bar must first touch the flip zone. That touch bar cannot also confirm. After an UPPER break, a subsequent close at or above `flip_zone.high + flip_confirmation_distance` confirms the flip; LOWER is symmetric below the zone.

## 14. Flip horizon

For Break index `B`, confirmation is allowed on actual indexes `B+1` through `B+flip_horizon_bars`, inclusive. If the endpoint is processed without a flip, the subject retires with `FLIP_HORIZON_EXPIRED`. No expired flip is revived.

## 15. Failed-break retirement

Before a flip, an UPPER break retires when close returns to or below `range.low - failed_break_retirement_buffer`; LOWER is symmetric above the range. This conservative check precedes flip processing and records `FAILED_BREAK`.

## 16. Effective side and role after Flip

Only `FLIPPED` reverses the effective mapping: UPPER/RESISTANCE becomes LOWER/SUPPORT, and LOWER/SUPPORT becomes UPPER/RESISTANCE. The original `subject_ref` remains unchanged and auditable.

## 17. Causal prefix

As-Of processing begins at the first source bar and stops at the first incomplete bar or bar whose availability follows processing time. That blocker and all later bars are excluded. A delayed early bar is never skipped to process a later timestamp.

## 18. Subject monitoring start

A subject enters only when processing time reaches its ConfirmTime. Price monitoring uses only complete bars with `bar.timestamp >= subject.confirm_time`. If confirmation occurs during an observation bar, that whole bar is excluded and monitoring starts with the next complete bar.

## 19. Event OriginTime

Bar-driven event OriginTime is the source bar opening timestamp. Activation uses the structural ConfirmTime because it is a visibility event rather than a historical price observation.

## 20. Event ConfirmTime

For source index `i`, bar-driven event ConfirmTime is `max(bar.available_time for source[0:i+1])`. It can be later than the event bar's own availability when an earlier prefix member was delayed. `first_seen_time` always equals Event ConfirmTime.

## 21. Deterministic IDs

Event, state, and snapshot identities hash canonical compact sorted-key UTF-8 JSON with SHA-256. Exact Decimal strings, causal times, configuration, subject facts, source bar keys, evidence, and necessary prior event identity are included. No clock, UUID, Python hash, filename, or input position supplies identity.

## 22. Provenance

Event provenance references the original subject and at most the immediate prior event. State provenance references the subject and latest event. Complete bar history is never copied into provenance.

## 23. Batch

Batch advances over the sorted unique union of subject ConfirmTimes and source bar available times. Subjects or bars sharing a time are evaluated in one As-Of snapshot, which makes simultaneous activation atomic.

All snapshots in one history use the same configuration. Visible subject IDs are monotonic: once a subject appears, it cannot disappear, and its original `BoundaryRef` cannot change under the same object ID. Each later state event list extends the earlier list as a prefix. When no new event exists, every state fact except AsOfTime must remain identical.

## 24. As-Of

As-Of requires an aware processing time and returns immutable visible states, the complete event prefix, configuration, and a bounded report. The full immutable input is validated fail-closed before causal filtering.

## 25. Replay

Default replay uses the same Batch schedule. An explicit schedule must be aware, strictly increasing, unique, and include every true Event first-seen time. Sparse late discovery cannot masquerade as causal first appearance.

Ledger, state, provenance, and history-coherence checks are public C-006A contract validation. They do not infer trend direction, rebuild price decisions, or introduce C-006B `TimeframeState` behavior.

## 26. No-Lookahead guarantees

OriginTime never grants activation. Confirmation bars must be available. The continuous prefix blocks later data behind delayed early data. Future appends or price changes do not rewrite earlier event payloads. Every new fact produces a new immutable state, while old events remain unchanged. Batch and replay compare complete event and snapshot payloads.

## 27. Known limitations

This is an offline, prevalidated-history baseline without live watermarks, correction events, or a late-revision protocol. Gaps count actual bars rather than a production session calendar. OHLC cannot resolve intrabar path. Thresholds are caller-supplied baseline parameters and are not approved XAUUSD values.

## 28. C-006B boundary

C-006B, not this module, may construct `TimeframeState` or define up/down/range/turning state. C-006A exposes lifecycle facts only.

## 29. C-007 boundary

C-007, not this module, owns multi-timeframe resonance, dependency penalties, cluster ranking, boundary selection, and Active Box behavior.

## 30. Open questions

- Which H-XXX and EXP-XXX records will compare lifecycle thresholds and alternative policies?
- Which live watermark and correction protocol can preserve the immutable event ledger?
- Which session calendar should govern gap interpretation for real XAUUSD data?
- Which out-of-sample stability criteria are required before any lifecycle parameter influences the core model?

C-006A contains no TimeframeState engine, trend direction, resonance score, Active Box, Fibonacci, Imbalance, RSI, volume/momentum filter, signal, EA, Pine code, parameter optimization, or real-trading conclusion.
