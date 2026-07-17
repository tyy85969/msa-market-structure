# C001D Market-Data and MTF No-Lookahead Audit

## 1. Audit Scope

C-001D independently attacked the canonical bar contract, source-configured
loading, sequence-quality validation, explicit alignment, fixed and calendar
resampling, batch event order, causal replay, and no-lookahead invariants added
by C-001A/B/C. The audit was limited to the production state at the audited
commit and to synthetic, deterministic, offline data.

No production implementation, accepted ADR, README, Pine file, market
structure algorithm, signal behavior, or C-002 file was modified.

## 2. Audited Commit

`ccab8d28e6b46479d87346ed0dbe8daf06e0d86f`

The working branch was created directly from this verified `main` commit:
`audit/c001d-market-data-no-lookahead`.

## 3. Independence Statement

This audit did not reuse C-001A/B/C conclusions as evidence. It read the
accepted contracts and implementation to construct a fresh threat model, then
added independent adversarial fixtures, replay probes, and metamorphic tests.
Existing tests were treated as coverage to inspect, not proof of correctness.

## 4. Files Reviewed

- `AGENTS.md`
- `CONTRIBUTING.md`
- `docs/architecture/market_data_contract.md`
- `docs/architecture/market_data_loading.md`
- `docs/architecture/market_data_resampling.md`
- `docs/validation/no_lookahead_rules.md`
- `docs/decisions/ADR-0002-no-lookahead.md`
- `src/python/msa/data/contracts.py`
- `src/python/msa/data/source_config.py`
- `src/python/msa/data/loaders.py`
- `src/python/msa/data/quality.py`
- `src/python/msa/data/alignment.py`
- `src/python/msa/data/resampling.py`
- all existing C-001A/B/C tests under `tests/data` and `tests/lookahead`
- GitHub Issue #3, which remained Open during the audit

## 5. Threat Model

The audit attempted to cause early HTF events, final-looking incomplete OHLC,
future-bucket rewrites, append instability, batch/replay timing divergence,
timestamp-role conflation, DST mislocalization, implicit anchors or calendars,
silent repair, source-identity mixing, coverage bypass, non-monotonic event
misordering, and mutation of source inputs or historical outputs.

Attack inputs included invalid fixed durations, naive and non-UTC times,
ambiguous/nonexistent wall times, offset conflicts, invalid OHLCV, duplicates,
conflicts, out-of-order rows, overlaps, gaps, missing fields, incomplete bars,
misaligned slots, cross-boundary intervals, delayed members, non-24x7 D/W
schedules, future price mutations, future appends, and fixed-seed randomized
availability schedules.

## 6. Contract Findings

### C001D-F001 — Canonical time, interval, numeric, and immutability guards hold

- **Severity:** INFO
- **Evidence:** `test_fixed_canonical_bar_rejects_declared_m15_interval_mismatch`,
  canonical time-field, non-finite OHLCV, incomplete-snapshot, volume round-trip,
  D/W boundary, and frozen-dataclass audit cases.
- **Reproduction:** Run `python -m pytest tests/audit -q`.
- **Impact:** An M15 bar cannot enter as a 10- or 20-minute interval; completed
  data cannot claim early availability; `None` volume is not converted to zero.
- **Recommendation:** Retain these cases as permanent contract regression tests.
- **Status:** VERIFIED PASS

## 7. Loader Findings

### C001D-F002 — Loader timestamps and availability fail closed

- **Severity:** INFO
- **Evidence:** Independent OPEN_TIME/CLOSE_TIME, IANA zone, fixed offset, DST,
  embedded-offset conflict, observed-time, negative-lag, D/W boundary, CSV
  immutability, and future-append tests.
- **Reproduction:** Run `python -m pytest tests/audit -q -k loader`.
- **Impact:** Concrete row versions retain their own causal availability; no
  next row, file tail, implicit symbol alias, or silent timestamp repair was found.
- **Recommendation:** Require an approved source configuration before loading
  real XAUUSD data; do not infer provider semantics from a filename or schema.
- **Status:** VERIFIED PASS

## 8. Quality Findings

### C001D-F003 — Invalid sequences are reported without repair or downstream bypass

