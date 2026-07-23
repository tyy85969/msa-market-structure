# C-007C Causal Active Box Selector Engine

## 1. Purpose

C-007C-ENGINE executes the frozen Active Box contracts across authoritative
C-007B score frames. It creates, observes, freezes, and replaces structural Box
episodes. It does not define a trading signal.

## 2. C-007C-CONTRACT dependency

The engine delegates all policy and identity facts to the existing C-007C
contract, policy, and projection helpers. Those modules remain authoritative.

## 3. C-007B authoritative input

`ResonanceScoreFrame` and `ResonanceScoreHistory` are the only scoring inputs.
The selector does not read C-007A histories, lifecycle histories,
TimeframeState histories, bars, Swings, Levels, or Pools.

## 4. Stateless selector

`ActiveBoxSelector` is a frozen, slotted dataclass containing only an immutable
`ActiveBoxSelectionConfig`. The caller supplies the previous ACTIVE snapshot;
the selector stores no mutable runtime cache or hidden history.

## 5. Selector input boundary

Each call validates the formal ScoreFrame, symbol, optional previous snapshot,
ACTIVE status, exact config, explicit output context, stable Zone keys, and
strictly advancing AsOf time. Invalid engine state fails closed.

## 6. Single-Frame algorithm

The selector builds exactly one LOWER and one UPPER decision, resolves any
selected Zones in the current ScoreFrame, compares the selected pair with the
previous pair, invokes the matching formal snapshot/event helpers, and finishes
with `build_selection_frame()`.

## 7. SideDecision delegation

Both sides call `build_side_decision()`. Eligibility, nearest-qualified
ordering, C-007C hysteresis, actions, and decision identities are neither
recomputed nor modified by the engine.

## 8. Selected Zone resolution

A selected side must provide both stable key and snapshot ID. The current
ScoreFrame must contain exactly one same-side Zone matching both facts.
Key-only lookup, stale snapshots, duplicates, and non-current Zones fail closed.

## 9. Initial pair creation

With no previous Box, a complete LOWER/UPPER pair is projected at the current
ScoreFrame AsOf, passed to `create_active_box_snapshot()`, and recorded by one
`CREATED(INITIAL_PAIR)` event.

## 10. Partial pair behavior

Without a previous Box, zero or one selected side produces no projection, Box,
or event. The engine never creates a half Box.

## 11. Retain and observe

When both selected stable keys equal the previous pair, the engine calls
`observe_active_box_snapshot()`. It updates current observed Zone snapshot IDs
and AsOf time without emitting an event.

## 12. Why unchanged Box does not reproject

Stable `zone_key_id` defines episode continuity. Score, freshness, Direction,
rank, or Zone snapshot changes do not replace the original projections,
creation time, selection price, or Box key.

## 13. Pair unavailable

If either side becomes unselected while a Box is ACTIVE, the complete episode
is frozen with `FROZEN(PAIR_UNAVAILABLE)`. The current SelectionFrame has no
ACTIVE Box and retains no single boundary.

## 14. Pair reappearance

After an unavailable freeze, the next frame receives no previous ACTIVE state.
A later complete pair therefore creates a distinct `INITIAL_PAIR` episode; an
old Box key is never revived.

## 15. Pair changed

When both sides remain selected but either stable key changes, the previous
episode freezes and a new episode is created at the same current AsOf.

## 16. Why replacement reprojects both sides

A replacement is a new episode. Both selected Zones are projected from the
current ScoreFrame even when one stable key did not change, so both boundaries
share the new episode's causal observation context.

## 17. Atomic Event ordering

Replacement events are always ordered as
`FROZEN(PAIR_CHANGED)` followed by `CREATED(PAIR_CHANGED)`.
`build_selection_frame()` and the history contract revalidate this ordering.

## 18. Frozen history

Batch history flattens Frame events in Frame order. Every FROZEN event's
resulting snapshot is retained in `frozen_boxes` in event order.

## 19. Batch

Batch processes every source ScoreFrame once in its formal order. The previous
state for the next frame is exactly the current SelectionFrame's optional
ACTIVE snapshot. Frames without an Active Box are never omitted.

## 20. Replay

Default Replay consumes the original ScoreHistory and is complete-payload
equivalent to Batch. Replay never fabricates or rescales a C-007B frame.

## 21. Extra ScoreFrame rules

An explicit replay history may contain valid extra ScoreFrames with the same
scoring config. Times and frame IDs must remain unique, every original frame
must remain byte-equivalent, and original relative order must be preserved.
The output history records the actual replay ScoreHistory.

## 22. Determinism

The engine only composes deterministic contract functions. It uses no system
time, UUID, Python hash, random tie-break, float, global state, object identity,
or set iteration as output semantics.

## 23. No-Lookahead

Selection and projection consume only the current immutable ScoreFrame.
Visibility follows upstream ConfirmTime and current Frame AsOf; OriginTime does
not grant eligibility. Appending future frames cannot rewrite prior complete
SelectionFrames, events, projections, or frozen snapshots.

## 24. Error boundary

Selector input and state failures use `ActiveBoxEngineError`. Replay schedule
and history failures use `ActiveBoxReplayError`. Public entrypoints type-check
before nested attribute access and do not intentionally expose
`AttributeError`, `KeyError`, or `AssertionError`.

## 25. Parameter disclaimer

All thresholds and margins are research configuration. They have not been
optimized for XAUUSD or validated as profitable parameters.

## 26. Known limitations

This is an offline immutable-history baseline without live watermarks,
correction handling, streaming persistence, parameter validation, or
profitability evaluation.

## 27. C-007D boundary

C-007D integration is not started. The selector does not provide Pine,
TradingView, alerts, or downstream production adaptation.

## 28. C-008 validation boundary

C-008 must independently evaluate stability, sensitivity, ablation,
out-of-sample behavior, and empirical no-lookahead. Active Box is not a buy or
sell signal and this stage defines no entry, exit, stop, target, or EA behavior.
