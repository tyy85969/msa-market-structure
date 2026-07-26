from dataclasses import replace
from datetime import timedelta

from msa.research.msa_core import replay_msa_core_run
from msa.validation import evaluate_structural_metrics
from tests.research.msa_core.fixtures import pipeline, source_input
from tests.research.resonance.fixtures import bar, load_result

from .fixtures import metric_config


def test_one_hundred_plus_asof_and_reference_bar_smoke_is_stable() -> None:
    source = source_input()
    bars = tuple(
        bar(
            index,
            high=str(105 + index % 3),
            low=str(95 - index % 3),
            close=str(100 + index % 2),
            source="reference-fixture",
        )
        for index in range(-1, 104)
    )
    extended = replace(
        source,
        reference_price_data=load_result(
            bars, config=source.reference_price_data.source_config
        ),
    )
    value = pipeline()
    baseline = value.run(extended)
    start = baseline.processing_times[0]
    schedule = tuple(
        sorted(
            {
                *baseline.processing_times,
                *(start + timedelta(minutes=index) for index in range(100)),
            }
        )
    )
    run = replay_msa_core_run(value, extended, schedule)
    first = evaluate_structural_metrics(run, metric_config()).to_dict()
    second = evaluate_structural_metrics(run, metric_config()).to_dict()
    assert len(run.processing_times) >= 100
    assert len(run.source_input.reference_price_data.bars) >= 100
    assert len(first["aggregates"]) == 10
    assert first == second
