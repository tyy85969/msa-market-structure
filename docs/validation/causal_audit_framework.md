# C-008A Independent Causal Audit Framework

## 1. Purpose

C-008A adds an immutable validation layer for the frozen MSA Core Alpha
pipeline. It detects cross-stage lineage conflicts, future visibility,
historical rewrites, and incomplete Batch/Replay equivalence. It does not
change, repair, or reinterpret the audited Run.

An audit PASS means only that the checked public causal contracts are
consistent. It does not establish profitability, win rate, or trading
advantage. An Active Box is a structural research object, not a trading
signal.

## 2. C-008 staging

C-008A owns audit contracts, deterministic reports, mutation detection,
synthetic engineering fixtures, and a reserved metric registry. C-008B may
later freeze metric formulas and event matching. C-008C may later conduct
formal experiments.

## 3. Independence from Core

Production audit code lives under `msa.validation`. It reads public C-007
contracts and their public `to_dict()` payloads. It calls only public replay
or Batch entrypoints when rebuilding an expected history. It does not import
underscore-prefixed C-007 helpers or reproduce scoring, eligibility,
hysteresis, projection, or lifecycle algorithms.

The auditor is a frozen, slotted dataclass containing only
`CausalAuditConfig`. It has no mutable ledger, cache, clock, random source, or
hidden previous state.

## 4. Authoritative public inputs

The audited boundary is:

- `MSACoreRun` and `MSACoreFrameBundle`;
- `MSACorePipeline` and `replay_msa_core_run()`;
- `ResonanceFrameInput`, `ResonanceFrame`, and `ResonanceFrameHistory`;
- `ResonanceScoreFrame` and `ResonanceScoreHistory`;
- `ActiveBoxSelectionFrame`, `ActiveBoxSelectionHistory`, events, and
  snapshots.

Complete serialized payloads are compared. IDs, counts, final objects, or Box
keys alone are not sufficient.

## 5. Audit contracts

`CausalAuditConfig`, `CausalAuditFact`, `CausalAuditFinding`,
`CausalAuditCheckResult`, `CausalAuditReport`, `MetricDefinition`, and
`SyntheticScenarioDescriptor` are frozen, slotted, schema-versioned
contracts. Their deserializers reject unknown fields and unknown schemas.
Datetimes are aware UTC, ordered tuples serialize as lists, and production
contracts expose no mutable list or dictionary fields.

`CausalAuditReport.passed` is exactly equivalent to having no ERROR finding.
WARNING and INFORMATIONAL treatment is configured explicitly by formal audit
code.

Each `CausalAuditKind` has one authoritative ordered check set defined by the
contract layer. A report must execute that set exactly: callers cannot delete,
repeat, reorder, rename, or append checks, even if they recompute every
semantic ID. Every finding is referenced exactly once and only by the check
whose name equals the finding code.

The assumptions tuple, public-entrypoint provenance value, ordered provenance
keys, and subject-ID bindings are also contract facts. Re-signing a payload
after changing any of them does not make the report valid.

## 6. Audit codes

Formal codes cover invalid contracts and schedules, duplicate AsOf values,
stage count/AsOf/lineage conflicts, future Evidence/context/reference data,
OriginTime visibility misuse, Active Box/event/projection time conflicts,
episode continuity, event and frozen ledgers, final Bundle and report counts,
public stage rebuilds, complete Batch/Replay mismatch, prefix rewrites, shared
AsOf rewrites, and unsupported trading fields.

Findings contain a fixed code, configured severity, stage, optional AsOf,
bounded object IDs, and bounded deterministic facts. They never embed a full
recursive Run.

Illegal, unhashable, or overlong inspected IDs and fact values are replaced by
bounded deterministic sentinels. The auditor does not call arbitrary object
`repr()` or allow a malformed nested ID to escape as an ordinary Python
exception.

## 7. Single Run audit

The single-Run audit checks strict round-trip validity, schedule order and
uniqueness, one Bundle per processing time, equal stage counts and AsOf
values, exact Score-to-Frame and Selection-to-Score consumption, every causal
availability boundary, episode continuity, ledgers, final Bundle, independent
report counts, public stage rebuilds, and the absence of trading fields.

## 8. Batch/Replay comparison

Both inputs are independently audited, then
`batch_run.to_dict() == replay_run.to_dict()` is required. A difference in any
nested Frame, Event, frozen Box, report, provenance fact, source input, or
history fails with `BATCH_REPLAY_MISMATCH`. Inputs are neither canonicalized
nor replaced by rebuilt results.

## 9. Prefix stability

The prefix schedule must be a strict starting prefix of the extended
schedule. Matching AsOf Bundles are compared by AsOf and complete payload,
not by position alone. Existing event and frozen ledgers must remain exact
prefixes. Total Run report counts may grow with the future.

