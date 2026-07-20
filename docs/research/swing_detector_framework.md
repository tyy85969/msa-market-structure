# Swing Detector Experiment Framework

## 1. Purpose

C-003A/B define a research-only, pluggable Swing detector protocol and four
causal baselines: confirmed Fractal/Pivot, ATR turning-point, Pivot plus
structure confirmation, and ATR turning-point plus structure confirmation.
The baselines make causal timing, configuration, provenance, batch, As-Of,
and replay behavior testable. They do not select a final Swing algorithm and
make no trading claim.

## 2. Dependency on C-001/C-002

Public detector entry points consume an error-free C-001 `LoadResult` and reuse
its immutable `CanonicalBar`, `Timeframe`, `available_time`, and quality report.
They do not parse, sort, deduplicate, fill, repair, or resample source data.

Every output reuses C-002 `LevelCandidate`, `PriceRange`, `ScaleDescriptor`,
`ProvenanceRef`, `StructureSourceType`, `BoundarySide`, `MarketRole`,
`ConfirmationStatus`, and `LifecycleState`. C-003 creates no parallel domain
model.

## 3. Research-Only Status

Every detector is a reproducible baseline for later comparison. None is
hard-coded into the production core or approved as optimal. C-003B performs no
parameter search, detector ranking, or real-trading evaluation and does not
advance C-004 or C-005.

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

C-003A supports only `strict=True`. This field declares the strict fail-closed
experiment input mode: invalid configuration, source quality, identity,
sequence, completeness, or causal availability fails instead of producing a
report-only result. `strict=False` is unsupported and fails during config
construction or deserialization. A future non-strict or report-only mode must
define separately approved behavior and use an explicit schema/version change;
it cannot silently reuse the current schema.

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

`TiePolicy.STRICT` and `PivotDetectorConfig.strict` are different concepts.
The tie policy defines strict high/low comparison inequalities. The config
field declares strict fail-closed input/error handling and, in C-003A, must be
exactly `True`.

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
- explicit scale and the `strict=true` mode marker.
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

## 19. Causal Prefix for Stateful Detectors

ATR state and both structure-confirmation detectors consume a fixed sequence
prefix. As-Of starts at the first source bar and stops at the first bar that is
incomplete or whose `available_time` follows `processing_time`. That blocker
and every later bar are excluded, even when a later bar has an earlier arrival
time. No bar is skipped, sorted, filled, repaired, or synthesized.

For fixed index `i`:

```text
prefix_available_time[i] = max(
    bar.available_time for bar in bars[0:i+1]
)
```

Any state fact confirmed while processing index `i` has ConfirmTime no earlier
than this prefix maximum. Batch, As-Of, and replay use the same fixed ordering.

## 20. ATR True Range and SMA

C-003B uses exact `Decimal` arithmetic. For the first bar:

```text
TR[0] = high[0] - low[0]
```

For each later bar:

```text
TR[i] = max(
    high[i] - low[i],
    abs(high[i] - close[i-1]),
    abs(low[i] - close[i-1]),
)
```

ATR is deliberately the simple moving average, not Wilder, EMA, or a hidden
third-party indicator:

```text
ATR[i] = mean(TR[i-atr_period+1:i+1])
```

The first ATR exists only after `atr_period` true-range observations. The
configuration requires `atr_period >= 1`, a finite positive Decimal reversal
multiplier, an explicit scale, and `strict=True`.

## 21. ATR Turning-Point State Machine

The ATR detector is the C-003B ZigZag baseline. It starts in `UNKNOWN`. At the
first available ATR it stores that bar's close as `anchor_close`; later closes
above or below the anchor enter `UP` or `DOWN`. Equal closes retain `UNKNOWN`.
Entering `UP` starts the extreme at that bar's high; entering `DOWN` starts it
at that bar's low.

In `UP`, a bar confirms the pre-bar high extreme when:

```text
bar.low <= pre_bar_high - reversal_multiplier * ATR[i]
```

The output is an `UPPER` / `RESISTANCE` / `SWING` confirmed candidate. `DOWN`
is symmetric and emits `LOWER` / `SUPPORT` / `SWING`. Equality reaches the
threshold. OriginTime is the stored extreme bar timestamp; ConfirmTime is the
reversal bar's prefix maximum availability.

## 22. Conservative Same-Bar Policy

The detector first tests reversal against the extreme that existed before the
current bar. It updates the current-direction extreme only when that reversal
does not occur. It never raises the high or lowers the low and then uses the
same OHLC bar to confirm that newly observed extreme in the opposite direction.
Equal highs or lows retain the earlier extreme. This policy avoids inventing an
unknown intrabar path from OHLC.

## 23. Pivot Structure Confirmation Baseline

`StructureBreakDetector` reuses the unchanged C-003A `PivotDetector` as its
seed. Only confirmed `SWING` candidates with the approved side/role mapping are
eligible; seed OriginTime never grants visibility. The latest confirmed seed
of a side replaces that side's unresolved pending seed.

