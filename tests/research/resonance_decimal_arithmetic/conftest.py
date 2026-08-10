import pytest

from msa.research.msa_core import MSACorePipeline
from msa.validation.contracts import SyntheticScenarioKind
from msa.validation.experiments.baseline import core_experiment_baseline
from msa.validation.experiments.synthetic_suite import (
    build_synthetic_source_input,
)


@pytest.fixture(scope="session")
def canonical_run():
    baseline = core_experiment_baseline()
    source = build_synthetic_source_input(
        SyntheticScenarioKind.SINGLE_TREND, 2
    )
    return MSACorePipeline(baseline.core_config_snapshot).run(source)


@pytest.fixture(scope="session")
def arithmetic_score_frame(canonical_run):
    return canonical_run.score_history.frames[1]
