from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from msa.research.active_box import ActiveBoxSelector
from msa.research.resonance import ResonanceScoreHistory
from tests.research.active_box_contract.fixtures import config
from tests.research.resonance.fixtures import T1, assembler, frame_input
from tests.research.resonance_scoring.fixtures import scorer, source_history


def selector(**overrides: object) -> ActiveBoxSelector:
    return ActiveBoxSelector(config(**overrides))


def score_history() -> ResonanceScoreHistory:
    return scorer().build_batch(source_history())


def replay_with_extra() -> ResonanceScoreHistory:
    score_engine = scorer()
    original_source = source_history()
    original = score_engine.build_batch(original_source)
    extra_source = assembler().build_as_of(
        frame_input(), T1 + timedelta(minutes=30)
    )
    extra = score_engine.score_frame(extra_source)
    frames = (original.frames[0], original.frames[1], extra, *original.frames[2:])
    return ResonanceScoreHistory(
        frames=frames,
        final_frame=frames[-1],
        source_history=original_source,
        config_snapshot=score_engine.config,
    )


PAIR_CHANGED_THRESHOLD = Decimal("0.25")
PAIR_UNAVAILABLE_THRESHOLD = Decimal("0.59")
