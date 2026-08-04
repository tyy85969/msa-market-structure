import json
import shutil
from pathlib import Path

import pytest

from msa.validation.experiments.execution.rca import evidence
from msa.validation.experiments.execution.rca.contracts import (
    C008CBRCAEvidenceLock,
    C008CBRCAManifest,
    C008CBRootCauseReport,
    DegenerationRuleAttribution,
    DeterminismDiagnosticResult,
    DiagnosticLayer,
    FixedCutoffDiagnosticResult,
    LayerDifferenceSummary,
    RootCauseDisposition,
    VariantDegenerationAttribution,
)
from msa.validation.experiments.execution.rca.errors import (
    C008CBRCAEvidenceError,
)
from msa.validation.experiments.execution.rca.report import (
    build_root_cause_report,
)
from msa.validation.experiments.identity import canonical_json_bytes, semantic_id


ROOT = Path(__file__).resolve().parents[5]


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _resign_mapping(cls, payload):
    result = dict(payload)
    result[cls._ID_FIELD] = semantic_id(
        cls._PREFIX,
        {key: value for key, value in result.items() if key != cls._ID_FIELD},
    )
    return result


def _resign(cls, payload):
    return cls.from_dict(_resign_mapping(cls, payload))


@pytest.fixture
def locked_repo(tmp_path, monkeypatch, b_sources):
    base = tmp_path / "repo"
    for relative in (
        evidence.MANIFEST_PATH,
        evidence.REPORT_PATH,
        evidence.ANALYSIS_PATH,
        evidence.LOCK_PATH,
    ):
        target = base / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    monkeypatch.setattr(evidence, "_base", lambda _root: base)
    monkeypatch.setattr(
        evidence, "check_existing_c008c_b_evidence", lambda _root: None
    )
    monkeypatch.setattr(evidence, "load_b_sources", lambda _root: b_sources)
    monkeypatch.setattr(
        evidence,
        "validate_c008c_b_rca_manifest",
        lambda manifest, _root: manifest,
    )
    return base, b_sources


def _contracts(base):
    manifest_raw = (base / evidence.MANIFEST_PATH).read_bytes()
    report_raw = (base / evidence.REPORT_PATH).read_bytes()
    return (
        C008CBRCAManifest.from_dict(json.loads(manifest_raw)),
        manifest_raw,
        C008CBRootCauseReport.from_dict(json.loads(report_raw)),
        report_raw,
    )


def _write_signed_bundle(base, b_sources, report, *, analysis_raw=None):
    manifest, manifest_raw, _, _ = _contracts(base)
    report_raw = canonical_json_bytes(report.to_dict())
    (base / evidence.REPORT_PATH).write_bytes(report_raw)
    if analysis_raw is None:
        analysis_raw = evidence.analysis_bytes(manifest, report)
    (base / evidence.ANALYSIS_PATH).write_bytes(analysis_raw)
    b_manifest, b_report, b_manifest_raw, b_report_raw = b_sources
    lock = evidence.build_evidence_lock(
        manifest,
        manifest_raw,
        report,
        report_raw,
        analysis_raw,
        b_manifest,
        b_manifest_raw,
        b_report,
        b_report_raw,
    )
    (base / evidence.LOCK_PATH).write_bytes(canonical_json_bytes(lock.to_dict()))


def _assert_rejected():
    with pytest.raises(C008CBRCAEvidenceError):
        evidence.check_existing_c008c_b_rca_evidence(None)


def test_unchanged_locked_evidence_passes(locked_repo):
    evidence.check_existing_c008c_b_rca_evidence(None)


