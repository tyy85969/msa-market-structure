# ADR-0004: Core Structure Sources

## Status

Accepted

## Context

An interpretable baseline needs a small set of general, traceable sources. Adding many popular indicators before measuring the baseline would prevent useful attribution.

## Decision

The V1 core research sources are:

1. multi-timeframe confirmed Swing;
2. periodic High / Low;
3. historical reaction Support / Resistance.

The following are deferred and not core in V1:

- Imbalance;
- Fibonacci;
- RSI;
- Volume;
- Momentum.

## Consequences

- Baseline behavior remains understandable and suitable for ablation.
- Deferred sources may be studied only as explicit incremental experiments.
- This ADR does not claim that any core or deferred source is already effective.
- No source algorithm is implemented by this decision document.
