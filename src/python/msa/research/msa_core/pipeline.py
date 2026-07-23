"""Stateless C-007D composition of the frozen C-007A/B/C stages."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from msa.domain import ProvenanceRef
from msa.research.active_box import (
    ActiveBoxSelectionHistory,
    ActiveBoxSelector,
)
from msa.research.resonance import (
    ResonanceFrameAssembler,
    ResonanceFrameHistory,
    ResonanceFrameInput,
    ResonanceScoreHistory,
    ResonanceScorer,
)

from .contracts import (
    MSACoreConfig,
    MSACoreFrameBundle,
    MSACoreRun,
    build_run_report,
    validate_source_input,
)
from .errors import (
    MSACoreConfigurationError,
    MSACoreInputError,
    MSACoreIntegrationError,
)
from .identity import digest, semantic_id


_PIPELINE_MODULE = "msa.research.msa_core.pipeline"
_STAGE_ERRORS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    AssertionError,
    RuntimeError,
)


def _formal_config(value: object) -> MSACoreConfig:
    if not isinstance(value, MSACoreConfig):
        raise MSACoreConfigurationError(
            "pipeline config must be an MSACoreConfig"
        )
    try:
        restored = MSACoreConfig.from_dict(value.to_dict())
    except _STAGE_ERRORS as exc:
        raise MSACoreConfigurationError(
            "pipeline config is not formally valid"
        ) from exc
    if restored != value:
        raise MSACoreConfigurationError(
            "pipeline config payload is not self-consistent"
        )
    return value


def _formal_history(value: object, expected_type: type, field_name: str):
    if not isinstance(value, expected_type):
        raise MSACoreIntegrationError(
            f"{field_name} must be a {expected_type.__name__}"
        )
    try:
        restored = expected_type.from_dict(value.to_dict())
    except _STAGE_ERRORS as exc:
        raise MSACoreIntegrationError(
            f"{field_name} is not a formally valid History"
        ) from exc
    if restored != value:
        raise MSACoreIntegrationError(
            f"{field_name} payload is not self-consistent"
        )
    return value


def _bundle_provenance(
    bundle_id: str,
    config: MSACoreConfig,
    resonance_frame_id: str,
    score_frame_id: str,
    selection_frame_id: str,
) -> ProvenanceRef:
    return ProvenanceRef(
        source_module=_PIPELINE_MODULE,
        source_version=config.engine_version,
        source_object_id=bundle_id,
        policy_id=config.policy_id,
        parent_object_ids=(
            resonance_frame_id,
            score_frame_id,
            selection_frame_id,
        ),
        notes=(f"engine_id={config.engine_id}",),
    )


def iter_msa_core_frame_bundles(
    config: MSACoreConfig,
    resonance_history: ResonanceFrameHistory,
    score_history: ResonanceScoreHistory,
    active_box_history: ActiveBoxSelectionHistory,
) -> Iterator[MSACoreFrameBundle]:
    """Map each authoritative AsOf index into one exact immutable bundle."""

    _formal_config(config)
    resonance_history = _formal_history(
        resonance_history, ResonanceFrameHistory, "resonance_history"
    )
    score_history = _formal_history(
        score_history, ResonanceScoreHistory, "score_history"
    )
    active_box_history = _formal_history(
        active_box_history,
        ActiveBoxSelectionHistory,
        "active_box_history",
    )
    counts = (
        len(resonance_history.frames),
        len(score_history.frames),
        len(active_box_history.frames),
    )
    if len(set(counts)) != 1 or counts[0] == 0:
        raise MSACoreIntegrationError(
            "all stage Histories must contain the same non-zero frame count"
        )
    for resonance_frame, score_frame, selection_frame in zip(
        resonance_history.frames,
        score_history.frames,
        active_box_history.frames,
    ):
        payload = {
            "as_of_time": resonance_frame.as_of_time.isoformat(),
            "resonance_frame_id": resonance_frame.frame_id,
            "score_frame_id": score_frame.score_frame_id,
            "selection_frame_id": selection_frame.selection_frame_id,
            "schema_version": 1,
        }
        bundle_id = semantic_id("msa-core-bundle-v1-", payload)
        yield MSACoreFrameBundle(
            bundle_id=bundle_id,
            as_of_time=resonance_frame.as_of_time,
            resonance_frame=resonance_frame,
            score_frame=score_frame,
            selection_frame=selection_frame,
            config_snapshot=config,
            provenance=_bundle_provenance(
                bundle_id,
                config,
                resonance_frame.frame_id,
                score_frame.score_frame_id,
                selection_frame.selection_frame_id,
            ),
        )


def _run_digest_ids(
    source_input: ResonanceFrameInput,
    resonance_history: ResonanceFrameHistory,
    score_history: ResonanceScoreHistory,
    active_box_history: ActiveBoxSelectionHistory,
) -> tuple[str, str, str, str]:
    return (
        semantic_id("msa-core-source-input-v1-", source_input.to_dict()),
        semantic_id(
            "msa-core-resonance-history-v1-",
            resonance_history.to_dict(),
        ),
        semantic_id("msa-core-score-history-v1-", score_history.to_dict()),
        semantic_id(
            "msa-core-active-box-history-v1-",
            active_box_history.to_dict(),
        ),
    )


def build_msa_core_run(
    config: MSACoreConfig,
    source_input: ResonanceFrameInput,
    resonance_history: ResonanceFrameHistory,
    score_history: ResonanceScoreHistory,
    active_box_history: ActiveBoxSelectionHistory,
) -> MSACoreRun:
    """Build and revalidate the immutable research Run from formal histories."""

    config = _formal_config(config)
    source_input = validate_source_input(source_input, config)
    bundles = tuple(
        iter_msa_core_frame_bundles(
            config,
            resonance_history,
            score_history,
            active_box_history,
        )
    )
    report = build_run_report(
        config,
        resonance_history,
        score_history,
        active_box_history,
    )
    processing_times = tuple(
        frame.as_of_time for frame in resonance_history.frames
    )
    source_id, resonance_id, score_id, active_id = _run_digest_ids(
        source_input,
        resonance_history,
        score_history,
        active_box_history,
    )
    identity_payload = {
        "config_snapshot": config.to_dict(),
        "source_input_digest_id": source_id,
        "processing_times": [item.isoformat() for item in processing_times],
        "resonance_history_digest_id": resonance_id,
        "score_history_digest_id": score_id,
        "active_box_history_digest_id": active_id,
        "bundle_ids": [item.bundle_id for item in bundles],
        "report": report.to_dict(),
        "schema_version": 1,
    }
    run_id = semantic_id("msa-core-run-v1-", identity_payload)
    provenance = ProvenanceRef(
        source_module=_PIPELINE_MODULE,
        source_version=config.engine_version,
        source_object_id=run_id,
        policy_id=config.policy_id,
        parent_object_ids=(
            source_id,
            resonance_id,
            score_id,
            active_id,
            bundles[-1].bundle_id,
            f"msa-core-report-v1-{digest(report.to_dict())}",
        ),
        notes=(f"engine_id={config.engine_id}",),
    )
    return MSACoreRun(
        run_id=run_id,
        source_input=source_input,
        processing_times=processing_times,
        resonance_history=resonance_history,
        score_history=score_history,
        active_box_history=active_box_history,
        frame_bundles=bundles,
        final_bundle=bundles[-1],
        report=report,
        config_snapshot=config,
        provenance=provenance,
    )


@dataclass(frozen=True, slots=True)
class MSACorePipeline:
    """An immutable configuration holder with no runtime state."""

    config: MSACoreConfig

    def __post_init__(self) -> None:
        _formal_config(self.config)

    def run(self, source_input: ResonanceFrameInput) -> MSACoreRun:
        config = _formal_config(self.config)
        source = validate_source_input(source_input, config)
        assembler = ResonanceFrameAssembler(config.frame_config)
        scorer = ResonanceScorer(config.scoring_config)
        selector = ActiveBoxSelector(config.active_box_config)
        try:
            resonance_history = assembler.build_batch(source)
        except _STAGE_ERRORS as exc:
            raise MSACoreInputError(
                "C-007A Batch rejected the authoritative source input"
            ) from exc
        try:
            score_history = scorer.build_batch(resonance_history)
            active_box_history = selector.build_batch(score_history)
        except _STAGE_ERRORS as exc:
            raise MSACoreIntegrationError(
                "a frozen downstream Batch stage failed"
            ) from exc
        return build_msa_core_run(
            config,
            source,
            resonance_history,
            score_history,
            active_box_history,
        )
