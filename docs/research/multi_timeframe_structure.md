# Multi-Timeframe Structure Research

## Research Question

How should independently confirmed structures from multiple completed timeframes be aligned without leaking future higher-timeframe information or double-counting one real extreme?

## Hypotheses

- H-001: distinct multi-timeframe Swing clustering may improve first-touch behavior.
- H-002: nested periods from one real extreme are dependent evidence.

## Candidate Methods

- completed-bar timeframe snapshots;
- event-time joins between source and target scales;
- StructureFamily-aware provenance and deduplication;
- scale-normalized persistence comparisons.

## Data Requirements

Time-aligned XAUUSD bars for each studied timeframe, explicit session/timezone rules, completed-bar indicators, and traceable mapping from lower-timeframe events to higher-timeframe availability.

## No-Lookahead Risks

Do not forward-fill the final state of an unfinished higher-timeframe bar. A higher-timeframe structure becomes available only after its own confirmation and must preserve that availability when projected to lower timeframes.

## Metrics

Confirmation Delay, duplicate-family rate, First Touch Reaction, Resonance Lift, cluster stability, Continued Break Rate, and replay/batch event-time mismatch count.

## Experiment Plan

Establish a single-timeframe baseline, add one completed higher timeframe, compare naive versus family-aware combination, and ablate each scale on locked splits.

## Current Status

Proposed. No multi-timeframe state or resonance algorithm is implemented in Phase 0.
