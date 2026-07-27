# Core Alpha v1 Formal Configuration Profile

## 1. Purpose

This document freezes the explicit Core Alpha v1 configuration profile used as
the semantic baseline for later C-008C experiments. The profile is a
versioned reference selection; it is not an implicit default for the generic
`MSACoreConfig` contract.

## 2. Separate reference profile

`MSACoreConfig`, `ResonanceFrameConfig`, `ResonanceScoringConfig`, and
`ActiveBoxSelectionConfig` remain general, explicit contracts. They receive no
new implicit defaults because later research may approve other named profiles.
Callers select this profile explicitly through
`msa.reference.core_alpha_v1_config()`.

## 3. Project-owner approval and authority

The project owner explicitly approved promotion of the exact complete payload
returned by
`tests.research.msa_core.fixtures.config().to_dict()` at commit
`d72c18f7994afd506e6ecf044571ccffbc695631`.
No field was adjusted, improved, omitted, or merged from another fixture.
Production code does not import the test package.

The reviewable serialized payload is
`docs/reference/core_alpha_v1_config.json`. Production constructs the same
payload from a code-frozen constant rather than reading documentation at
runtime.

## 4. Public API

The public `msa.reference` boundary exports:

- `CORE_ALPHA_V1_PROFILE_ID`
- `CORE_ALPHA_V1_PROFILE_VERSION`
- `CORE_ALPHA_V1_REFERENCE_COMMIT_SHA`
- `CORE_ALPHA_V1_SOURCE_AUTHORITY`
- `CoreBaselineProfile`
- `core_alpha_v1_config()`
- `core_alpha_v1_profile()`
- `validate_core_alpha_v1_config()`
- `validate_core_alpha_v1_profile()`

`core_alpha_v1_config()` accepts no override and returns a fresh formal
`MSACoreConfig` through its strict `from_dict()` constructor.
`CoreBaselineProfile` is frozen, slotted, schema-versioned, strictly
serializable, and binds the complete config payload digest plus a semantic ID
computed from the complete profile payload.

## 5. Frozen identity and serialization

The logical profile ID is `msa-core-alpha-v1`; the profile version is `1.0.0`.
The config digest is SHA-256 over compact, key-sorted UTF-8 canonical JSON.
The semantic profile ID binds the logical ID, version, authorized commit,
complete Core config, config digest, authority statements, assumptions, and
schema.

Unknown fields, unknown schemas, non-formal configs, modified authority
statements, and completely re-signed but non-authorized profiles fail closed.
No clock, UUID, Python hash, float, current directory, or mutable cache
participates.

## 6. Pipeline parity

Acceptance tests run the existing fixture source through both the old fixture
pipeline and `MSACorePipeline(core_alpha_v1_config())`. Complete Batch, default
Replay, and extra-AsOf Replay payloads must be equal, including Run and Bundle
IDs, Resonance and Score histories, Active Box history, event and frozen
ledgers, and the structural metric report. Existing Goldens are not changed.

## 7. Configuration assumptions

The profile retains XAUUSD, H12 macro and H4 primary structure contexts, H1
reference prices, the frozen C-007B scoring configuration, and the frozen
C-007C Active Box selection configuration exactly as authorized. These values
are semantic baseline facts, not optimized parameters.

## 8. Meaning and limitations

This profile:

- freezes Core Alpha v1 configuration semantics;
- does not modify any C-007 algorithm;
- does not modify C-008A or C-008B;
- does not execute sensitivity, ablation, OOS, or any C-008C experiment;
- is not a profitability or production-readiness claim;
- has not been optimized for XAUUSD or another market;
- treats Active Box as a structural research object, not a trading signal;
- provides no BUY/SELL, Entry/Exit, Stop/Target, EA, Pine, alert, or execution
  behavior.

C-008C may explicitly consume this profile after this contract is reviewed and
merged. C-009 may migrate approved semantics only after the later Core Alpha
freeze conditions are satisfied; it may not redesign the Core algorithm.

## 9. Change control

Any payload change requires explicit project-owner approval, a new reference
commit, and a new profile version or separately named profile. Existing
authority statements, evidence JSON, digest, semantic identity, parity tests,
and Golden expectations must not be silently rewritten.
