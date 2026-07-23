from __future__ import annotations

from dataclasses import replace

from msa.research.lifecycle import LifecycleHistory
from msa.research.msa_core import MSACoreRun
from msa.research.resonance import ResonanceFrameInput
from msa.research.timeframe_state import TimeframeStateHistory
from msa.validation import CausalAuditor
from tests.research.msa_core.fixtures import (
    batch_run,
    extra_run,
    pipeline,
    source_input,
)
from tests.research.resonance.fixtures import load_result


def auditor() -> CausalAuditor:
    return CausalAuditor()


def valid_run() -> MSACoreRun:
    return batch_run()


def valid_replay_run() -> MSACoreRun:
    value = pipeline()
    source = source_input()
    return value.run(source)


def truncate_source(
    source: ResonanceFrameInput, cutoff
) -> ResonanceFrameInput:
    lifecycle_snapshots = tuple(
        item
        for item in source.lifecycle_history.snapshots
        if item.as_of_time <= cutoff
    )
    lifecycle = LifecycleHistory(
        events=lifecycle_snapshots[-1].events,
        snapshots=lifecycle_snapshots,
        final_snapshot=lifecycle_snapshots[-1],
    )
    timeframe_histories = []
    for history in source.timeframe_state_histories:
        snapshots = tuple(
            item for item in history.snapshots if item.as_of_time <= cutoff
        )
        timeframe_histories.append(
            TimeframeStateHistory(
                events=snapshots[-1].events,
                snapshots=snapshots,
                final_snapshot=snapshots[-1],
                config_snapshot=history.config_snapshot,
            )
        )
    bars = tuple(
        item
        for item in source.reference_price_data.bars
        if item.available_time <= cutoff
    )
    return ResonanceFrameInput(
        lifecycle,
        tuple(timeframe_histories),
        load_result(
            bars, config=source.reference_price_data.source_config
        ),
    )


def valid_prefix_pair() -> tuple[MSACoreRun, MSACoreRun]:
    value = pipeline()
    source = source_input()
    extended = value.run(source)
    prefix_source = truncate_source(source, extended.processing_times[1])
    return value.run(prefix_source), extended


def valid_shared_asof_pair():
    baseline = batch_run()
    extended = extra_run()
    cutoff = baseline.processing_times[1]
    return baseline, extended, cutoff


def with_reference_prices(prices: tuple[str, ...]) -> MSACoreRun:
    source = source_input()
    if len(prices) != len(source.reference_price_data.bars):
        raise AssertionError("scenario price count must match source bars")
    bars = tuple(
        replace(
            bar,
            open=bar.close.__class__(price),
            high=bar.close.__class__(price) + bar.close.__class__("5"),
            low=bar.close.__class__(price) - bar.close.__class__("5"),
            close=bar.close.__class__(price),
        )
        for bar, price in zip(source.reference_price_data.bars, prices)
    )
    scenario_source = replace(
        source,
        reference_price_data=load_result(
            bars, config=source.reference_price_data.source_config
        ),
    )
    return pipeline().run(scenario_source)
