# Periodic Extreme and Historical Reaction Level Framework

## 1. Purpose

C-004 defines two research-only, deterministic `LevelCandidate` generators:
`PERIODIC_EXTREME` and `HISTORICAL_REACTION`. They provide explainable V1
candidate sources without selecting trades, optimizing parameters, clustering
prices, or changing lifecycle state.

## 2. Dependency on C-001/C-002/C-003A

Public generation input reuses the immutable C-001 `LoadResult`,
`CanonicalBar`, and `Timeframe`. It reuses C-002 `LevelCandidate`,
`PriceRange`, `ScaleDescriptor`, `ProvenanceRef`, and the stable domain enums.
Historical Reaction accepts confirmed C-003A-style `SWING` candidates as
seeds. C-004 creates no second data, timeframe, price-range, or level model.

## 3. Research-Only Status

Both generators are parameterized baselines for reproducible comparison. They
are not approved as optimal, make no trading or performance claim, and do not
enter the formal Pine implementation. Core-model admission still requires a
documented hypothesis, experiment, review, and later out-of-sample evidence.

## 4. Level Generator Protocol

`LevelGenerator` exposes an immutable config plus:

- `generate_batch(LevelGenerationInput)`;
- `generate_as_of(LevelGenerationInput, processing_time)`;
- `iter_events(LevelGenerationInput)`.

`LevelGenerationInput` contains one C-001 `LoadResult` and an ordered tuple of
C-002 seed snapshots. Periodic requires the tuple to be empty; Historical
Reaction requires it to be non-empty.

Configs, results, reports, and events are frozen, use `schema_version=1`, fail
on missing/unknown fields or schema versions, serialize Decimal values as
strings and tuples as ordered lists, and contain no system-clock, random UUID,
pickle, or Python-hash identity. Results contain confirmed candidates only,
ordered by `(confirm_time, candidate_id)`. Every event has
`first_seen_time == candidate.confirm_time`.

## 5. Periodic Input Contract

`PeriodicExtremeGenerator` requires the source and config timeframes to match.
All source bars must preserve one symbol, timeframe, source, source timezone,
and boundary policy. The supplied C-001 quality report must be error-free, and
timestamps must remain unique, ascending, and non-overlapping. Invalid OHLC,
duplicates, overlap, order errors, mixed identity, and mixed boundary policies
fail; no input is sorted or repaired.

## 6. No Reaggregation Rule

Periodic consumes bars already loaded and, when needed, resampled by C-001.
It never aggregates a lower timeframe, chooses an anchor, discovers a session,
or invents D/W boundaries. H4 candidates require H4 input; D/W candidates
require D/W input carrying its explicit `boundary_policy`.

## 7. Periodic OriginTime Limitation

Periodic `OriginTime` is exactly the periodic bar opening timestamp. It marks
the beginning of the represented interval, not the unknown intraperiod instant
at which its high or low occurred. An aggregated OHLC bar cannot justify a
fabricated intraperiod extreme timestamp.

## 8. Periodic ConfirmTime

For each completed periodic bar:

```text
ConfirmTime = bar.available_time
```

The high maps to `UPPER/RESISTANCE`; the low maps to `LOWER/SUPPORT`. Both use
`source_type=PERIODIC_EXTREME`, singleton exact-Decimal price ranges,
`confirmation_status=CONFIRMED`, `lifecycle_state=CONFIRMED`, zero touches,
and empty touch/break fields.

## 9. Incomplete Period Behavior

An incomplete periodic bar emits no confirmed or forming candidate. A trailing
incomplete suffix is ignored and reported without mutation. If a completed bar
follows an incomplete bar in the fixed input sequence, Periodic fails closed
instead of skipping the incomplete interval and continuing. A changing high or
low in a forming period is never backfilled as a historically confirmed level.

## 10. Historical Reaction Seeds

