# Swing Detector Experiment Framework

## 1. Purpose

C-003A defines a research-only, pluggable Swing detector protocol and one
confirmed Fractal/Pivot baseline. The baseline exists to make causal timing,
configuration, provenance, batch, As-Of, and replay behavior testable. It is
not the final selected Swing algorithm and it makes no trading claim.

## 2. Dependency on C-001/C-002

Public detector entry points consume an error-free C-001 `LoadResult` and reuse
its immutable `CanonicalBar`, `Timeframe`, `available_time`, and quality report.
They do not parse, sort, deduplicate, fill, repair, or resample source data.

Every output reuses C-002 `LevelCandidate`, `PriceRange`, `ScaleDescriptor`,
`ProvenanceRef`, `StructureSourceType`, `BoundarySide`, `MarketRole`,
`ConfirmationStatus`, and `LifecycleState`. C-003A creates no parallel domain
model.

## 3. Research-Only Status

The Pivot detector is a reproducible baseline for later comparison. It is not
hard-coded into the production core, is not approved as optimal, and does not
advance C-003B or C-004. No parameter optimization or real-trading conclusion
is part of this stage.

## 4. Detector Protocol

`SwingDetector` exposes:

- immutable `config`;
- stable `detector_id` and `detector_version`;
- `detect_batch(LoadResult)`;
- `detect_as_of(LoadResult, processing_time)`;
- `iter_events(LoadResult)`.

The shared outputs are immutable `SwingDetectionResult`,
`SwingDetectionReport`, and `SwingDetectionEvent` values. Their public
serialization is deterministic, JSON-compatible, and versioned with
`schema_version=1`.

## 5. PivotDetectorConfig

`PivotDetectorConfig` records explicit `detector_id`, `detector_version`,
`left_bars`, `right_bars`, `tie_policy`, `scale`, `policy_id`, `strict`, and
`schema_version`. Both bar counts must be at least one. `scale` is a caller-
supplied `ScaleDescriptor`; it is never inferred from `Timeframe`.

The configuration is frozen, contains no clock or random default, rejects
unknown fields and schema versions, and round-trips through `to_dict` and
`from_dict`.

## 6. Strict Tie Policy

C-003A implements only `STRICT`:

```text
high pivot: center.high > every other window member high
low pivot:  center.low  < every other window member low
```

Equal highs or equal lows invalidate that side. The implementation does not
pick the first, last, or visually preferred equal extreme. One wide center bar
may independently satisfy both rules and then emits distinct UPPER and LOWER
candidates.

## 7. Input Sequence Semantics

The complete `LoadResult` is prevalidated as one fixed historical sequence.
It must have an error-free C-001 quality report, one symbol, one `Timeframe`,
one source, strictly ascending unique timestamps, non-overlapping intervals,
and valid canonical OHLC. Any participating bar must be complete and causally
available. Invalid inputs fail; none are repaired.

As-Of uses the prevalidated fixed sequence to retain window membership when
availability is non-monotonic. It reads a window's OHLC only after every fixed-
position member is complete and `available_time <= processing_time`. A delayed
member therefore cannot be skipped so that later bars collapse into an earlier
window. This is an offline prevalidated-history replay API, not a live
watermarked ingestion or correction API.

## 8. Gap Semantics

`left_bars` and `right_bars` count actual canonical bars in sequence, not
missing wall-clock slots. A source gap is retained and reported; no imaginary
bar or price is inserted. A window may span a reported gap because the baseline
defines membership by actual confirmed bar count. Whether a particular market
closure should split a Swing experiment requires a future explicit session or
calendar policy.

## 9. OriginTime

`LevelCandidate.origin_time` is exactly the center bar `timestamp`. A future
historical chart may backplot the marker to this time for context. OriginTime
does not make the candidate available to events or downstream consumers.

## 10. ConfirmTime

For center index `i`, with complete window
`[i-left_bars, ..., i, ..., i+right_bars]`:

```text
ConfirmTime = max(member.available_time for every complete window member)
```

This formula includes delayed left, center, and right members. It does not use
the center `end_time`, last right opening time, next window, file tail, or
system time. The event becomes effective exactly at ConfirmTime, never before.

## 11. LevelCandidate Mapping

Both sides use `source_type=SWING`, `confirmation_status=CONFIRMED`,
`lifecycle_state=CONFIRMED`, `touch_count=0`, and empty touch/break fields.
`structure_family` is the stable `confirmed-pivot-strict-v1` identifier.

