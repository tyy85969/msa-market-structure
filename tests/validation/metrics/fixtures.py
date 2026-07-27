from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from msa.research.msa_core import MSACoreConfig, MSACorePipeline
from msa.research.resonance import ResonanceFrameInput
from msa.validation import (
    StructuralMetricConfig,
    ValidationMetricName,
    default_metric_formula_registry,
    evaluate_structural_metrics,
)
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.msa_core.fixtures import (
    batch_run,
    pipeline,
    source_input,
)
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    config as frame_config,
    load_result,
)
from tests.research.resonance_scoring.fixtures import scoring_config
from tests.research.timeframe_state.fixtures import (
    bar as direction_bar,
    direction_sequence_input,
    load_result as direction_load_result,
    timeframe_engine,
)


def metric_config(**overrides: object) -> StructuralMetricConfig:
    values: dict[str, object] = {
        "atr_period": 1,
        "turn_resolution_bars": 1,
        "break_observation_bars": 1,
        "trend_capture_bars": 1,
        "reaction_observation_bars": 1,
    }
    values.update(overrides)
    return StructuralMetricConfig(**values)  # type: ignore[arg-type]


def formula(name: ValidationMetricName):
    return next(
        item
        for item in default_metric_formula_registry()
        if item.metric_name is name
    )


def base_run():
    return batch_run()


def base_report(**config_overrides: object):
    return evaluate_structural_metrics(
        base_run(), metric_config(**config_overrides)
    )


def touch_run():
    source = source_input()
    bars = list(source.reference_price_data.bars)
    bars[2] = replace(
        bars[2], high=Decimal("111"), low=Decimal("90")
    )
    bars[3] = replace(
        bars[3], high=Decimal("115"), low=Decimal("85")
    )
    changed = replace(
        source,
        reference_price_data=load_result(
            tuple(bars),
            config=source.reference_price_data.source_config,
        ),
    )
    return pipeline().run(changed)


def touch_report(*, cutoff=None, **config_overrides: object):
    return evaluate_structural_metrics(
        touch_run(), metric_config(**config_overrides), cutoff
    )


def simultaneous_freeze_run():
    source = source_input()
    bars = list(source.reference_price_data.bars)
    bars[1] = replace(
        bars[1], high=Decimal("111"), low=Decimal("90")
    )
    changed = replace(
        source,
        reference_price_data=load_result(
            tuple(bars),
            config=source.reference_price_data.source_config,
        ),
    )
    return pipeline().run(changed)


def direction_run():
    data = direction_sequence_input()
    history = timeframe_engine().build_batch(data)
    bars = (
        direction_bar(0, high="111", low="90", close="100"),
        direction_bar(1, high="116", low="95", close="105"),
        direction_bar(2, high="106", low="85", close="95"),
        direction_bar(3, high="101", low="80", close="90"),
    )
    source = ResonanceFrameInput(
        data.lifecycle_history,
        (history,),
        direction_load_result(bars),
    )
    config = MSACoreConfig(
        engine_id="c008b-direction-core",
        engine_version="1.0.0",
        policy_id="c008b-direction-policy",
        frame_config=frame_config(contexts=(H4_PRIMARY,)),
        scoring_config=scoring_config(contexts=(H4_PRIMARY,)),
        active_box_config=active_config(
            minimum_selection_score=Decimal("0")
        ),
        strict=True,
    )
    return MSACorePipeline(config).run(source)


def direction_report(**config_overrides: object):
    return evaluate_structural_metrics(
        direction_run(), metric_config(**config_overrides)
    )