def test_full_resign_core_semantic_attack_is_rejected(locked_repo):
    base, b_sources = locked_repo
    manifest, _, report, _ = _contracts(base)
    diagnostics = list(report.determinism_results)
    target_index = next(
        index
        for index, item in enumerate(diagnostics)
        if item.core_semantic_mismatch
    )
    target_payload = diagnostics[target_index].to_dict()
    summaries = target_payload["layer_summaries"]
    core_index = next(
        index
        for index, item in enumerate(summaries)
        if item["layer"] == DiagnosticLayer.CORE.value
    )
    core = dict(summaries[core_index])
    removed = core["semantic_difference_count"]
    core.update(
        semantic_difference_count=0,
        first_semantic_difference_path=None,
        first_semantic_left_subtree_digest=None,
        first_semantic_right_subtree_digest=None,
    )
    core = _resign_mapping(LayerDifferenceSummary, core)
    summaries[core_index] = core
    target_payload["layer_summaries"] = summaries
    target_payload["core_run_payload_equal"] = (
        core["identity_difference_count"] == 0
    )
    target_payload["core_semantic_mismatch"] = False
    target_payload["core_identity_only_mismatch"] = (
        core["identity_difference_count"] > 0
    )
    target_payload["total_difference_count"] -= removed
    target_payload["differences"] = [
        item
        for item in target_payload["differences"]
        if not item["path"].startswith("/core_run")
    ]
    target_payload["mismatch_layer"] = (
        "CORE_RUN_IDENTITY"
        if core["identity_difference_count"]
        else "AUDIT_IDENTITY_OR_PROVENANCE"
    )
    target_payload["first_semantic_difference_path"] = next(
        item["first_semantic_difference_path"]
        for item in summaries
        if item["semantic_difference_count"]
    )
    target_payload["disposition"] = (
        RootCauseDisposition.PROTECTED_CORE_REMEDIATION_REQUIRED.value
    )
    diagnostics[target_index] = _resign(
        DeterminismDiagnosticResult, target_payload
    )
    b_report = b_sources[1]
    resigned_report = build_root_cause_report(
        manifest, b_report, tuple(diagnostics), report.cutoff_results
    )
    _write_signed_bundle(base, b_sources, resigned_report)
    _assert_rejected()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("disposition", RootCauseDisposition.HARNESS_CORRECTION_REQUIRED.value),
        ("recommendations", ["forged but fully re-signed recommendation"]),
    ),
)
def test_resigned_report_derivation_tamper_is_rejected(
    locked_repo, field, value
):
    base, b_sources = locked_repo
    payload = _json(base / evidence.REPORT_PATH)
    payload[field] = value
    report = _resign(C008CBRootCauseReport, payload)
    _write_signed_bundle(base, b_sources, report)
    _assert_rejected()


def test_resigned_first_metric_path_is_rejected(locked_repo):
    base, b_sources = locked_repo
    payload = _json(base / evidence.REPORT_PATH)
    diagnostic = next(
        item
        for item in payload["determinism_results"]
        if item["metric_semantic_mismatch"]
    )
    summary = next(
        item
        for item in diagnostic["layer_summaries"]
        if item["layer"] == DiagnosticLayer.METRIC.value
    )
    summary["first_semantic_difference_path"] += "/forged"
    summary.update(_resign_mapping(LayerDifferenceSummary, summary))
    diagnostic.update(_resign_mapping(DeterminismDiagnosticResult, diagnostic))
    report = _resign(C008CBRootCauseReport, payload)
    _write_signed_bundle(base, b_sources, report)
    _assert_rejected()


def test_resigned_degeneration_kind_is_rejected(locked_repo):
    base, b_sources = locked_repo
    payload = _json(base / evidence.REPORT_PATH)
    variant = payload["degeneration_attributions"][0]
    attribution = next(
        item
        for item in variant["attributions"]
        if item["evidence_kind"] == "VARIANT_DIRECT"
    )
    attribution.update(
        evidence_kind="SHARED_STATIC_EVIDENCE",
        evidence_direct_subject="FROZEN_EXECUTION_MANIFEST_CONFIG_AUTHORITY",
        variant_specific=False,
        shared_baseline_evidence=False,
        derived_from_failed_gate=False,
    )
    attribution.update(_resign_mapping(DegenerationRuleAttribution, attribution))
    variant.update(_resign_mapping(VariantDegenerationAttribution, variant))
    payload["variant_direct_evidence_count"] -= 1
    payload["shared_static_evidence_count"] += 1
    report = _resign(C008CBRootCauseReport, payload)
    _write_signed_bundle(base, b_sources, report)
    _assert_rejected()


def test_resigned_cutoff_final_layer_is_rejected(locked_repo):
    base, _ = locked_repo
    payload = _json(base / evidence.REPORT_PATH)
    cutoff = payload["cutoff_results"][0]
    cutoff["final_layer"] = "NONE"
    cutoff.update(_resign_mapping(FixedCutoffDiagnosticResult, cutoff))
    payload = _resign_mapping(C008CBRootCauseReport, payload)
    (base / evidence.REPORT_PATH).write_bytes(canonical_json_bytes(payload))
    _assert_rejected()


def test_resigned_lock_sha_is_rejected(locked_repo):
    base, _ = locked_repo
    payload = _json(base / evidence.LOCK_PATH)
    payload["root_cause_report_sha256"] = "0" * 64
    lock = _resign(C008CBRCAEvidenceLock, payload)
    (base / evidence.LOCK_PATH).write_bytes(canonical_json_bytes(lock.to_dict()))
    _assert_rejected()


def test_analysis_and_resigned_lock_attack_is_rejected(locked_repo):
    base, b_sources = locked_repo
    _, _, report, _ = _contracts(base)
    analysis = (base / evidence.ANALYSIS_PATH).read_bytes() + b"\nforged\n"
    _write_signed_bundle(base, b_sources, report, analysis_raw=analysis)
    _assert_rejected()