Historical Reaction accepts only non-empty, unique, explicitly ordered
`SWING` seeds. Each must be confirmed, have a ConfirmTime, use a singleton
price range, and match the source symbol and timeframe. `UPPER` requires
`RESISTANCE`; `LOWER` requires `SUPPORT`. Seeds must already be ordered by
`(confirm_time, candidate_id)`; the generator never sorts, deduplicates,
modifies, merges, or reprices them.

## 11. Reaction Zone

For seed price `P` and explicit `touch_tolerance`:

```text
zone.low  = P - touch_tolerance
zone.high = P + touch_tolerance
```

The inclusive C-002 `PriceRange` remains authoritative. A negative lower bound
fails; it is not clipped to zero. Every seed owns an independent zone even
when several zones overlap.

## 12. Touch Semantics

A completed eligible bar touches when:

```text
bar.high >= zone.low and bar.low <= zone.high
```

One seed may have only one active attempt. The touch bar starts an attempt but
cannot confirm its own rejection, because OHLC does not reveal an intrabar
path. Only later actual canonical bars may confirm or reject the attempt.

## 13. Rejection Confirmation

For touch index `T` and `H = confirmation_horizon_bars`, the confirmation
window is inclusive and fixed:

```text
T + 1 <= confirmation_index <= T + H
```

Within those subsequent actual bars:

- UPPER/RESISTANCE succeeds when `bar.close <= zone.low - min_reaction_distance`;
- LOWER/SUPPORT succeeds when `bar.close >= zone.high + min_reaction_distance`.

A wick reaching the close-away threshold is insufficient. The close condition
is deliberately conservative and side-symmetric. A bar at distance `H` may
still penetrate or confirm. A bar at distance greater than `H` cannot
penetrate, confirm, or otherwise revive the expired attempt.

## 14. Penetration Failure

Before success:

- UPPER fails when `bar.high > zone.high + max_penetration`;
- LOWER fails when `bar.low < zone.low - max_penetration`.

If a later bar contains both penetration and a close-away, penetration wins.
This fail-closed ordering avoids guessing which intrabar path occurred first.
An attempt also fails once, and only once, when its inclusive horizon ends
without success. A bar that causes penetration, confirmation, or horizon
expiry cannot also start a new touch attempt for the same seed.

Horizon distance counts every actual `CanonicalBar` sequence member after the
touch. Gaps do not create synthetic bars, and wall-clock or `available_time`
intervals do not extend or compress the window. An actual bar that is not
reaction-eligible because `bar.timestamp <= seed.origin_time` or
`bar.available_time <= seed.confirm_time` still advances the active attempt's
index distance, but cannot penetrate or confirm it. An ineligible bar at
distance `H` therefore expires the attempt.

## 15. Separation

Only successful reactions count. Consecutive successful touch indexes must
satisfy:

```text
current_touch_index - previous_touch_index >= min_separation_bars
```

Indexes count actual `CanonicalBar` sequence members. A gap may be crossed and
is reported, but no missing wall-clock bar is synthesized.

## 16. Causal Prefix

Historical Reaction uses fixed sequence membership. As-Of processing starts at
the first source bar and stops at the first bar that is incomplete or whose
`available_time` is later than `processing_time`. It never skips that member to
read a later timestamp. Batch similarly stops at the first incomplete bar.

The cumulative prefix availability at index `i` is:

```text
prefix_available_time[i] = max(
    bar.available_time for every fixed member from index 0 through i
)
```

A delayed earlier bar therefore delays every later causal fact. This API is an
offline, prevalidated-history replay boundary, not a live watermark or
correction protocol.

## 17. Historical Reaction Candidate

When a seed first reaches `min_reactions` successful reactions, the generator
freezes one candidate:

- source type `HISTORICAL_REACTION`;
- side and role copied from the seed;
- price range equal to the reaction zone;
- OriginTime copied from the seed;
- ConfirmTime equal to the causal time of the Nth confirmation;
- `touch_count=min_reactions`;
- `last_touch_time` equal to the Nth successful touch bar timestamp;
- `last_touch_confirm_time` equal to the Nth reaction confirmation time;
- confirmed status and lifecycle, with empty break fields.

