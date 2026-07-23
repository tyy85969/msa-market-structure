from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.domain import ProvenanceRef
from msa.research.msa_core import (
    MSACoreConfig,
    MSACorePipeline,
    MSACoreRun,
    replay_msa_core_run,
)
from msa.research.msa_core.contracts import validate_source_input
from msa.research.msa_core.identity import semantic_id
from msa.research.timeframe_state import (
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateEngine,
    TimeframeStateInput,
)
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.resonance.fixtures import (
    assembler,
    config as frame_config,
    frame_input,
    load_result,
    reference_data,
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


def source_lineage_attack(case: str):
    source_a = source_input()
    source_b = source_a
    if case == "reference_bar_payload":
        bars = list(source_a.reference_price_data.bars)
        bars[-1] = replace(
            bars[-1],
            high=bars[-1].high + Decimal("10"),
            close=bars[-1].close + Decimal("10"),
        )
        source_b = replace(
            source_a,
            reference_price_data=load_result(
                tuple(bars),
                config=source_a.reference_price_data.source_config,
            ),
        )
    elif case == "lifecycle_history":
        source_b = frame_input(include_extra=True)
    elif case == "timeframe_state_history":
        histories = []
        for history in source_a.timeframe_state_histories:
            child = history.config_snapshot
            alternate = TimeframeStateConfig(
                engine_id="alternate-c006b",
                engine_version=child.engine_version,
                policy_id=child.policy_id,
                symbol=child.symbol,
                target_timeframe=child.target_timeframe,
                target_scale=child.target_scale,
                selection_policy=TimeframeSelectionPolicy.LATEST_CAUSAL,
                strict=True,
            )
            histories.append(
                TimeframeStateEngine(alternate).build_batch(
                    TimeframeStateInput(source_a.lifecycle_history)
                )
            )
        source_b = replace(
            source_a, timeframe_state_histories=tuple(histories)
        )
    elif case == "default_causal_schedule":
        source_b = replace(
            source_a,
            reference_price_data=reference_data(include_future=False),
        )
    elif case == "future_input_facts":
        source_a = replace(
            source_a,
            reference_price_data=reference_data(include_future=False),
        )
        source_b = source_input()
    else:
        raise AssertionError(f"unknown source lineage attack case: {case}")
    run_a = pipeline().run(source_a)
    pipeline().run(source_b)
    return run_a, source_b


def resigned_source_fields(
    run: MSACoreRun, source_input_value
) -> tuple[object, str, ProvenanceRef]:
    canonical_source = validate_source_input(
        source_input_value, run.config_snapshot
    )
    source_id = semantic_id(
        "msa-core-source-input-v1-", canonical_source.to_dict()
    )
    identity_payload = run._identity_payload()
    identity_payload["source_input_digest_id"] = source_id
    run_id = semantic_id("msa-core-run-v1-", identity_payload)
    old_source_id = run._digest_ids()[0]
    parents = tuple(
        source_id if item == old_source_id else item
        for item in run.provenance.parent_object_ids
    )
    provenance = replace(
        run.provenance,
        source_object_id=run_id,
        parent_object_ids=parents,
    )
    return canonical_source, run_id, provenance