- **Severity:** INFO
- **Evidence:** Duplicate, conflicting duplicate, out-of-order, overlap, gap,
  invalid field, missing header, and report-only downstream rejection tests.
- **Reproduction:** Run `python -m pytest tests/audit -q -k "quality or report_only or gap"`.
- **Impact:** Invalid or ambiguous source data is not sorted, deduplicated,
  filled, clipped, or silently accepted by the resampler.
- **Recommendation:** Keep `strict=True` for canonical production ingestion and
  treat `strict=False` only as a diagnostic report mode.
- **Status:** VERIFIED PASS

## 9. Alignment Findings

### C001D-F004 — Alignment and D/W boundaries remain explicit and traceable

- **Severity:** INFO
- **Evidence:** Missing/naive/non-UTC/mismatched policy rejection, anchor-shift,
  non-integral slot, synthetic 23-hour D and 5.5-day W, duplicate/unordered/
  overlapping schedule, outside-member, and cross-boundary tests.
- **Reproduction:** Run `python -m pytest tests/audit -q -k "anchor or calendar"`.
- **Impact:** No first-bar, UTC-midnight, fixed-24-hour D, fixed-7-day W, or
  undocumented broker boundary was observed.
- **Recommendation:** Approve and version real XAUUSD anchors and calendars
  separately before real-source use.
- **Status:** VERIFIED PASS

## 10. Resampling Findings

### C001D-F005 — Fixed and calendar aggregation preserves causal membership

- **Severity:** INFO
- **Evidence:** M15 to M30/H1/H2/H4/H12, H1 to H2/H4, coverage gaps, trailing
  truncation, misaligned/extra/crossing slots, mixed identity, incomplete source,
  volume, session, provenance, and input-immutability cases.
- **Reproduction:** Run `python -m pytest tests/audit -q`.
- **Impact:** Only complete, expected, identity-compatible members produce a
  target; missing and invalid members do not produce filled bars.
- **Recommendation:** Preserve the explicit `policy_id` and coverage audit in
  all later data-source integrations.
- **Status:** VERIFIED PASS

## 11. Batch vs Replay Findings

### C001D-F006 — Valid complete inputs have identical final bars and first events

- **Severity:** INFO
- **Evidence:** Fixed-seed M30/H1/H2 replay comparisons, deliberate non-monotonic
  availability, and `iter_resample_events` ordering checks.
- **Reproduction:** Run `python -m pytest tests/lookahead -q`.
- **Impact:** Batch storage order does not force event-time order. Older buckets
  delayed beyond newer buckets first appear at their actual `available_time`.
- **Recommendation:** Downstream event consumers should use event order rather
  than assume target timestamps are availability-monotonic.
- **Status:** VERIFIED PASS

## 12. No-Lookahead Findings

### C001D-F007 — No early HTF OHLC or historical rewrite was found

- **Severity:** INFO
- **Evidence:** H1 absence at 15/30/45/60 minutes, delayed-member boundary,
  publication-lag formula, future append, future price mutation, and frozen
  emitted-history cases.
- **Reproduction:** Run
  `python -m pytest tests/lookahead/test_market_data_pipeline_replay_audit.py -q`.
- **Impact:** A target first appears only at
  `max(target end_time, all member available_time) + publication_lag`; later
  source buckets do not revise an already emitted target.
- **Recommendation:** Retain both final-series and first-event assertions in
  future MTF tests.
- **Status:** VERIFIED PASS

## 13. Random / Metamorphic Findings

### C001D-F008 — Deterministic adversarial invariants hold

- **Severity:** INFO
- **Evidence:** Seed `20260717`; randomized member delays for M30/H1/H2; append,
  future-price, publication-lag, anchor-shift, deterministic replay, and input
  immutability checks.
- **Reproduction:** Run the targeted random/metamorphic command in section 18.
- **Impact:** No stochastic ordering defect, future mutation leak, or input
  mutation was found.
- **Recommendation:** Keep the seed fixed; add new seeds only as additional
  deterministic cases rather than replacing this evidence.
- **Status:** VERIFIED PASS

## 14. Limitations

### C001D-F009 — `resample_as_of` prevalidates the complete historical dataset

- **Severity:** MINOR
- **Evidence:** `test_as_of_prevalidates_future_identity_and_fails_closed` and
  `test_as_of_prevalidates_future_quality_and_fails_closed`; implementation
  calls `_validate_public_input` before filtering source bars by processing time.