## 10. Shared AsOf stability

For legal extra-AsOf comparisons, every AsOf shared before the aware UTC
cutoff must retain its complete Bundle payload. Event and frozen ledgers
before the cutoff must also match. The extra observation may affect itself
and later state, never earlier state.

## 11. Event ledger audit

The public history event ledger must equal the ordered flattening of every
SelectionFrame's emitted events. Event ConfirmTime must equal its Bundle
AsOf. The auditor never deletes or reorders events.

## 12. Frozen ledger audit

The frozen ledger must equal the ordered resulting snapshots of FROZEN
events. A FROZEN result must have FROZEN status, and a frozen episode key
cannot later appear as the current ACTIVE episode.

## 13. Mutation harness

The test-only harness injects twenty deliberate faults: three future
availability leaks, two cross-stage source conflicts, three Active Box time
conflicts, historical Bundle/Event/Frozen rewrites, reactivation, retained
projection and episode-key changes, final Bundle and report corruption, three
source-history conflicts, and one nested Batch/Replay difference. Every case
must return a failed report containing its expected formal code. The
production Core is not changed to support these mutations.

## 14. Synthetic scenario registry

Five deterministic engineering fixtures are registered: single trend, range,
V reversal, false break, and gap shock. Each uses an explicit integer seed and
constructs a formal `MSACoreRun` that passes the independent auditor.
Synthetic bars do not represent real-market distributions.

## 15. Metric registry

The fixed registry contains Confirmation Delay in bars and ATR, False Turn
Rate, Continued Break Rate, Trend Capture Ratio, MFE, MAE, Box Churn, First
Touch Reaction, and Resonance Lift. It records only name, unit, description,
interpretation, required inputs, and the status `RESERVED_FOR_C008B`.

## 16. Why formulas are deferred to C-008B

Metric formulas require separately reviewed event matching, observation
windows, denominators, and causal normalization. Freezing temporary formulas
in C-008A would silently start the next stage, so this implementation
calculates no metric values.

## 17. Determinism

Finding, check, report, metric-definition, and scenario-descriptor identities
use compact canonical JSON and SHA-256. Golden tests freeze normal and failed
report digests, comparison report IDs, metric IDs, scenario IDs, and mutation
finding-code sequences. No UUID, system time, Python `hash()`, float, object
identity, or implicit random seed supplies identity.

## 18. Failure closed behavior

Invalid entrypoint types use the validation error hierarchy. Causal
violations normally become findings. If a subject is too damaged to provide
deterministic AsOf bounds, the audit raises `CausalAuditError`; it never
returns PASS. Public entrypoints do not intentionally leak `AttributeError`,
`KeyError`, `TypeError`, or `AssertionError`.

All entrypoints resolve configuration identically. Only `None` requests the
default; falsy non-config values and post-construction mutations raise
`ValidationConfigurationError`. Prefix and shared-AsOf comparisons validate
schedules, Bundle AsOf keys, events, frozen snapshots, and their comparison
times before building maps or applying cutoff relationships. If that
relationship cannot be determined safely, they raise
`ValidationComparisonError`.

## 19. No automatic data repair

The auditor never sorts schedules, removes Frames, deduplicates events, fills
missing facts, clips times, regenerates IDs, or replaces the subject with a
rebuilt Run. Public rebuilds are comparison evidence only.

## 20. No-Lookahead

Evidence state ConfirmTime, TimeframeState ConfirmTime, and reference-bar
AvailableTime must not follow the Bundle AsOf. OriginTime is retained for
historical context but never grants visibility. Active Box events occur at
the current AsOf, and projection selection time cannot be in the future.
Every current and event-result Active Box snapshot, including CREATED and
FROZEN results, must carry an Active Box AsOf exactly equal to its Bundle
AsOf; both past and future offsets fail.

## 21. Known limitations

C-008A is an offline immutable-history audit baseline. It does not provide a
live watermark, correction protocol, distributed persistence audit,
performance capacity claim, statistical power analysis, or real-market
representativeness. Parameters have not been optimized for XAUUSD.

## 22. C-008B boundary

C-008B may define reviewed metric formulas and causal event matching. C-008A
does not calculate MFE, MAE, returns, win rate, or any other formal metric.

## 23. C-008C boundary

C-008C may define reproducible experiments, parameter sensitivity, ablation,
and out-of-sample protocols. C-008A starts no experiment and draws no
empirical market conclusion.

## 24. C-009 boundary

C-009 may later validate a separately approved Pine migration. C-008A
implements no Pine, alert, BUY/SELL label, entry/exit, stop/target, EA, or
trading behavior.