| Pivot | Boundary side | Market role | Price range |
|---|---|---|---|
| High | `UPPER` | `RESISTANCE` | `[center.high, center.high]` |
| Low | `LOWER` | `SUPPORT` | `[center.low, center.low]` |

`FRESH`, `TESTED`, `BROKEN`, and every other lifecycle transition belong to
C-006 and are not assigned here.

## 12. Deterministic IDs

Candidate IDs use SHA-256 over canonical UTF-8 JSON. The identity includes:

- detector ID and version;
- policy ID and schema version;
- symbol and timeframe;
- boundary side;
- center OriginTime;
- causal ConfirmTime and source;
- exact Decimal price string;
- left/right counts and tie policy;
- explicit scale and strict setting.
- ordered window bar keys, compared high/low values, and member availability.

The public form is `swing-pivot-v1-<sha256>`. There is no `uuid4`, clock,
Python `hash()`, array-position identity, or filename identity. Equal facts and
configuration reproduce the same ID; changing a structural fact or config
changes it.

## 13. Provenance

Each candidate stores `source_module=msa.research.swing.pivot`, the detector
version as `source_version`, a deterministic side-specific Pivot-window source
object ID, `policy_id`, and bounded notes for detector, version, policy, tie
rule, timeframe, side, and window dimensions.

Every window member is referenced by this documented stable key:

```text
bar:v1:<canonical JSON of source, symbol, timeframe, timestamp>
```

JSON keys are sorted, UTF-8 is used, and compact separators are fixed. The
finite window references are stored as `ProvenanceRef.parent_object_ids`;
complete `CanonicalBar` objects are not copied into provenance.

## 14. Batch

Batch evaluates every complete fixed-position window in the approved history.
Candidates retain their real ConfirmTime and are ordered by
`(confirm_time, candidate_id)`. `iter_events` emits the same order with each
event's `first_seen_time` equal to its candidate ConfirmTime.

## 15. As-Of

`processing_time` must be timezone-aware. As-Of admits a source member only
when it is complete and its `available_time` is no later than processing time.
A fixed window is evaluated only when all of its members are admitted, and the
result returns only candidates whose ConfirmTime has been reached. Report
counts and time bounds disclose only causally visible/evaluated results.

## 16. Replay

Default replay advances through the sorted unique source `available_time`
events. It calls As-Of at every step, records each candidate once, and fails if
its first appearance differs from its declared ConfirmTime. An explicit replay
schedule must be timezone-aware, strictly ascending, unique, and include every
causal event needed to claim exact first appearance.

Batch events and replay events must match in candidate identity, price,
OriginTime, ConfirmTime, provenance, and first-seen time—not only final price.

## 17. Incomplete Windows

Bars without complete left context are counted as leading incomplete. Bars
without complete and available right context are counted as trailing/forming.
Neither case emits a `LevelCandidate`. C-003A does not create a FORMING domain
candidate and does not treat file termination as confirmation.

## 18. No-Lookahead Guarantees

- OriginTime never grants causal availability.
- Every right-side confirmation bar contributes its `available_time`.
- A delayed earlier member also delays confirmation.
- Incomplete final OHLC never enters confirmed Pivot detection.
- As-Of never compresses a fixed window around an unavailable member.
- Future bars outside a completed confirmation window cannot change the old
  candidate's ID, price, OriginTime, ConfirmTime, or provenance.
- Batch and replay compare exact first appearances.

Historical graphics may later backplot to OriginTime, but events can become
effective only from ConfirmTime.

## 19. Out of Scope

C-003A contains no ATR reversal, ZigZag, structure-break detector, combined
detector, periodic high/low, historical reaction support/resistance, clustering,
lifecycle engine, resonance, Active Box selection, Fibonacci, Imbalance, RSI,
volume/momentum filter, signal, EA, Pine Script, network download, optimization,
or real-trading conclusion.

## 20. C-003B Plan

C-003B remains deferred. Subject to a separate approved task, it may add the
other Issue #5 baselines under the same protocol and test them independently
before any comparison or selection. C-003A does not implement or scaffold
those detectors and does not announce optimal parameters.

## 21. Open Questions

- Which explicit H/EXP record will govern comparative detector evaluation?
- Which session/calendar policy, if any, should prevent actual-bar windows from
  spanning particular XAUUSD closures?
- What live watermark and late/correction event contract would replace the
  current prevalidated offline replay boundary?
- Which scale IDs and parameter grids will be approved before comparison?
- What out-of-sample and stability criteria will govern eventual selection?
