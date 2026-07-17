# Source-Agnostic Market-Data Loading

## 1. Purpose

C-001B provides a source-configured boundary between CSV or iterable records
and the canonical market-data contract. It adapts explicitly described source
rows, validates their sequence, and returns immutable `CanonicalBar` values
with an auditable `DataQualityReport`.

This task does not select the final XAUUSD provider. It provides an adapter
framework only. A first production source configuration requires separate
review and approval. A source is never identified from its filename, column
names, symbol spelling, or numeric values.

## 2. Dependency on the C-001A Contract

The loader imports and constructs the existing `CanonicalBar`, `Timeframe`,
and `VolumeType` types. It does not copy, subclass, or redefine the canonical
schema. C-001A remains authoritative for interval bounds, OHLCV validity,
UTC-aware datetimes, completion, and `available_time`.

C-001C may consume only `CanonicalBar` sequences that have passed this loading
and quality layer. C-001B does not start C-001C or aggregate any timeframe.

## 3. Source Configuration

`SourceDataConfig` is an immutable snapshot of source semantics. It records:

- `source` and `source_timezone`;
- `source_symbol`, `canonical_symbol`, and optional `symbol_column`;
- canonical `timeframe`;
- `timestamp_column`, `timestamp_semantics`, and `timestamp_format`;
- explicit source columns for open, high, low, and close;
- `volume_column` or `None`, plus `volume_type`;
- `completed_bar_policy` and, when needed, the complete-state column and its
  exact true/false value mappings;
- explicit `observed_time_column` for `EXPLICIT_COLUMN` snapshot versions;
- explicit `availability_lag`;
- optional `session_id` and `boundary_policy`;
- optional explicit `open_time_column` or `end_time_column` for interval
  boundaries;
- CSV `delimiter` and strict/report-only behavior.

Required semantic choices have no data-driven fallback. In particular,
`availability_lag`, timestamp semantics, source and canonical symbols, volume
meaning, and completion policy must be supplied by configuration.

For D/W `OPEN_TIME`, both `end_time_column` and `boundary_policy` are required.
For D/W `CLOSE_TIME`, both `open_time_column` and `boundary_policy` are
required. The loader does not infer a daily or weekly session boundary.

## 4. Explicit Symbol Mapping

`source_symbol = "GOLD"` and `canonical_symbol = "XAUUSD"` form an explicit
mapping. No built-in alias table converts `GOLD`, `XAUUSD.a`, or any other
spelling automatically.

When `symbol_column` is configured, each row must contain exactly the declared
`source_symbol`; empty or mismatched values fail strict loading. When the
source has no symbol column, the immutable configuration declares the symbol
for the complete input explicitly. The quality report records the mapping as
an assumption.

## 5. Timestamp Semantics

`TimestampSemantics.OPEN_TIME` means the source timestamp is the inclusive bar
opening boundary. For fixed intraday timeframes, the loader derives the ending
boundary by adding the C-001A fixed duration unless an explicit
`end_time_column` is configured.

`TimestampSemantics.CLOSE_TIME` means the source timestamp is the exclusive bar
ending boundary. For fixed intraday timeframes, the loader derives the opening
boundary by subtracting the fixed duration unless an explicit
`open_time_column` is configured.

The loader never guesses OPEN_TIME versus CLOSE_TIME from names or values.
Any explicit boundary still passes the C-001A interval-duration validation.

## 6. Timezone Conversion

The configuration accepts an explicit IANA timezone such as
`America/New_York` or a numeric offset such as `+02:00`. A timezone-naive CSV
timestamp is localized only through that configured timezone. A timestamp
that contains an offset must agree with the configured timezone at that local
wall time.

This localization rule also applies to an explicit snapshot observed time.
Ambiguous DST wall times without an offset and nonexistent DST wall times fail
with row, field, raw value, and reason. The loader never chooses a DST fold or
repairs a nonexistent time silently. All emitted `timestamp`, `end_time`, and
`available_time` values are aware UTC datetimes.

## 7. Completed-Bar Policy

`ALL_ROWS_ARE_CLOSED` is an explicit assertion that every source row is a
completed historical bar. It sets `is_complete=True` and records the assertion
in the report. `observed_time_column` may be omitted and does not replace the
closed-bar `end_time` availability basis.

`EXPLICIT_COLUMN` requires a configured state column, disjoint and non-empty
true/false value sets, and an explicit `observed_time_column` on every row.
Parsing is exact. Unknown strings, booleans, and generic truthy values are not
coerced. An explicitly incomplete row remains an incomplete `CanonicalBar`;
it never enters a confirmed stream merely because an availability time exists.

C-001B does not implement streaming and does not manufacture historical
forming snapshots from a final closed-bar CSV.

## 8. Availability Lag

Every configuration supplies a non-negative `timedelta`. Zero is valid only
when explicitly configured. `ALL_ROWS_ARE_CLOSED` applies:

```text
available_time = end_time + availability_lag
```

`EXPLICIT_COLUMN` applies independently for every concrete row version:

```text
available_time = explicit observed_time + availability_lag
```

A completed explicit row cannot claim an observed time before `end_time`, and
its final `available_time` must remain at or after `end_time`. An incomplete
snapshot must have an explicit observation time. Its `available_time` may be
before `end_time` but cannot precede the bar `timestamp`, and it can never enter
a confirmed stream.

The loader does not infer an incomplete snapshot's observation time from its
future `end_time`, a following row, or a file-level timestamp. `available_time`
remains part of every returned and serialized `CanonicalBar`, so chronological
replay uses the real availability of each concrete data version.

