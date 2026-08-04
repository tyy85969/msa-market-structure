from types import SimpleNamespace

from msa.validation.experiments.execution.rca.contracts import (
    CutoffRewriteLayer,
    DegenerationEvidenceKind,
    DeterminismDiagnosticKind,
    RootCauseDisposition,
    RootCauseSubject,
)
from msa.validation.experiments.execution.rca.report import derive_root_cause


def _determinism(kind, *, full_equal=True, core=False):
    return SimpleNamespace(
        diagnostic_kind=kind,
        full_payload_equal=full_equal,
        core_semantic_mismatch=core,
    )


def _cutoff(*, metric=True, frame=True, source=True):
    return SimpleNamespace(
        metric_semantic_equal=metric,
        frame_bundles_equal=frame,
        active_box_events_equal=True,
        frozen_boxes_equal=True,
        source_prefix_valid=source,
        processing_schedule_equal=True,
        shared_asof_audit_passed=True,
        prefix_audit_passed=True,
        final_layer=(
            CutoffRewriteLayer.NONE
            if metric and frame and source
            else CutoffRewriteLayer.METRIC_OUTCOME
            if not metric
            else CutoffRewriteLayer.FRAME_BUNDLE
            if not frame
            else CutoffRewriteLayer.PREFIX_SOURCE
        ),
    )


def _global_degeneration():
    return tuple(
        SimpleNamespace(
            attributions=(
                SimpleNamespace(
                    evidence_kind=DegenerationEvidenceKind.GLOBAL_BASELINE_PROPAGATION
                ),
            )
        )
        for _ in range(25)
    )


def test_subjects_disposition_and_recommendations_are_evidence_derived(b_report):
    determinism = tuple(
        item
        for _ in range(40)
        for item in (
            _determinism(DeterminismDiagnosticKind.SAME_CONTEXT_REPEAT),
            _determinism(
                DeterminismDiagnosticKind.DECIMAL_CONTEXT_PERTURBATION,
                full_equal=False,
                core=True,
            ),
        )
    )
    cutoff = tuple(_cutoff(metric=False) for _ in range(15))
    subjects, disposition, _, recommendations = derive_root_cause(
        b_report, determinism, cutoff, _global_degeneration()
    )
    assert RootCauseSubject.DETERMINISM_GATE_CONFLATION in subjects
    assert RootCauseSubject.DEGENERATION_GLOBAL_PROPAGATION in subjects
    assert RootCauseSubject.CORE_DECIMAL_CONTEXT_DEPENDENCE in subjects
    assert RootCauseSubject.METRIC_FIXED_CUTOFF_SEMANTICS in subjects
    assert disposition is RootCauseDisposition.MIXED_ROOT_CAUSE
    assert any("Core Decimal arithmetic" in item for item in recommendations)
    assert any("Metric fixed-cutoff semantic" in item for item in recommendations)


def test_missing_diagnostic_schedule_fails_to_insufficient(b_report):
    subjects, disposition, _, recommendations = derive_root_cause(
        b_report, (), (), ()
    )
    assert RootCauseSubject.DETERMINISM_GATE_CONFLATION in subjects
    assert disposition is RootCauseDisposition.INSUFFICIENT_EVIDENCE
    assert any("missing bounded diagnostic" in item for item in recommendations)
