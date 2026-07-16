# ADR-0002: Strict No-Lookahead

## Status

Accepted

## Context

Historical plotting can make a structure appear obvious before it was confirmable. Pivots, reversals, higher-timeframe bars, and batch calculations are especially vulnerable to future-information leakage.

## Decision

MSA strictly separates OriginTime from ConfirmTime. OriginTime records where a structure began; ConfirmTime records when real-time information first made it knowable. Backtests, alerts, signals, and state transitions use ConfirmTime. Incomplete higher-timeframe future data and unobserved right-side confirmation are forbidden.

## Consequences

- Historical lines may start at OriginTime only when confirmation availability remains explicit.
- Replay and batch results must be checkable for event-time consistency.
- Some outputs will appear later and look less perfect than hindsight plots.
- Any violation blocks acceptance regardless of apparent performance.
