"""C-008C-H2 Decimal remediation evidence and bounded parity runner."""

from __future__ import annotations

import hashlib
import json
from decimal import (
    Context,
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    getcontext,
    localcontext,
)
from pathlib import Path
from typing import Mapping

from msa.reference import core_alpha_v1_profile
from msa.research.msa_core import MSACorePipeline, replay_msa_core_run
from msa.research.resonance.decimal_arithmetic import (
    CANONICAL_DECIMAL_CAPITALS,
    CANONICAL_DECIMAL_CLAMP,
    CANONICAL_DECIMAL_EMAX,
    CANONICAL_DECIMAL_EMIN,
    CANONICAL_DECIMAL_PRECISION,
    CANONICAL_DECIMAL_ROUNDING,
    canonical_decimal_context,
)
from msa.validation import CausalAuditor
from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.experiments.baseline import core_experiment_baseline
from msa.validation.experiments.identity import (
    canonical_json_bytes,
    digest,
    semantic_id,
)
from msa.validation.experiments.synthetic_suite import (
    build_synthetic_source_input,
)
from msa.validation.metrics import StructuralMetricEvaluator


REMEDIATION_EVIDENCE_PATH = Path(
    "docs/validation/evidence/c008c_h2_decimal_remediation.json"
)
REMEDIATION_BASE_COMMIT = "204974930105a58a22e6c5449dccdaa2b58dbc40"
REMEDIATION_SCHEMA_VERSION = 1
VALIDATION_SEED = 2
REVIEWED_REMEDIATION_ID = (
    "c008c-h2-decimal-remediation-v1-"
    "326ba6c4e94328d1921e7b7fbe6ff0d124568f2442bcae1a45fe46dfdd74209f"
)

_SCENARIOS = tuple(SyntheticScenarioKind)
_EXPECTED_RUN_IDS = {
    SyntheticScenarioKind.SINGLE_TREND: (
        "msa-core-run-v1-"
        "119d0d2a3890fb61d11a32f0c6f6f75c2d2abee3a7a031bca5fb6aa5381b07ad"
    ),
    SyntheticScenarioKind.RANGE: (
        "msa-core-run-v1-"
        "53770fd285a64e374f8ad483be0269cb9e8696ad26125c34feca50bcf2ffceff"
    ),
    SyntheticScenarioKind.V_REVERSAL: (
        "msa-core-run-v1-"
        "e2223be77c4af5520c88a5f8fb6f23461010895180c823f1f3caf19d90de34f2"
    ),
    SyntheticScenarioKind.FALSE_BREAK: (
        "msa-core-run-v1-"
        "6602168ba50a4de2aedb7dd38b278db772ad659d4ddc20c57c7cef84b0f91e4d"
    ),
    SyntheticScenarioKind.GAP_SHOCK: (
        "msa-core-run-v1-"
        "976bc4033de63b1d1015d31d79cf3dab33e3575ec02b73a5858be365edf1f128"
    ),
}
_PROTECTED_PATHS = {
    "src/python/msa/research/resonance/contracts.py": {
        "old_blob_sha": "ce1e6445a925b2e31e9871e8bc884aa698a26c99",
        "old_sha256": (
            "47762b0af35924e057c13b96d3c1fed126884c4dbaf71c6283cb4ceefd56af7b"
        ),
    },
    "src/python/msa/research/resonance/scoring.py": {
        "old_blob_sha": "76a5f665baa461b3ebbea48c1c96c11061bf1e42",
        "old_sha256": (
            "6f0d3cc20705164a786210de3c18edb8751410d09c608d1f9ab76f416fe6825d"
        ),
    },
    "src/python/msa/research/resonance/scoring_contracts.py": {
        "old_blob_sha": "3382ad72ffd334811f93f3d5df65f2cdbb67b9cc",
        "old_sha256": (
            "3251eb62d3958c1d3883d99bcf3775f9590bfd7478a3eb27318c31d2bfc1af7d"
        ),
    },
}
_HISTORICAL_EVIDENCE_SHA256 = {
    "docs/validation/evidence/c008c_b_dev_validation_report.json": (
        "ad4ac03a07bf18384eb01b5dfda2e18b2b080bfb5892a206e526dedff8845cde"
    ),
    "docs/validation/evidence/c008c_b_execution_manifest.json": (
        "669775e4ba738e9ea629e422398f2c7b992be3fbad86a1e959560886dc19d363"
    ),
    "docs/validation/evidence/c008c_b_root_cause_lock.json": (
        "372a834e979793fc8edc55256a5b2a57fd0c026bcb5b93348e98c6ebabcd1fe2"
    ),
    "docs/validation/evidence/c008c_b_root_cause_manifest.json": (
        "f5e27d2ed5c86f8aab2102a49bced30d8f86c5fad10257557c474e8ec16656ec"
    ),
    "docs/validation/evidence/c008c_b_root_cause_report.json": (
        "78a629dbf561ae76ef9c2f76479b1ad55ee822aabf0a4514a50c9fb9f8bee02d"
    ),
    "docs/validation/evidence/c008c_baseline_snapshot.json": (
        "9b141b4f7614bbd14c76f25c3f6271c7a1db913968d2f4072b8ca6980d9fb7cf"
    ),
    "docs/validation/evidence/c008c_dataset_manifest.json": (
        "76f3f4f5da8b92aa6c3306c33c593092d32aa5ef5160e493e7fc7234613fbd32"
    ),
    "docs/validation/evidence/c008c_experiment_plan.json": (
        "262f9f3bd9a38b7c28699026391ae45ff096efe916faf9c44c46cd9d8e12535c"
    ),
    "docs/validation/evidence/c008c_protected_source_manifest.json": (
        "a4651a946ddc3731d35953e01d2018874672504a48eba74e87819ffb47d649a7"
    ),
}


