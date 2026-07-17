# Explicit Multi-Timeframe Market-Data Resampling

## 1. Purpose

C-001C implements source-agnostic OHLCV aggregation from an approved fixed
source timeframe into M30, H1, H2, H4, H12, D, or W target bars. Its purpose
is to make alignment, coverage, publication latency, provenance, and replay
timing explicit and auditable.

This layer produces completed `CanonicalBar` values only. It does not expose a
forming target bar with final-looking OHLC values.

## 2. Dependency on C-001A and C-001B

C-001A remains authoritative for `CanonicalBar`, `Timeframe`, `VolumeType`,
half-open intervals, UTC normalization, completeness, and `available_time`.
C-001C does not copy or modify that contract.

C-001B remains the only public loading and sequence-quality boundary. C-001C
accepts its immutable `LoadResult`; it does not parse arbitrary historical
rows or repair rejected source data.

The flow is:

```text
error-free C-001B LoadResult
    -> immutable ResampleConfig
    -> explicit alignment/boundary policy
    -> coverage validation
    -> OHLCV aggregation
    -> completed HTF CanonicalBar
    -> ResampleReport
    -> chronological replay by available_time
```

## 3. Public Input Boundary

`resample_load_result`, `resample_as_of`, and `iter_resample_events` accept a
`LoadResult` whose `quality_report.has_errors` is false. The source sequence
must have:

- one canonical symbol;
- one source timeframe matching `ResampleConfig.source_timeframe`;
- one source and source timezone;
- one volume type;
- strictly ascending, unique timestamps;
- non-overlapping intervals;
- completed source bars only.

Configuration metadata and canonical bar identity must agree. A report-only
C-001B result containing errors is rejected even if some canonical rows were
constructed. C-001C never sorts, deduplicates, groups incompatible identities,
clips, fills, or modifies the source sequence.

The current implementation supports every approved fixed-duration source
timeframe; it is not hard-coded to M15. A calendar-bound D/W source is outside
the C-001C input contract because it would require a second source-calendar
composition rule.

## 4. ResampleConfig

`ResampleConfig` is frozen and records:

- `source_timeframe`;
- `target_timeframe`;
- `alignment_policy`;
- `coverage_policy`;
- explicit non-negative `publication_lag`;
- `policy_id`;
- `session_id_policy`;
- optional `output_session_id`;
- `strict`, which defaults to true.

The config `policy_id` must equal the alignment policy identifier. The target
timeframe must be strictly greater than the source timeframe. Fixed targets
must be an integer multiple of the source duration. No configuration choice is
derived from the first source bar or filename.

## 5. Fixed-Duration Alignment

M30, H1, H2, H4, and H12 use `ExplicitFixedAnchorPolicy`. A fixed duration
defines elapsed length only; it does not choose boundaries.

For target duration `T`, explicit anchor `A`, and integer `n`, a bucket is:

```text
[A + n * T, A + (n + 1) * T)
```

The target duration must divide exactly into source-duration slots. Every
source timestamp must equal one of those expected slot starts, and every source
interval must remain wholly inside its target bucket.

## 6. Explicit Anchor Policy

`ExplicitFixedAnchorPolicy` contains `policy_id`, `anchor`, and
`target_timeframe`. The anchor must be a timezone-aware UTC datetime. A naive
or non-UTC anchor fails configuration.

The policy never defaults to UTC midnight, Unix epoch, the first input bar,
the first day in a file, a Pandas origin, or an undocumented broker midnight.
An approved configuration may deliberately provide UTC midnight, but that
choice remains explicit and identified by `policy_id`.

## 7. Calendar / D-W Boundary Interface

D and W use `ExplicitBoundarySchedule`. Each `ExplicitBoundary` supplies:

- UTC `start_time`;
- UTC `end_time`;
- the exact expected source timestamp starts.

The schedule supplies `policy_id` and target timeframe. At runtime it produces
a `TargetBucket` containing the concrete boundary, policy identifier, and
expected slots. Boundaries must be ordered and non-overlapping. A source bar
outside the schedule or crossing a supplied boundary is rejected.

This is an interface for synthetic tests or a separately approved external
calendar. It is not a production XAUUSD daily/weekly calendar and does not
assume D equals 24 hours or W equals seven 24-hour days.

## 8. Coverage Policies

`CONTIGUOUS_FIXED` derives every expected source start from the explicit anchor,
source duration, and target duration. Internal missing slots, empty buckets,
extra slots, misalignment, and cross-boundary bars are errors. No gap is
filled.

`EXPLICIT_EXPECTED_SLOTS` uses exactly the starts declared by the calendar or
session schedule. A planned break is represented by omitting that start from
the approved expected set; it is never inferred from actual input.

An input ending partway through its last bucket is recorded as a trailing
incomplete bucket and is not emitted. This expected terminal truncation is a
warning. A missing earlier or internal slot is a strict coverage error. In
as-of replay, not-yet-available source members are reported as incomplete
warnings because absence at that processing time is causal, not a repairable
data defect.

## 9. OHLCV Aggregation

For one complete valid bucket:

```text
timestamp = bucket.start_time
end_time  = bucket.end_time
open      = first source member open
high      = maximum source member high
low       = minimum source member low
close     = last source member close
```

All prices remain `Decimal`. C-001C does not synthesize values for an
incomplete bucket.

## 10. Volume Semantics

