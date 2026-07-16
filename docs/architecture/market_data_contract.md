# Canonical Market-Data Contract

## 1. Purpose

This document defines the single market-data contract that C-001B data
adapters and C-001C multi-timeframe resampling must obey. XAUUSD is the first
research market, but this contract is intentionally not hard-coded to one
symbol, broker, or venue.

The contract covers normalized bar data and time availability only. It does
not define a trading or market-structure algorithm.

## 2. CanonicalBar Schema

`CanonicalBar` is an immutable, validated value object with these fields:

| Field | Meaning |
|---|---|
| `symbol` | Explicit canonical symbol; symbol mapping must not be silent |
| `timeframe` | Approved `Timeframe` enum value |
| `timestamp` | Inclusive bar opening time, normalized to aware UTC |
| `end_time` | Exclusive bar interval end, normalized to aware UTC |
| `open`, `high`, `low`, `close` | Finite `Decimal` prices |
| `volume` | Non-negative `Decimal`, or `None` when unavailable |
| `volume_type` | `REAL`, `TICK`, or `UNAVAILABLE` |
| `source` | Non-empty data-source identifier |
| `source_timezone` | Original source timezone identifier or declared offset |
| `session_id` | Optional source/session identifier |
| `boundary_policy` | Optional boundary-policy identifier; required for D/W |
| `is_complete` | Whether the bar interval and final OHLCV are complete |
| `available_time` | Earliest real-time moment the represented data is safe to consume |

`end_time` is included because interval closure and D/W boundaries cannot be
validated from the opening timestamp alone. `boundary_policy` is included so a
calendar-bound bar can identify the external rule that produced its boundary
without implementing that calendar in this task.

Numeric inputs may arrive as `Decimal`, `int`, or finite `float`, but the
canonical object stores prices and available volume as `Decimal`. This avoids
making binary floating-point representation part of the serialized contract.

## 3. Timestamp Semantics

`timestamp` is the bar opening time, never the closing time. At system
boundaries, `timestamp`, `end_time`, and `available_time` are timezone-aware UTC
datetimes. Timezone-naive values are invalid. Aware non-UTC inputs are
normalized to UTC, while the original source timezone remains explicit in
`source_timezone`.

The three times remain separate during serialization and batch processing.
Keeping only `timestamp` is a contract violation.

## 4. Bar Interval Semantics

A bar represents the half-open interval:

```text
[timestamp, end_time)
```

The opening boundary is inclusive and the ending boundary is exclusive.
`end_time` must be later than `timestamp`. For fixed-duration intraday
timeframes it must equal `timestamp + timeframe.fixed_duration`.

## 5. Available-Time Semantics

`available_time` is the earliest real-time instant at which this exact bar
representation may safely be consumed by the corresponding data flow. It is
not an alias for `timestamp` or `end_time`.

For a normally close-confirmed completed bar, `available_time` must be at or
after `end_time`. A source may set it later to represent publication, transport,
or confirmed-ingestion latency. A completed bar is safe for a confirmed stream
at processing time `t` only when:

```text
is_complete and t >= available_time
```

## 6. Complete vs Incomplete Bars

`is_complete=true` means the interval has closed and the bar contains final
values under the declared source and boundary policy. Its `available_time`
cannot precede `end_time`.

`is_complete=false` is an explicitly forming snapshot. Its `available_time`
describes when that snapshot was observable, but never promotes it into the
confirmed/closed-bar stream. Consumers must use the confirmed-at guard and
must not infer confirmation merely because an `available_time` exists.

Incomplete snapshots must not be backfilled with their later final high, low,
or close. This task defines no exceptional early-completion event model.

## 7. Timeframe Contract

The stable approved codes are:

| Code | Fixed duration |
|---|---|
| `M15` | 15 minutes |
| `M30` | 30 minutes |
| `H1` | 1 hour |
| `H2` | 2 hours |
| `H4` | 4 hours |
| `H12` | 12 hours |
| `D` | No; boundary policy required |
| `W` | No; boundary policy required |