class RemediationEvidenceError(ValueError):
    """Raised when H2 evidence or its bounded execution is invalid."""


def _root(root: Path | None) -> Path:
    result = (Path.cwd() if root is None else Path(root)).resolve(strict=True)
    if not (result / "pyproject.toml").is_file():
        raise RemediationEvidenceError("remediation root is not an MSA checkout")
    return result


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_blob_sha(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()  # noqa: S324


def _context_snapshot(context: Context) -> dict[str, object]:
    return {
        "precision": context.prec,
        "rounding": context.rounding,
        "Emin": context.Emin,
        "Emax": context.Emax,
        "capitals": context.capitals,
        "clamp": context.clamp,
        "traps": {
            signal.__name__: enabled
            for signal, enabled in context.traps.items()
        },
        "flags": {
            signal.__name__: enabled
            for signal, enabled in context.flags.items()
        },
    }


def _external_context(precision: int, rounding: str) -> Context:
    canonical = canonical_decimal_context()
    return Context(
        prec=precision,
        rounding=rounding,
        Emin=canonical.Emin,
        Emax=canonical.Emax,
        capitals=canonical.capitals,
        clamp=canonical.clamp,
        flags=[],
        traps=[
            signal
            for signal, enabled in canonical.traps.items()
            if enabled
        ],
    )


def compare_decimal_context_case(
    scenario: SyntheticScenarioKind,
    seed: int,
) -> dict[str, object]:
    """Compare one authorized seed-2 case without B/OOS/matrix execution."""

    if not isinstance(scenario, SyntheticScenarioKind) or scenario not in _SCENARIOS:
        raise RemediationEvidenceError(
            "scenario is outside the H2 remediation set"
        )
    if seed != VALIDATION_SEED:
        raise RemediationEvidenceError(
            "H2 remediation accepts VALIDATION seed 2 only"
        )
    baseline = core_experiment_baseline()
    pipeline = MSACorePipeline(baseline.core_config_snapshot)
    evaluator = StructuralMetricEvaluator(baseline.metric_config_snapshot)
    source = build_synthetic_source_input(scenario, seed)
    specs = (
        ("DEFAULT", _external_context(28, ROUND_HALF_EVEN)),
        ("PRECISION_7_ROUND_FLOOR", _external_context(7, ROUND_FLOOR)),
        ("PRECISION_50_ROUND_CEILING", _external_context(50, ROUND_CEILING)),
    )
    caller_before = _context_snapshot(getcontext())
    artifacts: list[tuple[dict[str, object], ...]] = []
    results: list[dict[str, object]] = []
    for label, context in specs:
        with localcontext(context):
            run = pipeline.run(source)
            audit = CausalAuditor().audit_run(run)
            metric = evaluator.evaluate(run)
            replay = replay_msa_core_run(pipeline, source)
        artifact = (
            run.to_dict(),
            audit.to_dict(),
            metric.to_dict(),
            replay.to_dict(),
        )
        artifacts.append(artifact)
        results.append(
            {
                "context": label,
                "run_id": run.run_id,
                "audit_report_id": audit.audit_report_id,
                "metric_report_id": metric.metric_report_id,
                "replay_run_id": replay.run_id,
            }
        )
    caller_after = _context_snapshot(getcontext())
    if artifacts[0] != artifacts[1] or artifacts[0] != artifacts[2]:
        raise RemediationEvidenceError(
            f"altered-context mismatch: {scenario.value}"
        )
    if results[0]["run_id"] != _EXPECTED_RUN_IDS[scenario]:
        raise RemediationEvidenceError(
            f"default semantic parity failed: {scenario.value}"
        )
    return {
        "scenario": scenario.value,
        "seed": seed,
        "expected_default_run_id": _EXPECTED_RUN_IDS[scenario],
        "contexts": results,
        "core_audit_metric_replay_full_equal": True,
        "caller_context_restored": caller_before == caller_after,
    }


def _protected_changes(base: Path) -> list[dict[str, object]]:
    result = []
    for relative, old in _PROTECTED_PATHS.items():
        raw = (base / relative).read_bytes()
        if b"\r" in raw:
            raise RemediationEvidenceError(
                f"remediated protected source is not LF-only: {relative}"
            )
        result.append(
            {
                "relative_path": relative,
                **old,
                "new_blob_sha": _git_blob_sha(raw),
                "new_sha256": _sha256(raw),
            }
        )
    return result


def _historical_evidence(base: Path) -> list[dict[str, str]]:
    result = []
    for relative, expected in _HISTORICAL_EVIDENCE_SHA256.items():
        if _sha256((base / relative).read_bytes()) != expected:
            raise RemediationEvidenceError(
                f"historical Evidence bytes changed: {relative}"
            )
        result.append({"relative_path": relative, "sha256": expected})
    return result


def _validate_original_protected_manifest(base: Path) -> None:
    path = base / "docs/validation/evidence/c008c_protected_source_manifest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = {
            item["relative_path"]: item["sha256"]
            for item in payload["files"]
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RemediationEvidenceError(
            "invalid historical Protected Source Manifest"
        ) from exc
    if any(
        entries.get(relative) != values["old_sha256"]
        for relative, values in _PROTECTED_PATHS.items()
    ):
        raise RemediationEvidenceError(
            "remediation old source does not bind the historical Manifest"
        )


def _canonical_context_payload() -> dict[str, object]:
    context = canonical_decimal_context()
    return {
        "precision": CANONICAL_DECIMAL_PRECISION,
        "rounding": CANONICAL_DECIMAL_ROUNDING,
        "Emin": CANONICAL_DECIMAL_EMIN,
        "Emax": CANONICAL_DECIMAL_EMAX,
        "capitals": CANONICAL_DECIMAL_CAPITALS,
        "clamp": CANONICAL_DECIMAL_CLAMP,
        "traps": {
            signal.__name__: value
            for signal, value in context.traps.items()
        },
        "initial_flags": {
            signal.__name__: value
            for signal, value in context.flags.items()
        },
    }


def _added_authority(base: Path) -> dict[str, str]:
    relative = "src/python/msa/research/resonance/decimal_arithmetic.py"
    raw = (base / relative).read_bytes()
    if b"\r" in raw:
        raise RemediationEvidenceError(
            "Decimal arithmetic authority is not LF-only"
        )
    return {
        "relative_path": relative,
        "blob_sha": _git_blob_sha(raw),
    }


def _core_reference() -> dict[str, str]:
    profile = core_alpha_v1_profile()
    return {
        "profile_semantic_id": profile.profile_semantic_id,
        "core_config_payload_digest": profile.core_config_payload_digest,
    }


def build_decimal_remediation_evidence(base: Path) -> dict[str, object]:
    _validate_original_protected_manifest(base)
    cases = [
        compare_decimal_context_case(item, VALIDATION_SEED)
        for item in _SCENARIOS
    ]
    payload: dict[str, object] = {
        "remediation_version": "C008C_H2_DECIMAL_REMEDIATION_V1",
        "remediation_base_commit": REMEDIATION_BASE_COMMIT,
        "core_reference": _core_reference(),
        "canonical_decimal_context": _canonical_context_payload(),
        "protected_source_changes": _protected_changes(base),
        "added_arithmetic_authority": _added_authority(base),
        "default_semantic_parity": "FULL_PAYLOAD_AND_ID_EQUAL",
        "altered_context_parity": (
            "CORE_AUDIT_METRIC_REPLAY_FULL_EQUAL"
        ),
        "cases": cases,
        "parameters_thresholds_and_configuration_unchanged": True,
        "historical_evidence": _historical_evidence(base),
        "historical_evidence_unchanged": True,
        "oos_executed": False,
        "b_v2_executed": False,
        "schema_version": REMEDIATION_SCHEMA_VERSION,
    }
    return {
        "remediation_id": semantic_id(
            "c008c-h2-decimal-remediation-v1-", payload
        ),
        "payload_sha256": digest(payload),
        **payload,
    }


def validate_decimal_remediation_evidence(
    evidence: Mapping[str, object], base: Path
) -> dict[str, object]:
    data = dict(evidence)
    remediation_id = data.pop("remediation_id", None)
    payload_sha256 = data.pop("payload_sha256", None)
    if payload_sha256 != digest(data):
        raise RemediationEvidenceError("remediation payload SHA-256 mismatch")
    if remediation_id != semantic_id(
        "c008c-h2-decimal-remediation-v1-", data
    ):
        raise RemediationEvidenceError("remediation canonical ID mismatch")
    if remediation_id != REVIEWED_REMEDIATION_ID:
        raise RemediationEvidenceError(
            "remediation differs from reviewed authority"
        )
    if data.get("remediation_base_commit") != REMEDIATION_BASE_COMMIT:
        raise RemediationEvidenceError("remediation base commit mismatch")
    if data.get("schema_version") != REMEDIATION_SCHEMA_VERSION:
        raise RemediationEvidenceError("remediation schema mismatch")
    if data.get("core_reference") != _core_reference():
        raise RemediationEvidenceError("Core Reference identity mismatch")
    if data.get("canonical_decimal_context") != _canonical_context_payload():
        raise RemediationEvidenceError("canonical Decimal Context mismatch")
    if data.get("protected_source_changes") != _protected_changes(base):
        raise RemediationEvidenceError(
            "current protected source differs from remediation"
        )
    if data.get("added_arithmetic_authority") != _added_authority(base):
        raise RemediationEvidenceError(
            "Decimal arithmetic authority differs from remediation"
        )
    historical = _historical_evidence(base)
    _validate_original_protected_manifest(base)
    if data.get("historical_evidence") != historical:
        raise RemediationEvidenceError(
            "historical Evidence bindings mismatch"
        )
    cases = data.get("cases")
    if not isinstance(cases, list) or [
        item.get("scenario") for item in cases
    ] != [item.value for item in _SCENARIOS]:
        raise RemediationEvidenceError(
            "remediation case set or order mismatch"
        )
    if any(
        item.get("seed") != VALIDATION_SEED
        or item.get("expected_default_run_id")
        != _EXPECTED_RUN_IDS[scenario]
        or item.get("core_audit_metric_replay_full_equal") is not True
        or item.get("caller_context_restored") is not True
        for scenario, item in zip(_SCENARIOS, cases, strict=True)
    ):
        raise RemediationEvidenceError("remediation parity result mismatch")
    if data.get("default_semantic_parity") != "FULL_PAYLOAD_AND_ID_EQUAL":
        raise RemediationEvidenceError("default parity declaration mismatch")
    if data.get("altered_context_parity") != (
        "CORE_AUDIT_METRIC_REPLAY_FULL_EQUAL"
    ):
        raise RemediationEvidenceError("altered parity declaration mismatch")
    required = {
        "parameters_thresholds_and_configuration_unchanged": True,
        "historical_evidence_unchanged": True,
        "oos_executed": False,
        "b_v2_executed": False,
    }
    if any(data.get(key) is not value for key, value in required.items()):
        raise RemediationEvidenceError(
            "remediation boundary declaration mismatch"
        )
    return dict(evidence)


def write_decimal_remediation_evidence(root: Path | None = None) -> Path:
    base = _root(root)
    path = base / REMEDIATION_EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        canonical_json_bytes(build_decimal_remediation_evidence(base))
    )
    return path


