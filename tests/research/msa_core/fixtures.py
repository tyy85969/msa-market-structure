from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from msa.research.msa_core import (
    MSACoreConfig,
    MSACorePipeline,
    replay_msa_core_run,
)
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.resonance.fixtures import (
    assembler,
    config as frame_config,
    frame_input,
)
from tests.research.resonance_scoring.fixtures import scoring_config


def config(**overrides: object) -> MSACoreConfig:
    values: dict[str, object] = {
        "engine_id": "c007d-msa-core",
        "engine_version": "1.0.0",
        "policy_id": "causal-msa-core-alpha-v1",
        "frame_config": frame_config(),
        "scoring_config": scoring_config(),
        "active_box_config": active_config(
            minimum_selection_score=Decimal("0.25")
        ),
        "strict": True,
    }
    values.update(overrides)
    return MSACoreConfig(**values)  # type: ignore[arg-type]


def pipeline(**overrides: object) -> MSACorePipeline:
    return MSACorePipeline(config(**overrides))


def source_input(**overrides: object):
    return frame_input(**overrides)


def batch_run(**overrides: object):
    return pipeline(**overrides).run(source_input())


def extra_schedule():
    source = source_input()
    default = assembler().default_schedule(source)
    return (default[0], default[0] + timedelta(minutes=30), *default[1:])


def extra_run():
    return replay_msa_core_run(
        pipeline(), source_input(), extra_schedule()
    )
