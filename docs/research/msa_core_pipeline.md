# Causal MSA Core Alpha Pipeline

## 1. Purpose

C-007D composes the approved C-007A resonance frame, C-007B scoring, and
C-007C Active Box stages into one immutable research Run. It audits exact
lineage and causal availability; it does not add an algorithm.

## 2. C-007D scope

The stage owns integration contracts, one Bundle per AsOf, a stateless Batch
entrypoint, unified Replay, deterministic Run identity, end-to-end
no-lookahead validation, and a bounded research report.

## 3. C-007A dependency

`ResonanceFrameInput`, `ResonanceFrameAssembler`, and
`ResonanceFrameHistory` remain authoritative for lifecycle visibility,
timeframe context, completed reference bars, and the default processing
schedule. C-007D never constructs a `ResonanceFrame` manually.

## 4. C-007B dependency

`ResonanceScorer` and `ResonanceScoreHistory` remain authoritative for Zone
clustering, dependency adjustment, quality, selection score, explanation,
and ranking. C-007D does not recalculate any of those facts.

## 5. C-007C dependency

`ActiveBoxSelector` and `ActiveBoxSelectionHistory` remain authoritative for
eligibility, hysteresis, projection, create/retain/replace/freeze behavior,
events, and frozen history. C-007D does not reinterpret Box state.

## 6. Authoritative input boundary

The only raw integration input is a formally round-trippable
`ResonanceFrameInput`. Its reference symbol and timeframe must match the
integration Frame config. Timeframe histories must exactly cover configured
contexts; their legal input order is normalized to the canonical config
context order. A Run additionally replays that canonical input through the
official C-007A `replay_history()` API with its stored Frame config and exact
processing schedule, then requires complete `ResonanceFrameHistory` payload
equality. Re-signing a Run around different lifecycle, timeframe, reference
bar, future-fact, or default-schedule input therefore fails closed.

## 7. MSACoreConfig

`MSACoreConfig` contains only integration identity and the three formal child
configs. It is frozen, slotted, schema-versioned, strict-only, and rejects
symbol or context-weight coverage conflicts. Child engine and policy
identities remain independent and authoritative.

## 8. Stateless pipeline

`MSACorePipeline` is a frozen, slotted dataclass containing only
`MSACoreConfig`. It has no runtime cache, mutable ledger, clock, random state,
or hidden previous Box.

## 9. Batch chain

Batch calls, in order:

```text
ResonanceFrameAssembler.build_batch(source_input)
ResonanceScorer.build_batch(resonance_history)
ActiveBoxSelector.build_batch(score_history)
```

Only after all three formal histories exist does C-007D build Bundles, the
report, and the Run.

## 10. FrameBundle

Every processing time has one `MSACoreFrameBundle` containing the exact
`ResonanceFrame`, `ResonanceScoreFrame`, and `ActiveBoxSelectionFrame` at that
index. All three AsOf values must be equal.

## 11. Exact lineage

Each ScoreFrame must embed and identify the Bundle ResonanceFrame. Each
SelectionFrame must embed and identify the Bundle ScoreFrame. Bundle
provenance has exactly those three frame IDs as parents. Re-signed but
source-inconsistent payloads fail closed.

## 12. Run contract

`MSACoreRun` stores the canonical source input, exact processing schedule,
three formal histories, ordered Bundles, final Bundle, report, config, and
bounded provenance. Every nested public contract completes a strict
serialization round trip during validation.

## 13. Report

`MSACoreRunReport` recomputes stage counts, Evidence and Zone counts, CREATED
and FROZEN counts, frozen boxes, Box/no-Box frames, final Box state, and all
four engine IDs from authoritative histories. Successful Runs have empty
warnings and errors.

## 14. Default Replay

`replay_msa_core_run(..., processing_times=None)` is complete-payload
equivalent to `pipeline.run(source_input)`, including source input, histories,
Bundles, report, identities, and provenance.

## 15. Explicit Replay

Explicit Replay delegates schedule validation and C-007A frame construction
to `replay_history()`. It then builds effective C-007B and C-007C histories
through their formal Batch APIs.

## 16. Extra AsOf rules

An explicit schedule must be aware, strictly increasing, unique, begin no
earlier than common causal availability, and contain every default Frame
time. Legal extra AsOf values are allowed. The complete prefix before an
insertion is unchanged; the inserted observation and later state may differ.

## 17. Stage Replay cross-audit

C-007D calls `replay_score_history()` against the baseline C-007A history and
requires every replayed ScoreFrame payload to equal the effective Batch
ScoreFrame. It calls `replay_active_box_history()` against the baseline score
history and requires the complete effective Active Box history payload to
match.

## 18. Determinism

The same canonical source input, integration config, and processing schedule
produce identical stage histories, Bundles, report, Run ID, and complete Run
payload. Input object identity and set iteration do not supply output order.

## 19. Identity

Bundle, Run, source-input digest, and history digest identities use compact
canonical JSON plus SHA-256. They use no UUID, system time, Python `hash()`,
float, random choice, or memory position.

## 20. Provenance

Bundle provenance is bounded to its three frame IDs. Run provenance is bounded
to the canonical source digest, three history digests, final Bundle, and
report digest. Module, version, policy, source object, and the single
integration engine note are exact.

## 21. No-Lookahead

Every Bundle audits Evidence state ConfirmTime, TimeframeState ConfirmTime,
and reference-bar AvailableTime against its AsOf. Score and selection stages
consume only their embedded current source frame. Event time and current Box
AsOf equal the current Bundle AsOf.

## 22. Prefix stability

Appending immutable future lifecycle snapshots, timeframe snapshots, or
reference bars cannot change an earlier full Bundle payload. Future Zone,
score, selection, event, and frozen-box effects cannot backfill earlier
Bundles. OriginTime grants no visibility.

## 23. Error boundary

Configuration, input, integration, Replay, and serialization failures use the
dedicated `MSACore*Error` hierarchy. Public entrypoints type-check before
nested access and do not intentionally leak `AttributeError`, `KeyError`,
`TypeError`, or `AssertionError`.

## 24. Parameter disclaimer

All child thresholds, weights, margins, and policies are explicit research
configuration. They have not been optimized for XAUUSD and establish no
profitability, win-rate, or trading advantage.

## 25. Known limitations

This is an offline immutable-history integration baseline. It has no live
watermark, correction protocol, persistence layer, resource-capacity claim,
or parameter validation. The 100+ AsOf test is a functional smoke test only.

## 26. C-008 boundary

C-008 may separately study stability, sensitivity, ablation, sample
dependence, and out-of-sample behavior. C-007D starts none of those
experiments.

## 27. C-009 boundary

C-009 may later migrate approved semantics to Pine/TradingView and validate
semantic equivalence. C-007D implements no Pine, alert, buy/sell signal,
entry/exit, stop/target, EA, or trading recommendation. An Active Box is a
structural research object, not advice.
