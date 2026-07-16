# Swing Detection Research

## Research Question

Which causal confirmation family can identify persistent XAUUSD turning structure with an acceptable balance between confirmation delay and false turns?

## Hypotheses

- H-001: distinct multi-timeframe confirmed Swing clusters may outperform a single-timeframe baseline.
- H-006: forming candidates may move, while confirmed structures should freeze.
- H-007: confirmation delay and false turns form a measurable tradeoff.

## Candidate Methods

- right-confirmed pivot or fractal families;
- reversal-threshold or ZigZag-style research families;
- ATR-normalized reversal confirmation;
- periodic high/low baselines.

These are candidates for later experiments, not approved implementations.

## Data Requirements

Chronological XAUUSD OHLC data with documented source, timezone, missing-bar policy, multiple completed timeframes, and Development / Validation / Out-of-Sample splits.

## No-Lookahead Risks

Right-side bars must be included in ConfirmTime. Reversal structure cannot confirm before its threshold event. Historical backplot must not imply real-time availability, and incomplete higher-timeframe bars are forbidden.

## Metrics

Confirmation Delay, False Turn Rate, Continued Break Rate, Trend Capture Ratio, MFE, MAE, candidate revisions, and post-confirm mutation count.

## Experiment Plan

Define a simple causal baseline, pre-register parameters and event semantics, replay bar by bar, compare batch event times, then test one incremental confirmation family at a time with ablation.

## Current Status

Proposed. No Swing detector, Pivot algorithm, ZigZag algorithm, or ATR reversal algorithm is implemented in Phase 0.