Later bars and reactions neither mutate the candidate nor create an automatic
new version.

## 18. IDs

Both families hash canonical sorted-key compact UTF-8 JSON with SHA-256.
Periodic identity includes generator/version/policy, bar key, symbol,
timeframe, boundary policy, side, exact price, OriginTime, ConfirmTime, scale,
and strict mode.

Historical identity includes generator/version/policy, seed ID, symbol,
timeframe, side/role, seed OriginTime and exact price, zone, all config values,
every touch and confirmation bar key used for first confirmation, reaction
times, ConfirmTime, scale, schema, and strict mode. Configuration or evidence
changes therefore change identity deterministically.

## 19. Provenance

Periodic provenance retains the canonical bar key, timeframe, boundary policy,
side, and generator policy. Historical provenance retains the seed candidate
ID, a stable reference to seed provenance, configuration summary, and exactly
the finite `min_reactions` touch/confirmation evidence records used for first
confirmation. Full bars and unlimited later history are never copied.

## 20. Batch

Batch evaluates the fixed approved history while preserving every candidate's
real ConfirmTime. Periodic evaluates completed bars independently. Historical
Reaction evaluates each seed independently over the continuous complete causal
prefix and freezes at first confirmation.

## 21. As-Of

`processing_time` must be timezone-aware. Periodic admits a completed bar only
when its own availability has arrived. Historical Reaction admits a seed only
at or after seed ConfirmTime and admits only the continuous source prefix.
Candidates remain invisible before their declared ConfirmTime and become
visible at equality.

## 22. Replay

Default replay advances through the UTC-sorted unique union of source bar
`available_time` and seed candidate `confirm_time`. It records each candidate
once and rejects a schedule that first discovers a candidate later than the
candidate's ConfirmTime. Batch events and replay events must match complete
candidate and provenance serialization plus first-seen time.

## 23. No-Lookahead Guarantees

- Periodic never reads incomplete-period final-looking extrema.
- Periodic ConfirmTime is the actual periodic bar availability.
- OriginTime never grants availability.
- A touch bar cannot confirm itself.
- Reaction never monitors before seed ConfirmTime.
- Reaction never skips an unavailable or incomplete earlier bar.
- Reaction confirmation uses the cumulative prefix availability.
- Future appends and prices cannot rewrite frozen candidates.
- Batch and replay compare exact first appearances and provenance.

## 24. C-005 Boundary

C-004 does not build a Level Pool, deduplicate IDs or prices, merge overlapping
zones, cluster levels, choose representatives, or score resonance. Those
responsibilities belong to separately approved C-005 work.

## 25. Known Limitations

- Periodic aggregated OHLC cannot reveal the true intraperiod extreme time.
- Historical Reaction is a parameterized close-away baseline, not a final S/R
  definition.
- Separation counts actual bars and has no approved production session calendar.
- Fixed OHLC cannot resolve intrabar touch/penetration ordering; conservative
  failure rules are used.
- Replay is based on a prevalidated offline sequence and has no live watermark,
  correction, or late-revision event model.
- No real XAUUSD provider, D/W calendar, or parameter set is approved here.

## 26. Open Questions

- Which H-XXX and EXP-XXX records will govern comparative evaluation?
- Which XAUUSD source, anchor, session calendar, and correction policy will be
  approved for real data?
- Which scale IDs and parameter grids may be evaluated without data leakage?
- What out-of-sample, stability, and sensitivity criteria are required before
  either baseline can influence the core model?
- What future live watermark/revision contract will preserve immutable prior
  availability while accepting late data?

C-006, not C-004, will define lifecycle transitions and later versions.
C-004 performs no weighting, optimization, buy/sell signal, EA, or trading
conclusion.