Code must use `Timeframe` values rather than scattered arbitrary strings.

## 8. Daily and Weekly Boundary Policy

D and W are calendar/session-bound periods, not fixed UTC windows. Their
opening and ending instants must be supplied by a documented source calendar,
session policy, or explicit boundary policy. The resulting `CanonicalBar`
records the concrete UTC `timestamp` and `end_time` plus a non-empty
`boundary_policy` identifier.

This contract does not decide the XAUUSD daily boundary. Brokers and sources
may use different sessions, DST rules, weekend handling, and holiday calendars.
C-001B/C must select and document the applicable policy; they must not assume
UTC 00:00 or convert D/W blindly from a fixed duration.

## 9. OHLCV Validation

Construction fails with an explainable `ContractValidationError` when:

- `high < open`, `high < close`, or `high < low`;
- `low > open` or `low > close`;
- any OHLC value is NaN or positive/negative infinity;
- non-null volume is negative or non-finite;
- `symbol`, `source`, or `source_timezone` is empty;
- a time field is timezone-naive;
- fixed-duration `end_time` is inconsistent;
- completed `available_time` precedes `end_time`.

Invalid OHLC values are rejected. The canonical contract never swaps, clamps,
forward-fills, backward-fills, or otherwise repairs them automatically.

## 10. Volume Semantics

`REAL` means source-reported traded volume. `TICK` means a count or measure of
price-update activity and is not real traded volume. Adapters must never
silently relabel tick volume as `REAL`.

`UNAVAILABLE` means no volume observation exists and therefore requires
`volume=None`. `REAL` and `TICK` require a non-negative numeric value. A value
of `0` is an observed zero and is different from `None`, which means absent.

## 11. Data Quality Rules

Sequences presented to downstream consumers must be ordered by ascending
`timestamp`. More than one bar with the same
`symbol + timeframe + timestamp` is a data-quality error unless an explicit,
traceable correction policy is applied before canonical consumption.

Missing bars must be reported. They must not be silently synthesized, and OHLC
must not be forward-filled or backward-filled. Conflicting bars must not be
silently overwritten. DST, weekends, holidays, and session boundaries belong
to later source adapters and calendar policies.

This task does not implement a complete sequence-quality scanner.

## 12. Provenance

Every bar preserves `source`, `source_timezone`, optional `session_id`, and
optional `boundary_policy`. Source symbol-to-canonical symbol mapping must be
explicit and traceable. Cleaning, correction, and mapping decisions belong in
adapter provenance; they must not occur silently inside `CanonicalBar`.

Serialization round trips preserve both event times, interval boundaries,
timeframe, volume type, completeness, OHLCV, source timezone, session, and
boundary policy.

## 13. No-Lookahead Requirements

- Only information available at the processing time may be emitted.
- Confirmed streams accept only completed bars at or after `available_time`.
- An unfinished higher-timeframe bar's final OHLC is future information.
- C-001C may emit final HTF OHLC as confirmed only after the HTF `end_time` and
  its resulting `available_time`.
- Historical or batch data must not replace an earlier incomplete snapshot with
  final values as though they had already been known.
- Batch structures must preserve `available_time`; final-series equality alone
  does not prove chronological equivalence.

These rules implement the data-layer implications of ADR-0002.

## 14. Out of Scope

C-001A does not implement loaders, CSV/Parquet/Pandas integration, downloads,
broker or platform APIs, databases, caching, sequence-quality scanning,
missing-bar repair, session calendars, resampling, or any structure, indicator,
signal, execution, or optimization logic.

## 15. Open Questions

- Which source/broker and symbol mapping will C-001B approve for the first
  XAUUSD dataset?
- Which named session/calendar policy will define XAUUSD D and W boundaries?
- How will adapters record source corrections or late revisions without
  silently overwriting canonical history?
- Will a later task need an explicit exceptional completion/correction event
  model in addition to ordinary closed bars?

C-001B and C-001C must answer their applicable questions while continuing to
obey this contract.
