# C-001D Market-Data and MTF No-Lookahead Audit Checklist

Audited commit: `ccab8d28e6b46479d87346ed0dbe8daf06e0d86f`

Verdict: **PASS WITH NON-BLOCKING LIMITATIONS**

This checklist records the independent C-001D adversarial coverage. A checked
item means the behavior was exercised by C-001D tests or by an explicit
configuration-construction rejection. It does not approve a real XAUUSD data
provider, broker calendar, or live-stream ingestion design.

## CanonicalBar

- [x] `timestamp`, `end_time`, and `available_time` reject naive datetimes.
- [x] Aware non-UTC inputs normalize to aware UTC without conflating the three times.
- [x] Completed bars cannot become available before `end_time`.
- [x] Incomplete snapshots may be observed before `end_time` but never confirm.
- [x] M15 bars with 10-minute or 20-minute actual intervals are rejected.
- [x] Every approved fixed timeframe has an exact elapsed-duration contract.
- [x] D/W bars require a named boundary policy.
- [x] NaN, infinity, invalid OHLC relationships, and invalid volume are rejected.
- [x] `volume=None` remains distinct from observed `volume=0`.
- [x] Serialization round trips preserve times, enums, completeness, provenance, and availability.
- [x] Normal dataclass mutation is blocked by frozen `CanonicalBar` semantics.

## Loader and Quality Layer

- [x] OPEN_TIME and CLOSE_TIME produce the expected half-open UTC interval.
- [x] IANA timezone localization and matching fixed UTC offsets are accepted.
- [x] Ambiguous and nonexistent DST wall times are rejected.
- [x] Embedded offsets conflicting with `source_timezone` are rejected.
- [x] Explicit completion requires an observed-time column.
- [x] Incomplete availability comes only from its own observed time, not a later row or file tail.
- [x] Negative availability lag is rejected.
- [x] Symbol mapping is exact; mismatches are rejected rather than aliased.
- [x] Volume meaning remains explicit through `VolumeType` and config provenance.
- [x] Duplicate, conflicting duplicate, out-of-order, overlap, and invalid-row attacks fail closed.
- [x] Fixed-interval gaps are reported and never filled or synthesized.
- [x] Missing fields and invalid OHLCV/timestamps retain row and field context.
- [x] `strict=False` results with errors are rejected by the resampling boundary.
- [x] Input records and CSV bytes remain unchanged.
- [x] Appending future rows does not change already loaded earlier canonical bars.
- [x] D/W loading requires and preserves an explicit boundary and concrete end time.

## Alignment and Resampling

- [x] M15 to M30/H1/H2/H4/H12 aggregation was independently checked.
- [x] H1 to H2/H4 aggregation was independently checked.
- [x] Targets not greater than their source are rejected.
- [x] Non-integral source-duration slot construction is rejected.
- [x] Missing, naive, non-UTC, or provenance-mismatched policies are rejected.
- [x] Anchor changes alter buckets only through the explicit policy.
- [x] The first source bar is not an implicit anchor.
- [x] Misaligned source slots and cross-boundary intervals are rejected.
- [x] Internal, leading, and fully empty buckets fail strict coverage.
- [x] A terminal trailing incomplete bucket is warned and not emitted.
- [x] Mixed symbol, source, timezone, timeframe, or volume type is rejected.
- [x] Incomplete source bars are rejected from confirmed resampling.
- [x] D/W targets require an explicit boundary schedule.
- [x] Duplicate, unordered, and overlapping D/W boundary definitions are rejected.
- [x] A synthetic 23-hour D and 5.5-day W schedule work without 24x7 assumptions.
- [x] Session-ID conflicts are explicitly cleared and reported.
- [x] Publication lag is explicit and non-negative.
- [x] Any delayed member, including the earliest member arriving last, delays the target.

## No-Lookahead, Replay, and Metamorphic Checks

- [x] H1 final OHLC is absent at 15, 30, 45, and 60 minutes while a member remains unavailable.
- [x] A target first appears only at `max(target end, all member availability) + publication_lag`.
- [x] Batch and replay final bars match for valid complete inputs.
- [x] Batch and replay first-appearance events match for valid complete inputs.
- [x] Event order follows `(available_time, timestamp)`, not timestamp alone.
- [x] Non-monotonic source availability replays deterministically.
- [x] Repeating the same processing time returns the same result.
- [x] Appending later buckets does not change existing target bars.
- [x] Mutating future-bucket prices does not rewrite prior target OHLC.
- [x] Publication-lag shifts change availability only, not OHLCV.
- [x] Explicit anchor shifts change only the declared bucket partition.
- [x] Source records and canonical inputs remain unchanged by replay.
- [x] Fixed-seed randomized M30/H1/H2 batch/replay comparisons pass.
- [x] A permanently missing slot never produces a synthetic target.

## Explicit Design Limitations

- [x] `resample_as_of` prevalidates the complete supplied `LoadResult` before
  causal filtering. A future quality or identity defect therefore rejects the
  dataset fail-closed even for an earlier `processing_time`. This is accepted
  only for prevalidated historical replay; it is not a live-stream contract.
- [x] Without a watermark or end-of-stream signal, replay treats missing causal
  members as incomplete warnings. Strict batch validation remains the final
  detector for a permanently missing internal slot; replay still does not emit
  a target for that incomplete bucket.
- [x] No real XAUUSD provider, correction/revision model, or production D/W
  calendar was approved by C-001A/B/C or by this audit.

## Evidence Commands

```text
python -m pytest -q
python -m pytest tests/audit -q
python -m pytest tests/lookahead -q
git diff --check
```