- **Reproduction:** Append a future bar with a conflicting source identity, or
  append a future duplicate to a report-only load, then request an earlier as-of
  snapshot. The valid prefix emits, while the complete invalid dataset rejects.
- **Impact:** This API is a prevalidated historical-dataset replay, not a live
  append-only streaming API. Future invalid metadata can reject the dataset,
  but it does not cause an early market event or alter accepted historical OHLC.
- **Recommendation:** Keep the limitation explicit. A future live ingestion
  task should validate causal prefixes/events separately and define revision,
  watermark, and quarantine behavior.
- **Status:** ACCEPTED NON-BLOCKING DESIGN LIMITATION

### C001D-F010 — Replay has no watermark for permanently missing source slots

- **Severity:** MINOR
- **Evidence:** `test_permanent_gap_never_synthesizes_target_during_replay`;
  as-of coverage absence is a warning, while strict batch rejects the permanently
  incomplete dataset.
- **Reproduction:** Remove one M15 member from the first H1 bucket, retain a
  later complete H1 bucket, and replay at a much later processing time.
- **Impact:** Replay cannot distinguish a late member from a permanently absent
  member without an external watermark/end-of-stream declaration. It does not
  emit the incomplete target, and valid-input batch/replay equivalence is intact.
- **Recommendation:** For live operation, define watermarks and late-data policy.
  For offline final validation, require strict batch success.
- **Status:** ACCEPTED NON-BLOCKING DESIGN LIMITATION

### C001D-F011 — Real-provider and production-calendar decisions remain external

- **Severity:** INFO
- **Evidence:** C-001B/C explicitly provide source/calendar interfaces but do
  not approve a broker, symbol feed, correction model, or XAUUSD D/W calendar.
- **Reproduction:** Inspect the reviewed architecture documents and configuration
  contracts; all audit data is synthetic and offline.
- **Impact:** This audit validates the pipeline semantics, not accuracy or
  completeness of a future real market-data source.
- **Recommendation:** Approve source mapping, corrections, anchors, sessions,
  holidays, and D/W boundaries during real-source integration.
- **Status:** OPEN EXTERNAL DECISION; NOT A PIPELINE DEFECT

## 15. Blocking Defects

None found.

## 16. Non-Blocking Observations

- The as-of API is intentionally fail-closed at whole-dataset eligibility.
- Replay missing-member warnings need a future watermark policy for live use.
- Tick versus real volume remains an explicit source-configuration assertion;
  synthetic tests cannot independently prove a provider's volume semantics.
- The production XAUUSD provider, correction model, anchor, and D/W calendar
  remain unselected.

No MAJOR finding was recorded.

## 17. Final Verdict

**PASS WITH NON-BLOCKING LIMITATIONS**

No future leak, unfinished-HTF exposure, accepted-input batch/replay timing
divergence, silent repair, implicit resampling boundary, early availability,
or future-bucket historical rewrite was found. The two MINOR limitations are
fail-closed/offline-replay boundaries and do not violate the current C-001
historical pipeline contract.

## 18. Evidence and Test Commands

Executed from the repository root:

```text
python -m pytest -q
# 247 passed

python -m pytest tests/audit -q
# 62 passed

python -m pytest tests/lookahead -q
# 36 passed (25 C-001D cases plus 11 pre-existing cases)

python -m pytest tests/lookahead/test_market_data_pipeline_replay_audit.py -q -k "seeded_random or nonmonotonic or append_future or future_bucket_price_mutation or publication_lag or explicit_anchor_shift or replay_does_not_mutate"

git diff --check
```

The starting baseline was 160 tests. C-001D adds 87 deterministic cases: 62
under `tests/audit` and 25 in the new replay audit file.

## 19. Recommendation for Issue #3

Recommend closing Issue #3 when this audit Draft PR is reviewed and merged.
The PR may use `Closes #3`. The open provider/calendar/correction decisions are
real-source integration work, not unresolved defects in the current market-data
pipeline contract.

## 20. Whether C-002 May Start

C-002 may start only after the C-001D Draft PR is reviewed/merged and Issue #3
is closed. C-002 was not started by this task.
