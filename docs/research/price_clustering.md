# Price Clustering Research

## Research Question

How can overlapping structure candidates be deduplicated into stable price regions while retaining source provenance and avoiding inflated resonance?

## Hypotheses

- H-001: deduplicated distinct multi-timeframe evidence may improve reaction behavior.
- H-002: nested candidates from one real extreme should not count as independent evidence.

## Candidate Methods

- fixed price-distance baselines;
- ATR-normalized distance thresholds;
- interval-overlap grouping;
- StructureFamily-aware hierarchical deduplication.

## Data Requirements

Confirmed LevelCandidate event streams with source type, scale, price range, OriginTime, ConfirmTime, StructureFamily, and provenance, plus chronological XAUUSD prices.

## No-Lookahead Risks

Cluster membership and range at a given time may use only candidates confirmed by that time. A final batch cluster must not be projected backward as if all members were previously known.

## Metrics

Duplicate rate, cluster count, cluster width, membership churn, First Touch Reaction, Resonance Lift, and replay/batch membership mismatch count.

## Experiment Plan

Create a no-clustering baseline, compare one distance rule at a time, add family-aware deduplication, and use ablation to separate proximity effects from source diversity.

## Current Status

Proposed. No clustering or resonance-scoring algorithm is implemented in Phase 0.