For a pending upper seed, the reference is the latest causally available lower
seed whose OriginTime precedes the pending upper OriginTime. The lower case is
symmetric. A break bar must follow the complete confirmation windows of both
seeds. A right-window bar used to confirm a Pivot cannot simultaneously act as
an earlier structure-confirmation bar.

## 24. Close-Only Break Rule

The supported basis is exactly `CLOSE`, and the buffer is a finite non-negative
Decimal:

```text
pending upper: close <= reference lower.low - break_buffer
pending lower: close >= reference upper.high + break_buffer
```

A wick crossing without the close does not confirm. Output OriginTime, price,
side, role, timeframe, and scale come from the pending seed. Output ConfirmTime
is:

```text
max(
    pending_seed.confirm_time,
    reference_seed.confirm_time,
    prefix_available_time[break_bar_index],
)
```

## 25. ATR Plus Structure Confirmation

`AtrStructureBreakDetector` reuses confirmed ATR turning-point candidates as
seeds and applies the same close-only break, earlier-opposing-reference, latest
pending replacement, buffer, and causal-prefix rules. Its output represents an
ATR turning point that subsequently received opposing-structure close
confirmation. It does not return ordinary ATR seeds unchanged.

The combined candidate retains the ATR seed's OriginTime and price, while its
ConfirmTime is no earlier than the pending ATR seed, its reference ATR seed,
and the break bar's causal prefix time. Its candidate prefix, structure family,
source module, and provenance are distinct from both plain ATR and Pivot-based
structure outputs.

## 26. Deterministic Candidate IDs

All C-003B IDs use SHA-256 over canonical UTF-8 JSON with sorted keys and
compact separators. ATR identity includes detector/version/policy, ATR period,
multiplier, side, OriginTime, ConfirmTime, exact price, origin and confirmation
bar keys, ATR value, finite ATR-window facts, scale, strict mode, and the
same-bar policy.

Structure identity includes the complete detector config, pending and
reference seed IDs, break bar key, exact break close and buffer, side, price,
OriginTime, and ConfirmTime. No ID uses array position alone, filename,
`datetime.now()`, random UUID, Python `hash()`, or the final file length.

## 27. Bounded Provenance

ATR provenance references its finite ATR window plus origin and confirmation
bars. Structure provenance references exactly the pending seed ID, reference
seed ID, and break bar key, with bounded notes for detector, policy, close
basis, exact close, buffer, and replacement rule. It never embeds an unlimited
history or mutates either seed.

## 28. Batch, As-Of, and Replay Parity

Batch processes the complete validated fixed sequence and retains each factual
ConfirmTime. As-Of applies the causal prefix and returns no candidate before its
ConfirmTime. Default replay advances over unique source `available_time`
values, calls As-Of, and requires first appearance to equal candidate
ConfirmTime. Events remain ordered by `(confirm_time, candidate_id)`.

Parity compares full candidate identity, OriginTime, ConfirmTime, side, exact
price, structure family, provenance, and first-seen time rather than final price
alone.

## 29. Report Semantics

The public `SwingDetectionReport` schema remains unchanged. For the ATR
detector, `evaluated_center_count` counts bars with an available ATR,
`leading_incomplete_count` counts warm-up bars,
`trailing_incomplete_count` records one unresolved directional endpoint when
present, and `rejected_window_count` counts trend bars that did not reverse.

For structure confirmation, `evaluated_center_count` counts eligible pending,
reference, and break-bar close evaluations; `trailing_incomplete_count` counts
unresolved pending sides; and `rejected_window_count` counts evaluated closes
that did not reach the threshold. Warnings disclose warm-up, `UNKNOWN`, gaps,
unresolved state, and causal-prefix truncation. No field contains a synthetic
or estimated count.

## 30. Known Limitations and Deferred Comparison

- The stateful APIs operate on a prevalidated offline sequence; they do not
  define live watermarks, correction events, or permanently missing-bar policy.
- ATR uses only the explicitly fixed SMA definition in this baseline.
- The conservative same-bar rule intentionally declines to infer intrabar path.
- Latest-confirmed pending replacement is a baseline policy, not a claim of
  optimality.
- Gaps are reported and retained; no session/calendar rule splits state.
- No detector comparison, parameter optimization, sensitivity analysis,
  out-of-sample ranking, or final selection is performed in C-003B.
- Candidate pooling and clustering belong to C-005. Lifecycle transitions,
  including `FRESH`, `TESTED`, and `BROKEN`, belong to C-006.

## 31. Out of Scope

C-003B contains no periodic high/low, historical reaction support/resistance,
Level Pool, clustering, deduplication, lifecycle engine, resonance, Active Box,
Fibonacci, Imbalance, RSI, volume/momentum filter, signal, EA, Pine Script,
network download, parameter optimization, or real-trading conclusion. It does
not start C-005.

## 32. Open Questions

- Which explicit H/EXP record will govern comparative detector evaluation?
- Which session/calendar policy, if any, should prevent actual-bar windows from
  spanning particular XAUUSD closures?
- What live watermark and late/correction event contract would replace the
  current prevalidated offline replay boundary?
- Which scale IDs and parameter grids will be approved before comparison?
- What out-of-sample and stability criteria will govern eventual selection?