- `VolumeType.REAL`: sum all real-volume members as `Decimal`;
- `VolumeType.TICK`: sum all tick-volume members as `Decimal`;
- `VolumeType.UNAVAILABLE`: output `volume=None`.

Volume types cannot be mixed. Tick volume is never relabeled as real volume.
`None` is never interpreted as zero, and a partial set of missing numeric
volumes cannot be silently summed.

## 11. Target available_time

Every completed target bar uses:

```text
base_available_time = max(
    target end_time,
    maximum source member available_time
)

target available_time = base_available_time + publication_lag
```

Consequently, a target cannot confirm before its interval ends. Any delayed
source member delays the target, including an early member that arrives after
later members. The explicit publication lag is applied last and recorded in
the config snapshot and report assumptions.

The formula does not use a member opening timestamp, the next target bucket,
system execution time, or file-end time.

## 12. Batch Semantics

`resample_load_result` calculates every complete target bucket present under
the configured boundary and coverage policy. Each returned bar retains its
causal `available_time`; batch calculation does not make all bars available at
once.

`iter_resample_events` orders completed batch bars by
`(available_time, timestamp)`. Event order may therefore differ from target
timestamp order when an older bucket has a longer source delay.

## 13. Replay / As-Of Semantics

`resample_as_of(load_result, config, processing_time)` first admits only source
bars for which:

```text
source_bar.is_confirmed_at(processing_time) is True
```

It validates coverage over that causal snapshot and then returns only target
bars satisfying:

```text
target_bar.available_time <= processing_time
```

Repeated evaluation at the same processing time is deterministic. Later
source buckets do not mutate an already completed historical target bucket.
Tests compare both final OHLC and the first availability event, because final
series equality alone does not prove no-lookahead behavior.

## 14. Incomplete Bucket Handling

An incomplete bucket never produces a completed target `CanonicalBar`. The
report records its expected count, member count, missing count, timestamp
range, and `INCOMPLETE` status. C-001C does not:

- guess missing OHLC;
- forward-fill or backward-fill;
- insert a synthetic source bar;
- treat file termination as confirmation;
- emit a forming target with its future final high, low, or close.

Once all real source members are present and causally available, a later replay
snapshot may emit the completed target for the first time.

## 15. Provenance

The target bar inherits canonical symbol, source, source timezone, and volume
type. Its timeframe is the configured target, and `boundary_policy` is the
explicit resampling `policy_id`.

`SessionIdPolicy.INHERIT_IF_UNANIMOUS_ELSE_NONE` inherits one unanimous member
value. Conflicting member values are deterministically cleared to `None` and
reported; the implementation never chooses the first member at random.
`SessionIdPolicy.EXPLICIT` uses the configured value, including an explicitly
chosen `None`.

`ResampleResult` retains the config snapshot, source and target timeframes,
input/output counts, target bars, and report. `BucketAudit` stores bounded
membership summaries rather than copying an unbounded complete member list
into every target bar.

## 16. ResampleReport

The immutable report records:

- input and output bar counts;
- complete, incomplete, and rejected bucket counts;
- missing-slot, misaligned-bar, cross-boundary, and source-identity counts;
- earliest and latest emitted target timestamps;
- warnings, errors, assumptions, and `policy_id`;
- per-bucket start/end, status, expected/member/missing/extra counts;
- per-bucket member timestamp range and maximum member availability;
- the target availability derived for complete buckets.

## 17. Strict Failure Rules

Strict mode rejects:

- a `LoadResult` containing errors;
- incomplete, mixed-identity, mixed-timeframe, mixed-volume-type, duplicate,
  out-of-order, or overlapping source input;
- absent or mismatched alignment provenance;
- naive or non-UTC anchors and boundaries;
- targets not greater than their source or not exactly divisible;
- source bars outside expected slots or crossing boundaries;
- internal coverage gaps and extra slots;
- D/W without an explicit boundary schedule;
- invalid or negative publication lag.

Non-strict resampling may return unaffected valid buckets with a report that
contains bucket errors. It never changes the source data or turns an invalid
bucket into a target bar. Public input validation remains mandatory in either
mode.

## 18. No-Lookahead Guarantees

- Only completed source bars enter aggregation.
- A target bar appears no earlier than both its end and every member's
  availability, plus publication lag.
- No forming target exposes final OHLC.
- Replay consumes source information as of the requested processing time.
- Batch events and replay first-appearance events are tested for equality.
- Future buckets cannot rewrite a previously emitted target bar.
- No system clock, file tail, following bucket, or inferred calendar supplies
  confirmation.

These guarantees implement the data-layer requirements of ADR-0002. They do
not approve a downstream market-structure algorithm.

## 19. Out of Scope

C-001C does not choose an XAUUSD provider, download data, identify sessions,
connect to MT5/TradingView/brokers, implement a database or websocket, merge
historical corrections, or implement Swing, Pivot, Fractal, ZigZag, ATR,
periodic levels, support/resistance, clustering, lifecycle, resonance, Active
Box, Fibonacci, Imbalance, Pine Script, signals, EA behavior, or optimization.

## 20. Open Questions

- Which XAUUSD data provider and source configuration will be approved first?
- Which production D/W boundary and holiday policy will be approved?
- Which production H4/H12 anchor will be approved?
- How will a future revision/correction event model preserve old availability?

C-001C does not answer these questions. The first approved source
configuration must supply its anchors and calendar boundaries explicitly.
C-001D will independently audit this implementation; C-001C does not start
that audit or any C-002 work.
