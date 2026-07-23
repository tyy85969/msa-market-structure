from dataclasses import replace

import pytest

from msa.research.msa_core import (
    MSACoreInputError,
    MSACoreIntegrationError,
    MSACorePipeline,
)
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.resonance.fixtures import config as frame_config

from .fixtures import batch_run, config, pipeline, source_input


def test_non_source_input_uses_core_error() -> None:
    with pytest.raises(MSACoreInputError):
        pipeline().run(object())  # type: ignore[arg-type]


def test_tampered_source_input_uses_core_error() -> None:
    source = source_input()
    object.__setattr__(source.lifecycle_history, "snapshots", ())
    with pytest.raises(MSACoreInputError):
        pipeline().run(source)


def test_tampered_timeframe_history_uses_core_error() -> None:
    source = source_input()
    object.__setattr__(
        source.timeframe_state_histories[0], "snapshots", ()
    )
    with pytest.raises(MSACoreInputError):
        pipeline().run(source)


def test_tampered_reference_load_result_uses_core_error() -> None:
    source = source_input()
    object.__setattr__(source.reference_price_data, "bars", ())
    with pytest.raises(MSACoreInputError):
        pipeline().run(source)


def test_reference_symbol_conflict_uses_core_error() -> None:
    with pytest.raises(MSACoreInputError):
        MSACorePipeline(
            config(
                frame_config=frame_config(symbol="EURUSD"),
                active_box_config=active_config(symbol="EURUSD"),
            )
        ).run(source_input())


@pytest.mark.parametrize(
    "field",
    [
        "resonance_history",
        "score_history",
        "active_box_history",
        "frame_bundles",
        "final_bundle",
        "run_id",
    ],
)
def test_run_direct_attacks_fail_closed(field: str) -> None:
    run = batch_run()
    replacements = {
        "resonance_history": object(),
        "score_history": object(),
        "active_box_history": object(),
        "frame_bundles": run.frame_bundles[:-1],
        "final_bundle": run.frame_bundles[0],
        "run_id": "msa-core-run-v1-" + "0" * 64,
    }
    with pytest.raises(MSACoreIntegrationError):
        replace(run, **{field: replacements[field]})


def test_processing_time_mismatch_fails_closed() -> None:
    run = batch_run()
    with pytest.raises(MSACoreIntegrationError):
        replace(run, processing_times=run.processing_times[:-1])