## 9. CSV and Record Loading Flow

The source-agnostic flow is:

```text
UTF-8 CSV / Iterable Records
    -> explicit source column mapping
    -> timestamp, timezone, symbol, volume, and completion normalization
    -> CanonicalBar construction
    -> sequence-quality validation in original row order
    -> LoadResult + DataQualityReport
```

`load_csv(path, config)` uses Python's standard `csv` module and the configured
single-character delimiter. It validates required headers, reads UTF-8, does
not use the network, and never writes to the input path. `load_records` applies
the same adapter rules to iterable mappings.

`LoadResult` contains the immutable bars, quality report, configuration
snapshot, and loaded/accepted/rejected row counts.

## 10. Strict Validation

Strict mode is the default. Invalid timestamps, timezone conflicts, symbol
mismatches, invalid OHLC, invalid volume, unknown completion states,
duplicates, conflicts, out-of-order rows, and overlapping fixed intervals make
the complete load fail with `DataLoadError`.

The exception retains the complete `DataQualityReport`. Each error contains a
row number, field, bounded raw-value representation, and reason. The loader
does not put secrets, API keys, or connection strings into configuration or
exception context.

`strict=False` is an explicit report-only option. It may return validly
constructed rows alongside an error report, but it still does not sort,
deduplicate, repair, or synthesize data. Downstream canonical consumption must
use an error-free result.

## 11. DataQualityReport

The immutable report records:

- `total_rows`, `accepted_rows`, and `rejected_rows`;
- `duplicate_count` and `conflicting_duplicate_count`;
- `out_of_order_count`, `overlap_count`, and `gap_count`;
- invalid OHLC, timestamp, and volume counts;
- symbol mismatch count;
- source and timeframe;
- earliest and latest canonical timestamps;
- traceable warning and error tuples;
- explicit configuration assumptions.

Accepted rows are rows that constructed a `CanonicalBar` before the strict
sequence gate. A strict load still fails as a whole when the report has any
error.

## 12. Duplicate and Conflict Policy

The duplicate key is `symbol + timeframe + timestamp`. An identical repeated
bar is an error. A repeated key with different OHLCV, completion,
availability, or provenance is a conflicting duplicate and is also an error.

C-001B never keeps the first, keeps the last, or merges revisions silently.
Future correction support must define a revision identifier, a `supersedes`
relationship, the revision's own `available_time`, and full provenance. It
must not overwrite old history in place.

## 13. Interval Overlap and Gap Reporting

For adjacent, ascending bars with the same symbol and fixed timeframe,
`previous.timestamp < current.timestamp < previous.end_time` is an
`interval_overlap` error. Strict loading fails and records the current row,
current timestamp, and `previous.end_time`. Equal timestamps remain duplicate
or conflicting-duplicate errors and are not counted again as overlaps.

The loader never repairs an overlap by moving a timestamp, clipping an
interval, sorting rows, or deleting either bar. C-001C must later choose any
alignment anchor used for resampling, but regardless of that future choice,
adjacent canonical intervals within one source load for the same symbol and
timeframe cannot overlap.

For a fixed-duration timeframe, a later adjacent input timestamp beyond the
next expected interval produces an `interval_gap` warning. The report includes
the concrete interval from the preceding `end_time` to the next timestamp.

A gap is not automatically a bad bar. It may reflect a weekend, holiday, or
session closure. C-001B has no calendar with which to decide. It reports the
gap and never forward-fills, backward-fills, or inserts synthetic bars. D/W
gap inference is not performed because those periods are calendar/session
bound.

## 14. Provenance

Every bar retains the configured source, source timezone, session identifier,
and boundary policy. The immutable configuration snapshot and quality-report
assumptions retain the symbol mapping, timestamp semantics, completion policy,
available-time basis, and availability lag used for the load.

Source corrections are reported as duplicates or conflicts; they do not
rewrite earlier bars.

## 15. No-Lookahead Rules

- The loader preserves `available_time` separately from bar opening time.
- A completed row cannot become available before `end_time`.
- Each explicit incomplete snapshot requires its own observed time.
- Incomplete availability is never inferred from `end_time`, a later row, or
  the final timestamp in a file.
- A forming snapshot's OHLC is preserved as that version; later final OHLC is
  not backfilled into it.
- A final historical CSV is not expanded into imaginary incomplete snapshots.
- Completion never depends on a later row or the final timestamp in a file.
- Input order is audited as supplied; the loader never silently sorts it.
- Duplicate removal, repairs, and future rows never rewrite earlier bars.
- No structure, indicator, score, signal, or trade calculation occurs here.

These rules make the batch output eligible for chronological replay by
`available_time`; they do not by themselves approve any downstream model.

## 16. Out of Scope

C-001B does not implement downloads, provider APIs, MT5, TradingView, broker
integration, databases, caches, streaming, session calendars, resampling,
M15-to-HTF aggregation, D/W generation, market structure, Swing, Pivot,
ZigZag, support/resistance, clustering, lifecycle, resonance, Active Box,
Pine Script, signals, EA execution, or parameter optimization.

## 17. Open Questions

The project owner must decide separately:

- the final XAUUSD data provider and first approved real source configuration;
- whether the first source is broker, MT5, or TradingView-derived data;
- the XAUUSD daily close and weekly boundary policy;
- H4/H12 and other future resampling alignment anchors;
- source revision and historical correction policy;
- any approved calendar needed to distinguish expected closures from missing
  data.

No answer to these questions is implied by C-001B.