def check_existing_decimal_remediation_evidence(
    root: Path | None = None,
) -> Path:
    base = _root(root)
    path = base / REMEDIATION_EVIDENCE_PATH
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        validated = validate_decimal_remediation_evidence(payload, base)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RemediationEvidenceError(
            "invalid Decimal remediation Evidence"
        ) from exc
    if raw != canonical_json_bytes(validated):
        raise RemediationEvidenceError(
            "Decimal remediation Evidence is non-canonical"
        )
    return path


def validate_historical_protected_source_transition(
    historical_manifest: object,
    root: Path | None = None,
) -> None:
    """Bridge the immutable v1 Manifest to the exact reviewed remediation."""

    base = _root(root)
    manifest_path = (
        base / "docs/validation/evidence/c008c_protected_source_manifest.json"
    )
    try:
        committed_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        supplied_payload = historical_manifest.to_dict()  # type: ignore[attr-defined]
    except (
        AttributeError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        raise RemediationEvidenceError(
            "invalid historical Protected Source authority"
        ) from exc
    if supplied_payload != committed_payload:
        raise RemediationEvidenceError(
            "supplied historical Manifest differs from committed bytes"
        )
    evidence_path = check_existing_decimal_remediation_evidence(base)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    changed_sha256 = {
        item["relative_path"]: item["new_sha256"]
        for item in evidence["protected_source_changes"]
    }
    historical_sha256 = {
        item["relative_path"]: item["sha256"]
        for item in committed_payload["files"]
    }
    from msa.validation.experiments.protected_source import (
        build_protected_source_manifest,
    )

    current = build_protected_source_manifest(base)
    current_sha256 = {
        item.relative_path: item.sha256 for item in current.files
    }
    added_path = evidence["added_arithmetic_authority"]["relative_path"]
    if set(current_sha256) != set(historical_sha256) | {added_path}:
        raise RemediationEvidenceError(
            "protected path set exceeds the reviewed remediation"
        )
    for relative, old_sha256 in historical_sha256.items():
        expected = changed_sha256.get(relative, old_sha256)
        if current_sha256.get(relative) != expected:
            raise RemediationEvidenceError(
                f"unreviewed protected source difference: {relative}"
            )


__all__ = [
    "REMEDIATION_EVIDENCE_PATH",
    "REVIEWED_REMEDIATION_ID",
    "RemediationEvidenceError",
    "build_decimal_remediation_evidence",
    "check_existing_decimal_remediation_evidence",
    "compare_decimal_context_case",
    "validate_decimal_remediation_evidence",
    "validate_historical_protected_source_transition",
    "write_decimal_remediation_evidence",
]
