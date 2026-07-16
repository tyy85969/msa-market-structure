# MSA Logical Data Model

## Conventions

This is a logical model for future implementation. Time fields use an explicit timezone, preferably UTC at system boundaries. Price ranges satisfy PriceLow ≤ PriceHigh. Identifiers are stable within a reproducible run, and provenance is never discarded.

## LevelCandidate

A normalized structural price point or zone proposed by one source.

| Field | Meaning |
|---|---|
| ID | Stable candidate identifier |
| Symbol | Market symbol, initially XAUUSD |
| Timeframe / Scale | Source timeframe or approved structural scale |
| Type | Source type, such as confirmed Swing, periodic High/Low, or historical reaction S/R |
| Direction | Upper, lower, resistance, support, or another approved orientation |
| PriceLow | Inclusive lower bound |
| PriceHigh | Inclusive upper bound |
| OriginTime | Time/location where the underlying structure originated |
| ConfirmTime | Earliest real-time moment the algorithm could know the structure |
| Status | Candidate, confirmed, touched, broken, expired, or another approved lifecycle value |
| TouchCount | Count under a documented touch definition |
| LastTouchTime | Most recent eligible touch time |
| BreakTime | First confirmed break time, if any |
| StructureFamily | Stable family used to identify related or nested evidence |
| SourceStrength / metadata | Source-specific measurements that are not silently promoted to a universal score |
| Provenance | Dataset, source method, parameters, code version, and parent identifiers |

## StructureCluster

A price region that groups deduplicated LevelCandidate members.

| Field | Meaning |
|---|---|
| ClusterID | Stable cluster identifier |
| PriceRange | Inclusive aggregate lower and upper range |
| Members | Ordered references to LevelCandidate IDs |
| SourceTypes | Distinct source types represented |
| Timeframes | Distinct source timeframes or scales represented |
| StructureFamilies | Distinct underlying families represented |
| FirstConfirmTime | Earliest time at which the cluster itself met its confirmation contract |
| Status | Current cluster lifecycle state |

Member count is not automatically resonance strength. Candidates sharing one underlying extreme or StructureFamily require explicit dependence handling.

## TimeframeState

The available structural state for one scale.

| Field | Meaning |
|---|---|
| Scale | Timeframe or structural scale |
| TrendState | Approved categorical state; unknown is valid |
| CandidateTop | Current forming upper candidate reference |
| CandidateBottom | Current forming lower candidate reference |
| ConfirmedTop | Current confirmed upper boundary reference |
| ConfirmedBottom | Current confirmed lower boundary reference |
| LastStateChangeTime | Event time when this state first became available |

## ActiveBox

An interpretable pair of active structural boundaries around current price.

| Field | Meaning |
|---|---|
| UpperBoundary | Selected upper StructureCluster reference |
| LowerBoundary | Selected lower StructureCluster reference |
| CreatedTime | Time the pair first satisfied selection rules |
| FrozenTime | Time immutable box fields were frozen, if applicable |
| Status | Forming, active, replaced, invalidated, or another approved state |
| SelectionReason | Traceable explanation of eligibility and tie-breaking |

## OriginTime is not ConfirmTime

**OriginTime** is where the underlying extreme, structure, or region truly began.

**ConfirmTime** is the earliest time at which an algorithm operating under real-time conditions had enough information to identify or confirm it.

For example, a pivot can originate on one bar but require right-side bars before confirmation. A historical chart may draw the structure back from OriginTime to show its source. That drawing does not make it available in the past.

The following may become effective only from ConfirmTime:

- backtests;
- alerts;
- signals;
- state transitions.

Any later selection object, including a cluster, TimeframeState, or ActiveBox, must also use its own real availability time. Batch computation must preserve the same event-time semantics as chronological replay.
