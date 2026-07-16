# Fibonacci Research

## Research Question

Does Fibonacci provide incremental structural information when it overlaps an independently defined MSA region?

## Hypotheses

- H-004: Fibonacci may have limited standalone value but could add information when aligned with structure.

H-004 is Proposed and is not evidence of effectiveness.

## Candidate Methods

Future experiments may compare structure-only, Fibonacci-only, and overlap conditions using a predeclared anchor and ratio policy. No anchor or ratio implementation is approved here.

## Data Requirements

Chronological XAUUSD data, causally confirmed anchors, explicit ratios, fixed parameters, documented timezone, and isolated Development / Validation / Out-of-Sample splits.

## No-Lookahead Risks

Anchors must not be selected using a later completed move and backdated. Ratio levels inherit the later of all required input confirmation times.

## Metrics

First Touch Reaction, MFE, MAE, Resonance Lift, parameter sensitivity, false-discovery controls, and ablation difference.

## Experiment Plan

Defer until the core baseline is stable. Then pre-register one minimal condition, measure standalone and incremental behavior, and reject any result that depends on hindsight anchor selection.

## Current Status

**Deferred / Not Core in V1.** No effectiveness is claimed, and no Fibonacci algorithm is implemented in Phase 0.
