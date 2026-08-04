# C-008C-B Root Cause Analysis

This is bounded diagnostic evidence. It does not recalculate any frozen Gate,
does not modify the original B Evidence, and leaves `BLOCKED_BEFORE_OOS` intact.

## Frozen schedules

- RCA Manifest: `c008c-b-rca-manifest-v1-19369f6a38d647d5f73ae95e6e5ea344e58ddbba269fd6816c56ce461d889ae8`
- B Report: `c008c-b-run-report-v1-2d52678c4633e646e99bb0eac192f53158bbedae4b87e7a72c012acc28f46d79`
- Determinism: 40 pairs, normal A + normal B + precision-7 `ROUND_FLOOR`
- Fixed cutoff: 15 cases, one selected checkpoint per case
- Replay/OOS/full 390 matrix/full AsOf matrix: not executed

## Source-derived findings

- Root Cause Subjects: `['DETERMINISM_GATE_CONFLATION', 'DEGENERATION_GLOBAL_PROPAGATION', 'CORE_DECIMAL_CONTEXT_DEPENDENCE', 'METRIC_FIXED_CUTOFF_SEMANTICS']`
- Disposition: `MIXED_ROOT_CAUSE`
- Attribution gaps: `['The frozen DETERMINISTIC_REPEAT and DECIMAL_CONTEXT_INDEPENDENCE Gates bind the same altered-Decimal comparison evidence', 'FUTURE_PREFIX_REWRITE is a global Baseline fixed-cutoff aggregate propagated to every Variant rather than direct per-Variant evidence']`
- Recommendations: `['Use a separately authorized change to split formal same-context and Decimal-context Gate evidence', 'Use a separately authorized change to make degeneration evidence subject-bound instead of globally propagated', 'Independently diagnose and remediate protected Core Decimal arithmetic context dependence under separate authorization', 'Independently diagnose and remediate protected Metric fixed-cutoff semantic divergence under separate authorization', 'Do not recalculate formal Gates or change BLOCKED_BEFORE_OOS until the project owner reviews this RCA']`

## Determinism results

- Same-context mismatches: 0/40
- Decimal-context mismatches: 40/40
- Core semantic mismatches: 40
- Audit semantic mismatches: 0
- Audit identity/provenance mismatches: 40
- Metric semantic mismatches: 40
- Decimal Core first semantic paths: `['/score_history/frames/1/score_frame_id']`
- Decimal Audit first identity/provenance paths: `['/audit_report_id']`
- Decimal Metric first semantic paths: `['/']`

## Fixed-cutoff results

- Final-layer counts: `{'IDENTITY_OR_SOURCE_BINDING': 6, 'METRIC_OUTCOME': 9}`
- Metric semantic rewrites and first paths: `[('c008c-dataset-case-v1-81fd815d8692fad7d608546c9737bd463f4519b182b0c9d48369802d8f096768', '/events/5'), ('c008c-dataset-case-v1-6fe6c03a50a4180d2e9b8bedc50d30eff405185f037ec2331f9d82764a0f30c2', '/events/5'), ('c008c-dataset-case-v1-610f958dbb6fa2fad461c190200c7c5a5cf9ef7d1705d88935598601fd5db9f6', '/events/5'), ('c008c-dataset-case-v1-b84bd2a825e4e7d992bbb542ab68705eb6bcc801ab24d8650c70681aa6264896', '/events/5'), ('c008c-dataset-case-v1-a34c138277c80a1363d01a34fbaa5ad748b7ba1e96f5806519659e3b080579a3', '/events/5'), ('c008c-dataset-case-v1-90e50e8d5b6a79c5899df7f6baa6541943f63966f8a72e984050ae59ffed4c6c', '/events/5'), ('c008c-dataset-case-v1-e35d9b5965eb64283a366409ea500758069312e60f2f609214383459c72ec01d', '/events/5'), ('c008c-dataset-case-v1-bb55619ef36c18490391ca9703946a180a3c47022311aa82bf6529fa38700587', '/events/5'), ('c008c-dataset-case-v1-0ed97d0b92784c5d2b3a2e335a5c2bf43abaf74e54d8e238409b5aa10133cbad', '/events/5')]`
- Identity/source controls and first paths: `[('c008c-dataset-case-v1-5725a4171e3d8b3cd70b6d4f7d9278d2965c89e3a5eb36d97aabd9daa6e264ff', '/metric_report_id'), ('c008c-dataset-case-v1-c3c5de1c2342774b9a375e9fd49c80952b64157d3eb4b6aa4f8d558ec5d744b4', '/metric_report_id'), ('c008c-dataset-case-v1-4ab0050553e298eac5b0dfc6d0c802207089a968d21e25f6cb42abf9d5944500', '/metric_report_id'), ('c008c-dataset-case-v1-29e9773416b2c1aff00ce6a7a1dd32cbe7fc577981ed3c69f5d2f6290de4f03b', '/metric_report_id'), ('c008c-dataset-case-v1-ac3eaf19eadc5a2cc0d164f124ab3bdb8c2c4dd6678b2ace1fe9de0a8131953f', '/metric_report_id'), ('c008c-dataset-case-v1-08980f74eff8ec362e5fd3a07d64e36dc18f902f0685f89ad66c7400f4a603b2', '/metric_report_id')]`
- Prefix Source invalid: 0
- Frame rewrites: 0
- Active Box Ledger rewrites: 0

`compare_shared_asof` uses the strict boundary `item.as_of_time < cutoff_time`.
Supplying formal AsOf plus one microsecond includes the exact formal AsOf; the
RCA independently validates the truncated Prefix Source before classification.

## Degeneration attribution

- Variant-direct evidence: 200
- Global Baseline propagation evidence: 25
- Shared static evidence: 25
- Insufficient evidence: 0
- Direct triggered rules: 0
- Global propagated triggered rules: 25
- Status without global propagation: `{'NOT_DEGENERATED': 23, 'SENSITIVE': 2}`

## Boundary

The original B Manifest/Report, Gate results, Stage status, protected source,
Dataset, Plan, parameters, thresholds, Metrics, Causal Audit, Reference, and
Core are unchanged. No remediation is performed by this RCA hardening task.
