# Historical Reaction Support / Resistance Research

## Research Question

Do causally defined historical rejection regions add structural explanatory value beyond the approved Swing and periodic high/low baseline?

## Hypotheses

- H-003: repeated historical rejection regions may add incremental explanatory value.

## Candidate Methods

- reaction-count zones with predefined touch and rejection rules;
- persistence-weighted historical regions;
- confirmed Swing-derived support/resistance baselines;
- zone invalidation and break lifecycle studies.

## Data Requirements

Chronological XAUUSD OHLC data, fixed ATR or price normalization inputs available at event time, explicit touch/rejection labels, and isolated dataset splits.

## No-Lookahead Risks

A region cannot use later reactions to increase its earlier strength. TouchCount, LastTouchTime, and break state update only when each event occurs. Zone construction and backplot must preserve ConfirmTime.

## Metrics

First Touch Reaction, Continued Break Rate, MFE, MAE, region lifetime, false rejection rate, and incremental lift over the baseline.

## Experiment Plan

Predefine one minimal historical-reaction rule, add it to the baseline, replay chronologically, lock thresholds on Development data, and perform increment and ablation comparisons.

## Current Status

Proposed. No historical support/resistance algorithm is implemented in Phase 0.
