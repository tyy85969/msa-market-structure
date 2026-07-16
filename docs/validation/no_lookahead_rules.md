# Strict No-Lookahead Rules

## Core time contract

OriginTime identifies where a structure originated. ConfirmTime identifies when the algorithm first had enough real-time information to know it. They may be equal only when the definition genuinely requires no later information; equality must not be assumed.

Historical drawing may begin at OriginTime for visual context. Backtests, alerts, signals, lifecycle transitions, strength updates, cluster membership, and state selection become effective only from their causal availability time.

## Pivot / Fractal

Any required right-side confirmation bars are part of the confirmation delay. A pivot at bar t that needs r right-side bars cannot have ConfirmTime earlier than the close or approved availability event of bar t+r.

The historical marker may be placed at bar t only if the implementation and report retain the later ConfirmTime.

## ZigZag / ATR Reversal

A reversal is confirmed only when the predefined reversal condition is satisfied using data available at that event. The final historical turning point must not be treated as known before the threshold event.

If a forming endpoint moves, it remains a candidate. A confirmed endpoint may not be silently rewritten unless an approved lifecycle explicitly records a correction as a new event.

## Historical Backplot

Drawing a confirmed structure from OriginTime is allowed for context. It must not:

- create past trading or alert events;
- increase historical strength before evidence arrived;
- change an earlier state as if later members were already known;
- be used to claim zero-delay detection.

Research views should expose ConfirmTime or confirmation delay whenever backplot is shown.

## Multi-timeframe data

- Only completed higher-timeframe information available at the lower-timeframe event may be used.
- The final OHLC or structure of an unfinished higher-timeframe bar is future information.
- Projection to a lower timeframe preserves the source event's ConfirmTime.
- Timezone, session boundaries, and bar-close semantics must be explicit.

## Batch calculation

Vectorized or batch results must be auditable against chronological bar replay. For each emitted event, record the earliest input timestamp used and verify that it does not exceed the event's declared availability.

A valid batch implementation must produce event availability consistent with a one-pass replay under the same rules. Final-series equality alone is insufficient if intermediate availability differs.

## Dataset and research leakage

- Validation and Out-of-Sample periods must not influence feature definitions, thresholds, or parameter choices.
- Normalization and aggregation use statistics available within the declared training context.
- Manual screenshot annotations are not labels unless a separate labeling protocol defines and audits them.
- Removed or failed experiments remain recorded to reduce selective reporting.

## Test convention

Future automated tests belong under tests/lookahead/. They should cover right-side confirmation, incomplete higher-timeframe bars, historical backplot, moving candidates, frozen confirmations, batch/replay equivalence, and boundary event timing.

Phase 0 establishes this contract and directory only. It does not implement a Swing, Pivot, ZigZag, ATR reversal, support/resistance, clustering, resonance, Active Box, Fibonacci, or Imbalance algorithm.
