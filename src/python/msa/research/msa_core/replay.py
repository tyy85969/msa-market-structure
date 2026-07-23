"""Unified Batch-equivalent and explicit replay for C-007D."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime

from msa.research.active_box import ActiveBoxSelector, replay_active_box_history
from msa.research.resonance import (
    ResonanceFrameAssembler,
    ResonanceFrameInput,
    ResonanceScorer,
    replay_history,
    replay_score_history,
)

from .contracts import (
    MSACoreFrameBundle,
    MSACoreRun,
    validate_source_input,
)
from .errors import MSACoreReplayError
from .pipeline import (
    MSACorePipeline,
    _formal_config,
    build_msa_core_run,
)


_REPLAY_ERRORS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    AssertionError,
    RuntimeError,
)


def replay_msa_core_run(
    pipeline: MSACorePipeline,
    source_input: ResonanceFrameInput,
    processing_times: Iterable[datetime] | None = None,
) -> MSACoreRun:
    """Replay the complete chain and cross-audit both downstream stages."""

    if not isinstance(pipeline, MSACorePipeline):
        raise MSACoreReplayError("pipeline must be an MSACorePipeline")
    try:
        config = _formal_config(pipeline.config)
        source = validate_source_input(source_input, config)
    except _REPLAY_ERRORS as exc:
        raise MSACoreReplayError(
            "pipeline config or source input is not formally valid"
        ) from exc
    if processing_times is None:
        batch = pipeline.run(source)
        replayed = pipeline.run(source)
        if replayed.to_dict() != batch.to_dict():
            raise MSACoreReplayError(
                "default Replay must equal Batch for the complete Run payload"
            )
        return replayed
    try:
        schedule = tuple(processing_times)
    except TypeError as exc:
        raise MSACoreReplayError(
            "processing_times must be an iterable of datetimes"
        ) from exc
    assembler = ResonanceFrameAssembler(config.frame_config)
    scorer = ResonanceScorer(config.scoring_config)
    selector = ActiveBoxSelector(config.active_box_config)
    try:
        baseline_resonance = assembler.build_batch(source)
        baseline_score = scorer.build_batch(baseline_resonance)
        effective_resonance = replay_history(
            assembler, source, schedule
        )
        effective_score = scorer.build_batch(effective_resonance)
        effective_active = selector.build_batch(effective_score)
        audited_score = replay_score_history(
            scorer,
            baseline_resonance,
            effective_resonance.frames,
        )
        audited_active = replay_active_box_history(
            selector,
            baseline_score,
            effective_score,
        )
    except _REPLAY_ERRORS as exc:
        raise MSACoreReplayError(
            "explicit unified Replay rejected the requested schedule"
        ) from exc
    audited_score_payloads = tuple(
        frame.to_dict() for frame in audited_score.frames
    )
    effective_score_payloads = tuple(
        frame.to_dict() for frame in effective_score.frames
    )
    if audited_score_payloads != effective_score_payloads:
        raise MSACoreReplayError(
            "C-007B stage Replay differs from stage Batch"
        )
    if audited_active.to_dict() != effective_active.to_dict():
        raise MSACoreReplayError(
            "C-007C stage Replay differs from stage Batch"
        )
    return build_msa_core_run(
        config,
        source,
        effective_resonance,
        effective_score,
        effective_active,
    )


def iter_replay_msa_core_frame_bundles(
    pipeline: MSACorePipeline,
    source_input: ResonanceFrameInput,
    processing_times: Iterable[datetime] | None = None,
) -> Iterator[MSACoreFrameBundle]:
    yield from replay_msa_core_run(
        pipeline, source_input, processing_times
    ).frame_bundles
